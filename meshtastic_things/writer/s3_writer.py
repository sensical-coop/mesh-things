import json
import os
import asyncio
from datetime import datetime, timezone

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from aiohttp import web
from botocore.exceptions import ClientError
import structlog
from kafka import KafkaConsumer
from tools.healthcheck import HealthState, KafkaConsumerHealth

log = structlog.get_logger()

# One object per partition
PARTITION_FILENAME = "data.parquet"
UNKNOWN_MESH = "unknown"
_MISSING_OBJECT_CODES = {"NoSuchKey", "404", "NotFound"}

SCHEMA = pa.schema(
    [
        ("node_id", pa.int64()),
        ("packet_id", pa.int64()),
        ("portnum", pa.int64()),
        ("rx_time", pa.int64()),
        ("hop_start", pa.int64()),
        ("channel_id", pa.string()),
        ("gateway_id", pa.int64()),
        ("payload_kind", pa.string()),
        ("payload_json", pa.string()),
    ]
)

# Identifies a row within its partition to avoid duplication
_ROW_KEY = ("node_id", "packet_id", "rx_time", "payload_kind")

def _flatten(event: dict) -> dict:
    """Flatten a decoded message to SCHEMA.

    The "payload" shape varies across portnums (telemetry sub-metrics, position,
    nodeinfo, ...), so it is carried as JSON instead of as columns.
    """
    return {
        "node_id": event.get("node_id"),
        "packet_id": event.get("packet_id"),
        "portnum": event.get("portnum"),
        "rx_time": event.get("rx_time"),
        "hop_start": event.get("hop_start"),
        "channel_id": event.get("channel_id"),
        "gateway_id": event.get("gateway_id"),
        "payload_kind": event.get("payload_kind"),
        "payload_json": json.dumps(event.get("payload")),
    }


def _dedupe(rows: list[dict]) -> list[dict]:
    """Last occurrence of each row key takes precedence"""
    return list({tuple(r.get(k) for k in _ROW_KEY): r for r in rows}.values())


