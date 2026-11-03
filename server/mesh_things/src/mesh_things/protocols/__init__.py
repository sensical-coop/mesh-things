"""The Meshtastic protocol versions this package decodes.

Each version is a set of protobuf modules generated from the upstream protos, under
`mesh_things.protocols.<slug>`, so versions load side by side. Listing the versions
needs nothing extra; loading a set needs mesh-things[protobuf].
"""
import importlib
from types import ModuleType

CANONICAL = "2.7"
# Oldest first.
VERSIONS = {"2.7": "v2_7", "2.8": "v2_8"}
# A device that sends fields no supported version knows.
UNSUPPORTED = "unsupported"


def newer_than(version: str) -> list[str]:
    """The supported versions after `version`, oldest first."""
    versions = list(VERSIONS)
    return versions[versions.index(version) + 1:]


def _rank(version: str) -> int:
    return len(VERSIONS) if version == UNSUPPORTED else list(VERSIONS).index(version)


def is_newer(version: str | None, than: str) -> bool:
    """Whether `version`, a supported one or UNSUPPORTED, comes after `than`. None never does."""
    return version is not None and _rank(version) > _rank(than)


def newest(versions) -> str:
    """The newest of several versions, UNSUPPORTED above every supported one."""
    return max(versions, key=_rank)


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
