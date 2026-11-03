"""The bridge's side of gateway discovery: which topics are candidates and how they are paced."""
import base64
import json

import pytest

from bridge.discovery import IDLE_WINDOWS, DiscoveryPacer, candidate_event, parse_candidate
from bridge.mqtt_handler import MQTTHandler
from common import sources

SOURCE = "5b1f3c1e-8a55-4a8e-9a0f-1d2b3c4d5e6f"
REMOTE = "msh/EU_868/2/e/LongFast/!aabbccdd"


@pytest.fixture(autouse=True)
def _production_namespace(monkeypatch):
    monkeypatch.delenv("MQTT_CONNECTORS__NAMESPACE", raising=False)


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_own_and_bridged_topics_are_parsed():
    assert parse_candidate(REMOTE) == (None, "LongFast", "!aabbccdd")
    assert parse_candidate(f"{sources.local_topic_prefix(SOURCE)}/{REMOTE}") == (SOURCE, "LongFast", "!aabbccdd")


@pytest.mark.parametrize("topic", [
    "msh/EU_868/2/json/LongFast/!aabbccdd",
    "msh/EU_868/2/map/",
    "msh/EU_868/2/e/LongFast/aabbccdd",
    "health/ping",
])
def test_topics_without_an_envelope_are_not_candidates(topic):
    assert parse_candidate(topic) is None


def test_the_event_is_keyed_by_source_and_gateway():
    key, event = candidate_event(None, "LongFast", "!aabbccdd", b"\x01\x02")

    assert key == "own:!aabbccdd"
    assert event["channel_id"] == "LongFast"
    assert base64.b64decode(event["sample_b64"]) == b"\x01\x02"
    assert candidate_event(SOURCE, "LongFast", "!aabbccdd", b"")[0] == f"{SOURCE}:!aabbccdd"


def test_the_first_new_gateways_are_sent_at_once_and_later_ones_wait():
    clock = _Clock()
    pacer = DiscoveryPacer(immediate_gateways=2, delay_seconds=900, clock=clock)

    assert pacer.should_send("a")
    assert pacer.should_send("b")
    assert not pacer.should_send("c")
    assert not pacer.should_send("a")

    clock.now += 899
    assert not pacer.should_send("c")
    clock.now += 1
    assert pacer.should_send("c")


def test_the_budget_refills_as_the_window_rolls():
    clock = _Clock()
    pacer = DiscoveryPacer(immediate_gateways=1, delay_seconds=900, clock=clock)

    assert pacer.should_send("a")
    clock.now += 900
    assert pacer.should_send("b")


def test_a_gateway_is_retried_once_per_window():
    clock = _Clock()
    pacer = DiscoveryPacer(immediate_gateways=5, delay_seconds=900, clock=clock)

    assert pacer.should_send("a")
    clock.now += 600
    assert not pacer.should_send("a")
    clock.now += 300
    assert pacer.should_send("a")
    assert not pacer.should_send("a")


def test_a_gateway_quieter_than_the_window_is_still_sent_once_the_budget_is_spent():
    clock = _Clock()
    pacer = DiscoveryPacer(immediate_gateways=1, delay_seconds=900, clock=clock)
    pacer.should_send("busy")

    assert not pacer.should_send("quiet")
    clock.now += 1200
    pacer.should_send("busy")
    assert pacer.should_send("quiet")


def test_idle_gateways_are_forgotten():
    clock = _Clock()
    pacer = DiscoveryPacer(immediate_gateways=1, delay_seconds=900, clock=clock)
    pacer.should_send("a")

    clock.now += IDLE_WINDOWS * 900
    pacer.should_send("b")

    assert len(pacer) == 1


class _Producer:
    def __init__(self):
        self.sent = []

    def send(self, topic, key, value):
        self.sent.append((topic, key, json.loads(value)))


def _handler(**gateway_sources) -> MQTTHandler:
    handler = object.__new__(MQTTHandler)
    handler.gateway_sources = dict(gateway_sources)
    handler.kafka_producer = _Producer()
    handler.discovery_pacer = DiscoveryPacer(immediate_gateways=5, delay_seconds=900)
    handler.discovery_topic = "mesh.gateway_candidates.v1"
    handler.discovery_candidates_sent = 0
    return handler


def test_the_bridge_samples_unregistered_gateways_only():
    handler = _handler(**{"!11111111": None})

    handler.observe_candidate(REMOTE, b"raw")
    handler.observe_candidate("msh/EU_868/2/e/LongFast/!11111111", b"raw")

    assert [(t, k) for t, k, _ in handler.kafka_producer.sent] == [("mesh.gateway_candidates.v1", b"own:!aabbccdd")]
    assert handler.discovery_candidates_sent == 1
