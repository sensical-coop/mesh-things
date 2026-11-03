"""Names for Meshtastic portnums."""
from mesh_things import protocols


def portnum_name(portnum: int | None) -> str:
    """The `PortNum` name, `ENCRYPTED` for a packet that never decrypted, or `PORTNUM_<n>` if unknown.

    The newest protocol version that knows the portnum names it.
    """
    if portnum is None:
        return "ENCRYPTED"
    for version in reversed(protocols.VERSIONS):
        try:
            return protocols.get(version).PortNum.Name(portnum)
        except ValueError:
            continue
    return f"PORTNUM_{portnum}"
