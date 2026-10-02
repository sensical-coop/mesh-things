import io
from unittest.mock import MagicMock

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from botocore.exceptions import ClientError

import json
from types import SimpleNamespace

from writer.s3_writer import PARTITION_FILENAME, S3Writer, _flatten


class _FakeS3:
    """In-memory FakeS3"""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.put_count = 0
        self.fail_get_with: Exception | None = None

    def get_object(self, Bucket, Key):
        if self.fail_get_with is not None:
            raise self.fail_get_with
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, Bucket, Key, Body):
        self.objects[Key] = Body
        self.put_count += 1

    def rows(self, key) -> list[dict]:
        return pq.read_table(pa.BufferReader(self.objects[key])).to_pylist()

def _make_s3_writer():
    writer = object.__new__(S3Writer)
    writer.s3_client = _FakeS3()
    writer.s3_bucket = "bucket"
    writer.s3_prefix = "telemetry"
    writer.archived = set()
    return writer

def _record(node_id, mesh_id=None, packet_id=1, rx_time=1757000000):
    event = {"node_id": node_id, "packet_id": packet_id, "rx_time": rx_time,
             "portnum": 67, "payload_kind": "telemetry:environment_metrics", "payload": {}}
    if mesh_id:
        event["mesh_id"] = mesh_id
    return event


MESH_A = "11111111-2222-3333-4444-555555555555"
MESH_B = "99999999-8888-7777-6666-555544443333"

def test_flatten_omits_mesh_id_because_it_is_the_partition_key():
    row = _flatten({"node_id": 123, "mesh_id": MESH_A, "payload": {}})

    assert "mesh_id" not in row
    assert row["node_id"] == 123

def test_flush_writes_one_object_per_mesh_regardless_of_device_count():
    writer = _make_s3_writer()
    records = [
        _record(1, MESH_A),
        _record(2, MESH_A),  # different device, same mesh
        _record(1, MESH_B),
    ]

    writer.flush(records)

    keys = writer.s3_client.objects
    assert len(keys) == 2
    assert any(f"mesh_id={MESH_A}/dt=" in k for k in keys)
    assert any(f"mesh_id={MESH_B}/dt=" in k for k in keys)
    assert not any("node_id=" in k for k in keys)

def test_the_partition_is_mesh_date_and_hour():
    writer = _make_s3_writer()

    writer.flush([_record(1, MESH_A)])

    key = next(iter(writer.s3_client.objects))
    assert key.startswith(f"telemetry/mesh_id={MESH_A}/dt=")
    assert key.endswith(PARTITION_FILENAME)


def _sink_record(key, sinks, op="upsert"):
    return SimpleNamespace(value=json.dumps({"key": key, "sinks": sinks, "op": op}).encode())


def test_only_devices_that_opted_in_are_archived():
    writer = _make_s3_writer()
    writer._apply_sink_record(_sink_record(f"{MESH_A}:1", ["archive"]))

    assert writer.archives(_record(1, MESH_A))
    assert not writer.archives(_record(2, MESH_A))
    # The same node number on another mesh is another device.
    assert not writer.archives(_record(1, MESH_B))


def test_readings_without_a_mesh_are_never_archived():
    writer = _make_s3_writer()
    writer._apply_sink_record(_sink_record(f"{MESH_A}:1", ["archive"]))

    assert not writer.archives(_record(1))


def test_a_tombstone_or_another_sink_stops_archiving():
    writer = _make_s3_writer()
    key = f"{MESH_A}:1"
    for update in (_sink_record(key, [], op="delete"), _sink_record(key, ["sink:other"])):
        writer._apply_sink_record(_sink_record(key, ["archive"]))
        writer._apply_sink_record(update)

        assert not writer.archives(_record(1, MESH_A))


def test_derived_rows_follow_their_device():
    writer = _make_s3_writer()
    writer._apply_sink_record(_sink_record(f"{MESH_A}:1", ["archive"]))

    assert writer.archives(_derived_record("pp-1"))

def test_flush_is_a_noop_for_empty_records():
    writer = _make_s3_writer()

    writer.flush([])

    assert writer.s3_client.put_count == 0

def test_a_second_flush_rolls_into_the_same_object():
    writer = _make_s3_writer()

    writer.flush([_record(1, MESH_A, packet_id=1)])
    writer.flush([_record(2, MESH_A, packet_id=2)])   # a different device, same mesh

    assert len(writer.s3_client.objects) == 1
    key = next(iter(writer.s3_client.objects))
    assert sorted(r["packet_id"] for r in writer.s3_client.rows(key)) == [1, 2]

