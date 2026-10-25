"""Device postprocessing: derive new channels from decoded telemetry.

Reads mesh.telemetry.decoded.v1 keyed by device, runs every enabled plan
registry publishes for that device on mesh.postprocessing_config.v1, and
writes what they derive to mesh.telemetry.derived.v1 in the decoded envelope
shape, so storage, the archive and the detectors treat derived channels like
any other.

The join state of each device lives in keyed state, so a step whose inputs
arrive in separate packets still completes across them. All logic is in
common/postprocessing; this file only wires it to Flink.
"""
import argparse
import json
import os
import traceback

import structlog
from dotenv import load_dotenv

from pyflink.common import WatermarkStrategy
from pyflink.common.serialization import SimpleStringSchema
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

from common.flink_kafka import committed_or_latest

log = structlog.get_logger()


def _udf_log_exception(message: str) -> None:
    print(f"{message}\n{traceback.format_exc()}")


# "<mesh_id>:<device_id>" -> the raw config event, as registry published it.
PLANS_STATE = MapStateDescriptor("postprocessing-plans", Types.STRING(), Types.STRING())


class DeviceKeySelector(KeySelector):
    """Per device, the grain plans are published at."""

    def get_key(self, value: str) -> str:
        try:
            event = json.loads(value)
            return f"{event.get('mesh_id')}:{event.get('node_id')}"
        except Exception:
            return "unparseable"


class RunPostprocessing(KeyedBroadcastProcessFunction):
    def open(self, runtime_context):
        # Imported here, not at module level: `common` resolves on the
        # taskmanager rather than the submitting client.
        from common import postprocessing
        from common.postprocessing import stream

        self._postprocessing = postprocessing
        self._stream = stream
        self._join_state = runtime_context.get_state(ValueStateDescriptor("join-state", Types.STRING()))
        # Parsed plans per device, reused while the raw config is unchanged.
        self._parsed: dict[str, tuple[str, list]] = {}
        self._reported: set[str] = set()

    def _plans(self, key: str, raw: str) -> list:
        cached = self._parsed.get(key)
        if cached and cached[0] == raw:
            return cached[1]
        plans = self._stream.plans_from_config(json.loads(raw))
        self._parsed[key] = (raw, plans)
        return plans

    def process_element(self, value: str, ctx):
        try:
            event = json.loads(value)
        except Exception:
            _udf_log_exception("Bad decoded message, skipping")
            return
        key = ctx.get_current_key()
        raw = ctx.get_broadcast_state(PLANS_STATE).get(key)
        if not raw:
            if self._join_state.value() is not None:
                self._join_state.clear()
            return
        try:
            plans = self._plans(key, raw)
            observations = self._stream.observations_from_event(event)
            if not observations:
                return
            state = json.loads(self._join_state.value() or "{}")
            result = self._postprocessing.apply(plans, state, observations)
            self._join_state.update(json.dumps(state))
        except Exception:
            _udf_log_exception(f"Postprocessing failed for {key}, skipping message")
            return

        for failure, (count, first) in result.failures.items():
            # Once per step per task, so a miscalibrated sensor cannot flood the log.
            if failure not in self._reported:
                self._reported.add(failure)
                print(f"Postprocessing step {failure} skipped {count} row(s): {first}")

        for derived in self._stream.derived_events(event.get("mesh_id"), event.get("node_id"), result.derived, plans):
            yield json.dumps(derived)

    def process_broadcast_element(self, value: str, ctx):
        broadcast_state = ctx.get_broadcast_state(PLANS_STATE)
        try:
            event = json.loads(value)
        except Exception:
            _udf_log_exception("Bad postprocessing config event")
            return
        key = event.get("key")
        if not key:
            return
        if event.get("op") == "delete":
            broadcast_state.remove(key)
        else:
            broadcast_state.put(key, value)
        yield from ()  # this method only mutates broadcast state


def build_pipeline(env, kafka_bootstrap: str, decoded_topic: str, config_topic: str, derived_topic: str):
    source = (
        KafkaSource.builder()
        .set_bootstrap_servers(kafka_bootstrap)
        .set_topics(decoded_topic)
        .set_group_id("flink-postprocessing-group")
        # Live data only: history is reprocessed by a backfill, not by replaying the topic.
        .set_starting_offsets(committed_or_latest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )
    stream = env.from_source(source, WatermarkStrategy.no_watermarks(), "decoded-messages")

    config_source = (
        KafkaSource.builder()
        .set_bootstrap_servers(kafka_bootstrap)
        .set_topics(config_topic)
        .set_group_id("flink-postprocessing-config-group")
        .set_starting_offsets(KafkaOffsetsInitializer.earliest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )
    config_stream = env.from_source(config_source, WatermarkStrategy.no_watermarks(), "postprocessing-config")

    derived = (
        stream.key_by(DeviceKeySelector(), key_type=Types.STRING())
        .connect(config_stream.broadcast(PLANS_STATE))
        .process(RunPostprocessing(), output_type=Types.STRING())
    )

    sink = (
        KafkaSink.builder()
        .set_bootstrap_servers(kafka_bootstrap)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(derived_topic)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .set_delivery_guarantee(DeliveryGuarantee.AT_LEAST_ONCE)
        .build()
    )
    derived.sink_to(sink)


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
            "flink-connector-kafka-4.0.1-2.0.jar",
            "flink-sql-connector-kafka-4.0.1-2.0.jar",
            "kafka-clients-3.9.1.jar",
        ]
        jar_paths = tuple(f"file://{os.path.join(src_dir, 'jars', name)}" for name in jar_files)
        env.add_jars(*jar_paths)
    else:
        kafka_bootstrap = os.environ["KAFKA_BOOTSTRAP"]

    log.info("Starting Flink postprocessing job")

    build_pipeline(
        env,
        kafka_bootstrap=kafka_bootstrap,
        decoded_topic=os.environ["PROTO_DECODE__KAFKA_TOPIC"],
        config_topic=os.environ.get(
            "REGISTRY__POSTPROCESSING_CONFIG_KAFKA_TOPIC", "mesh.postprocessing_config.v1"
        ),
        derived_topic=os.environ.get("POSTPROCESSING__DERIVED_KAFKA_TOPIC", "mesh.telemetry.derived.v1"),
    )

    env.execute("mesh-postprocessing")


if __name__ == "__main__":
    main()
