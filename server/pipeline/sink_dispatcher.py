"""Publishes readings and alarms to the MQTT sinks their device or mesh is attached to.

Each message goes to this instance's own broker, under the sink's topics, where only
the sink's consumer may subscribe. The broker holds no remote credentials and this
service connects nowhere else.
"""
import argparse
import asyncio
import json
import os
import sys

import aiomqtt
import structlog
from aiohttp import web
from kafka import KafkaConsumer

from mesh_things import streams as stream_names

from common import sinks
from pipeline.config_state import replay_consumer, replay_to_end
from tools.env import get_bool_env
from tools.healthcheck import KafkaConsumerHealth

log = structlog.get_logger()


class SinkRouting:
    """The state of mesh.sink_config.v1: each sink's streams, and the sinks of each mesh and device."""

    def __init__(self):
        self.sink_streams: dict[str, set[str]] = {}
        self.mesh_sinks: dict[str, list[str]] = {}
        self.device_sinks: dict[str, list[str]] = {}

    def apply(self, event: dict) -> None:
        key = event.get("key")
        kind = event.get("kind")
        deleted = event.get("op") == "delete"
        if not key:
            return
        if kind == "sink":
            if deleted:
                self.sink_streams.pop(event["sink_id"], None)
            else:
                self.sink_streams[event["sink_id"]] = set(event.get("streams") or [])
            return
        table = self.mesh_sinks if kind == "mesh_sinks" else self.device_sinks
        refs = [] if deleted else [sid for sid in map(sinks.id_from_ref, event.get("sinks") or []) if sid]
        if kind == "mesh_sinks":
            key = event["mesh_id"]
        if refs:
            table[key] = refs
        else:
            table.pop(key, None)

    def topics(self, stream: str, event: dict) -> list[str]:
        """Return the destinations of one event, none for a backfill, which a consumer would read as new."""
        mesh_id = event.get("mesh_id")
        node_id = event.get("node_id", event.get("device_id"))
        if not mesh_id or node_id is None or event.get("backfill"):
            return []
        sink_ids = dict.fromkeys(self.mesh_sinks.get(mesh_id, []) + self.device_sinks.get(f"{mesh_id}:{node_id}", []))
        return [
            sinks.topic(sink_id, stream, mesh_id, node_id)
            for sink_id in sink_ids
            if stream in self.sink_streams.get(sink_id, ())
        ]


def message(event: dict) -> bytes:
    return json.dumps({**event, "schema": sinks.SCHEMA_VERSION}).encode()


async def dispatch_batch(consumer, routing: SinkRouting, stream_of: dict[str, str], publish, messages) -> bool:
    """Publish one poll batch and advance the offsets.

    A failed publish rewinds that partition to the record that failed and stops
    reading it, so nothing is committed past what the broker acknowledged.

    Returns:
        Whether every publish succeeded.
    """
    retry_from = {}
    for topic_partition, records in messages.items():
        stream = stream_of[topic_partition.topic]
        for record in records:
            try:
                event = json.loads(record.value)
            except Exception as e:
                # Not retryable - a malformed record won't parse differently next time.
                log.exception("Unreadable record skipped", exc_info=e)
                continue
            try:
                for topic in routing.topics(stream, event):
                    await publish(topic, message(event))
            except Exception as e:
                log.warning("Failed to publish to a sink, rewound to retry", error=str(e))
                retry_from[topic_partition] = record.offset
                break
    for topic_partition, offset in retry_from.items():
        consumer.seek(topic_partition, offset)
    # The rewound partitions commit the offset they will resume from.
    consumer.commit()
    return not retry_from


