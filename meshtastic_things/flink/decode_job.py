import argparse
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
from pyflink.datastream.functions import KeySelector, KeyedBroadcastProcessFunction
from pyflink.datastream.state import MapStateDescriptor
from pyflink.common.serialization import SimpleStringSchema
from pyflink.java_gateway import get_gateway

log = structlog.get_logger()


def _udf_log(message: str) -> None:
    """Never use anything else here except print.

    PyFlink UDF methods crashes otherwise.
    """
    print(message)


def _udf_log_exception(message: str) -> None:
    print(f"{message}\n{traceback.format_exc()}")


def _udf_log_drop(reason: str) -> None:
    print(f"Dropping packet: {reason}")

# SimpleStringSchema decodes raw bytes with a Charset
# UTF-8 corrupts protobuf packets, so we use ISO-8859-1
RAW_BYTES_CHARSET = "ISO-8859-1"

# Keyed by gateway_id, value {"psk_b64":..., "mesh_id":..., "source_id":...}
GATEWAY_KEY_STATE = MapStateDescriptor("gateway-keys", Types.STRING(), Types.STRING())

# Keyed by "mesh_id:device_id", presence means rejected
NODE_REJECTED_STATE = MapStateDescriptor("node-rejections", Types.STRING(), Types.STRING())


class _BroadcastGatewayState:
    """Adapts Flink's MapState for decode_packet"""

    def __init__(self, map_state):
        self._map_state = map_state

    def get(self, key):
        if not self._map_state.contains(key):
            return None
        return json.loads(self._map_state.get(key))


class _BroadcastRejectedSet:
    """Adapts Flink's MapState to the decode_packet checks"""

    def __init__(self, map_state):
        self._map_state = map_state

    def __contains__(self, key):
        return self._map_state.contains(key)


class PacketKeySelector(KeySelector):
    """Keys the main packet stream by gateway_id so it can be connected to the
    broadcast config stream"""

    def open(self, runtime_context):
        from common import codec

        self._codec = codec

    def get_key(self, value: str) -> str:
        try:
            se = self._codec.parse_envelope(value.encode(RAW_BYTES_CHARSET))
            return se.gateway_id or "unparseable"
        except Exception:
            return "unparseable"


class DecodeWithBroadcastKey(KeyedBroadcastProcessFunction):
    """Decrypt/decode a ServiceEnvelope only if the gateway is registered and the
    node isn't rejected."""

    def open(self, runtime_context):
        from common import decode

        self._decode = decode

    def process_element(self, value: str, ctx):
        gateway_state_map = ctx.get_broadcast_state(GATEWAY_KEY_STATE)
        current_key = ctx.get_current_key()
        if not gateway_state_map.contains(current_key):
            _udf_log(f"Dropping packet from unregistered gateway: gateway_id={current_key}")
            return

        raw = value.encode(RAW_BYTES_CHARSET)
        rejected_state = ctx.get_broadcast_state(NODE_REJECTED_STATE)
        try:
            events = self._decode.decode_packet(
                raw,
                _BroadcastGatewayState(gateway_state_map),
                _BroadcastRejectedSet(rejected_state),
                on_drop=_udf_log_drop,
                received_at=ctx.timestamp(),
            )
        except Exception:
            _udf_log_exception("Failed to decode packet")
            return
        if events is None:
            return

        for kind, payload in events.items():
            yield json.dumps({"kind": kind, "payload": payload})

    def process_broadcast_element(self, value: str, ctx):
        try:
            event = json.loads(value)
        except Exception:
            _udf_log_exception(f"Failed to parse broadcast-config event: raw={value}")
            return
        key = event.get("key")
        if not key:
            return

        if event.get("kind") == "node_rejection":
            rejected_state = ctx.get_broadcast_state(NODE_REJECTED_STATE)
            if event.get("op") == "delete":
                rejected_state.remove(key)
            else:
                rejected_state.put(key, "1")
        else:
            gateway_state_map = ctx.get_broadcast_state(GATEWAY_KEY_STATE)
            if event.get("op") == "delete":
                gateway_state_map.remove(key)
            else:
                state_value = json.dumps(
                    {
                        "psk_b64": event.get("psk_b64", ""),
                        "mesh_id": event.get("mesh_id"),
                        "source_id": event.get("source_id"),
                    }
                )
                gateway_state_map.put(key, state_value)
        yield from ()  # this method only changes broadcast state


def _committed_offsets_or_earliest() -> KafkaOffsetsInitializer:
    """The group's committed offsets, or the earliest ones where it has none.

    KafkaOffsetsInitializer.committed_offsets passes the shaded
    OffsetResetStrategy, but which of the two Kafka connector jars in lib/
    provides OffsetsInitializer depends on classpath order, so the enum is
    taken from the signature that actually loaded.
    """
    initializers = get_gateway().jvm.org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer
    for method in initializers._java_lang_class.getMethods():
        if method.getName() == "committedOffsets" and len(method.getParameterTypes()) == 1:
            strategy_class = method.getParameterTypes()[0]
            earliest = next(c for c in strategy_class.getEnumConstants() if c.name() == "EARLIEST")
            return KafkaOffsetsInitializer(initializers.committedOffsets(earliest))
    raise RuntimeError("OffsetsInitializer.committedOffsets(OffsetResetStrategy) not found")