def test_replaying_the_same_records_does_not_duplicate_rows():
    writer = _make_s3_writer()
    records = [_record(1, MESH_A, packet_id=1), _record(1, MESH_A, packet_id=2)]

    writer.flush(records)
    writer.flush(records)

    key = next(iter(writer.s3_client.objects))
    assert sorted(r["packet_id"] for r in writer.s3_client.rows(key)) == [1, 2]

def test_an_unreadable_partition_is_not_overwritten():
    writer = _make_s3_writer()
    writer.flush([_record(1, MESH_A, packet_id=1)])
    before = dict(writer.s3_client.objects)
    writer.s3_client.fail_get_with = ClientError({"Error": {"Code": "InternalError"}}, "GetObject")

    with pytest.raises(ClientError):
        writer.flush([_record(1, MESH_A, packet_id=2)])

    assert writer.s3_client.objects == before

def test_rewind_seeks_every_partition_back_to_its_commit():
    # poll() has already advanced the fetch position and a failed flush has to
    # seek back or the buffered records are never redelivered.
    writer = _make_s3_writer()
    first, second = object(), object()
    writer.kafka_consumer = MagicMock()
    writer.kafka_consumer.assignment.return_value = [first, second]
    writer.kafka_consumer.committed.side_effect = lambda tp: 10 if tp is first else 40

    writer._rewind_to_committed()

    assert sorted(c.args[1] for c in writer.kafka_consumer.seek.call_args_list) == [10, 40]

def test_rewind_starts_from_the_beginning_when_nothing_is_committed():
    writer = _make_s3_writer()
    partition = object()
    writer.kafka_consumer = MagicMock()
    writer.kafka_consumer.assignment.return_value = [partition]
    writer.kafka_consumer.committed.return_value = None

    writer._rewind_to_committed()

    writer.kafka_consumer.seek_to_beginning.assert_called_once_with(partition)
    writer.kafka_consumer.seek.assert_not_called()

def test_rows_keep_a_declared_schema_across_flushes():
    # An all-null column in one batch must not get a different type from the next.
    writer = _make_s3_writer()

    writer.flush([_record(1, MESH_A, packet_id=1)])          # no gateway_id
    writer.flush([{**_record(1, MESH_A, packet_id=2), "gateway_id": 431637602}])

    key = next(iter(writer.s3_client.objects))
    schema = pq.read_table(pa.BufferReader(writer.s3_client.objects[key])).schema
    assert schema.field("gateway_id").type == pa.int64()
    assert schema.field("node_id").type == pa.int64()

def _materialise(writer, root):
    """Write the fake bucket out as a directory tree, the way a reader sees it."""
    for key, body in writer.s3_client.objects.items():
        path = root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    return root / writer.s3_prefix

def test_archive_reads_back_through_pyarrow_and_pandas(tmp_path):
    """The layout has to survive a plain read."""
    import pandas as pd
    import pyarrow.dataset as ds

    writer = _make_s3_writer()
    writer.flush([_record(1, MESH_A, packet_id=1), _record(2, MESH_A, packet_id=2)])
    writer.flush([_record(1, MESH_B, packet_id=3)])
    root = _materialise(writer, tmp_path)

    table = ds.dataset(root, format="parquet", partitioning="hive").to_table()
    assert sorted(table.column("node_id").to_pylist()) == [1, 1, 2]
    # mesh_id comes back from the path
    assert set(table.column("mesh_id").to_pylist()) == {MESH_A, MESH_B}

    one_device = pd.read_parquet(root, filters=[("node_id", "==", 1)])
    assert sorted(one_device["packet_id"]) == [1, 3]


def _derived_record(postprocessing_id, rx_time=1757000000):
    return {"node_id": 1, "mesh_id": MESH_A, "rx_time": rx_time, "payload_kind": "computed:derived",
            "payload": {"derived": {"x": 1.0}}, "postprocessing_id": postprocessing_id}


def test_derived_rows_of_two_postprocessings_at_the_same_time_are_both_kept():
    # Neither has a packet_id, so the postprocessing is what tells them apart.
    writer = _make_s3_writer()

    writer.flush([_derived_record("pp-1"), _derived_record("pp-2")])

    key = next(iter(writer.s3_client.objects))
    assert sorted(r["postprocessing_id"] for r in writer.s3_client.rows(key)) == ["pp-1", "pp-2"]


def test_decoded_rows_have_no_postprocessing_id():
    assert _flatten(_record(1, MESH_A))["postprocessing_id"] is None
