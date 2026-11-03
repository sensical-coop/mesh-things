"""The Meshtastic protocol versions this package decodes.

Each version is a set of protobuf modules generated from the upstream protos, under
`mesh_things.protocols.<slug>`, so versions load side by side. Listing the versions
needs nothing extra; loading a set needs mesh-things[protobuf].
"""
import importlib
from datetime import date
from types import ModuleType
from typing import NamedTuple

CURRENT = "current"
SUPPORTED = "supported"
DEPRECATED = "deprecated"
SUNSET = "sunset"
STATUSES = (CURRENT, SUPPORTED, DEPRECATED, SUNSET)


class Protocol(NamedTuple):
    """One supported version and where it stands.

    `adds_only` says the version only adds fields to the one before it, so a mesh can
    move up to it without any reading changing meaning. It is declared, since a unit
    change on the same wire type cannot be seen in the schema.
    """

    version: str
    slug: str
    source_ref: str
    status: str
    sunset: date | None = None
    adds_only: bool = False


# Oldest first. A version past its sunset date counts as sunset, whatever its status.
PROTOCOLS = {
    p.version: p
    for p in (
        Protocol("2.7", "v2_7", "v2.7.26", SUPPORTED),
        Protocol("2.8", "v2_8", "v2.8.2", CURRENT, adds_only=True),
    )
}
VERSIONS = {p.version: p.slug for p in PROTOCOLS.values()}
# Stored readings use this version's units and channel names.
CANONICAL = "2.7"
# What a new mesh is declared on.
DEFAULT = "2.8"
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


def status(version: str, today: date | None = None) -> str:
    """A version's status on `today`: its declared one, or SUNSET once its sunset date has passed."""
    protocol = PROTOCOLS[version]
    if protocol.sunset is not None and (today or date.today()) >= protocol.sunset:
        return SUNSET
    return protocol.status


def can_move_up(version: str) -> bool:
    """Whether meshes on `version` may be moved to the next version without anything changing meaning."""
    following = newer_than(version)
    return bool(following) and PROTOCOLS[following[0]].adds_only


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
