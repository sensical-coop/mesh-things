"""Offset handling for the InfluxDB writer."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.healthcheck import HealthState
from writer.influx_writer import InfluxWriter


class _Record:
    def __init__(self, offset, value):
        self.offset = offset
        self.value = json.dumps(value).encode()
        self.key = None
        self.timestamp = 0


class _Partition:
    topic = "mesh.telemetry.decoded.v1"
    partition = 0


TOPIC_PARTITION = _Partition()

def _telemetry(node_id: int) -> dict:
    return {
        "node_id": node_id,
        "packet_id": node_id,
        "rx_time": 1757000000,
        "portnum": 67,
        "payload_kind": "telemetry:environment_metrics",
        "payload": {"environment_metrics": {"temperature": 21.5}},
    }

def _make_writer(monkeypatch):
    monkeypatch.setenv("INFLUX__TOKEN", "t")
    monkeypatch.setenv("INFLUX__ORG", "o")
    monkeypatch.setenv("INFLUX__BUCKET", "b")
    writer = object.__new__(InfluxWriter)
    writer.health_state = HealthState()
    writer.consumer_health = MagicMock()
    writer.influx_url = "http://influxdb:8086"
    writer.kafka_consumer = MagicMock()
    return writer

def _influx_client(write_side_effect=None):
    client = MagicMock()
    client.write_api.return_value.write = AsyncMock(side_effect=write_side_effect)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client

def test_successful_write_commits_and_does_not_rewind(monkeypatch):
    writer = _make_writer(monkeypatch)
    messages = {TOPIC_PARTITION: [_Record(10, _telemetry(1)), _Record(11, _telemetry(2))]}

    with patch("writer.influx_writer.InfluxDBClientAsync", return_value=_influx_client()):
        asyncio.run(writer.write_batch(messages))

    writer.kafka_consumer.commit.assert_called_once()
    writer.kafka_consumer.seek.assert_not_called()

def test_failed_write_rewinds_to_the_start_of_the_batch_and_does_not_commit(monkeypatch):
    writer = _make_writer(monkeypatch)
    messages = {TOPIC_PARTITION: [_Record(10, _telemetry(1)), _Record(11, _telemetry(2))]}
    client = _influx_client(write_side_effect=Exception("influx down"))

    with patch("writer.influx_writer.InfluxDBClientAsync", return_value=client):
        asyncio.run(writer.write_batch(messages))

    # Rewound to the first offset of the batch, not the last.
    writer.kafka_consumer.seek.assert_called_once_with(TOPIC_PARTITION, 10)
    writer.kafka_consumer.commit.assert_not_called()

def test_batch_with_nothing_to_persist_still_commits(monkeypatch):
    # device:portnum_1 is in SKIP_PAYLOAD_KINDS, so the batch yields no points.
    # Those offsets must still advance or the consumer replays them forever.
    writer = _make_writer(monkeypatch)
    skipped = {"node_id": 1, "packet_id": 1, "rx_time": 1757000000,
               "portnum": 1, "payload_kind": "device:portnum_1", "payload": {}}
    messages = {TOPIC_PARTITION: [_Record(10, skipped)]}

    with patch("writer.influx_writer.InfluxDBClientAsync") as client:
        asyncio.run(writer.write_batch(messages))
        client.assert_not_called()

    writer.kafka_consumer.commit.assert_called_once()
    writer.kafka_consumer.seek.assert_not_called()

def test_a_malformed_record_does_not_block_the_batch(monkeypatch):
    writer = _make_writer(monkeypatch)
    bad = _Record(10, _telemetry(1))
    bad.value = b"not json"
    messages = {TOPIC_PARTITION: [bad, _Record(11, _telemetry(2))]}

    with patch("writer.influx_writer.InfluxDBClientAsync", return_value=_influx_client()):
        asyncio.run(writer.write_batch(messages))

    # Unparseable records are skipped, not retried - only the good one is written.
    writer.kafka_consumer.commit.assert_called_once()
    writer.kafka_consumer.seek.assert_not_called()

def test_rewind_covers_every_partition_in_the_batch(monkeypatch):
    writer = _make_writer(monkeypatch)
    other = _Partition()
    messages = {
        TOPIC_PARTITION: [_Record(10, _telemetry(1)), _Record(11, _telemetry(2))],
        other: [_Record(40, _telemetry(3))],
    }
    client = _influx_client(write_side_effect=Exception("influx down"))

    with patch("writer.influx_writer.InfluxDBClientAsync", return_value=client):
        asyncio.run(writer.write_batch(messages))

    assert sorted(c.args[1] for c in writer.kafka_consumer.seek.call_args_list) == [10, 40]
    writer.kafka_consumer.commit.assert_not_called()
