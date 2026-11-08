"""The bridge's front desk: what reaches Kafka from the shared gateway login."""
import json

import pytest

from bridge import front_desk
from bridge.discovery import DiscoveryPacer
from bridge.mqtt_handler import MQTTHandler
from common import sources
from mesh_things.protocols.v2_7 import mqtt_pb2

SOURCE = "5b1f3c1e-8a55-4a8e-9a0f-1d2b3c4d5e6f"
GATEWAY = "!aabbccdd"
TOPIC = f"msh/EU_868/2/e/LongFast/{GATEWAY}"
MAP_TOPIC = "msh/EU_868/2/map/"


@pytest.fixture(autouse=True)
def _production_namespace(monkeypatch):
    monkeypatch.delenv("MQTT_CONNECTORS__NAMESPACE", raising=False)


def _envelope(gateway_id: str = GATEWAY) -> bytes:
    envelope = mqtt_pb2.ServiceEnvelope(channel_id="LongFast", gateway_id=gateway_id)
    setattr(envelope.packet, "from", 0xAABBCCDD)
    envelope.packet.encrypted = b"\x01\x02"
    return envelope.SerializeToString()


class _Producer:
    def __init__(self):
        self.sent = []

    def send(self, topic, key, value):
        self.sent.append((topic, key, json.loads(value)))


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _handler(rate: float = 0, burst: int = 1, clock=None, **gateway_sources) -> MQTTHandler:
    handler = object.__new__(MQTTHandler)
    handler.gateway_sources = dict(gateway_sources)
    handler.gateway_rate = front_desk.GatewayRate(rate, burst, clock=clock or _Clock())
    handler.rate_limited_at = {}
    handler.kafka_producer = _Producer()
    handler.discovery_pacer = DiscoveryPacer(immediate_gateways=5, delay_seconds=900)
    handler.discovery_topic = "mesh.gateway_candidates.v1"
    handler.discovery_candidates_sent = 0
    return handler


@pytest.mark.parametrize(
    "topic, kind",
    [
        (TOPIC, front_desk.ENCRYPTED),
        (f"msh/EU_868/ES/2/e/LongFast/{GATEWAY}", front_desk.ENCRYPTED),
        (f"msh/EU_868/2/e/PKI/{GATEWAY}", front_desk.ENCRYPTED),
        (MAP_TOPIC, front_desk.MAP),
        ("msh/EU_868/2/map", front_desk.MAP),
        (f"msh/EU_868/2/json/LongFast/{GATEWAY}", None),
        (f"msh/EU_868/2/stat/{GATEWAY}", None),
        ("msh/EU_868/2/e/LongFast/", None),
    ],
)
def test_only_envelope_topics_are_recognised(topic, kind):
    assert front_desk.topic_kind(topic) == kind


def test_a_registered_gateway_passes_keyed_by_itself():
    assert _handler(**{GATEWAY: None}).admit(TOPIC, _envelope()) == (GATEWAY, None)


def test_an_unregistered_gateway_only_reaches_discovery():
    handler = _handler()

    assert handler.admit(TOPIC, _envelope()) == (GATEWAY, front_desk.UNREGISTERED)
    assert [(t, k) for t, k, _ in handler.kafka_producer.sent] == [("mesh.gateway_candidates.v1", b"own:!aabbccdd")]


def test_an_envelope_naming_another_gateway_is_refused():
    handler = _handler(**{GATEWAY: None, "!11111111": None})

    assert handler.admit(TOPIC, _envelope("!11111111")) == ("!11111111", front_desk.GATEWAY_MISMATCH)


def test_a_map_report_counts_for_the_gateway_its_envelope_names():
    assert _handler(**{GATEWAY: None}).admit(MAP_TOPIC, _envelope()) == (GATEWAY, None)


def test_an_unregistered_map_report_is_not_a_discovery_sample():
    handler = _handler()

    assert handler.admit(MAP_TOPIC, _envelope()) == (GATEWAY, front_desk.UNREGISTERED)
    assert handler.kafka_producer.sent == []


@pytest.mark.parametrize("topic", [f"msh/EU_868/2/json/LongFast/{GATEWAY}", f"msh/EU_868/2/stat/{GATEWAY}"])
def test_topics_without_an_envelope_are_refused(topic):
    assert _handler(**{GATEWAY: None}).admit(topic, b"{}") == (None, front_desk.NOT_ENVELOPE)


def test_garbage_on_an_envelope_topic_is_refused():
    assert _handler(**{GATEWAY: None}).admit(TOPIC, b"\xff\xff\xff") == (None, front_desk.UNPARSEABLE)


def test_a_registered_gateway_on_another_source_is_refused():
    handler = _handler(**{GATEWAY: SOURCE})

    assert handler.admit(TOPIC, _envelope()) == (GATEWAY, front_desk.WRONG_SOURCE)
    assert handler.admit(f"{sources.local_topic_prefix(SOURCE)}/{TOPIC}", _envelope()) == (GATEWAY, None)


def test_a_gateway_over_its_rate_is_dropped_until_it_slows_down():
    clock = _Clock()
    handler = _handler(rate=1, burst=2, clock=clock, **{GATEWAY: None})

    verdicts = [handler.admit(TOPIC, _envelope())[1] for _ in range(3)]
    assert verdicts == [None, None, front_desk.RATE_LIMITED]
    assert GATEWAY in handler.rate_limited_at

    clock.now += 1
    assert handler.admit(TOPIC, _envelope())[1] is None
    assert GATEWAY not in handler.rate_limited_at


def test_a_rate_of_zero_lets_everything_through():
    rate = front_desk.GatewayRate(0, 1)

    assert all(rate.allow(GATEWAY) for _ in range(1000))


def test_buckets_fill_back_only_up_to_the_burst():
    clock = _Clock()
    rate = front_desk.GatewayRate(1, 2, clock=clock)
    clock.now += 3600

    assert [rate.allow(GATEWAY) for _ in range(3)] == [True, True, False]
