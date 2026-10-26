"""Test for a device that is not publishing"""

import argparse
import datetime
import json
import os
import time
import traceback

import structlog
from dotenv import load_dotenv

from pyflink.common import WatermarkStrategy
from pyflink.common.typeinfo import Types
from pyflink.datastream import RuntimeExecutionMode, StreamExecutionEnvironment
from pyflink.datastream.connectors import DeliveryGuarantee
from pyflink.datastream.connectors.kafka import (
    KafkaOffsetsInitializer,
    KafkaRecordSerializationSchema,
    KafkaSink,
    KafkaSource,
)
from pyflink.datastream.functions import KeyedBroadcastProcessFunction, KeySelector
from pyflink.datastream.state import MapStateDescriptor, ValueStateDescriptor
from pyflink.common.serialization import SimpleStringSchema

log = structlog.get_logger()


def _udf_log_exception(message: str) -> None:

    print(f"{message}\n{traceback.format_exc()}")


QUALITY_CONFIG_STATE = MapStateDescriptor("quality-config", Types.STRING(), Types.STRING())

# Number of publish intervals of silence before alarming.
MISSED_INTERVALS = float(os.environ.get("ABSENCE_DETECTION__MISSED_INTERVALS", "3"))
MIN_TIMER_SECONDS = 60
# A device that published after an alarm alarms again only this many silence
# limits after the previous one.
REPEAT_FACTOR = float(os.environ.get("ABSENCE_DETECTION__REPEAT_FACTOR", "3"))


def _silence_ms(interval_seconds: float) -> int:
    return int(max(MIN_TIMER_SECONDS, interval_seconds * MISSED_INTERVALS) * 1000)

SOURCE_STREAM = "stream"


class DeviceKeySelector(KeySelector):
    """Per (mesh_id, device_id)"""

    def get_key(self, value: str) -> str:
        try:
            event = json.loads(value)
            return f"{event.get('mesh_id')}:{event.get('device_id')}"
        except Exception:
            return "unparseable"


