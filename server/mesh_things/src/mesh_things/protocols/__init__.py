"""The Meshtastic protocol versions this package decodes.

Each version is a set of protobuf modules generated from the upstream protos, under
`mesh_things.protocols.<slug>`, so versions load side by side. Listing the versions
needs nothing extra; loading a set needs mesh-things[protobuf].
"""
import importlib
from types import ModuleType

CANONICAL = "2.7"
VERSIONS = {"2.7": "v2_7", "2.8": "v2_8"}


def get(version: str = CANONICAL) -> ModuleType:
    """The generated set for a protocol version, such as `2.7`."""
    try:
        slug = VERSIONS[version]
    except KeyError:
        raise ValueError(f"unknown protocol {version!r}; known: {', '.join(VERSIONS)}") from None
    try:
        return importlib.import_module(f"{__name__}.{slug}")
    except ImportError as error:
        if error.name and error.name.startswith("google"):
            raise ImportError("mesh_things.protocols needs the protobufs: pip install 'mesh-things[protobuf]'") from error
        raise
