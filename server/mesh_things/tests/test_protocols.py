import importlib
import pkgutil

import pytest

pytest.importorskip("google.protobuf", reason="needs mesh-things[protobuf]")

from mesh_things import protocols


@pytest.mark.parametrize("version", sorted(protocols.VERSIONS))
def test_every_generated_module_imports_on_this_runtime(version):
    package = protocols.get(version)
    modules = [m.name for m in pkgutil.iter_modules(package.__path__) if m.name.endswith("_pb2")]
    assert modules
    for name in modules:
        importlib.import_module(f"{package.__name__}.{name}")


@pytest.mark.parametrize("version", sorted(protocols.VERSIONS))
def test_each_version_has_its_own_proto_package(version):
    package = protocols.get(version)
    assert package.mesh_pb2.DESCRIPTOR.package == package.__name__
    assert package.REF and len(package.COMMIT) == 40


@pytest.mark.parametrize("version", sorted(protocols.VERSIONS))
def test_payload_messages_are_keyed_by_portnum(version):
    package = protocols.get(version)
    assert set(package.PAYLOAD_MESSAGES) <= set(package.PortNum.values())
    assert package.PortNum.TEXT_MESSAGE_APP not in package.PAYLOAD_MESSAGES


def test_the_default_is_the_canonical_version():
    assert protocols.get() is protocols.get(protocols.CANONICAL)


def test_an_unknown_version_is_refused():
    with pytest.raises(ValueError, match="unknown protocol"):
        protocols.get("1.0")