class SinkDispatcher:
    def __init__(self, kafka_bootstrap_server: str):
        self.kafka_bootstrap_server = kafka_bootstrap_server
        self.sink_config_topic = os.environ.get('REGISTRY__SINK_CONFIG_KAFKA_TOPIC', 'mesh.sink_config.v1')
        self.stream_of = {
            os.environ['PROTO_DECODE__KAFKA_TOPIC']: stream_names.DECODED,
            os.environ.get('POSTPROCESSING__DERIVED_KAFKA_TOPIC', 'mesh.telemetry.derived.v1'): stream_names.DERIVED,
            os.environ.get('PATTERN_DETECTION__ALARMS_TOPIC', 'mesh.telemetry.alarms.v1'): stream_names.ALARMS,
        }
        # Starts at the newest reading: a new dispatcher does not replay history to consumers.
        self.consumer = KafkaConsumer(
            bootstrap_servers=kafka_bootstrap_server,
            group_id='sink-dispatcher-group',
            enable_auto_commit=False,
            auto_offset_reset='latest',
        )
        self.consumer.subscribe(topics=list(self.stream_of))
        self.routing = SinkRouting()
        self.config_consumer = None
        self.consumer_health = KafkaConsumerHealth(self.consumer, topic=os.environ['PROTO_DECODE__KAFKA_TOPIC'])
        self.mqtt_connected = False

    def _apply_config_record(self, record) -> None:
        self.routing.apply(json.loads(record.value))

    def load_config(self) -> None:
        """Read mesh.sink_config.v1 to its current end before the first data poll, so
        readings of attached devices are not skipped while the state is still empty."""
        self.config_consumer = replay_consumer(self.kafka_bootstrap_server, self.sink_config_topic)
        read = replay_to_end(self.config_consumer, self._apply_config_record)
        log.info(
            "Loaded sink config",
            records=read,
            sinks=len(self.routing.sink_streams),
            meshes=len(self.routing.mesh_sinks),
            devices=len(self.routing.device_sinks),
        )

    async def follow_config(self):
        while True:
            messages = await asyncio.to_thread(self.config_consumer.poll, timeout_ms=1000)
            for records in messages.values():
                for record in records:
                    try:
                        self._apply_config_record(record)
                    except Exception as e:
                        log.exception("Bad sink config message skipped", exc_info=e)

    def _client(self) -> aiomqtt.Client:
        tls_params = aiomqtt.TLSParameters() if get_bool_env('MQTT_BRIDGE__SSL', default=True) else None
        suffix = os.environ.get('MQTT_BRIDGE__INSTANCE_SUFFIX', '').strip()
        return aiomqtt.Client(
            os.environ['MQTT_BRIDGE__BROKER'],
            port=int(os.environ.get('MQTT_BRIDGE__PORT', 8883)),
            username=sinks.dispatcher_username(),
            password=sinks.dispatcher_password(),
            identifier=f"sink-dispatcher-{suffix}" if suffix else "sink-dispatcher",
            protocol=aiomqtt.ProtocolVersion.V5,
            tls_params=tls_params,
        )

    async def dispatch(self):
        reconnect = int(os.environ.get('MQTT_BRIDGE__RECONNECT', 5))
        while True:
            try:
                async with self._client() as client:
                    self.mqtt_connected = True
                    log.info("Connected to the broker for sinks")

                    async def publish(topic, payload):
                        await client.publish(topic, payload=payload, qos=1)

                    while True:
                        messages = await asyncio.to_thread(
                            self.consumer.poll,
                            timeout_ms=int(os.environ.get('SINK_DISPATCHER__CONSUMER__TIMEOUT_MS', 1000)),
                            max_records=int(os.environ.get('SINK_DISPATCHER__CONSUMER__N_MSGS', 100)),
                        )
                        if messages and not await dispatch_batch(
                            self.consumer, self.routing, self.stream_of, publish, messages
                        ):
                            raise aiomqtt.MqttError("publish failed")
            except aiomqtt.MqttError as e:
                self.mqtt_connected = False
                log.warning(f"Broker connection lost ({e}); reconnecting in {reconnect} seconds")
                await asyncio.sleep(reconnect)

    async def health_handler(self, request):
        if self.consumer_health.is_healthy() and self.mqtt_connected:
            return web.json_response({"status": "ok"})
        return web.json_response({"status": "unhealthy"}, status=503)

    async def start_health_server(self):
        port = int(os.environ['SINK_DISPATCHER__HEALTHCHECK_PORT'])
        log.info(f"Starting health server on 0.0.0.0:{port}")
        app = web.Application()
        app.router.add_get("/health", self.health_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", port).start()


async def create_tasks(dispatcher: SinkDispatcher):
    await asyncio.to_thread(dispatcher.load_config)
    log.info('Creating sink dispatcher tasks...')
    async with asyncio.TaskGroup() as tg:
        tg.create_task(dispatcher.follow_config())
        tg.create_task(dispatcher.dispatch())
        tg.create_task(dispatcher.start_health_server())
        tg.create_task(dispatcher.consumer_health.monitor())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--local", default=False, dest='local', action='store_true', help="Local development mode"
    )
    args = parser.parse_args()

    if args.local:
        # Only needed for local development.
        from dotenv import load_dotenv

        load_dotenv("../.env")
        kafka_bootstrap_server = os.environ['KAFKA_BOOTSTRAP_LOCAL']
    else:
        kafka_bootstrap_server = os.environ['KAFKA_BOOTSTRAP']

    dispatcher = SinkDispatcher(kafka_bootstrap_server)
    log.info("Starting sink dispatcher...")
    try:
        asyncio.run(create_tasks(dispatcher))
    except KeyboardInterrupt:
        log.info("Program interrupted by user")
        sys.exit(0)
