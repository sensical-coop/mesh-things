import base64

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from google.protobuf import unknown_fields
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import DecodeError, Message

from mesh_things import node_ids, portnum_registry, protocols
from mesh_things.protocols.v2_7 import mesh_pb2, mqtt_pb2

# Channel.psk default AQ==
_DEFAULT_CHANNEL_KEY = bytes(
    [0xD4, 0xF1, 0xBB, 0x3A, 0x20, 0x29, 0x07, 0x59, 0xF0, 0xBC, 0xFF, 0xAB, 0xCF, 0x4E, 0x69, 0x01]
)


def parse_envelope(raw: bytes) -> mqtt_pb2.ServiceEnvelope:
    """Parse an MQTT envelope with the canonical protocol.

    The envelope names the gateway, and so the mesh and its protocol, so it is read
    before either is known. Its fields have the same numbers in every version.
    """
    se = mqtt_pb2.ServiceEnvelope()
    se.ParseFromString(raw)
    return se

def parse_service_envelope(raw: bytes) -> mesh_pb2.MeshPacket:
    return parse_envelope(raw).packet

def _cipher(packet_id: int, node_id: int, key_bytes: bytes) -> Cipher:
    nonce = packet_id.to_bytes(8, "little") + node_id.to_bytes(8, "little")
    return Cipher(algorithms.AES(key_bytes), modes.CTR(nonce), backend=default_backend())

def encrypt_packet(data_bytes: bytes, packet_id: int, node_id: int, key_bytes: bytes) -> bytes:
    """Encrypt a serialized `Data` the way a node does; the inverse of decrypt_packet."""
    encryptor = _cipher(packet_id, node_id, key_bytes).encryptor()
    return encryptor.update(data_bytes) + encryptor.finalize()

def decrypt_packet(mp: mesh_pb2.MeshPacket, key_bytes: bytes | None) -> mesh_pb2.Data | None:
    """Decrypt a payload. Returns None if there is a failure"""
    if not key_bytes:
        return None
    try:
        decryptor = _cipher(getattr(mp, "id"), getattr(mp, "from"), key_bytes).decryptor()
        decrypted_bytes = decryptor.update(getattr(mp, "encrypted")) + decryptor.finalize()

        data = mesh_pb2.Data()
        data.ParseFromString(decrypted_bytes)
        return data
    except Exception:
        # Do not log anything here
        return None

def parse_payload(mp: mesh_pb2.MeshPacket, protocol: str = protocols.CANONICAL) -> tuple[int, Message] | None:
    """Returns (portnum, message) or None, parsing with a protocol version's messages."""
    if not mp.HasField("decoded"):
        return None

    portnum = mp.decoded.portnum
    message = protocols.get(protocol).PAYLOAD_MESSAGES.get(portnum)
    if message is None:
        return None

    pb = message()
    pb.ParseFromString(mp.decoded.payload)
    return portnum, pb


def _is_repeated(field) -> bool:
    # protobuf >= 6 dropped FieldDescriptor.label in favour of is_repeated.
    is_repeated = getattr(field, "is_repeated", None)
    return field.label == field.LABEL_REPEATED if is_repeated is None else is_repeated


def _with_enum_defaults(message: Message, fields: dict) -> dict:
    """Add the enum fields MessageToDict leaves out at value 0, recursively.

    An enum without presence cannot say it was not sent, and its value 0 is usually
    meaningful (role `CLIENT`, preset `LONG_FAST`). Numeric fields at 0 stay out, since
    there 0 commonly means the device has no value.
    """
    for field in message.DESCRIPTOR.fields:
        if (
            field.enum_type is not None
            and not field.has_presence
            and not _is_repeated(field)
            and field.name not in fields
        ):
            fields[field.name] = field.enum_type.values_by_number[field.default_value].name
    for field, value in message.ListFields():
        if field.message_type is None or field.message_type.GetOptions().map_entry:
            continue
        if _is_repeated(field):
            for item, item_fields in zip(value, fields.get(field.name) or []):
                _with_enum_defaults(item, item_fields)
        elif isinstance(fields.get(field.name), dict):
            _with_enum_defaults(value, fields[field.name])
    return fields


def payload_fields(portnum: int, pb: Message) -> tuple[dict, str]:
    """A parsed payload as (pb_dict, payload_kind), with enums at value 0 included."""
    pb_dict = _with_enum_defaults(pb, MessageToDict(pb, preserving_proto_field_name=True))
    return pb_dict, portnum_registry.classify(portnum, pb)


def decode_payload(mp: mesh_pb2.MeshPacket, protocol: str = protocols.CANONICAL):
    """Returns (portnum, pb_dict, payload_kind) or None, decoding with a protocol version's messages."""
    parsed = parse_payload(mp, protocol)
    if parsed is None:
        return None
    portnum, pb = parsed
    return (portnum, *payload_fields(portnum, pb))


def has_unknown_fields(message: Message) -> bool:
    """Whether a parsed message, or any message inside it, holds fields its schema does not know."""
    if len(unknown_fields.UnknownFieldSet(message)):
        return True
    for field, value in message.ListFields():
        if field.message_type is None or field.message_type.GetOptions().map_entry:
            continue
        values = value if _is_repeated(field) else [value]
        if any(has_unknown_fields(item) for item in values):
            return True
    return False


