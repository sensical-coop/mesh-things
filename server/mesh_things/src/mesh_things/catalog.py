"""The telemetry channels the Meshtastic `Telemetry` protobuf can carry."""
from typing import Iterator, NamedTuple

from google.protobuf.descriptor import FieldDescriptor
from meshtastic.protobuf import telemetry_pb2

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
    """Each `Telemetry.variant` and its catalogued fields, in schema order."""
    for variant_field in telemetry_pb2.Telemetry.DESCRIPTOR.oneofs_by_name["variant"].fields:
        message = variant_field.message_type
        yield TelemetryVariant(
            payload_kind=f"{TELEMETRY}:{variant_field.name}",
            message_name=message.name,
            field_names=tuple(f.name for f in message.fields if is_catalogued(f)),
        )
