from mesh_things.portnums import portnum_name


def test_known_portnum():
    assert portnum_name(67) == "TELEMETRY_APP"


def test_encrypted_and_unknown():
    assert portnum_name(None) == "ENCRYPTED"
    assert portnum_name(9999) == "PORTNUM_9999"
