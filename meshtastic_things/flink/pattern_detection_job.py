"""Data-quality checks: per-point/small-batch detectors.

Two checks run here, both per (mesh_id, device_id, channel):
  - flat_value  - the channel has reported one value for a configured span of time
  - range       - several readings in a row fell outside the device's configured range

A condition raises one alarm when it starts, then at most one per
PATTERN_DETECTION__ALARM_REPEAT_HOURS while it holds, by the readings' own time.
Those later ones are marked `repeat`, which registry does not email on its own.

Config comes from "registry" over mesh.quality_config.v1: flat_value's default
enabled/disabled state comes from the catalog (TelemetryVariantMeasurement);
range has no catalog default - its bounds only ever come from a device's own
Measurement row.

Reads decoded and derived telemetry alike, so channels computed by
postprocessing are checked exactly like the ones a device reports.

Alarms carry the reading's own time, so a replayed reading rewrites the alarm
already stored for it. Each alarm is held briefly before it is sent: if its
channel turns out to be arriving at a rate no device reports at, the history is
being replayed and the alarm is marked `replay`, which registry never emails.
"""
import argparse
import datetime
import json
import os
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
from pyflink.datastream.functions import FlatMapFunction, KeySelector, KeyedBroadcastProcessFunction
from pyflink.datastream.state import ListStateDescriptor, MapStateDescriptor, ValueStateDescriptor
from pyflink.common.serialization import SimpleStringSchema

from common.flink_kafka import committed_or_latest

log = structlog.get_logger()


def _udf_log_exception(message: str) -> None:

    print(f"{message}\n{traceback.format_exc()}")


# Config from registry. Three kinds share this map, distinguished by the key
# shape (same pattern decode_job.py uses for its two merged broadcast streams):
#   "<measurement>.<field>"             -> {"kind": "variant_config", default_reading_interval_seconds, default_enabled_detectors}
#   "<mesh_id>:<device_id>"             -> {"kind": "device_intervals", reading_interval_seconds, publish_interval_seconds}
#   "<mesh_id>:<device_id>:<channel>"   -> {"kind": "measurement_alarms", enabled_detectors, valid_min, valid_max}
QUALITY_CONFIG_STATE = MapStateDescriptor("quality-config", Types.STRING(), Types.STRING())

FLAT_VALUE_HOURS = float(os.environ.get("PATTERN_DETECTION__FLAT_VALUE_HOURS", "12"))
ALARM_REPEAT_SECONDS = float(os.environ.get("PATTERN_DETECTION__ALARM_REPEAT_HOURS", "1")) * 3600

SOURCE_STREAM = "stream"


class ExplodeFields(FlatMapFunction):
    """One record per numeric leaf, carrying the identity downstream needs.

    mesh_id travels with every record because device_id alone is only unique
    among currently-allowed Device rows - see docs/architecture.md.
    """

    def open(self, runtime_context):
        # Imported here, not at module level - the established convention for
        # every UDF in this codebase, since `common` resolves on the
        # taskmanager rather than the submitting client.
        from common import channels, timestamps

        self._channels = channels
        self._timestamps = timestamps

    def flat_map(self, value: str):
        try:
            event = json.loads(value)
        except Exception:
            _udf_log_exception("Bad message, skipping")
            return
        if event.get("backfill"):
            # Recomputed history: alarming on it now would report long-past faults as new.
            return
        device_id = event.get("node_id")
        mesh_id = event.get("mesh_id")
        try:
            reading_time, _ = self._timestamps.resolve_timestamp(event)
        except KeyError:
            reading_time = None
        payload_kind = event.get("payload_kind")
        for channel, val in self._channels.channels_in(payload_kind, event.get("payload") or {}):
            yield json.dumps(
                {
                    "mesh_id": mesh_id,
                    "device_id": device_id,
                    "channel": channel,
                    "value": val,
                    "time": reading_time,
                }
            )


class ObservationKeySelector(KeySelector):
    """Per (mesh_id, device_id, channel) - the finest grain these checks act on."""

    def get_key(self, value: str) -> str:
        try:
            obs = json.loads(value)
            return f"{obs.get('mesh_id')}:{obs.get('device_id')}:{obs.get('channel')}"
        except Exception:
            return "unparseable"


