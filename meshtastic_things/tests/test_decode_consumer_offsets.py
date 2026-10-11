"""Offset handling for the lite decode consumer."""
from unittest.mock import MagicMock, patch

from pipeline.decode_consumer import DecodeConsumer


class _Record:
    def __init__(self, offset, value=b"raw"):
        self.offset = offset
        self.value = value
        self.timestamp = 1_700_000_000_000


class _Partition:
    def __init__(self, partition=0):
        self.topic = "mesh.telemetry.raw.v1"
        self.partition = partition

def _make_consumer():
    consumer = object.__new__(DecodeConsumer)
    consumer.raw_consumer = MagicMock()
    consumer.gateway_state = {}
    consumer.rejected_nodes = set()
    return consumer

def _events(node_id: int) -> dict:
    return {"decoded": {"node_id": node_id}}

def test_clean_batch_commits_and_does_not_rewind():
    consumer = _make_consumer()
    consumer._publish = MagicMock()
    tp = _Partition()
    messages = {tp: [_Record(10), _Record(11), _Record(12)]}

    with patch("pipeline.decode_consumer.decode.decode_packet", side_effect=[_events(1), _events(2), _events(3)]):
        consumer.decode_batch(messages)

    assert consumer._publish.call_count == 3
    consumer.raw_consumer.commit.assert_called_once()
    consumer.raw_consumer.seek.assert_not_called()

def test_publish_failure_rewinds_to_the_failed_record_not_the_batch_start():
    consumer = _make_consumer()
    # Second record fails to publish.
    consumer._publish = MagicMock(side_effect=[None, Exception("kafka down"), None])
    tp = _Partition()
    messages = {tp: [_Record(10), _Record(11), _Record(12)]}

    with patch("pipeline.decode_consumer.decode.decode_packet", side_effect=[_events(1), _events(2), _events(3)]):
        consumer.decode_batch(messages)

    # Offset 10 was published already, so rewinding to 10 would duplicate it.
    consumer.raw_consumer.seek.assert_called_once_with(tp, 11)
    # Committing the rewound position is what makes the retry durable.
    consumer.raw_consumer.commit.assert_called_once()

def test_publish_failure_stops_reading_that_partition():
    consumer = _make_consumer()
    consumer._publish = MagicMock(side_effect=[None, Exception("kafka down"), None])
    tp = _Partition()
    messages = {tp: [_Record(10), _Record(11), _Record(12)]}

    with patch("pipeline.decode_consumer.decode.decode_packet", side_effect=[_events(1), _events(2), _events(3)]):
        consumer.decode_batch(messages)

    # Publishing 12 after 11 failed would put it on the topic ahead of 11, and
    # then republish it after the rewind.
    assert consumer._publish.call_count == 2

def test_an_undecodable_record_is_skipped_not_retried():
    consumer = _make_consumer()
    consumer._publish = MagicMock()
    tp = _Partition()
    messages = {tp: [_Record(10), _Record(11)]}

    with patch("pipeline.decode_consumer.decode.decode_packet", side_effect=[ValueError("bad protobuf"), _events(2)]):
        consumer.decode_batch(messages)

    assert consumer._publish.call_count == 1
    consumer.raw_consumer.commit.assert_called_once()
    consumer.raw_consumer.seek.assert_not_called()

def test_a_dropped_packet_still_commits():
    # decode_packet returns None for an unregistered gateway or a rejected node.
    consumer = _make_consumer()
    consumer._publish = MagicMock()
    tp = _Partition()
    messages = {tp: [_Record(10), _Record(11)]}

    with patch("pipeline.decode_consumer.decode.decode_packet", return_value=None):
        consumer.decode_batch(messages)

    consumer._publish.assert_not_called()
    consumer.raw_consumer.commit.assert_called_once()
    consumer.raw_consumer.seek.assert_not_called()

def test_only_the_failing_partition_is_rewound():
    consumer = _make_consumer()
    first, second = _Partition(0), _Partition(1)
    messages = {first: [_Record(10), _Record(11)], second: [_Record(40)]}

    def publish(events):
        if events["decoded"]["node_id"] == 2:
            raise Exception("kafka down")

    consumer._publish = MagicMock(side_effect=publish)

    with patch("pipeline.decode_consumer.decode.decode_packet", side_effect=[_events(1), _events(2), _events(3)]):
        consumer.decode_batch(messages)

    consumer.raw_consumer.seek.assert_called_once_with(first, 11)
    consumer.raw_consumer.commit.assert_called_once()
