from meshtastic import protocols
from meshtastic.protobuf import portnums_pb2

from mesh_things.channels import (
    DEVICE,
    NODEINFO_KIND,
    PORTNUM_PREFIX,
    POSITION_KIND,
    TELEMETRY,
    namespace_of,
)

_NAMED_PORTNUMS = {
    portnums_pb2.PortNum.POSITION_APP: POSITION_KIND,
    portnums_pb2.PortNum.NODEINFO_APP: NODEINFO_KIND,
    portnums_pb2.PortNum.TELEMETRY_APP: TELEMETRY,
}

_TELEMETRY_ONEOF = "variant"


def classify(portnum: int, pb) -> str:
    """Identify the shape of a decoded payload for a portnum.

    Returns a full "<namespace>:<measurement>" payload_kind, so the measurement
    half always matches what writer/point_builders.py stores.

    Add a new portnum here to make it cascade everywhere else.
    """
    base = _NAMED_PORTNUMS.get(portnum)
    if base is None:
        return f"{DEVICE}:{PORTNUM_PREFIX}{portnum}"
    if base == TELEMETRY:
        variant = pb.WhichOneof(_TELEMETRY_ONEOF) if pb is not None else None
        # No variant set means an empty Telemetry message; it has no sub-metric
        # measurement and nothing downstream will store it.
        return f"{TELEMETRY}:{variant}" if variant else TELEMETRY
    return base


def message_type(payload_kind: str):
    """The protobuf message a payload_kind's payload decodes to, or None for one with no message."""
    base = TELEMETRY if namespace_of(payload_kind) == TELEMETRY else payload_kind
    portnum = next((num for num, kind in _NAMED_PORTNUMS.items() if kind == base), None)
    prefix = f"{DEVICE}:{PORTNUM_PREFIX}"
    if portnum is None and payload_kind.startswith(prefix) and payload_kind[len(prefix):].isdigit():
        portnum = int(payload_kind[len(prefix):])
    handler = protocols.get(portnum)
    return handler.protobufFactory if handler else None
