"""Gateway config from mesh.keys.v1 and mesh.node_rejections.v1, for the non-Flink runtimes.

The twin of decode_job.py's broadcast state.
"""
import json
import time

import structlog
from kafka import KafkaConsumer, TopicPartition

log = structlog.get_logger()


def gateway_entry(event: dict) -> dict:
    """The state kept per gateway from one upsert on mesh.keys.v1."""
    return {
        "psk_b64": event.get("psk_b64", ""),
        "mesh_id": event.get("mesh_id"),
        "source_id": event.get("source_id"),
    }


def apply_config_event(gateway_state: dict, rejected_nodes: set, is_rejection: bool, value: bytes) -> None:
    """Apply one record from either config topic. A delete is a same-key tombstone."""
    event = json.loads(value)
    key = event.get("key")
    if not key:
        return
    if is_rejection:
        if event.get("op") == "delete":
            rejected_nodes.discard(key)
        else:
            rejected_nodes.add(key)
    elif event.get("op") == "delete":
        gateway_state.pop(key, None)
    else:
        gateway_state[key] = gateway_entry(event)


def replay_consumer(bootstrap_servers: str, topic: str) -> KafkaConsumer:
    """A consumer positioned at the start of every partition of a compacted topic.

    It has no group, so each process reads the whole topic rather than a share of it.
    """
    consumer = KafkaConsumer(bootstrap_servers=bootstrap_servers, group_id=None, enable_auto_commit=False)
    found = consumer.partitions_for_topic(topic)
    # Replaying nothing would leave a gate built on this state open, so fail and be restarted.
    if not found:
        raise RuntimeError(f"Topic {topic} has no partitions")
    partitions = [TopicPartition(topic, p) for p in sorted(found)]
    consumer.assign(partitions)
    consumer.seek_to_beginning(*partitions)
    return consumer


def replay_to_end(consumer: KafkaConsumer, on_record) -> int:
    """Poll until every assigned partition reaches the end it had when this was called.

    Returns the number of records read.
    """
    partitions = consumer.assignment()
    end = consumer.end_offsets(list(partitions))
    read = 0
    while True:
        for records in consumer.poll(timeout_ms=1000).values():
            for record in records:
                read += 1
                try:
                    on_record(record)
                except Exception as e:
                    log.exception("Bad config message skipped", exc_info=e)
        # kafka-python's position() blocks until a poll has resolved the seek to the beginning.
        if all(consumer.position(tp) >= end[tp] for tp in partitions):
            return read


class FellBehind(RuntimeError):
    """A replay consumer stopped keeping up with its topic."""


class CatchUpCheck:
    """Raises FellBehind when a replay consumer stops following its topic.

    Checked at most every `interval_s`. Staying behind the end, or failing to read it,
    for longer than `max_behind_s` raises, as does a position past the end, which means
    the topic was recreated. The process is then expected to exit and replay afresh.
    """

    def __init__(self, consumer: KafkaConsumer, interval_s: float = 30, max_behind_s: float = 120, clock=time.monotonic):
        self.consumer = consumer
        self.interval_s = interval_s
        self.max_behind_s = max_behind_s
        self._clock = clock
        self._last_check = clock()
        self._behind_since: float | None = None

    def check(self) -> None:
        now = self._clock()
        if now - self._last_check < self.interval_s:
            return
        self._last_check = now
        partitions = list(self.consumer.assignment())
        try:
            end = self.consumer.end_offsets(partitions)
            position = {tp: self.consumer.position(tp) for tp in partitions}
        except Exception as e:
            log.warning("Could not read the config topic's end", error=str(e))
        else:
            if any(position[tp] > end[tp] for tp in partitions):
                raise FellBehind(f"Position {position} is past the end {end}; the topic was recreated")
            if all(position[tp] >= end[tp] for tp in partitions):
                self._behind_since = None
                return
        if self._behind_since is None:
            self._behind_since = now
        elif now - self._behind_since > self.max_behind_s:
            raise FellBehind(f"Not caught up with the config topic for {now - self._behind_since:.0f}s")
