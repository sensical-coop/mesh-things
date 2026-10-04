"""Exports: a mesh's readings as one zip, built by a worker and fetched through a temporary link.

A job is a Redis hash, queued on one list and moved to a processing list while a worker
builds it, so a crash leaves it visible. A worker that finds a job whose heartbeat has
stopped fails it. The zip goes to `exports/<mesh_id>/<id>.zip` in the archive bucket,
uploaded part by part, and kept for EXPORT_TTL_S. The job outlives it for EXPORT_HISTORY_S,
shown as expired, so the owner can see what they asked for and ask again.
"""
import csv
import io
import json
import socket
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone

import redis
import structlog
from django.conf import settings

from common.channels import DERIVED_KIND, TELEMETRY, channel_name, namespace_of, payload_kind_of_measurement

from . import archive

log = structlog.get_logger()

CSV = "csv"
PARQUET = "parquet"
FORMATS = (CSV, PARQUET)

QUEUED = "queued"
RUNNING = "running"
READY = "ready"
FAILED = "failed"
EXPIRED = "expired"
ACTIVE = (QUEUED, RUNNING)

EXPORT_TTL_S = 24 * 3600
EXPORT_HISTORY_S = 30 * 24 * 3600
# A day of one mesh is one query or a few dozen objects; a job silent this long is dead.
HEARTBEAT_STALE_S = 600
# S3 needs every part but the last to be at least 5 MiB.
PART_SIZE = 8 * 1024 * 1024

_QUEUE = "exports:queue"
_PROCESSING = "exports:processing"
_INT_FIELDS = ("days_done", "days_total", "size")
_TIME_FIELDS = ("created_at", "started_at", "finished_at", "heartbeat_at", "expires_at")

_redis = None


class ExportLimitReached(Exception):
    """The owner already has a different export queued or running."""


class NothingToExport(Exception):
    """The range holds no data for the export."""


def store() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(settings.CACHES["default"]["LOCATION"], decode_responses=True)
    return _redis


def _job_key(job_id) -> str:
    return f"exports:job:{job_id}"


def _owner_key(owner_id) -> str:
    return f"exports:owner:{owner_id}"


def _active_key(owner_id) -> str:
    return f"exports:active:{owner_id}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def object_key(mesh_id, job_id) -> str:
    return f"exports/{mesh_id}/{job_id}.zip"


def filename(job: dict) -> str:
    """By the mesh's short id: readings may not read mesh labels."""
    start, stop = job["start"], job["stop"]
    days = f"{start:%Y-%m-%d}" if start == stop else f"{start:%Y-%m-%d}_{stop:%Y-%m-%d}"
    return f"mesh-{str(job['mesh_id'])[:8]}_{days}_{job['format']}.zip"


def days_between(start: date, stop: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((stop - start).days + 1)]


def _encode(fields: dict) -> dict:
    out = {}
    for name, value in fields.items():
        if value is None:
            out[name] = ""
        elif isinstance(value, (datetime, date)):
            out[name] = value.isoformat()
        elif isinstance(value, list):
            out[name] = json.dumps(value)
        else:
            out[name] = str(value)
    return out


def _decode(raw: dict) -> dict:
    job = {name: (value if value != "" else None) for name, value in raw.items()}
    for name in _INT_FIELDS:
        if job.get(name) is not None:
            job[name] = int(job[name])
    for name in _TIME_FIELDS:
        if job.get(name) is not None:
            job[name] = datetime.fromisoformat(job[name])
    job["start"] = date.fromisoformat(job["start"])
    job["stop"] = date.fromisoformat(job["stop"])
    job["node_ids"] = json.loads(job["node_ids"]) if job.get("node_ids") else None
    return job


def get(job_id) -> dict | None:
    """The job, `expired` once a ready export's file is gone."""
    raw = store().hgetall(_job_key(job_id))
    if not raw:
        return None
    job = _decode(raw)
    if job["status"] == READY and job["expires_at"] <= _now():
        job["status"] = EXPIRED
    return job


def _update(job_id, **fields) -> None:
    store().hset(_job_key(job_id), mapping=_encode(fields))


def _same_request(job: dict, mesh_id, fmt, start, stop, node_ids) -> bool:
    return (job["mesh_id"], job["format"], job["start"], job["stop"], job["node_ids"]) == (
        str(mesh_id), fmt, start, stop, sorted(node_ids) if node_ids else None
    )


