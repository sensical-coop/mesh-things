import base64
import os

import pytest

pytest.importorskip("cryptography", reason="needs mesh-things[codec]")
pytest.importorskip("google.protobuf", reason="needs mesh-things[codec]")

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from mesh_things import codec, protocols
from mesh_things.protocols.v2_7 import mesh_pb2, mqtt_pb2, telemetry_pb2

def _build_envelope(mp: mesh_pb2.MeshPacket, channel_id: str = "LongFast", gateway_id: str = "!aabbccdd") -> bytes:
    se = mqtt_pb2.ServiceEnvelope()
    se.packet.CopyFrom(mp)
    se.channel_id = channel_id
    se.gateway_id = gateway_id
    return se.SerializeToString()

def _telemetry_packet(packet_id: int, node_id: int, battery_level: int) -> mesh_pb2.MeshPacket:
    tel = telemetry_pb2.Telemetry()
    tel.time = 1700000010
    tel.device_metrics.battery_level = battery_level

    data = mesh_pb2.Data()
    data.portnum = 67  # TELEMETRY_APP
    data.payload = tel.SerializeToString()

    mp = mesh_pb2.MeshPacket()
    mp.id = packet_id
    setattr(mp, "from", node_id)
    mp.rx_time = 1700000001
    mp.decoded.CopyFrom(data)
    return mp

def test_decode_plaintext_telemetry():
    mp = _telemetry_packet(packet_id=1, node_id=123456, battery_level=87)
    raw = _build_envelope(mp)

    result = codec.decode_message(raw, key_bytes=None)

    assert result is not None
    assert result["node_id"] == 123456
    assert result["packet_id"] == 1
    assert result["portnum"] == 67
    assert result["channel_id"] == "LongFast"
    # The envelope carries "!aabbccdd"; the decoded event carries the number.
    assert result["gateway_id"] == 0xAABBCCDD
    assert result["payload_kind"] == "telemetry:device_metrics"
    assert result["payload"]["device_metrics"]["battery_level"] == 87
    assert result["protocol"] == "2.7"


def test_decode_names_the_protocol_it_was_asked_for():
    raw = _build_envelope(_telemetry_packet(packet_id=1, node_id=1, battery_level=5))

    assert codec.decode_message(raw, key_bytes=None, protocol="2.7")["protocol"] == "2.7"


def test_an_unknown_protocol_is_refused():
    raw = _build_envelope(_telemetry_packet(packet_id=1, node_id=1, battery_level=5))

    with pytest.raises(ValueError, match="unknown protocol"):
        codec.decode_message(raw, key_bytes=None, protocol="9.9")

def test_decode_encrypted_with_correct_key():
    key_bytes = os.urandom(32)

    data = mesh_pb2.Data()
    data.portnum = 3  # POSITION_APP
    pos = mesh_pb2.Position()
    pos.latitude_i = 123456789
    pos.longitude_i = -987654321
    data.payload = pos.SerializeToString()

    mp = mesh_pb2.MeshPacket()
    mp.id = 42
    setattr(mp, "from", 999)
    mp.rx_time = 1700000000
    nonce = mp.id.to_bytes(8, "little") + getattr(mp, "from").to_bytes(8, "little")
    cipher = Cipher(algorithms.AES(key_bytes), modes.CTR(nonce), backend=default_backend())
    encryptor = cipher.encryptor()
    mp.encrypted = encryptor.update(data.SerializeToString()) + encryptor.finalize()

    raw = _build_envelope(mp)
    result = codec.decode_message(raw, key_bytes=key_bytes)

    assert result is not None
    assert result["payload_kind"] == "device:position"
    assert result["payload"]["latitude_i"] == 123456789

def test_decode_encrypted_with_wrong_key_returns_none_not_raises():
    key_bytes = os.urandom(32)
    wrong_key = os.urandom(32)

    data = mesh_pb2.Data()
    data.portnum = 67
    data.payload = b"irrelevant"

    mp = mesh_pb2.MeshPacket()
    mp.id = 1
    setattr(mp, "from", 1)
    nonce = mp.id.to_bytes(8, "little") + getattr(mp, "from").to_bytes(8, "little")
    cipher = Cipher(algorithms.AES(key_bytes), modes.CTR(nonce), backend=default_backend())
    encryptor = cipher.encryptor()
    mp.encrypted = encryptor.update(data.SerializeToString()) + encryptor.finalize()

    raw = _build_envelope(mp)
    result = codec.decode_message(raw, key_bytes=wrong_key)

    assert result is None

