"""The MQTT client id and session expiry, which decide whether the bridge keeps receiving."""
from bridge.mqtt_handler import _client_id, session_expiry_seconds

def test_the_id_does_not_depend_on_the_hostname(monkeypatch):
    """The whole bug: gethostname() is the container id under Docker, so it changed on every
    recreate and left the old session behind.
"""
    monkeypatch.delenv("MQTT_BRIDGE__CLIENT_ID", raising=False)

    import socket

    monkeypatch.setattr(socket, "gethostname", lambda: "some-container-id")
    first = _client_id()
    monkeypatch.setattr(socket, "gethostname", lambda: "a-different-one")

    assert _client_id() == first == "mesh-bridge"

def test_the_configured_id_is_used(monkeypatch):
    monkeypatch.setenv("MQTT_BRIDGE__CLIENT_ID", "mesh-bridge-2")

    assert _client_id() == "mesh-bridge-2"

def test_a_blank_id_falls_back_rather_than_asking_for_a_random_one(monkeypatch):
    """`MQTT_BRIDGE__CLIENT_ID=` in an .env file is empty, not a valid id, and an empty id
    makes the broker assign a random one - which is the original bug wearing a different
    hat.
"""
    monkeypatch.setenv("MQTT_BRIDGE__CLIENT_ID", "   ")

    assert _client_id() == "mesh-bridge"

def test_session_expiry_defaults_to_something_generous(monkeypatch):
    """A member that never returns holds its share until the session expires, so this bounds
    the damage.
"""
    monkeypatch.delenv("MQTT_BRIDGE__SESSION_EXPIRY", raising=False)

    assert session_expiry_seconds() >= 600

def test_session_expiry_is_configurable(monkeypatch):
    monkeypatch.setenv("MQTT_BRIDGE__SESSION_EXPIRY", "900")

    assert session_expiry_seconds() == 900

def test_retiring_a_session_asks_the_broker_to_discard_it(monkeypatch):
    """The two arguments that make it work: `clean_start=True` throws the existing session
    away, and a zero expiry stops a new one outliving this connection.
"""
    import asyncio
    from unittest import mock

    import bridge.mqtt_handler as handler

    for var, value in {
        "MQTT_BRIDGE__USER": "u",
        "MQTT_BRIDGE__PASS": "p",
        "MQTT_BRIDGE__SSL": "false",
    }.items():
        monkeypatch.setenv(var, value)

    created = {}

    def fake_client(*args, **kwargs):
        created.update(kwargs)
        return mock.AsyncMock()

    monkeypatch.setattr(handler.aiomqtt, "Client", fake_client)
    asyncio.run(handler.retire_session("broker.example", "mesh-bridge-3"))

    assert created["identifier"] == "mesh-bridge-3"
    assert created["clean_start"] is True
    assert created["properties"].SessionExpiryInterval == 0