class DetectPatterns(KeyedBroadcastProcessFunction):
    """flat_value, driven by the registry catalog, and range, driven entirely
    by the device's own Measurement override."""

    def open(self, runtime_context):
        from common import detectors

        self._detectors = detectors
        self._flat = runtime_context.get_state(ValueStateDescriptor("flat-stretch", Types.STRING()))
        self._range_streak = runtime_context.get_state(ValueStateDescriptor("range-streak", Types.INT()))
        # Detector -> reading time of its last alarm.
        self._last_raised = runtime_context.get_map_state(
            MapStateDescriptor("last-raised", Types.STRING(), Types.DOUBLE())
        )
        # Detector -> when its condition last held and last cleared, as JSON.
        self._conditions = runtime_context.get_map_state(
            MapStateDescriptor("conditions", Types.STRING(), Types.STRING())
        )
        self._arrivals = runtime_context.get_list_state(ListStateDescriptor("arrivals", Types.DOUBLE()))
        self._pending = runtime_context.get_list_state(ListStateDescriptor("pending-alarms", Types.STRING()))
        self._release_at = runtime_context.get_state(ValueStateDescriptor("release-at", Types.LONG()))

    def process_element(self, value: str, ctx):
        try:
            obs = json.loads(value)
        except Exception:
            _udf_log_exception("Bad observation, skipping")
            return

        mesh_id = obs.get("mesh_id")
        device_id = obs.get("device_id")
        channel = obs.get("channel")
        obs_value = obs.get("value")
        if obs_value is None:
            return

        timer_service = ctx.timer_service()
        now_ms = timer_service.current_processing_time()
        arrivals, replay = self._detectors.track_arrival(list(self._arrivals.get() or []), now_ms / 1000)
        self._arrivals.update(arrivals)
        alarms = []

        config = self._lookup(ctx, channel)
        intervals = self._lookup(ctx, f"{mesh_id}:{device_id}")
        # A device's own reading interval overrides the variant default.
        interval = intervals.get("reading_interval_seconds") or config.get("default_reading_interval_seconds")
        # No override entry is the common case, not a miss: it means "inherit".
        override = self._lookup(ctx, f"{mesh_id}:{device_id}:{channel}")
        enabled = self._detectors.enabled_detectors_for(
            override.get("enabled_detectors") if override else None,
            config.get("default_enabled_detectors") if config else None,
        )

        reading_time = obs.get("time") or datetime.datetime.now(datetime.timezone.utc).timestamp()

        raw_flat = self._flat.value()
        flat = self._detectors.track_flat(json.loads(raw_flat) if raw_flat else None, obs_value, reading_time)
        self._flat.update(json.dumps(flat))
        if self._detectors.FLAT_VALUE in enabled:
            hours = (flat["last"] - flat["since"]) / 3600
            alarms += self._raise(
                self._detectors.FLAT_VALUE,
                self._detectors.flat_value_triggered(flat, hours=FLAT_VALUE_HOURS),
                reading_time, mesh_id, device_id, channel, obs_value,
                f"Value flat at {obs_value} for {hours:.1f}h ({flat['count']} readings)",
            )

        valid_min, valid_max = override.get("valid_min"), override.get("valid_max")
        out_of_range = self._detectors.range_check_triggered(obs_value, valid_min, valid_max)
        streak = (self._range_streak.value() or 0) + 1 if out_of_range else 0
        self._range_streak.update(streak)
        if self._detectors.RANGE in enabled:
            alarms += self._raise(
                self._detectors.RANGE,
                streak >= self._detectors.range_readings_for(interval),
                reading_time, mesh_id, device_id, channel, obs_value,
                f"{streak} readings in a row outside the configured range [{valid_min}, {valid_max}], "
                f"latest {obs_value}",
            )

        if replay:
            release_at = self._release_at.value()
            if release_at is not None:
                timer_service.delete_processing_time_timer(release_at)
            yield from self._release(replay=True, extra=alarms)
        elif alarms:
            if self._release_at.value() is None:
                release_at = now_ms + int(self._detectors.REPLAY_HOLD_SECONDS * 1000)
                timer_service.register_processing_time_timer(release_at)
                self._release_at.update(release_at)
            for alarm in alarms:
                self._pending.add(json.dumps(alarm))

    def on_timer(self, timestamp: int, ctx):
        yield from self._release(replay=False)

    def _release(self, replay: bool, extra: tuple = ()):
        """Send the held alarms and `extra`, marked as a replay when one was detected."""
        for alarm in [json.loads(raw) for raw in self._pending.get() or []] + list(extra):
            if replay:
                alarm["replay"] = True
            yield json.dumps(alarm)
        self._pending.clear()
        self._release_at.clear()

    def _raise(self, detector, holds, reading_time, mesh_id, device_id, channel, value, message) -> list[dict]:
        """The alarm for a condition holding at `reading_time`, unless one was raised within the repeat interval."""
        raw = self._conditions.get(detector)
        condition, repeat = self._detectors.track_condition(
            json.loads(raw) if raw else None, holds, reading_time, ALARM_REPEAT_SECONDS
        )
        self._conditions.put(detector, json.dumps(condition))
        if not holds or not self._detectors.alarm_due(self._last_raised.get(detector), reading_time, ALARM_REPEAT_SECONDS):
            return []
        self._last_raised.put(detector, float(reading_time))
        return [self._alarm(mesh_id, device_id, channel, value, reading_time, detector, message, repeat)]

    @staticmethod
    def _lookup(ctx, key: str) -> dict:
        if not key:
            return {}
        try:
            raw = ctx.get_broadcast_state(QUALITY_CONFIG_STATE).get(key)
            return json.loads(raw) if raw else {}
        except Exception:
            _udf_log_exception(f"Bad quality config for {key}")
            return {}

    def process_broadcast_element(self, value: str, ctx):
        broadcast_state = ctx.get_broadcast_state(QUALITY_CONFIG_STATE)
        try:
            event = json.loads(value)
        except Exception:
            _udf_log_exception("Bad quality-config event")
            return
        key = event.get("key")
        if not key:
            return
        if event.get("op") == "delete":
            broadcast_state.remove(key)
        else:
            broadcast_state.put(key, json.dumps(event))
        yield from ()  # this method only mutates broadcast state, never emits output

    @staticmethod
    def _alarm(mesh_id, device_id, channel, value, reading_time, detector, message, repeat) -> dict:
        """Shared shape with quality_worker's batch alarms - one consumer routes
        both to email (registry's consume_quality_alarms), one writer persists
        both (writer/point_builders.py's build_alarm_points)."""
        alarm = {
            "mesh_id": mesh_id,
            "device_id": device_id,
            "channel": channel,
            "detector": detector,
            "source": SOURCE_STREAM,
            "value": value,
            "message": message,
            "triggered_at": datetime.datetime.fromtimestamp(reading_time, datetime.timezone.utc).isoformat(),
        }
        if repeat:
            alarm["repeat"] = True
        return alarm


