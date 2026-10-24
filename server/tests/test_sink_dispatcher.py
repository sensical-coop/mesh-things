import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from kafka import TopicPartition
from paho.mqtt.client import topic_matches_sub

from mesh_things import streams as stream_names

from bridge.mqtt_handler import subscription_filters
from common import sinks
from pipeline.sink_dispatcher import SinkRouting, dispatch_batch

MESH = "11111111-2222-3333-4444-555555555555"
SINK_A = "aaaaaaaa-0000-0000-0000-000000000000"
SINK_B = "bbbbbbbb-0000-0000-0000-000000000000"
DECODED_TOPIC = "mesh.telemetry.decoded.v1"
STREAM_OF = {DECODED_TOPIC: stream_names.DECODED, "mesh.telemetry.derived.v1": stream_names.DERIVED, "mesh.telemetry.alarms.v1": stream_names.ALARMS}


@pytest.fixture(autouse=True)
def namespace(monkeypatch):
    monkeypatch.setenv("MQTT_CONNECTORS__NAMESPACE", "ns")


def routing(*events):
    r = SinkRouting()
    for event in events:
        r.apply(event)
    return r


def sink_event(sink_id, streams, op="upsert"):
    return {"kind": "sink", "key": f"sink:{sink_id}", "sink_id": sink_id, "streams": streams, "op": op}


def mesh_event(sinks_, op="upsert"):
    return {"kind": "mesh_sinks", "key": f"mesh:{MESH}", "mesh_id": MESH, "sinks": sinks_, "op": op}


def device_event(device_id, sinks_, op="upsert"):
    return {"kind": "device_sinks", "key": f"{MESH}:{device_id}", "mesh_id": MESH, "device_id": device_id, "sinks": sinks_, "op": op}


def test_a_mesh_sink_covers_every_node_of_the_mesh():
    r = routing(sink_event(SINK_A, ["decoded"]), mesh_event([f"sink:{SINK_A}"]))

    assert r.topics("decoded", {"mesh_id": MESH, "node_id": 7}) == [f"ns-sinks/{SINK_A}/decoded/{MESH}/7"]
    assert r.topics("decoded", {"mesh_id": MESH, "node_id": 8}) == [f"ns-sinks/{SINK_A}/decoded/{MESH}/8"]


def test_a_device_sink_covers_only_that_node_and_ignores_the_archive():
    r = routing(sink_event(SINK_A, ["decoded"]), device_event(7, ["archive", f"sink:{SINK_A}"]))

    assert r.topics("decoded", {"mesh_id": MESH, "node_id": 7}) == [f"ns-sinks/{SINK_A}/decoded/{MESH}/7"]
    assert r.topics("decoded", {"mesh_id": MESH, "node_id": 8}) == []


def test_a_sink_on_both_the_mesh_and_the_device_gets_one_message():
    r = routing(sink_event(SINK_A, ["decoded"]), mesh_event([f"sink:{SINK_A}"]), device_event(7, [f"sink:{SINK_A}"]))

    assert len(r.topics("decoded", {"mesh_id": MESH, "node_id": 7})) == 1


def test_only_the_streams_a_sink_chose_are_sent():
    r = routing(
        sink_event(SINK_A, ["decoded"]),
        sink_event(SINK_B, ["alarms"]),
        mesh_event([f"sink:{SINK_A}", f"sink:{SINK_B}"]),
    )

    assert r.topics("alarms", {"mesh_id": MESH, "device_id": 7}) == [f"ns-sinks/{SINK_B}/alarms/{MESH}/7"]
    assert r.topics("derived", {"mesh_id": MESH, "node_id": 7}) == []


def test_a_sink_without_its_own_record_sends_nothing():
    """Registry publishes the sink before attaching it, and removes it when paused."""
    r = routing(mesh_event([f"sink:{SINK_A}"]))

    assert r.topics("decoded", {"mesh_id": MESH, "node_id": 7}) == []


def test_deletes_remove_state():
    r = routing(sink_event(SINK_A, ["decoded"]), mesh_event([f"sink:{SINK_A}"]), device_event(7, [f"sink:{SINK_A}"]))
    r.apply(mesh_event([], op="delete"))
    r.apply(device_event(7, [], op="delete"))

    assert r.topics("decoded", {"mesh_id": MESH, "node_id": 7}) == []
    r.apply(sink_event(SINK_A, [], op="delete"))
    assert r.sink_streams == {}


def test_backfills_and_readings_without_a_mesh_are_not_sent():
    r = routing(sink_event(SINK_A, ["derived"]), mesh_event([f"sink:{SINK_A}"]))

    assert r.topics("derived", {"mesh_id": MESH, "node_id": 7, "backfill": True}) == []
    assert r.topics("derived", {"node_id": 7}) == []


def test_sink_topics_are_outside_what_the_bridge_reads():
    """Otherwise sinked JSON would come back in on the raw topic."""
    topic = sinks.topic(SINK_A, "decoded", MESH, 7)

    for bridge_filter in subscription_filters("msh/#"):
        assert not topic_matches_sub(bridge_filter, topic)
    assert topic_matches_sub(sinks.topic_filter(SINK_A), topic)


def _record(offset, value):
    return SimpleNamespace(offset=offset, value=json.dumps(value).encode())


def _batch(*values):
    tp = TopicPartition(DECODED_TOPIC, 0)
    return tp, {tp: [_record(i, v) for i, v in enumerate(values)]}


def test_each_reading_is_published_with_its_schema_version_then_committed():
    r = routing(sink_event(SINK_A, ["decoded"]), mesh_event([f"sink:{SINK_A}"]))
    consumer = MagicMock()
    published = []

    async def publish(topic, payload):
        published.append((topic, json.loads(payload)))

    _, messages = _batch({"mesh_id": MESH, "node_id": 7, "payload": {}}, {"mesh_id": "other", "node_id": 9})
    ok = asyncio.run(dispatch_batch(consumer, r, STREAM_OF, publish, messages))

    assert ok
    assert published == [(f"ns-sinks/{SINK_A}/decoded/{MESH}/7", {"mesh_id": MESH, "node_id": 7, "payload": {}, "schema": 1})]
    consumer.seek.assert_not_called()
    consumer.commit.assert_called_once()


def test_a_failed_publish_rewinds_to_that_record_and_stops_the_partition():
    r = routing(sink_event(SINK_A, ["decoded"]), mesh_event([f"sink:{SINK_A}"]))
    consumer = MagicMock()
    attempts = []

    async def publish(topic, payload):
        attempts.append(topic)
        if len(attempts) == 2:
            raise RuntimeError("broker gone")

    tp, messages = _batch(*({"mesh_id": MESH, "node_id": n} for n in (1, 2, 3)))
    ok = asyncio.run(dispatch_batch(consumer, r, STREAM_OF, publish, messages))

    assert not ok
    assert len(attempts) == 2
    consumer.seek.assert_called_once_with(tp, 1)
    consumer.commit.assert_called_once()


def test_an_unreadable_record_is_skipped():
    consumer = MagicMock()
    tp = TopicPartition(DECODED_TOPIC, 0)

    async def publish(topic, payload):
        raise AssertionError("nothing to publish")

    ok = asyncio.run(dispatch_batch(consumer, SinkRouting(), STREAM_OF, publish, {tp: [SimpleNamespace(offset=0, value=b"{")]}))

    assert ok
    consumer.commit.assert_called_once()