def test_decode_psk_expands_default_channel_key_shorthand():
    default_key = bytes(
        [0xD4, 0xF1, 0xBB, 0x3A, 0x20, 0x29, 0x07, 0x59, 0xF0, 0xBC, 0xFF, 0xAB, 0xCF, 0x4E, 0x69, 0x01]
    )
    assert codec.decode_psk("AQ==") == default_key  # index 1: the literal default key
    assert codec.decode_psk("Ag==") == default_key[:-1] + bytes([0x02])  # index 2: simple2
    assert codec.decode_psk("Cg==") == default_key[:-1] + bytes([0x0A])  # index 10: simple10

def test_decode_psk_treats_zero_byte_as_no_crypto():
    assert codec.decode_psk("AA==") is None
    assert codec.decode_psk("") is None
    assert codec.decode_psk(None) is None

def test_decode_psk_decodes_real_key():
    key_bytes = os.urandom(16)
    key_b64 = base64.b64encode(key_bytes).decode("ascii")
    assert codec.decode_psk(key_b64) == key_bytes

def _encrypted_position(key_b64: str) -> bytes:
    data = mesh_pb2.Data(portnum=3, payload=mesh_pb2.Position(latitude_i=1).SerializeToString())
    mp = mesh_pb2.MeshPacket(id=5)
    setattr(mp, "from", 77)
    mp.encrypted = codec.encrypt_packet(data.SerializeToString(), mp.id, 77, codec.decode_psk(key_b64))
    return _build_envelope(mp)

def test_decodes_with_accepts_the_right_key_only():
    key_b64 = base64.b64encode(os.urandom(16)).decode()
    raw = _encrypted_position(key_b64)

    assert codec.decodes_with(raw, key_b64)
    assert not codec.decodes_with(raw, base64.b64encode(os.urandom(16)).decode())
    assert not codec.decodes_with(raw, "")

def test_decodes_with_matches_a_plain_packet_to_a_mesh_without_encryption_only():
    raw = _build_envelope(_telemetry_packet(packet_id=1, node_id=1, battery_level=5))

    assert codec.decodes_with(raw, "")
    assert not codec.decodes_with(raw, "AQ==")

def test_decodes_with_refuses_garbage():
    assert not codec.decodes_with(b"\xff\x00garbage", "AQ==")
    assert not codec.decodes_with(_encrypted_position("AQ=="), "not base64!")

def test_well_known_psks():
    assert codec.is_well_known_psk("")
    assert codec.is_well_known_psk(None)
    assert codec.is_well_known_psk("AQ==")
    assert codec.is_well_known_psk("AA==")
    assert codec.is_well_known_psk("Cg==")
    assert not codec.is_well_known_psk(base64.b64encode(os.urandom(16)).decode())


def _soil_water_envelope() -> bytes:
    """A 2.8 packet with the soil_water_metrics variant, which 2.7 does not have."""
    v2_8 = protocols.get("2.8")
    telemetry = v2_8.telemetry_pb2.Telemetry(time=1700000010)
    telemetry.soil_water_metrics.solar_irradiance = 512.5
    telemetry.soil_water_metrics.soil_ph = 6.5
    packet = v2_8.mesh_pb2.MeshPacket(id=7, rx_time=1700000001)
    setattr(packet, "from", 42)
    packet.decoded.CopyFrom(v2_8.mesh_pb2.Data(portnum=67, payload=telemetry.SerializeToString()))
    envelope = v2_8.mqtt_pb2.ServiceEnvelope(channel_id="LongFast", gateway_id="!aabbccdd")
    envelope.packet.CopyFrom(packet)
    return envelope.SerializeToString()


def test_a_2_8_variant_decodes_with_2_8():
    result = codec.decode_message(_soil_water_envelope(), key_bytes=None, protocol="2.8")

    assert result["payload_kind"] == "telemetry:soil_water_metrics"
    assert result["payload"]["soil_water_metrics"] == {"solar_irradiance": 512.5, "soil_ph": 6.5}
    assert result["protocol"] == "2.8"


def test_a_2_8_variant_is_lost_on_a_mesh_declared_2_7():
    """What a mesh declared on the wrong version looks like: telemetry with no variant."""
    result = codec.decode_message(_soil_water_envelope(), key_bytes=None, protocol="2.7")

    assert result["payload_kind"] == "telemetry"
    assert "soil_water_metrics" not in result["payload"]


@pytest.mark.parametrize("battery_level", [0, 87, 101])
def test_a_2_7_packet_decodes_the_same_with_2_8(battery_level):
    raw = _build_envelope(_telemetry_packet(packet_id=1, node_id=1, battery_level=battery_level))

    as_2_7 = codec.decode_message(raw, key_bytes=None, protocol="2.7")
    as_2_8 = codec.decode_message(raw, key_bytes=None, protocol="2.8")

    assert {**as_2_7, "protocol": None} == {**as_2_8, "protocol": None}


