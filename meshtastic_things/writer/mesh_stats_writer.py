"""Aggregate mesh.traffic.v1 into per-mesh statistics in InfluxDB, and direct links for the registry.

Counters live in memory and are written every minute. Offsets are committed only
once every bucket holding a record has closed, so a restart replays and rebuilds
the open buckets rather than overwriting them with partial counts. Each hour's
direct links are published to mesh.links.v1 once that hour closes.
"""
import argparse
import asyncio
import json
import os
import sys
import time

import structlog
from aiohttp import web
from influxdb_client import Point
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from kafka import KafkaConsumer, KafkaProducer
from kafka.structs import OffsetAndMetadata

from common.mesh_stats import MESH_STATS_BUCKET, MeshStatsAggregator
from tools.healthcheck import HealthState, KafkaConsumerHealth

log = structlog.get_logger()

FLUSH_SECONDS = int(os.environ.get("MESH_STATS_WRITER__FLUSH_SECONDS") or 60)


class MeshStatsWriter:
    def __init__(self, kafka_bootstrap_server: str, influx_url: str):
        self.topic = os.environ.get("PROTO_DECODE__TRAFFIC_KAFKA_TOPIC") or "mesh.traffic.v1"
        self.kafka_consumer = KafkaConsumer(
            bootstrap_servers=kafka_bootstrap_server,
            group_id="mesh-stats-writer-group",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        self.kafka_consumer.subscribe(topics=[self.topic])
        self.links_topic = os.environ.get("MESH_STATS_WRITER__LINKS_KAFKA_TOPIC") or "mesh.links.v1"
        self.producer = KafkaProducer(
            bootstrap_servers=kafka_bootstrap_server,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        self._pending_links: list[dict] = []
        self.influx_url = influx_url
        self.aggregator = MeshStatsAggregator()
        self.health_state = HealthState()
        self.consumer_health = KafkaConsumerHealth(consumer=self.kafka_consumer, topic=self.topic)
        self._last_flush = time.monotonic()
        self._last_record = 0.0

    async def run(self):
        while True:
            messages = self.kafka_consumer.poll(max_records=1000, timeout_ms=1000)
            self.read_batch(messages)
            await asyncio.sleep(0.1)
            if time.monotonic() - self._last_flush >= FLUSH_SECONDS:
                await self.flush()

    def read_batch(self, messages) -> None:
        for topic_partition, records in messages.items():
            for record in records:
                try:
                    event = json.loads(record.value)
                    self.aggregator.add(
                        event,
                        event.get("received_at") or record.timestamp,
                        partition=topic_partition,
                        offset=record.offset,
                    )
                    self._last_record = time.time()
                except Exception as e:
                    log.exception("Bad traffic event skipped", exc_info=e)

    async def flush(self) -> None:
        """Write every bucket, then close the finished ones and commit what they covered."""
        self._last_flush = time.monotonic()
        rows = self.aggregator.rows()
        if rows:
            try:
                async with InfluxDBClientAsync(
                    url=self.influx_url, token=os.environ["INFLUX__TOKEN"], org=os.environ["INFLUX__ORG"]
                ) as client:
                    await client.write_api().write(
                        bucket=MESH_STATS_BUCKET, record=[Point.from_dict(row) for row in rows]
                    )
            except Exception as e:
                # Counters stay in memory and offsets uncommitted; the next flush retries.
                log.exception("Mesh stats write failed", exc_info=e)
                return
        # With nothing arriving, the clock stands in for event time so the last buckets close.
        idle = time.time() - self._last_record > self.aggregator.grace_ms / 1000
        self._pending_links += self.aggregator.close(watermark=int(time.time() * 1000) if idle else None)
        try:
            while self._pending_links:
                link = self._pending_links[0]
                self.producer.send(self.links_topic, key=link["mesh_id"].encode(), value=link).get(timeout=10)
                self._pending_links.pop(0)
        except Exception as e:
            # Offsets stay uncommitted until the links are out; the next flush retries.
            log.exception("Publishing direct links failed", exc_info=e, pending=len(self._pending_links))
            return
        offsets = self.aggregator.committable()
        if offsets:
            self.kafka_consumer.commit({tp: OffsetAndMetadata(offset, "", -1) for tp, offset in offsets.items()})
        log.info("Mesh stats flushed", rows=len(rows), committed={tp.partition: o for tp, o in offsets.items()})

    async def health_handler(self, request):
        self.health_state.kafka_connected = self.consumer_health.is_healthy()
        try:
            async with InfluxDBClientAsync(
                url=self.influx_url, token=os.environ["INFLUX__TOKEN"], org=os.environ["INFLUX__ORG"]
            ) as client:
                self.health_state.influx_connected = await client.ping()
        except Exception as e:
            log.warning("InfluxDB ping failed", error=str(e))
            self.health_state.influx_connected = False
        if self.health_state.is_healthy():
            return web.json_response({"status": "ok"})
        return web.json_response({"status": "unhealthy"}, status=503)

    async def start_health_server(self):
        port = int(os.environ.get("MESH_STATS_WRITER__HEALTHCHECK_PORT") or 19094)
        app = web.Application()
        app.router.add_get("/health", self.health_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", port).start()
        log.info(f"Health server on 0.0.0.0:{port}")


async def create_tasks(writer: MeshStatsWriter):
    async with asyncio.TaskGroup() as tg:
        tg.create_task(writer.start_health_server())
        tg.create_task(writer.consumer_health.monitor())
        tg.create_task(writer.run())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", default=False, action="store_true", help="Local development mode")
    args = parser.parse_args()

    if args.local:
        from dotenv import load_dotenv

        load_dotenv("../.env")
        kafka_bootstrap_server = os.environ["KAFKA_BOOTSTRAP_LOCAL"]
        influx_url = os.environ["INFLUX__URL_LOCAL"]
    else:
        kafka_bootstrap_server = os.environ["KAFKA_BOOTSTRAP"]
        influx_url = os.environ["INFLUX__URL"]

    writer = MeshStatsWriter(kafka_bootstrap_server=kafka_bootstrap_server, influx_url=influx_url)
    log.info("Starting mesh stats writer...")
    try:
        asyncio.run(create_tasks(writer))
    except KeyboardInterrupt:
        writer.kafka_consumer.close()
        sys.exit(0)
