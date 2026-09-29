"""Naming shared by the registry, which creates EMQX bridges for sources, and the
MQTT bridge, which reads what they republish.

A source's traffic is republished locally under `{namespace}/{source_id}/{remote topic}`,
so the last segment is still the gateway id the Kafka key is taken from. Sinks share the
namespace (common/sinks.py).
"""
from common.env import env_str

DEFAULT_NAMESPACE = "mt-sources"


def namespace() -> str:
    """Prefixes every source and sink on the EMQX, separating a dev stack from production; the dev overlay sets it."""
    return env_str("MQTT_CONNECTORS__NAMESPACE", DEFAULT_NAMESPACE)


def local_topic_prefix(source_id: str) -> str:
    return f"{namespace()}/{source_id}"


def local_topic_filter() -> str:
    """The filter that matches every source's republished traffic."""
    return f"{namespace()}/#"


def resource_name(source_id: str) -> str:
    """The name of a source's EMQX connector, source and rule."""
    return f"{namespace()}-src-{source_id}"


def source_id_from_resource_name(name: str) -> str | None:
    prefix = f"{namespace()}-src-"
    return name[len(prefix):] if name.startswith(prefix) else None


def source_id_from_topic(topic: str) -> str | None:
    """The source a message was bridged through, or None for the instance's own topic."""
    head, _, rest = topic.partition("/")
    if head != namespace() or not rest:
        return None
    source_id, _, remote = rest.partition("/")
    return source_id if remote else None
