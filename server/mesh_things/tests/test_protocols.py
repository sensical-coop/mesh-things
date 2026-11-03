import importlib
import pkgutil

import pytest

from mesh_things import protocols

try:
    import google.protobuf  # noqa: F401
except ImportError:
    HAS_PROTOBUF = False
else:
    HAS_PROTOBUF = True

needs_protobuf = pytest.mark.skipif(not HAS_PROTOBUF, reason="needs mesh-things[protobuf]")


def test_the_versions_are_listed_without_the_protobufs():
    assert protocols.CANONICAL in protocols.VERSIONS


@needs_protobuf
@pytest.mark.parametrize("version", sorted(protocols.VERSIONS))
def test_every_generated_module_imports_on_this_runtime(version):
    package = protocols.get(version)
    modules = [m.name for m in pkgutil.iter_modules(package.__path__) if m.name.endswith("_pb2")]
    assert modules
    for name in modules:
        importlib.import_module(f"{package.__name__}.{name}")


@needs_protobuf
@pytest.mark.parametrize("version", sorted(protocols.VERSIONS))
def test_each_version_has_its_own_proto_package(version):
    package = protocols.get(version)
    assert package.mesh_pb2.DESCRIPTOR.package == package.__name__
    assert package.REF and len(package.COMMIT) == 40


@needs_protobuf
@pytest.mark.parametrize("version", sorted(protocols.VERSIONS))
def test_payload_messages_are_keyed_by_portnum(version):
    package = protocols.get(version)
    assert set(package.PAYLOAD_MESSAGES) <= set(package.PortNum.values())
    assert package.PortNum.TEXT_MESSAGE_APP not in package.PAYLOAD_MESSAGES


@needs_protobuf
def test_the_default_is_the_canonical_version():
    assert protocols.get() is protocols.get(protocols.CANONICAL)


def test_an_unknown_version_is_refused():
    with pytest.raises(ValueError, match="unknown protocol"):
        protocols.get("1.0")


def test_versions_are_ordered_oldest_first():
    assert protocols.newer_than("2.7") == ["2.8"]
    assert protocols.newer_than("2.8") == []


def test_unsupported_is_newer_than_every_supported_version():
    assert protocols.is_newer("2.8", "2.7")
    assert not protocols.is_newer("2.7", "2.8")
    assert not protocols.is_newer("2.7", "2.7")
    assert protocols.is_newer(protocols.UNSUPPORTED, "2.8")
    assert not protocols.is_newer("2.8", protocols.UNSUPPORTED)
    assert not protocols.is_newer(None, "2.7")


def test_the_newest_of_several_versions():
    assert protocols.newest(["2.7", "2.8", "2.7"]) == "2.8"
    assert protocols.newest(["2.8", protocols.UNSUPPORTED]) == protocols.UNSUPPORTED


@needs_protobuf
@pytest.mark.parametrize("version", sorted(protocols.VERSIONS))
def test_the_declared_source_is_the_one_generated(version):
    assert protocols.get(version).REF == protocols.PROTOCOLS[version].source_ref


def _fields(message, seen=None) -> dict:
    """Every field reachable from a message, as {(message, number): (type, repeated)}."""
    seen = set() if seen is None else seen
    if message.name in seen:
        return {}
    seen.add(message.name)
    found = {}
    for field in message.fields:
        is_repeated = getattr(field, "is_repeated", None)
        if is_repeated is None:
            is_repeated = field.label == field.LABEL_REPEATED
        found[(message.name, field.number)] = (field.type, is_repeated)
        if field.message_type is not None:
            found.update(_fields(field.message_type, seen))
    return found


@needs_protobuf
@pytest.mark.parametrize("version", [v for v, p in protocols.PROTOCOLS.items() if p.adds_only])
def test_a_version_declared_adds_only_keeps_every_older_field(version):
    """A sanity check on the declaration: a unit change on the same wire type still needs a person.

    Remote administration is left out: it carries device configuration, not readings, and
    2.8 dropped fields from `TrafficManagementConfig` there.
    """
    older = protocols.get(list(protocols.VERSIONS)[list(protocols.VERSIONS).index(version) - 1])
    newer = protocols.get(version)
    for portnum, message in older.PAYLOAD_MESSAGES.items():
        if portnum == older.PortNum.ADMIN_APP:
            continue
        before = _fields(message.DESCRIPTOR)
        after = _fields(newer.PAYLOAD_MESSAGES[portnum].DESCRIPTOR)
        changed = {key: (old, after.get(key)) for key, old in before.items() if after.get(key) != old}
        assert changed == {}, f"{message.DESCRIPTOR.name}: {changed}"


def test_a_version_past_its_sunset_date_is_sunset():
    from datetime import date

    retiring = {**protocols.PROTOCOLS, "2.7": protocols.PROTOCOLS["2.7"]._replace(sunset=date(2027, 1, 1))}
    import unittest.mock as mock

    with mock.patch.object(protocols, "PROTOCOLS", retiring):
        assert protocols.status("2.7", date(2026, 12, 31)) == protocols.SUPPORTED
        assert protocols.status("2.7", date(2027, 1, 1)) == protocols.SUNSET


def test_moving_up_needs_a_newer_version_that_only_adds():
    assert protocols.can_move_up("2.7")
    assert not protocols.can_move_up("2.8")