def _parsed(raw: bytes, protocol: str):
    mp = codec.parse_service_envelope(raw)
    return codec.parse_payload(mp, protocol), mp.decoded.payload


def test_a_payload_the_declared_version_knows_needs_nothing_newer():
    (portnum, pb), payload = _parsed(_build_envelope(_telemetry_packet(1, 1, 50)), "2.7")

    assert codec.needed_protocol(portnum, pb, payload, "2.7") is None


def test_a_new_variant_needs_the_version_that_added_it():
    (portnum, pb), payload = _parsed(_soil_water_envelope(), "2.7")

    assert codec.needed_protocol(portnum, pb, payload, "2.7") == "2.8"


def test_a_payload_no_newer_version_can_parse_needs_an_unsupported_one():
    # Field 11 is soil_water_metrics in 2.8; these bytes are not a valid message.
    payload = telemetry_pb2.Telemetry(time=1).SerializeToString() + bytes([0x5A, 0x01, 0xFF])
    pb = telemetry_pb2.Telemetry()
    pb.ParseFromString(payload)

    assert codec.needed_protocol(67, pb, payload, "2.7") == protocols.UNSUPPORTED


def test_a_mesh_beacon_decodes_with_2_8():
    v2_8 = protocols.get("2.8")
    mp = mesh_pb2.MeshPacket()
    mp.decoded.portnum = v2_8.PortNum.MESH_BEACON_APP
    mp.decoded.payload = v2_8.mesh_beacon_pb2.MeshBeacon().SerializeToString()

    assert codec.decode_payload(mp, "2.8") is not None
    assert codec.decode_payload(mp, "2.7") is None


def test_a_new_field_inside_a_known_measurement_counts_too():
    v2_8 = protocols.get("2.8")
    telemetry = v2_8.telemetry_pb2.Telemetry(time=1)
    telemetry.environment_metrics.temperature = 20.0
    telemetry.environment_metrics.lightning_distance_km = 12.0
    pb = protocols.get("2.7").telemetry_pb2.Telemetry()
    pb.ParseFromString(telemetry.SerializeToString())

    assert pb.environment_metrics.temperature == 20.0
    assert codec.needed_protocol(67, pb, telemetry.SerializeToString(), "2.7") == "2.8"


def test_a_field_no_supported_version_knows_is_unsupported():
    # Field 999, varint 1: what a version newer than any supported one would add.
    payload = protocols.get("2.8").telemetry_pb2.Telemetry(time=1).SerializeToString() + bytes([0xB8, 0x3E, 0x01])
    pb = protocols.get("2.7").telemetry_pb2.Telemetry()
    pb.ParseFromString(payload)

    assert codec.needed_protocol(67, pb, payload, "2.7") == protocols.UNSUPPORTED
    assert codec.needed_protocol(67, pb, payload, "2.8") == protocols.UNSUPPORTED



def _decoded_payload(portnum: int, message) -> dict:
    mp = mesh_pb2.MeshPacket()
    mp.decoded.portnum = portnum
    mp.decoded.payload = message.SerializeToString()
    return codec.decode_payload(mp)[1]


def test_enums_at_value_zero_are_kept():
    user = _decoded_payload(4, mesh_pb2.User(long_name="Node", role="CLIENT", hw_model="UNSET"))

    assert user["role"] == "CLIENT"
    assert user["hw_model"] == "UNSET"


def test_a_map_report_keeps_its_default_preset_and_region():
    report = mqtt_pb2.MapReport(long_name="Roof", modem_preset="LONG_FAST")

    assert _decoded_payload(73, report)["modem_preset"] == "LONG_FAST"
    assert _decoded_payload(73, report)["region"] == "UNSET"


def test_numbers_at_zero_stay_out():
    position = _decoded_payload(3, mesh_pb2.Position(latitude_i=414000000, longitude_i=21000000))

    assert position["location_source"] == "LOC_UNSET"
    assert "time" not in position
    assert "sats_in_view" not in position


def test_the_decoded_event_carries_when_the_pipeline_received_it():
    raw = _build_envelope(_telemetry_packet(1, 2, 50))
    se = codec.parse_envelope(raw)
    portnum, pb_dict, kind = codec.decode_payload(se.packet)

    event = codec.build_decoded_message(se, portnum, pb_dict, kind, received_at=1700000005000)

    assert event["received_at"] == 1700000005000
