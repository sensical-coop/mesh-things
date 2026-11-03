"""The gateway config shared by the lite decode consumer and the bridge."""
import json
from unittest.mock import MagicMock

from pipeline.config_state import apply_config_event, replay_to_end


def _value(**event) -> bytes:
    return json.dumps(event).encode()


def test_a_gateway_upsert_keeps_its_key_mesh_and_source():
    gateways = {}

    apply_config_event(
        gateways, set(), False, _value(key="!aabbccdd", op="upsert", psk_b64="AQ==", mesh_id="m", source_id="s")
    )

    assert gateways == {"!aabbccdd": {"psk_b64": "AQ==", "mesh_id": "m", "source_id": "s"}}


def test_an_upsert_from_before_sources_reads_as_the_own_topic():
    gateways = {}

    apply_config_event(gateways, set(), False, _value(key="!aabbccdd", op="upsert", psk_b64="AQ==", mesh_id="m"))

    assert gateways["!aabbccdd"]["source_id"] is None


def test_deletes_are_tombstones_on_both_topics():
    gateways, rejected = {"!aabbccdd": {}}, {"m:1"}

    apply_config_event(gateways, rejected, False, _value(key="!aabbccdd", op="delete"))
    apply_config_event(gateways, rejected, True, _value(key="m:1", op="delete"))

    assert gateways == {} and rejected == set()


def test_a_rejection_is_added_to_the_set():
    rejected = set()

    apply_config_event({}, rejected, True, _value(key="m:1", op="upsert"))

    assert rejected == {"m:1"}


class _FakeConsumer:
    """Two partitions, each holding records up to the offset in `end`."""

    def __init__(self, end: dict):
        self._end = end
        self._position = {tp: 0 for tp in end}

    def assignment(self):
        return set(self._end)

    def end_offsets(self, partitions):
        return dict(self._end)

    def position(self, tp):
        return self._position[tp]

    def poll(self, timeout_ms):
        batch = {}
        for tp, end in self._end.items():
            if self._position[tp] < end:
                batch[tp] = [MagicMock(value=_value(key=f"!{tp}{self._position[tp]}", op="upsert"))]
                self._position[tp] += 1
        return batch


def test_replay_reads_every_partition_to_its_end_before_returning():
    seen = []

    read = replay_to_end(_FakeConsumer({"a": 3, "b": 1}), seen.append)

    assert read == 4 and len(seen) == 4


def test_a_bad_record_does_not_stop_the_replay():
    def explode(record):
        raise ValueError("bad")

    assert replay_to_end(_FakeConsumer({"a": 2}), explode) == 2