def create(owner_id, mesh_id, fmt: str, start: date, stop: date, node_ids: list[int] | None = None) -> tuple[dict, bool]:
    """Queue an export, or return the identical one the owner already has queued or running.

    Returns:
        The job, and whether it was created.

    Raises:
        ExportLimitReached: If the owner has a different export queued or running.
    """
    r = store()
    active_id = r.get(_active_key(owner_id))
    if active_id:
        active = get(active_id)
        if active and active["status"] in ACTIVE:
            if _same_request(active, mesh_id, fmt, start, stop, node_ids):
                return active, False
            raise ExportLimitReached
        r.delete(_active_key(owner_id))

    job_id = str(uuid.uuid4())
    if not r.set(_active_key(owner_id), job_id, nx=True, ex=EXPORT_TTL_S):
        raise ExportLimitReached
    now = _now()
    job = {
        "id": job_id,
        "owner_id": str(owner_id),
        "mesh_id": str(mesh_id),
        "format": fmt,
        "start": start,
        "stop": stop,
        "node_ids": sorted(node_ids) if node_ids else None,
        "status": QUEUED,
        "days_done": 0,
        "days_total": len(days_between(start, stop)),
        "size": None,
        "error": None,
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "heartbeat_at": None,
        "expires_at": now + timedelta(seconds=EXPORT_TTL_S),
    }
    pipe = r.pipeline()
    pipe.hset(_job_key(job_id), mapping=_encode(job))
    pipe.expire(_job_key(job_id), EXPORT_HISTORY_S)
    pipe.zadd(_owner_key(owner_id), {job_id: now.timestamp()})
    pipe.expire(_owner_key(owner_id), EXPORT_HISTORY_S)
    pipe.lpush(_QUEUE, job_id)
    pipe.execute()
    log.info("export_queued", job_id=job_id, owner_id=str(owner_id), mesh_id=str(mesh_id), format=fmt)
    return get(job_id), True


def list_for(owner_id, mesh_id=None) -> list[dict]:
    """The owner's exports of the last EXPORT_HISTORY_S, newest first, of one mesh or all."""
    r = store()
    r.zremrangebyscore(_owner_key(owner_id), "-inf", (_now() - timedelta(seconds=EXPORT_HISTORY_S)).timestamp())
    jobs = [get(job_id) for job_id in r.zrevrange(_owner_key(owner_id), 0, -1)]
    return [job for job in jobs if job and (mesh_id is None or job["mesh_id"] == str(mesh_id))]


def download_url(job: dict) -> str | None:
    """A link to a ready export, valid until the file expires."""
    if job["status"] != READY:
        return None
    seconds = int((job["expires_at"] - _now()).total_seconds())
    if seconds <= 0:
        return None
    return archive.presigned_url(object_key(job["mesh_id"], job["id"]), expires_in=seconds, filename=filename(job))


def _release(job: dict) -> None:
    """Let the owner request another export, and take the job off the processing list."""
    r = store()
    active = _active_key(job["owner_id"])
    if r.get(active) == job["id"]:
        r.delete(active)
    r.lrem(_PROCESSING, 0, job["id"])


def finish(job: dict, size: int) -> dict:
    now = _now()
    expires_at = now + timedelta(seconds=EXPORT_TTL_S)
    _update(job["id"], status=READY, size=size, days_done=job["days_total"], finished_at=now, expires_at=expires_at)
    store().expire(_job_key(job["id"]), EXPORT_HISTORY_S)
    _release(job)
    return get(job["id"])


def fail(job: dict, error: str) -> dict:
    _update(job["id"], status=FAILED, error=error, finished_at=_now())
    _release(job)
    return get(job["id"])


def take(timeout: int = 5) -> dict | None:
    """Move the next queued job to the processing list and mark it running."""
    r = store()
    job_id = r.blmove(_QUEUE, _PROCESSING, timeout, "RIGHT", "LEFT")
    if not job_id:
        return None
    job = get(job_id)
    if not job:
        r.lrem(_PROCESSING, 0, job_id)
        return None
    now = _now()
    _update(job_id, status=RUNNING, started_at=now, heartbeat_at=now, worker=socket.gethostname())
    return get(job_id)


def heartbeat(job: dict, days_done: int) -> None:
    _update(job["id"], days_done=days_done, heartbeat_at=_now())


def stalled() -> list[dict]:
    """Jobs on the processing list whose worker stopped, claimed so that one worker fails each."""
    r = store()
    found = []
    for job_id in r.lrange(_PROCESSING, 0, -1):
        job = get(job_id)
        if not job:
            r.lrem(_PROCESSING, 0, job_id)
            continue
        if job["status"] not in ACTIVE:
            _release(job)
            continue
        last = job["heartbeat_at"] or job["created_at"]
        if (_now() - last).total_seconds() < HEARTBEAT_STALE_S:
            continue
        if r.set(f"exports:recovering:{job_id}", "1", nx=True, ex=HEARTBEAT_STALE_S):
            found.append(job)
    return found