class S3Writer(object):
    def __init__(
        self,
        kafka_bootstrap_server,
        s3_bucket,
        s3_prefix,
        endpoint_url=None,
        access_key=None,
        secret_key=None,
        region_name=None,
    ):
        self.kafka_bootstrap_server = kafka_bootstrap_server
        self.kafka_consumer = KafkaConsumer(
            bootstrap_servers=self.kafka_bootstrap_server,
            group_id="s3-writer-group",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        log.debug(f"Subscribing to kafka topics {[os.environ['PROTO_DECODE__KAFKA_TOPIC']]}")
        self.kafka_consumer.subscribe(topics=[os.environ["PROTO_DECODE__KAFKA_TOPIC"]])
        self.health_state = HealthState()
        self.consumer_health = KafkaConsumerHealth(
            consumer=self.kafka_consumer, topic=os.environ["PROTO_DECODE__KAFKA_TOPIC"]
        )
        self.s3_bucket = s3_bucket
        self.s3_prefix = s3_prefix
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
            # Not needed for MinIO
            region_name=region_name or None,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self.s3_client.head_bucket(Bucket=self.s3_bucket)
        except Exception:
            try:
                self.s3_client.create_bucket(Bucket=self.s3_bucket)
                log.info(f"Created S3 bucket {self.s3_bucket}")
            except Exception as e:
                log.warning(f"Could not create/verify bucket {self.s3_bucket}, will retry on write", error=str(e))

    def _partition_key(self, mesh_id, now: datetime) -> str:
        # Every partition is the same depth
        return "/".join(
            [
                self.s3_prefix,
                f"mesh_id={mesh_id or UNKNOWN_MESH}",
                f"dt={now:%Y-%m-%d}",
                f"hour={now:%H}",
                PARTITION_FILENAME,
            ]
        )

    def _read_partition(self, key: str) -> list[dict]:
        """Rows already archived under this key, empty if there are none yet"""
        try:
            body = self.s3_client.get_object(Bucket=self.s3_bucket, Key=key)["Body"].read()
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in _MISSING_OBJECT_CODES:
                return []
            raise
        return pq.read_table(pa.BufferReader(body)).to_pylist()

    def flush(self, records: list[dict]) -> None:
        """Roll each (mesh_id, dt, hour) partition into a single object.

        Parquet cannot be appended to, so the partition is read back and
        rewritten whole.
        """
        if not records:
            return
        now = datetime.now(timezone.utc)
        groups: dict[str | None, list[dict]] = {}
        for r in records:
            groups.setdefault(r.get("mesh_id"), []).append(r)

        for mesh_id, group_records in groups.items():
            key = self._partition_key(mesh_id, now)
            rows = _dedupe(self._read_partition(key) + [_flatten(r) for r in group_records])
            buf = pa.BufferOutputStream()
            pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), buf)
            self.s3_client.put_object(Bucket=self.s3_bucket, Key=key, Body=buf.getvalue().to_pybytes())
            log.info(f"Flushed {len(group_records)} records into s3://{self.s3_bucket}/{key} ({len(rows)} total)")

    async def write_kafka_s3(self):
        batch_size = int(os.environ.get("S3_WRITER__BATCH_SIZE", 1000))
        flush_interval = int(os.environ.get("S3_WRITER__FLUSH_INTERVAL_S", 60))

        buffer: list[dict] = []
        last_flush = asyncio.get_event_loop().time()

        while True:
            messages = self.kafka_consumer.poll(max_records=batch_size, timeout_ms=1000)
            await asyncio.sleep(0.5)

            for topic_partition, consumer_records in messages.items():
                for record in consumer_records:
                    try:
                        event = json.loads(record.value)
                        if event is not None:
                            buffer.append(event)
                    except Exception as e:
                        log.exception("Bad message skipped", exc_info=e)

            now = asyncio.get_event_loop().time()
            should_flush = len(buffer) >= batch_size or (buffer and now - last_flush >= flush_interval)
            if not should_flush:
                continue

            try:
                self.flush(buffer)
            except Exception as e:
                # Drop the buffer and re-read from the last commit
                self._rewind_to_committed()
                log.exception("S3 write failed, rewound to retry", exc_info=e)
            else:
                self.kafka_consumer.commit()
                log.debug("Commit offset")
            buffer = []
            last_flush = now

    def _rewind_to_committed(self) -> None:
        """Re-read everything since the last commit"""
        for topic_partition in self.kafka_consumer.assignment():
            offset = self.kafka_consumer.committed(topic_partition)
            if offset is None:
                self.kafka_consumer.seek_to_beginning(topic_partition)
            else:
                self.kafka_consumer.seek(topic_partition, offset)

    async def health_handler(self, request):
        self.health_state.kafka_connected = self.consumer_health.is_healthy()
        try:
            self.s3_client.head_bucket(Bucket=self.s3_bucket)
            self.health_state.s3_connected = True
        except Exception as e:
            log.warning("S3 head_bucket check failed", error=str(e))
            self.health_state.s3_connected = False
        log.info(f"Health check. Kafka connected: {self.health_state.kafka_connected}, S3 connected: {self.health_state.s3_connected}")

        if self.health_state.is_healthy():
            return web.json_response({"status": "ok"})
        return web.json_response({"status": "unhealthy"}, status=503)

    async def start_health_server(self):
        try:
            log.info(f"Starting health server on 0.0.0.0:{int(os.environ['S3_WRITER__HEALTHCHECK_PORT'])}")
            app = web.Application()
            app.router.add_get("/health", self.health_handler)

            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", int(os.environ["S3_WRITER__HEALTHCHECK_PORT"]))
            await site.start()
        except Exception as e:
            log.exception("Problem with web server", exc_info=e)
