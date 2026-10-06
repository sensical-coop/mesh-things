"""Naming shared by the registry, which creates EMQX bridges for sources, and the
MQTT bridge, which reads what they republish.

A source subscribes to `{root}/2/e/{channel}/+` once per channel its meshes use, and its
traffic is republished locally under `{namespace}/{source_id}/{remote topic}`, so the last
segment is still the gateway id the Kafka key is taken from. Sinks share the namespace
(common/sinks.py).
"""
import hashlib

from common.env import env_str

DEFAULT_NAMESPACE = "mt-sources"
UUID_LENGTH = 36


def namespace() -> str:
    """Prefixes every source and sink on the EMQX, separating a dev stack from production; the dev overlay sets it."""
    return env_str("MQTT_CONNECTORS__NAMESPACE", DEFAULT_NAMESPACE)


def local_topic_prefix(source_id: str) -> str:
    return f"{namespace()}/{source_id}"


def local_topic_filter() -> str:
    """The filter that matches every source's republished traffic."""
    return f"{namespace()}/#"


def resource_name(source_id: str) -> str:
    """The name of a source's EMQX connector, and the prefix of its per-channel resources."""
    return f"{namespace()}-src-{source_id}"


def channel_resource_name(source_id: str, channel: str) -> str:
    """The name of the EMQX source and rule of one channel. Hashed, since EMQX names allow fewer characters than channels."""
    return f"{resource_name(source_id)}-{hashlib.sha1(channel.encode()).hexdigest()[:12]}"


def channel_filter(root: str, channel: str) -> str:
    """The remote topic filter of one channel's encrypted feed."""
    return f"{root}/2/e/{channel}/+"


def source_id_from_resource_name(name: str) -> str | None:
    prefix = f"{namespace()}-src-"
    if not name.startswith(prefix):
        return None
    rest = name[len(prefix):]
    # A fixed-length UUID, followed by a channel suffix on per-channel resources.
    if len(rest) == UUID_LENGTH or (len(rest) > UUID_LENGTH and rest[UUID_LENGTH] == "-"):
        return rest[:UUID_LENGTH]
    return None


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