def build_pipeline(
    env, kafka_bootstrap: str, input_topics: list[str], alarms_topic: str, quality_config_topic: str
):
    source = (
        KafkaSource.builder()
        .set_bootstrap_servers(kafka_bootstrap)
        .set_topics(*input_topics)
        .set_group_id("flink-pattern-detection-group")
        # Alarms are for live data: a topic seen for the first time is not replayed.
        .set_starting_offsets(committed_or_latest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )
    stream = env.from_source(source, WatermarkStrategy.no_watermarks(), "decoded-and-derived-messages")
    exploded = stream.flat_map(ExplodeFields(), output_type=Types.STRING())

    config_source = (
        KafkaSource.builder()
        .set_bootstrap_servers(kafka_bootstrap)
        .set_topics(quality_config_topic)
        .set_group_id("flink-pattern-detection-quality-config-group")
        .set_starting_offsets(KafkaOffsetsInitializer.earliest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )
    config_stream = env.from_source(config_source, WatermarkStrategy.no_watermarks(), "quality-config")

    keyed_stream = exploded.key_by(ObservationKeySelector(), key_type=Types.STRING())
    broadcast_stream = config_stream.broadcast(QUALITY_CONFIG_STATE)

    alarms_stream = keyed_stream.connect(broadcast_stream).process(DetectPatterns(), output_type=Types.STRING())

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
    alarms_stream.sink_to(sink)


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
            "flink-connector-kafka-3.3.0-1.19.jar",
            "flink-sql-connector-kafka-3.3.0-1.19.jar",
            "kafka-clients-3.2.3.jar",
        ]
        jar_paths = tuple(f"file://{os.path.join(src_dir, 'jars', name)}" for name in jar_files)
        env.add_jars(*jar_paths)
    else:
        kafka_bootstrap = os.environ["KAFKA_BOOTSTRAP"]

    log.info("Starting Flink pattern-detection job")

    build_pipeline(
        env,
        kafka_bootstrap=kafka_bootstrap,
        input_topics=[
            os.environ["PROTO_DECODE__KAFKA_TOPIC"],
            os.environ.get("POSTPROCESSING__DERIVED_KAFKA_TOPIC", "mesh.telemetry.derived.v1"),
        ],
        alarms_topic=os.environ.get("PATTERN_DETECTION__ALARMS_TOPIC", "mesh.telemetry.alarms.v1"),
        quality_config_topic=os.environ.get("REGISTRY__QUALITY_CONFIG_KAFKA_TOPIC", "mesh.quality_config.v1"),
    )

    env.execute("mesh-pattern-detection")


if __name__ == "__main__":
    main()
