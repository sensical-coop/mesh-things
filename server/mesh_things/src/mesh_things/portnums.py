"""Names for Meshtastic portnums."""
from mesh_things.protocols.v2_7 import portnums_pb2


def portnum_name(portnum: int | None) -> str:
    """The `PortNum` name, `ENCRYPTED` for a packet that never decrypted, or `PORTNUM_<n>` if unknown."""
    if portnum is None:
        return "ENCRYPTED"
    try:
        return portnums_pb2.PortNum.Name(portnum)
    except ValueError:
        return f"PORTNUM_{portnum}"
