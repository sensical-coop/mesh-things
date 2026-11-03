"""The probe packet: telemetry from the monitor's gateway, encrypted like a real node's."""
import secrets

from meshtastic.protobuf import mesh_pb2, mqtt_pb2, portnums_pb2, telemetry_pb2

from mesh_things import node_ids
from mesh_things.codec import decode_psk, encrypt_packet


def build_probe(gateway_node_id: int, channel_id: str, psk_b64: str, topic_prefix: str, marker: int) -> tuple[str, bytes]:
    """Return the MQTT topic and ServiceEnvelope bytes of a probe carrying `marker`.

    The marker travels as `device_metrics.uptime_seconds`, so the probe can be told
    apart from any earlier one once it reaches the readings API or a sink.
    """
    telemetry = telemetry_pb2.Telemetry()
    telemetry.time = marker
    telemetry.device_metrics.uptime_seconds = marker

    data = mesh_pb2.Data()
    data.portnum = portnums_pb2.TELEMETRY_APP
    data.payload = telemetry.SerializeToString()

    packet = mesh_pb2.MeshPacket()
    packet.id = secrets.randbits(32)
    setattr(packet, "from", gateway_node_id)
    packet.rx_time = marker
    packet.hop_start = 1
    packet.encrypted = encrypt_packet(data.SerializeToString(), packet.id, gateway_node_id, decode_psk(psk_b64))

    gateway_id = node_ids.to_hex(gateway_node_id)
    envelope = mqtt_pb2.ServiceEnvelope()
    envelope.packet.CopyFrom(packet)
    envelope.channel_id = channel_id
    envelope.gateway_id = gateway_id

    # The bridge keys Kafka by the last topic segment, which must be the gateway.
    return f"{topic_prefix}/{channel_id}/{gateway_id}", envelope.SerializeToString()
