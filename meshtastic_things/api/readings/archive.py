"""The Parquet archive: a mesh's partitions, credentials scoped to it, and presigned downloads.

Works against the bundled MinIO or an external S3. The archive is laid out as
`{prefix}/mesh_id=<id>/dt=<YYYY-MM-DD>/hour=<HH>/data.parquet`, so a mesh is one
key prefix and a credential can be limited to it.
"""
import io
import json
import re
import zipfile
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timezone

from django.conf import settings

PARTITION_FILENAME = "data.parquet"
STS_MINIO = "minio"
STS_AWS = "aws"
# boto3 needs a region to sign; MinIO accepts its default.
_DEFAULT_REGION = "us-east-1"
_PARTITION = re.compile(r"/dt=(\d{4}-\d{2}-\d{2})/hour=(\d{2})/" + re.escape(PARTITION_FILENAME) + "$")

# Parallel object reads while zipping: S3 answers each GET in tens of milliseconds, and
# the whole zip has to stream well inside a gunicorn worker's timeout.
ZIP_READERS = 8

_clients: dict = {}


def is_enabled() -> bool:
    """Whether this instance runs the archive (not on the lite profile)."""
    return bool(settings.ARCHIVE_BUCKET)


def issues_credentials() -> bool:
    """Whether the storage provider offers STS, so credentials can be handed out."""
    return is_enabled() and bool(settings.ARCHIVE_STS)


def region() -> str:
    return settings.ARCHIVE_REGION or _DEFAULT_REGION


def mesh_prefix(mesh_id) -> str:
    return f"{settings.ARCHIVE_PREFIX}/mesh_id={mesh_id}/"


def partition_key(mesh_id, day: date, hour: int) -> str:
    return f"{mesh_prefix(mesh_id)}dt={day:%Y-%m-%d}/hour={hour:02d}/{PARTITION_FILENAME}"


def _client(service: str, endpoint_url: str):
    key = (service, endpoint_url)
    if key not in _clients:
        import boto3
        from botocore.config import Config

        _clients[key] = boto3.client(
            service,
            endpoint_url=endpoint_url or None,
            aws_access_key_id=settings.ARCHIVE_ACCESS_KEY or None,
            aws_secret_access_key=settings.ARCHIVE_SECRET_KEY or None,
            region_name=region(),
            # Path-style, so a self-hosted endpoint needs no wildcard DNS.
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
    return _clients[key]


def list_partitions(mesh_id, start: date | None = None, stop: date | None = None) -> list[dict]:
    """Every current-layout partition of the mesh within [start, stop], oldest first."""
    s3 = _client("s3", settings.ARCHIVE_ENDPOINT_URL)
    partitions = []
    pages = s3.get_paginator("list_objects_v2").paginate(Bucket=settings.ARCHIVE_BUCKET, Prefix=mesh_prefix(mesh_id))
    for page in pages:
        for obj in page.get("Contents", []):
            match = _PARTITION.search(obj["Key"])
            if not match:
                continue
            day = date.fromisoformat(match.group(1))
            if (start and day < start) or (stop and day > stop):
                continue
            partitions.append(
                {
                    "dt": day,
                    "hour": int(match.group(2)),
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"],
                }
            )
    return sorted(partitions, key=lambda p: (p["dt"], p["hour"]))


def session_policy(mesh_id) -> dict:
    """Read-only on one mesh's prefix. Listing is allowed only under that prefix, so
    other meshes' key names stay hidden."""
    prefix = mesh_prefix(mesh_id)
    bucket = settings.ARCHIVE_BUCKET
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:GetObject"],
                # The bare prefix too: pyarrow probes it as an object before listing it as a directory.
                "Resource": [f"arn:aws:s3:::{bucket}/{prefix}*", f"arn:aws:s3:::{bucket}/{prefix.rstrip('/')}"],
            },
            {
                "Effect": "Allow",
                "Action": ["s3:ListBucket"],
                "Resource": [f"arn:aws:s3:::{bucket}"],
                "Condition": {"StringLike": {"s3:prefix": [prefix, f"{prefix}*"]}},
            },
        ],
    }


