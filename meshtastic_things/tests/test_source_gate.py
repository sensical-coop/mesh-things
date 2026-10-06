"""Source topics on the bridge, and the gate that keeps a gateway to the source its mesh is on."""
import json

import pytest

from bridge.mqtt_handler import MQTTHandler, subscription_filters
from common import sources

SOURCE = "5b1f3c1e-8a55-4a8e-9a0f-1d2b3c4d5e6f"
OTHER_SOURCE = "0e9d8c7b-6a59-4847-8362-5f4e3d2c1b0a"
REMOTE = "msh/EU_868/2/e/LongFast/!aabbccdd"


@pytest.fixture(autouse=True)
def _production_namespace(monkeypatch):
    monkeypatch.delenv("MQTT_CONNECTORS__NAMESPACE", raising=False)


class _Record:
    def __init__(self, event: dict):
        self.value = json.dumps(event).encode()


def _handler(**gateway_sources) -> MQTTHandler:
    handler = object.__new__(MQTTHandler)
    handler.gateway_sources = dict(gateway_sources)
    return handler


def test_a_bridged_topic_keeps_the_gateway_as_its_last_segment():
    topic = f"{sources.local_topic_prefix(SOURCE)}/{REMOTE}"

    assert topic.split("/")[-1] == "!aabbccdd"
    assert sources.source_id_from_topic(topic) == SOURCE


def test_the_own_topic_has_no_source():
    assert sources.source_id_from_topic(REMOTE) is None
    assert sources.source_id_from_topic(f"{sources.namespace()}/{SOURCE}") is None


def test_the_namespace_separates_dev_from_production(monkeypatch):
    monkeypatch.setenv("MQTT_CONNECTORS__NAMESPACE", "mt-sources-dev")

    assert sources.source_id_from_topic(f"mt-sources/{SOURCE}/{REMOTE}") is None
    assert sources.source_id_from_topic(f"mt-sources-dev/{SOURCE}/{REMOTE}") == SOURCE
    assert sources.source_id_from_resource_name(f"mt-sources-src-{SOURCE}") is None
    assert sources.source_id_from_resource_name(sources.resource_name(SOURCE)) == SOURCE


def test_a_channel_resource_name_still_names_its_source():
    name = sources.channel_resource_name(SOURCE, "LongFast")

    assert name.startswith(f"{sources.resource_name(SOURCE)}-")
    assert sources.source_id_from_resource_name(name) == SOURCE
    assert name != sources.channel_resource_name(SOURCE, "longfast")


def test_a_name_that_is_not_a_source_id_is_ignored():
    assert sources.source_id_from_resource_name(f"{sources.resource_name(SOURCE)}x") is None
    assert sources.source_id_from_resource_name("mt-sources-src-short") is None


def test_a_channel_is_subscribed_beneath_the_root():
    assert sources.channel_filter("msh/EU_868", "LongFast") == "msh/EU_868/2/e/LongFast/+"


@pytest.mark.parametrize("topic", ["#", "+/#", "+/x/#", "mt-sources/#", "mt-sources-sinks/a/#", "mt-sources-dev/s/#"])
def test_a_source_filter_reaching_republished_or_sinked_topics_is_reserved(topic):
    assert sources.reaches_reserved_topics(topic)


@pytest.mark.parametrize("topic", ["msh/#", "msh/EU_868/2/e/LongFast/#", "test/#", "+", "mt-sources"])
def test_an_ordinary_source_filter_is_not_reserved(topic):
    assert not sources.reaches_reserved_topics(topic)


def test_the_default_namespace_stays_reserved_on_a_dev_stack(monkeypatch):
    monkeypatch.setenv("MQTT_CONNECTORS__NAMESPACE", "dev-stack")
    assert sources.reaches_reserved_topics("dev-stack-sinks/x/#")
    assert sources.reaches_reserved_topics("mt-sources/#")


def test_the_bridge_subscribes_to_its_own_topic_and_the_sources():
    assert subscription_filters("msh/#") == ["msh/#", "mt-sources/#"]


@pytest.mark.parametrize("own_topic", ["#", "mt-sources/#", "+/+/#"])
def test_an_own_topic_overlapping_the_sources_is_refused(own_topic):
    with pytest.raises(ValueError):
        subscription_filters(own_topic)


def test_an_unregistered_gateway_is_not_ingested_either_way():
    handler = _handler()

    assert not handler.is_registered(REMOTE)
    assert not handler.accepts(REMOTE)
    assert not handler.accepts(f"{sources.local_topic_prefix(SOURCE)}/{REMOTE}")


def test_a_gateway_on_the_own_topic_is_refused_through_a_source():
    handler = _handler(**{"!aabbccdd": None})

    assert handler.accepts(REMOTE)
    assert not handler.accepts(f"{sources.local_topic_prefix(SOURCE)}/{REMOTE}")


def test_a_gateway_on_a_source_is_refused_on_the_own_topic_and_other_sources():
    handler = _handler(**{"!aabbccdd": SOURCE})

    assert handler.accepts(f"{sources.local_topic_prefix(SOURCE)}/{REMOTE}")
    assert not handler.accepts(REMOTE)
    assert not handler.accepts(f"{sources.local_topic_prefix(OTHER_SOURCE)}/{REMOTE}")


def test_gateway_sources_follow_upserts_and_tombstones():
    handler = _handler()

    handler._apply_gateway_record(_Record({"key": "!aabbccdd", "op": "upsert", "source_id": SOURCE}))
    assert handler.gateway_sources == {"!aabbccdd": SOURCE}

    handler._apply_gateway_record(_Record({"key": "!aabbccdd", "op": "upsert", "source_id": None}))
    assert handler.gateway_sources == {"!aabbccdd": None}

    handler._apply_gateway_record(_Record({"key": "!aabbccdd", "op": "delete"}))
    assert handler.gateway_sources == {}
