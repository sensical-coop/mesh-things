"""The Meshtastic protocol versions this package decodes. Needs mesh-things[protobuf].

Each version is a set of protobuf modules generated from the upstream protos, under
`mesh_things.protocols.<slug>`, so versions load side by side.
"""
import importlib
from types import ModuleType

try:
    import google.protobuf  # noqa: F401
except ImportError as error:
    raise ImportError("mesh_things.protocols needs the protobufs: pip install 'mesh-things[protobuf]'") from error

CANONICAL = "2.7"
VERSIONS = {"2.7": "v2_7"}


def get(version: str = CANONICAL) -> ModuleType:
    """The generated set for a protocol version, such as `2.7`."""
    try:
        slug = VERSIONS[version]
    except KeyError:
        raise ValueError(f"unknown protocol {version!r}; known: {', '.join(VERSIONS)}") from None
    return importlib.import_module(f"{__name__}.{slug}")
