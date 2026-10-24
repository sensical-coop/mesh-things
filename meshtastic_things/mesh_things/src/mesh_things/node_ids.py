"""Conversion between the two forms of a Meshtastic node number."""


def to_num(value: str | int | None) -> int | None:
    """Return the node number for a `!aabbccdd` id, or None if unparseable.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    text = value.strip()
    if not text.startswith("!"):
        return None
    try:
        return int(text[1:], 16)
    except ValueError:
        return None


def to_hex(num: int) -> str:
    """Return the wire form of a node number, e.g. `!19ba4462`."""
    return f"!{num:08x}"
