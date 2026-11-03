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
