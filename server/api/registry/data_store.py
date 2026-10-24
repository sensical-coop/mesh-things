"""Deletes stored readings from InfluxDB and the Parquet archive.

Both are keyed by mesh: InfluxDB points carry a `mesh_id` tag, and the archive
is partitioned as `{prefix}/mesh_id=<id>/dt=<YYYY-MM-DD>/hour=<HH>/`.
"""
import re
from datetime import datetime, timezone

import structlog

from mesh_things.env import env_str

from common.alarm_counts import ALARM_COUNTS_BUCKET, ALARMS_BUCKET

log = structlog.get_logger()

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_PARTITION = re.compile(r"/dt=(\d{4}-\d{2}-\d{2})/hour=(\d{2})/")


def partition_start(key: str) -> datetime | None:
    """Start of the hour an archive object covers, or None if the key is not a partition."""
    match = _PARTITION.search(key)
    if not match:
        return None
    return datetime.strptime(f"{match.group(1)} {match.group(2)}", "%Y-%m-%d %H").replace(tzinfo=timezone.utc)


class DataStore:
    def __init__(self):
        self.influx_bucket = env_str("INFLUX__BUCKET")
        self.influx_org = env_str("INFLUX__ORG")
        self._influx_url = env_str("INFLUX__URL")
        self._influx_token = env_str("INFLUX__TOKEN")
        # Blank on a deployment without the archive (the lite profile).
        self.archive_bucket = env_str("S3_WRITER__BUCKET")
        self.archive_prefix = env_str("S3_WRITER__PREFIX", "telemetry").strip("/")
        self._influx = None
        self._s3 = None

    def _delete_api(self):
        if self._influx is None:
            from influxdb_client import InfluxDBClient

            self._influx = InfluxDBClient(url=self._influx_url, token=self._influx_token, org=self.influx_org)
        return self._influx.delete_api()

    def _s3_client(self):
        if self._s3 is None:
            import boto3

            self._s3 = boto3.client(
                "s3",
                endpoint_url=env_str("S3_WRITER__ENDPOINT_URL") or None,
                aws_access_key_id=env_str("S3_WRITER__ACCESS_KEY") or None,
                aws_secret_access_key=env_str("S3_WRITER__SECRET_KEY") or None,
                region_name=env_str("S3_WRITER__REGION") or None,
            )
        return self._s3

    def close(self) -> None:
        if self._influx is not None:
            self._influx.close()
            self._influx = None

    def delete_mesh_readings(self, mesh_id: str, until: datetime) -> None:
        """Delete a mesh's InfluxDB points and archive partitions up to `until`."""
        self._delete_influx(mesh_id, until)
        # An hour partition that straddles `until` is deleted whole: at most an hour of
        # later readings goes with it, rather than keeping earlier ones.
        self._delete_archive(mesh_id, lambda start: start < until)
        log.info("Deleted mesh readings", mesh_id=mesh_id, until=until.isoformat())

    def _delete_influx(self, mesh_id: str, until: datetime) -> None:
        # The predicate takes the mesh id verbatim, so only accept a plain id.
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", mesh_id):
            raise ValueError(f"Not a mesh id: {mesh_id!r}")
        for bucket in (self.influx_bucket, ALARMS_BUCKET, ALARM_COUNTS_BUCKET):
            self._delete_api().delete(
                start=EPOCH, stop=until, predicate=f'mesh_id="{mesh_id}"', bucket=bucket, org=self.influx_org
            )

    def _delete_archive(self, mesh_id: str, partition_is_due) -> None:
        if not self.archive_bucket:
            return
        s3 = self._s3_client()
        prefix = f"{self.archive_prefix}/mesh_id={mesh_id}/"
        due = []
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=self.archive_bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                start = partition_start(obj["Key"])
                if start is not None and partition_is_due(start):
                    due.append({"Key": obj["Key"]})
        # delete_objects takes at most 1000 keys per call.
        for i in range(0, len(due), 1000):
            s3.delete_objects(Bucket=self.archive_bucket, Delete={"Objects": due[i : i + 1000], "Quiet": True})


_store: DataStore | None = None


def get_data_store() -> DataStore:
    global _store
    if _store is None:
        _store = DataStore()
    return _store
