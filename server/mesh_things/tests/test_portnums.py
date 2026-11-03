import pytest

pytest.importorskip("google.protobuf", reason="needs mesh-things[protobuf]")

from mesh_things.portnums import portnum_name


def test_known_portnum():
    assert portnum_name(67) == "TELEMETRY_APP"


def test_encrypted_and_unknown():
    assert portnum_name(None) == "ENCRYPTED"
    assert portnum_name(9999) == "PORTNUM_9999"


def test_a_portnum_only_a_later_protocol_knows_is_named():
    assert portnum_name(37) == "MESH_BEACON_APP"