def build_pipeline(
    env,
    kafka_bootstrap: str,
    raw_topic: str,
    decoded_topic: str,
    keys_topic: str,
    devices_topic: str,
    node_rejections_topic: str,
    sensor_discovery_topic: str,
    traffic_topic: str,
):
    source = (
        KafkaSource.builder()
        .set_bootstrap_servers(kafka_bootstrap)
        .set_topics(raw_topic)
        .set_group_id("flink-decode-group")
        # Without a checkpoint, resume from the offsets the last run committed
        # rather than re-decoding the whole raw topic.
        .set_starting_offsets(_committed_offsets_or_earliest())
        .set_value_only_deserializer(SimpleStringSchema(RAW_BYTES_CHARSET))
        .build()
    )
    # Kafka record timestamps survive no_watermarks(), so ctx.timestamp() is when the bridge received a packet.
    stream = env.from_source(source, WatermarkStrategy.no_watermarks(), "raw-mesh-packets").uid("raw-mesh-packets")

    keys_source = (
        KafkaSource.builder()
        .set_bootstrap_servers(kafka_bootstrap)
        .set_topics(keys_topic)
        .set_group_id("flink-decode-keys-group")
        .set_starting_offsets(KafkaOffsetsInitializer.earliest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )
    keys_stream = env.from_source(keys_source, WatermarkStrategy.no_watermarks(), "gateway-key-config").uid(
        "gateway-key-config"
    )

    node_rejections_source = (
        KafkaSource.builder()
        .set_bootstrap_servers(kafka_bootstrap)
        .set_topics(node_rejections_topic)
        .set_group_id("flink-decode-node-rejections-group")
        .set_starting_offsets(KafkaOffsetsInitializer.earliest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )
    node_rejections_stream = env.from_source(
        node_rejections_source, WatermarkStrategy.no_watermarks(), "node-rejection-config"
    ).uid("node-rejection-config")

    keyed_stream = stream.key_by(PacketKeySelector(), key_type=Types.STRING())
    # Both config topics feed one broadcast connection - "kind" routes each
    # event to the right state map in process_broadcast_element.
    broadcast_stream = keys_stream.union(node_rejections_stream).broadcast(GATEWAY_KEY_STATE, NODE_REJECTED_STATE)

    # Stable uids let a savepoint restore after operators are added or removed.
    combined_stream = (
        keyed_stream.connect(broadcast_stream)
        .process(DecodeWithBroadcastKey(), output_type=Types.STRING())
        .uid("decode")
    )

    for kind, topic in (
        ("decoded", decoded_topic),
        ("sighting", devices_topic),
        ("discovery", sensor_discovery_topic),
        ("traffic", traffic_topic),
    ):
        _sink_kind(combined_stream, kafka_bootstrap, kind, topic)


def _sink_kind(combined_stream, kafka_bootstrap: str, kind: str, topic: str) -> None:
    """Route one kind of event from the decode output to its own topic."""
    sink = (
        KafkaSink.builder()
        .set_bootstrap_servers(kafka_bootstrap)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(topic)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .set_delivery_guarantee(DeliveryGuarantee.AT_LEAST_ONCE)
        .build()
    )
    combined_stream.filter(lambda v: json.loads(v)["kind"] == kind).map(
        lambda v: json.dumps(json.loads(v)["payload"]), output_type=Types.STRING()
    ).sink_to(sink).uid(f"{kind}-sink")


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

    log.info("Starting Flink decode job")

    build_pipeline(
        env,
        kafka_bootstrap=kafka_bootstrap,
        raw_topic=os.environ["MQTT_BRIDGE__KAFKA_TOPIC"],
        decoded_topic=os.environ["PROTO_DECODE__KAFKA_TOPIC"],
        keys_topic=os.environ.get("REGISTRY__KAFKA_TOPIC", "mesh.keys.v1"),
        devices_topic=os.environ.get("REGISTRY__DEVICES_KAFKA_TOPIC", "mesh.devices.v1"),
        node_rejections_topic=os.environ.get("REGISTRY__NODE_REJECTIONS_KAFKA_TOPIC", "mesh.node_rejections.v1"),
        sensor_discovery_topic=os.environ.get(
            "REGISTRY__SENSOR_DISCOVERY_KAFKA_TOPIC", "mesh.sensor_discovery.v1"
        ),
        traffic_topic=os.environ.get("PROTO_DECODE__TRAFFIC_KAFKA_TOPIC", "mesh.traffic.v1"),
    )

    env.execute("mesh-decode-decrypt")


if __name__ == "__main__":
    main()
