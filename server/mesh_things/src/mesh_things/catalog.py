"""The telemetry channels the Meshtastic `Telemetry` protobuf can carry."""
from typing import Iterator, NamedTuple

from google.protobuf.descriptor import FieldDescriptor

from mesh_things import protocols
from mesh_things.channels import TELEMETRY

_SKIP_CPP_TYPES = (FieldDescriptor.CPPTYPE_STRING, FieldDescriptor.CPPTYPE_MESSAGE)


class TelemetryVariant(NamedTuple):
    payload_kind: str
    message_name: str
    field_names: tuple[str, ...]


def is_catalogued(field: FieldDescriptor) -> bool:
    """Whether a protobuf field is one numeric channel.

    Repeated numerics arrive as a list, so nothing downstream can write them.
    """
    if field.cpp_type in _SKIP_CPP_TYPES:
        return False
    # protobuf >= 6 dropped FieldDescriptor.label in favour of is_repeated.
    is_repeated = getattr(field, "is_repeated", None)
    if is_repeated is None:
        is_repeated = field.label == FieldDescriptor.LABEL_REPEATED
    return not is_repeated


def telemetry_variants() -> Iterator[TelemetryVariant]:
    """Each `Telemetry.variant` of every protocol version, with its catalogued fields.

    Versions are read oldest first, so variants and fields keep the order they first
    appeared in, and a later version only adds the ones it introduces.
    """
    variants: dict[str, TelemetryVariant] = {}
    for version in protocols.VERSIONS:
        telemetry = protocols.get(version).telemetry_pb2.Telemetry
        for variant_field in telemetry.DESCRIPTOR.oneofs_by_name["variant"].fields:
            message = variant_field.message_type
            payload_kind = f"{TELEMETRY}:{variant_field.name}"
            known = variants[payload_kind].field_names if payload_kind in variants else ()
            new = tuple(f.name for f in message.fields if is_catalogued(f) and f.name not in known)
            variants[payload_kind] = TelemetryVariant(payload_kind, message.name, known + new)
    yield from variants.values()