class MultipartUpload:
    """A write-only file that uploads to S3 in parts as it fills. Not seekable, so
    zipfile writes data descriptors instead of going back to fix up headers."""

    def __init__(self, client, bucket: str, key: str):
        self._client, self._bucket, self._key = client, bucket, key
        self._upload_id = client.create_multipart_upload(Bucket=bucket, Key=key, ContentType="application/zip")["UploadId"]
        self._buffer = bytearray()
        self._parts: list[dict] = []
        self.size = 0

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def write(self, data) -> int:
        self._buffer += data
        while len(self._buffer) >= PART_SIZE:
            self._send(bytes(self._buffer[:PART_SIZE]))
            del self._buffer[:PART_SIZE]
        return len(data)

    def flush(self) -> None:
        pass

    def _send(self, data: bytes) -> None:
        number = len(self._parts) + 1
        response = self._client.upload_part(
            Bucket=self._bucket, Key=self._key, UploadId=self._upload_id, PartNumber=number, Body=data
        )
        self._parts.append({"ETag": response["ETag"], "PartNumber": number})
        self.size += len(data)

    def complete(self) -> int:
        if self._buffer or not self._parts:
            self._send(bytes(self._buffer))
            self._buffer.clear()
        self._client.complete_multipart_upload(
            Bucket=self._bucket, Key=self._key, UploadId=self._upload_id, MultipartUpload={"Parts": self._parts}
        )
        return self.size

    def abort(self) -> None:
        self._client.abort_multipart_upload(Bucket=self._bucket, Key=self._key, UploadId=self._upload_id)


def _writer_client():
    return archive._client(
        "s3", settings.ARCHIVE_ENDPOINT_URL, settings.EXPORT_ACCESS_KEY, settings.EXPORT_SECRET_KEY
    )


def _csv_bytes(columns: list[str], rows: list[dict]) -> bytes:
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return text.getvalue().encode()


def channels_csv(channels: set[str], catalog: dict[str, dict]) -> bytes:
    """Each exported channel as the measurement catalog describes it.

    `telemetry_variant` is blank for channels a sensor did not measure, and `derived`
    marks the outputs of postprocessing.
    """
    columns = ["channel", "name", "unit", "description", "telemetry_variant", "derived", "quantity_kind", "vocabulary_uri"]
    rows = []
    for channel in sorted(channels):
        row = catalog.get(channel) or {}
        payload_kind = row.get("payload_kind") or payload_kind_of_measurement(channel.split(".", 1)[0])
        rows.append(
            {
                "channel": channel,
                "name": row.get("field_name") or channel.split(".", 1)[1],
                "unit": row.get("unit"),
                "description": row.get("description"),
                "telemetry_variant": payload_kind if namespace_of(payload_kind) == TELEMETRY else None,
                "derived": "true" if payload_kind == DERIVED_KIND else "false",
                "quantity_kind": row.get("quantity_kind"),
                "vocabulary_uri": row.get("vocabulary_uri"),
            }
        )
    return _csv_bytes(columns, rows)


def write_csv(job: dict, out, influx, catalog: dict[str, dict], progress) -> None:
    """A CSV per measurement and day, `YYYY-MM-DD/<measurement>.csv`, plus `channels.csv`."""
    channels: set[str] = set()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for done, day in enumerate(days_between(job["start"], job["stop"]), start=1):
            for measurement, table in sorted(influx.day_rows(job["mesh_id"], day, job["node_ids"]).items()):
                columns = ["time", "node_id", *table["tags"], *table["fields"]]
                zf.writestr(f"{day:%Y-%m-%d}/{measurement}.csv", _csv_bytes(columns, table["rows"]))
                payload_kind = payload_kind_of_measurement(measurement)
                channels.update(channel_name(payload_kind, field) for field in table["fields"])
            progress(done)
        if not channels:
            raise NothingToExport("No readings in that range")
        zf.writestr("channels.csv", channels_csv(channels, catalog))


def write_parquet(job: dict, out, progress) -> None:
    """The archive's hourly Parquet files, `YYYY-MM-DD/YYYY-MM-DD_HH.parquet`."""
    partitions = archive.list_partitions(job["mesh_id"], job["start"], job["stop"])
    if not partitions:
        raise NothingToExport("Nothing archived in that range")
    archive.zip_partitions(
        job["mesh_id"], partitions, out, progress=lambda p: progress((p["dt"] - job["start"]).days + 1)
    )


def build(job: dict, influx=None, catalog=None) -> int:
    """Build the job's zip into the bucket, returning its size in bytes."""
    upload = MultipartUpload(_writer_client(), settings.ARCHIVE_BUCKET, object_key(job["mesh_id"], job["id"]))
    progress = lambda days_done: heartbeat(job, days_done)  # noqa: E731
    try:
        if job["format"] == CSV:
            write_csv(job, upload, influx, catalog, progress)
        else:
            write_parquet(job, upload, progress)
    except BaseException:
        upload.abort()
        raise
    return upload.complete()
