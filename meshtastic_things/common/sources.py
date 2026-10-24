"""Naming shared by the registry, which creates EMQX bridges for sources, and the
MQTT bridge, which reads what they republish.

A source's traffic is republished locally under `{namespace}/{source_id}/{remote topic}`,
so the last segment is still the gateway id the Kafka key is taken from. Sinks share the
namespace (common/sinks.py).
"""
from mesh_things.env import env_str

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


def reaches_reserved_topics(topic_filter: str) -> bool:
    """Whether a source's filter could match what a stack republishes or sinks on its broker.

    Those topics all start with a namespace (`{namespace}/...` for sources,
    `{namespace}-sinks/...` for sinks), this instance's or the default one a production
    stack sharing the broker uses. Bridging them back in would republish each message
    under its own filter again, without end. Refused wherever the broker is, since an
    address or alias can name this instance's broker without looking like it.
    """
    levels = topic_filter.split("/")
    if levels[0] == "#":
        return True
    # Every reserved topic has at least two levels.
    if len(levels) == 1:
        return False
    return levels[0] == "+" or levels[0].startswith((namespace(), DEFAULT_NAMESPACE))