class DetectAbsence(KeyedBroadcastProcessFunction):
    """Alarms once when a device goes silent, and again only after it has published.

    Every publication restarts a processing-time timer. A later silence alarms
    only once REPEAT_FACTOR times the silence limit has passed since the
    previous alarm; one due earlier is held until then.
    """

    def open(self, runtime_context):
        from mesh_things import detectors

        self._detectors = detectors
        self._started_ms = int(time.time() * 1000)
        self._deadline = runtime_context.get_state(ValueStateDescriptor("absence-deadline", Types.LONG()))
        self._identity = runtime_context.get_state(ValueStateDescriptor("absence-identity", Types.STRING()))
        self._last_seen = runtime_context.get_state(ValueStateDescriptor("absence-last-seen", Types.LONG()))
        self._last_alarm = runtime_context.get_state(ValueStateDescriptor("absence-last-alarm", Types.LONG()))

    def process_element(self, value: str, ctx):
        try:
            event = json.loads(value)
        except Exception:
            _udf_log_exception("Bad discovery event, skipping")
            return

        mesh_id = event.get("mesh_id")
        device_id = event.get("device_id")
        if mesh_id is None or device_id is None:
            return

        interval = self._publish_interval(ctx, mesh_id, device_id)
        if not interval:
            return

        now = ctx.timer_service().current_processing_time()
        self._identity.update(json.dumps({"mesh_id": mesh_id, "device_id": device_id, "interval": interval}))
        self._last_seen.update(now)
        self._arm(ctx, now + _silence_ms(interval))
        yield from ()

    def _arm(self, ctx, deadline: int) -> None:
        timer_service = ctx.timer_service()
        previous = self._deadline.value()
        if previous is not None:
            timer_service.delete_processing_time_timer(previous)
        timer_service.register_processing_time_timer(deadline)
        self._deadline.update(deadline)

    def on_timer(self, timestamp, ctx):
        """Nothing arrived before the deadline"""
        raw = self._identity.value()
        # PyFlink can still fire a timer deleted after it was queued, so only the current deadline counts.
        if not raw or timestamp != self._deadline.value():
            return
        identity = json.loads(raw)
        interval = self._publish_interval(ctx, identity["mesh_id"], identity["device_id"])
        if not interval:
            # No longer configured for monitoring
            self._deadline.clear()
            self._identity.clear()
            return

        now = ctx.timer_service().current_processing_time()
        last_seen = self._last_seen.value()
        if last_seen is not None and now - last_seen < _silence_ms(interval):
            self._arm(ctx, last_seen + _silence_ms(interval))
            return
        if timestamp < self._started_ms:
            # Due while the job was down: give the backlog time to arrive first.
            self._arm(ctx, now + _silence_ms(interval))
            return

        held_until = self._detectors.absence_on_timer(
            self._last_alarm.value(), now, _silence_ms(interval) * REPEAT_FACTOR
        )
        if held_until is not None:
            self._arm(ctx, int(held_until))
            return

        self._deadline.clear()
        self._last_alarm.update(now)
        silent_for = int((now - (self._last_seen.value() or now)) / 1000)
        yield json.dumps(
            {
                "mesh_id": identity["mesh_id"],
                "device_id": identity["device_id"],
                # Device-wide, not channel-specific.
                "channel": None,
                "detector": "absence",
                "source": SOURCE_STREAM,
                "value": silent_for,
                "message": (
                    f"No telemetry received for {silent_for}s "
                    f"(limit {MISSED_INTERVALS:g}x the {interval}s publish interval). "
                    "Note this is a publishing fault, not necessarily a reading fault - "
                    "a batching device may still deliver this window later."
                ),
                "triggered_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        )

    def _publish_interval(self, ctx, mesh_id, device_id):
        """Device publish interval"""
        state = ctx.get_broadcast_state(QUALITY_CONFIG_STATE)
        try:
            raw = state.get(f"{mesh_id}:{device_id}")
            if raw:
                config = json.loads(raw)
                # Opt-in: an interval alone no longer turns absence on.
                if not config.get("absence_detection_enabled"):
                    return None
                if config.get("publish_interval_seconds"):
                    return config["publish_interval_seconds"]
                if config.get("reading_interval_seconds"):
                    # No publish interval configured
                    return config["reading_interval_seconds"]
        except Exception:
            _udf_log_exception(f"Bad device intervals for {mesh_id}:{device_id}")
        return None

    def process_broadcast_element(self, value: str, ctx):
        state = ctx.get_broadcast_state(QUALITY_CONFIG_STATE)
        try:
            event = json.loads(value)
        except Exception:
            _udf_log_exception("Bad quality-config event")
            return
        key = event.get("key")
        if not key:
            return
        if event.get("op") == "delete":
            state.remove(key)
        else:
            state.put(key, json.dumps(event))
        yield from ()


def build_pipeline(env, kafka_bootstrap: str, sightings_topic: str, alarms_topic: str, quality_config_topic: str):
    source = (
        KafkaSource.builder()
        .set_bootstrap_servers(kafka_bootstrap)
        .set_topics(sightings_topic)
        .set_group_id("flink-absence-detection-group")
        # latest() to avoid replaying old alarms from the beginning
        .set_starting_offsets(KafkaOffsetsInitializer.latest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )
    sightings = env.from_source(source, WatermarkStrategy.no_watermarks(), "sensor-discovery-sightings")

    config_source = (
        KafkaSource.builder()
        .set_bootstrap_servers(kafka_bootstrap)
        .set_topics(quality_config_topic)
        .set_group_id("flink-absence-detection-quality-config-group")
        .set_starting_offsets(KafkaOffsetsInitializer.earliest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )
    config_stream = env.from_source(config_source, WatermarkStrategy.no_watermarks(), "quality-config")

    keyed = sightings.key_by(DeviceKeySelector(), key_type=Types.STRING())
    alarms = keyed.connect(config_stream.broadcast(QUALITY_CONFIG_STATE)).process(
        DetectAbsence(), output_type=Types.STRING()
    )

    sink = (
        KafkaSink.builder()
        .set_bootstrap_servers(kafka_bootstrap)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(alarms_topic)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .set_delivery_guarantee(DeliveryGuarantee.AT_LEAST_ONCE)
        .build()
    )
    alarms.sink_to(sink)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--local", default=False, dest="local", action="store_true", help="Local development mode"
    )
    args = parser.parse_args()

    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_runtime_mode(RuntimeExecutionMode.STREAMING)

    if args.local:
        log.warning("Local development mode")
        load_dotenv("../.env")
        kafka_bootstrap = os.environ["KAFKA_BOOTSTRAP_LOCAL"]
        src_dir = os.path.dirname(os.path.realpath(__file__))
        jar_files = [
            "flink-connector-kafka-5.0.0-2.2.jar",
            "flink-sql-connector-kafka-5.0.0-2.2.jar",
            "kafka-clients-4.2.0.jar",
        ]
        jar_paths = tuple(f"file://{os.path.join(src_dir, 'jars', name)}" for name in jar_files)
        env.add_jars(*jar_paths)
    else:
        kafka_bootstrap = os.environ["KAFKA_BOOTSTRAP"]

    log.info("Starting Flink absence-detection job")

    build_pipeline(
        env,
        kafka_bootstrap=kafka_bootstrap,
        sightings_topic=os.environ.get("REGISTRY__SENSOR_DISCOVERY_KAFKA_TOPIC", "mesh.sensor_discovery.v1"),
        alarms_topic=os.environ.get("PATTERN_DETECTION__ALARMS_TOPIC", "mesh.telemetry.alarms.v1"),
        quality_config_topic=os.environ.get("REGISTRY__QUALITY_CONFIG_KAFKA_TOPIC", "mesh.quality_config.v1"),
    )

    env.execute("mesh-absence-detection")


if __name__ == "__main__":
    main()