def assume_role_args(mesh_id, session_name: str) -> dict:
    args = {
        "RoleSessionName": session_name,
        "Policy": json.dumps(session_policy(mesh_id)),
        "DurationSeconds": settings.ARCHIVE_CREDENTIAL_TTL_S,
    }
    if settings.ARCHIVE_STS == STS_AWS:
        args["RoleArn"] = settings.ARCHIVE_ROLE_ARN
    else:
        # MinIO requires the argument but assumes the calling user's own policy.
        args["RoleArn"] = "arn:minio:iam:::role/archive-reader"
    return args


def issue_credentials(mesh_id, session_name: str) -> dict:
    """Temporary credentials that can read one mesh's archive and nothing else."""
    endpoint = settings.ARCHIVE_ENDPOINT_URL if settings.ARCHIVE_STS == STS_MINIO else ""
    response = _client("sts", endpoint).assume_role(**assume_role_args(mesh_id, session_name))
    credentials = response["Credentials"]
    expires_at = credentials["Expiration"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return {
        "access_key_id": credentials["AccessKeyId"],
        "secret_access_key": credentials["SecretAccessKey"],
        "session_token": credentials["SessionToken"],
        "expires_at": expires_at,
        "endpoint": settings.ARCHIVE_PUBLIC_ENDPOINT_URL or None,
        "region": region(),
        "bucket": settings.ARCHIVE_BUCKET,
        "prefix": mesh_prefix(mesh_id),
        "s3_path": f"s3://{settings.ARCHIVE_BUCKET}/{mesh_prefix(mesh_id)}",
    }


def object_exists(key: str) -> bool:
    from botocore.exceptions import ClientError

    try:
        _client("s3", settings.ARCHIVE_ENDPOINT_URL).head_object(Bucket=settings.ARCHIVE_BUCKET, Key=key)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise
    return True


def presigned_url(key: str) -> str:
    """A download link for one object, signed for the endpoint callers reach."""
    return _client("s3", settings.ARCHIVE_PUBLIC_ENDPOINT_URL).generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.ARCHIVE_BUCKET, "Key": key},
        ExpiresIn=settings.ARCHIVE_CREDENTIAL_TTL_S,
    )


def read_object(key: str) -> bytes:
    return _client("s3", settings.ARCHIVE_ENDPOINT_URL).get_object(Bucket=settings.ARCHIVE_BUCKET, Key=key)["Body"].read()


def zip_entry_name(day: date, hour: int) -> str:
    """One folder per day, and a name that says which hour, unlike the stored data.parquet."""
    return f"{day:%Y-%m-%d}/{day:%Y-%m-%d}_{hour:02d}.parquet"


class _Sink(io.RawIOBase):
    """Where zipfile writes; drained after every entry so the zip streams. Not seekable,
    so zipfile writes data descriptors instead of going back to fix up headers."""

    def __init__(self):
        self._chunks: list[bytes] = []

    def writable(self) -> bool:
        return True

    def write(self, data) -> int:
        self._chunks.append(bytes(data))
        return len(data)

    def drain(self) -> bytes:
        out = b"".join(self._chunks)
        self._chunks.clear()
        return out


def _read_in_order(keys: list[str]):
    """Yield each object in order, keeping at most ZIP_READERS reads ahead of the consumer."""
    with ThreadPoolExecutor(max_workers=ZIP_READERS) as pool:
        pending = deque()
        for key in keys:
            pending.append(pool.submit(read_object, key))
            if len(pending) >= ZIP_READERS:
                yield pending.popleft().result()
        while pending:
            yield pending.popleft().result()


def zip_partitions(mesh_id, partitions: list[dict]):
    """The partitions as one zip, streamed entry by entry. Parquet is already compressed,
    so entries are stored as they are. Objects are read a few at a time, in order."""
    keys = [partition_key(mesh_id, p["dt"], p["hour"]) for p in partitions]
    sink = _Sink()
    with zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED) as zf:
        for partition, data in zip(partitions, _read_in_order(keys)):
            modified = partition["last_modified"].astimezone(timezone.utc)
            info = zipfile.ZipInfo(zip_entry_name(partition["dt"], partition["hour"]), date_time=modified.timetuple()[:6])
            zf.writestr(info, data)
            yield sink.drain()
    yield sink.drain()