def needed_protocol(portnum: int, pb: Message, payload: bytes, protocol: str) -> str | None:
    """The version a payload needs when `protocol` leaves fields unknown, or None when it does not.

    The oldest newer version that knows every field, or protocols.UNSUPPORTED when none does.
    """
    if not has_unknown_fields(pb):
        return None
    for version in protocols.newer_than(protocol):
        message = protocols.get(version).PAYLOAD_MESSAGES.get(portnum)
        if message is None:
            continue
        newer = message()
        try:
            newer.ParseFromString(payload)
        except DecodeError:
            # Bytes the declared version skipped as unknown need not be valid in a newer one.
            continue
        if not has_unknown_fields(newer):
            return version
    return protocols.UNSUPPORTED

def build_decoded_message(
    se: mqtt_pb2.ServiceEnvelope,
    portnum: int,
    pb_dict: dict,
    payload_kind: str,
    protocol: str = protocols.CANONICAL,
    received_at: int | None = None,
) -> dict:
    """Shape a decoded packet into the event downstream writers consume.

    `rx_time` is when the gateway heard it, in epoch seconds, or 0 when the gateway
    had no clock. `received_at` is when the pipeline did, in epoch milliseconds.
    """
    mp = se.packet
    return {
        "node_id": getattr(mp, "from"),
        "to": mp.to,
        "packet_id": mp.id,
        "portnum": portnum,
        "request_id": mp.decoded.request_id or None,
        "rx_time": mp.rx_time,
        "received_at": received_at,
        **routing_fields(mp),
        "channel_id": se.channel_id,
        "gateway_id": node_ids.to_num(se.gateway_id),
        "payload_kind": payload_kind,
        "protocol": protocol,
        "payload": pb_dict,
    }


def routing_fields(mp: mesh_pb2.MeshPacket) -> dict:
    """Return the route a packet took to the gateway that heard it.

    `hop_start` is 0 on firmware that predates it, which leaves the hop count
    unknown. Signal readings are 0 when the gateway did not receive the packet
    over the air (via MQTT, or relayed from its own phone), so both become None.
    """
    heard_over_air = mp.rx_rssi != 0
    return {
        "hop_start": mp.hop_start,
        "hop_limit": mp.hop_limit,
        "rx_snr": mp.rx_snr if heard_over_air else None,
        "rx_rssi": mp.rx_rssi if heard_over_air else None,
        "relay_node": mp.relay_node or None,
        "next_hop": mp.next_hop or None,
        "via_mqtt": mp.via_mqtt,
    }

def decode_message(raw: bytes, key_bytes: bytes | None, protocol: str = protocols.CANONICAL) -> dict | None:
    """Parse, decrypt (if needed), decode, and shape the output.

    Returns None if the message cannot be decrypted, has an unknown
    portnum, or has no protobuf schema for that portnum.
    """
    se = parse_envelope(raw)
    mp = se.packet

    if mp.HasField("encrypted") and not mp.HasField("decoded"):
        decrypted = decrypt_packet(mp, key_bytes)
        if decrypted is None:
            return None
        mp.decoded.CopyFrom(decrypted)

    result = decode_payload(mp, protocol)
    if result is None:
        return None

    portnum, pb_dict, payload_kind = result
    return build_decoded_message(se, portnum, pb_dict, payload_kind, protocol)


def decode_psk(key_b64: str) -> bytes | None:
    """Base64-decode a channel PSK read from the key store.

    """
    if not key_b64:
        return None
    raw = base64.b64decode(key_b64.encode("ascii"))
    if len(raw) == 1:
        index = raw[0]
        if index == 0:
            return None
        return _DEFAULT_CHANNEL_KEY[:-1] + bytes([(_DEFAULT_CHANNEL_KEY[-1] + index - 1) & 0xFF])
    return raw


def is_well_known_psk(key_b64: str | None) -> bool:
    """Whether a PSK is blank or a one-byte index key, both of which anyone can decrypt."""
    if not key_b64:
        return True
    try:
        return len(base64.b64decode(key_b64.encode("ascii"))) <= 1
    except ValueError:
        return False


def decodes_with(raw: bytes, key_b64: str | None, protocol: str = protocols.CANONICAL) -> bool:
    """Whether a ServiceEnvelope fully decodes with a channel PSK and protocol version.

    An encrypted packet must decrypt to a known portnum whose payload parses; a
    plain one only matches a mesh without encryption. Parsing alone is not
    enough, since a wrong key yields random bytes that sometimes parse as `Data`.
    """
    try:
        mp = parse_service_envelope(raw)
        key_bytes = decode_psk(key_b64)
    except Exception:
        return False
    encrypted = mp.HasField("encrypted") and not mp.HasField("decoded")
    if encrypted != (key_bytes is not None):
        return False
    if encrypted:
        decrypted = decrypt_packet(mp, key_bytes)
        if decrypted is None:
            return False
        mp.decoded.CopyFrom(decrypted)
    try:
        return decode_payload(mp, protocol) is not None
    except Exception:
        return False
