"""Naming shared by the registry, which creates a sink's EMQX user and rules, and
sink_dispatcher, which publishes each sink's readings.

A sink's messages are published under `{namespace}-sinks/{sink_id}/{stream}/{mesh_id}/{node_id}`.
The prefix sits outside `{namespace}/#`, which the bridge subscribes to for sources,
so sinked JSON is never read back in as raw packets.
"""
from mesh_things.env import env_str
from common.sources import namespace

SCHEMA_VERSION = 1


def ref(sink_id) -> str:
    """How a sink is listed on mesh.sink_config.v1, beside `archive`."""
    return f"sink:{sink_id}"


def id_from_ref(value: str) -> str | None:
    prefix = "sink:"
    return value[len(prefix):] if value.startswith(prefix) else None


def topic_root() -> str:
    return f"{namespace()}-sinks"


def topic_filter(sink_id) -> str:
    """Everything one sink's consumer may subscribe to."""
    return f"{topic_root()}/{sink_id}/#"


def topic(sink_id, stream: str, mesh_id, node_id) -> str:
    return f"{topic_root()}/{sink_id}/{stream}/{mesh_id}/{node_id}"


def username(sink_id) -> str:
    """The EMQX user a sink's consumer connects as."""
    return f"{namespace()}-sink-{sink_id}"


def id_from_username(name: str) -> str | None:
    prefix = f"{namespace()}-sink-"
    return name[len(prefix):] if name.startswith(prefix) else None


def dispatcher_username() -> str:
    """The user sink_dispatcher publishes as; the bridge's unless one of its own is set."""
    return env_str("MQTT_SINKS__USER") or env_str("MQTT_BRIDGE__USER")


def dispatcher_password() -> str:
    return env_str("MQTT_SINKS__PASS") or env_str("MQTT_BRIDGE__PASS")
