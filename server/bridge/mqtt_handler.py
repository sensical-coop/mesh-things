import asyncio
import json
import os
import time

import aiomqtt
from aiohttp import web
import structlog
from kafka import KafkaProducer
from paho.mqtt.client import topic_matches_sub
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties

from bridge import discovery, front_desk
from common import sources
from pipeline.config_state import replay_consumer, replay_to_end
from tools.healthcheck import HealthState, KakfaProducerHealth, MQTTHealth
from tools.env import get_bool_env


def _instance_suffix() -> str:
    """Separates a dev stack from prod on a shared broker; only the dev overlay sets it."""
    return os.environ.get('MQTT_BRIDGE__INSTANCE_SUFFIX', '').strip()


def _suffixed(name: str) -> str:
    suffix = _instance_suffix()
    return f'{name}-{suffix}' if suffix else name


def _client_id() -> str:
    """The MQTT client id: stable across restarts, unique per pool member."""
    return _suffixed(os.environ.get('MQTT_BRIDGE__CLIENT_ID', '').strip() or 'mesh-bridge')


def shared_group() -> str:
    """The `$share` group this member joins; members of one group split the topic between them."""
    return _suffixed(os.environ.get('MQTT_BRIDGE__SHARED_GROUP', '').strip() or 'kafka-bridge')


def session_expiry_seconds() -> int:
    """Return the time the broker keeps a member's session after it disconnects.

    A single-member deployment wants this generous.
    """
    return int(os.environ.get('MQTT_BRIDGE__SESSION_EXPIRY', 3600))


def _connection_kwargs() -> dict:
    """Broker port, credentials and TLS shared by every connection the bridge opens."""
    return dict(
        port=int(os.environ.get('MQTT_BRIDGE__PORT', 8883)),
        username=os.environ['MQTT_BRIDGE__USER'],
        password=os.environ['MQTT_BRIDGE__PASS'],
        tls_params=aiomqtt.TLSParameters() if get_bool_env('MQTT_BRIDGE__SSL', default=True) else None,
    )


def _session_properties() -> Properties:
    properties = Properties(PacketTypes.CONNECT)
    properties.SessionExpiryInterval = session_expiry_seconds()
    return properties


async def retire_session(broker: str, client_id: str) -> None:
    """Discard a member's session on the broker immediately

    Trick. Removing a member from the shared group does not remove its session.
    until it expires the broker still keeps every message and holds it for a
    client that is not coming back. Connecting once with `clean_start=True`
    and a zero expiry throws the session away as soon as this disconnects.

    Use it when scaling the pool down, before the id stops being used.
    """
    properties = Properties(PacketTypes.CONNECT)
    properties.SessionExpiryInterval = 0
    async with aiomqtt.Client(
        broker,
        identifier=client_id,
        protocol=aiomqtt.ProtocolVersion.V5,
        clean_start=True,
        properties=properties,
        **_connection_kwargs(),
    ):
        log.info(f'Retired MQTT session for client_id={client_id}')


def subscription_filters(own_topic: str) -> list[str]:
    """The instance's own topic filter, plus the one every source is republished under.

    Refuses an own filter that also matches the source topics, which would ingest
    bridged traffic twice and without its source.
    """
    probe = f"{sources.namespace()}/00000000-0000-0000-0000-000000000000/msh/2/e/LongFast/!00000000"
    if topic_matches_sub(own_topic, probe):
        raise ValueError(
            f"MQTT_BRIDGE__TOPIC={own_topic!r} overlaps the source topics under {sources.namespace()}/"
        )
    return [own_topic, sources.local_topic_filter()]


log = structlog.get_logger()

# A gateway rate limited this recently is listed on /health.
RATE_LIMITED_RECENT_SECONDS = 600

class MQTTHandler(object):
    def __init__(self, broker, kafka_bootstrap_server):
        self.mqtt_broker = broker
        self.kafka_bootstrap_server = kafka_bootstrap_server
        self.kafka_producer = KafkaProducer(bootstrap_servers=self.kafka_bootstrap_server)
        self.health_state = HealthState()
        self.producer_health = KakfaProducerHealth(
            self.kafka_producer,
            topic=os.environ['MQTT_BRIDGE__HEALTH__KAFKA_TOPIC'],
            timeout=int(os.environ['MQTT_BRIDGE__HEALTH__TIMEOUT'])
        )
        self.mqtt_health = MQTTHealth()
        self.client_id = _client_id()
        self.keys_topic = os.environ.get('REGISTRY__KAFKA_TOPIC', 'mesh.keys.v1')
        # gateway_id -> the source its mesh is bridged from, None for the own topic.
        self.gateway_sources: dict[str, str | None] = {}
        self.gateway_rate = front_desk.GatewayRate.from_env()
        self.drops: dict[str, int] = {}
        # gateway_id -> monotonic time it was last rate limited, for /health.
        self.rate_limited_at: dict[str, float] = {}
        self.config_consumer = None
        self.discovery_pacer = discovery.DiscoveryPacer.from_env()
        self.discovery_topic = discovery.candidate_topic()
        self.discovery_candidates_sent = 0

    def _apply_gateway_record(self, record) -> None:
        event = json.loads(record.value)
        key = event.get("key")
        if not key:
            return
        if event.get("op") == "delete":
            self.gateway_sources.pop(key, None)
            self.gateway_rate.forget(key)
            self.rate_limited_at.pop(key, None)
        else:
            self.gateway_sources[key] = event.get("source_id")

    def load_gateway_sources(self) -> None:
        """Read mesh.keys.v1 to its current end. Runs before subscribing, so the
        source gate is never open while the state is still empty."""
        self.config_consumer = replay_consumer(self.kafka_bootstrap_server, self.keys_topic)
        read = replay_to_end(self.config_consumer, self._apply_gateway_record)
        log.info('Loaded gateway sources', records=read, gateways=len(self.gateway_sources))

    async def follow_gateway_sources(self):
        while True:
            messages = await asyncio.to_thread(self.config_consumer.poll, timeout_ms=1000)
            for records in messages.values():
                for record in records:
                    try:
                        self._apply_gateway_record(record)
                    except Exception as e:
                        log.exception("Bad config message skipped", exc_info=e)

    def accepts(self, topic: str, gateway_id: str) -> bool:
        """False when a registered gateway arrives through a source its mesh is not on.

        Stops the same gateway being ingested twice, for example directly and again
        through a bridged public broker.
        """
        return self.gateway_sources[gateway_id] == sources.source_id_from_topic(topic)

    def admit(self, topic: str, payload: bytes) -> tuple[str | None, str | None]:
        """Return (gateway_id, None) to send a message on to Kafka, or (gateway_id, reason) to drop it.

        Only a registered gateway's envelopes pass, and only when the envelope names
        the gateway its topic does. An unregistered gateway's traffic goes no further
        than the paced samples gateway discovery gets.
        """
        kind = front_desk.topic_kind(topic)
        if kind is None:
            return None, front_desk.NOT_ENVELOPE
        gateway_id = front_desk.envelope_gateway(payload)
        if gateway_id is None:
            return None, front_desk.UNPARSEABLE
        if kind == front_desk.ENCRYPTED and topic.rsplit('/', 1)[-1] != gateway_id:
            return gateway_id, front_desk.GATEWAY_MISMATCH
        if gateway_id not in self.gateway_sources:
            if kind == front_desk.ENCRYPTED:
                try:
                    self.observe_candidate(topic, payload)
                except Exception as e:
                    log.warning('Gateway discovery sample not sent', topic=topic, error=str(e))
            return gateway_id, front_desk.UNREGISTERED
        if not self.accepts(topic, gateway_id):
            return gateway_id, front_desk.WRONG_SOURCE
        if not self.gateway_rate.allow(gateway_id):
            if gateway_id not in self.rate_limited_at:
                log.warning('Gateway over its rate, dropping its packets', gateway_id=gateway_id)
            self.rate_limited_at[gateway_id] = time.monotonic()
            return gateway_id, front_desk.RATE_LIMITED
        self.rate_limited_at.pop(gateway_id, None)
        return gateway_id, None

    def observe_candidate(self, topic: str, payload: bytes) -> None:
        """Send a paced sample of an unregistered gateway's traffic to the registry for discovery."""
        if topic.split('/')[-1] in self.gateway_sources:
            return
        candidate = discovery.parse_candidate(topic)
        if candidate is None or not self.discovery_pacer.should_send(candidate):
            return
        key, event = discovery.candidate_event(*candidate, payload)
        self.kafka_producer.send(self.discovery_topic, key=key.encode(), value=json.dumps(event).encode())
        self.discovery_candidates_sent += 1

    async def bridge_mqtt_kafka(self, topics: list[str], shared_sub=False):

        if shared_sub:
            topics = [f'$share/{shared_group()}/{topic}' for topic in topics]

        qos = int(os.environ.get('MQTT_BRIDGE__QOS', 1))
        client = aiomqtt.Client(
            self.mqtt_broker,
            identifier=self.client_id,
            protocol=aiomqtt.ProtocolVersion.V5,
            # Resume the session
            clean_start=False,
            properties=_session_properties(),
            **_connection_kwargs(),
        )

        while True:
            try:
                async with client:
                    self.mqtt_health.mark_connected()
                    for topic in topics:
                        log.info(f'Subscription: {self.mqtt_broker}, topic: {topic}, client_id: {self.client_id}, qos: {qos}')
                        await client.subscribe(topic, qos=qos)
                    async for message in client.messages:
                        self.mqtt_health.mark_connected()
                        log.debug(f'Got message: {message.topic}: {message.payload}')
                        gateway_id, reason = self.admit(message.topic.value, message.payload)
                        if reason is not None:
                            self.drops[reason] = self.drops.get(reason, 0) + 1
                            log.debug('Dropping message', topic=message.topic.value, reason=reason)
                            continue
                        # Keyed by gateway, which decode_job.py's broadcast-state lookup keys off of.
                        self.kafka_producer.send(
                            os.environ['MQTT_BRIDGE__KAFKA_TOPIC'], key=gateway_id.encode(), value=message.payload
                        )
            except aiomqtt.MqttError as e:
                self.mqtt_health.mark_disconnected()
                log.warning(f"Connection lost ({e}); Reconnecting in {int(os.environ['MQTT_BRIDGE__RECONNECT'])} seconds ...")
                await asyncio.sleep(int(os.environ['MQTT_BRIDGE__RECONNECT']))
            except Exception as e:
                log.exception("An error occurred", exc_info=e)

    async def monitor_publish(self):
        while True:
            log.debug('MQTT monitor sending health ping')
            try:
                await self.publish_to_mqtt("health/ping", "ok")
            except aiomqtt.MqttError as e:
                log.warning('MQTT health ping failed', error=str(e))
                self.mqtt_health.mark_disconnected()
            await asyncio.sleep(10)

    async def publish_to_mqtt(self, topic, payload):
        # A random client id, so the ping never takes over the bridge's session.
        async with aiomqtt.Client(self.mqtt_broker, **_connection_kwargs()) as client:
            await client.publish(topic, payload=payload)
            self.mqtt_health.mark_connected()

    async def health_handler(self, request):

        self.health_state.kafka_connected = self.producer_health.is_healthy()
        self.health_state.mqtt_connected = self.mqtt_health.is_healthy()
        log.info(f'Health check. Kafka connected: {self.health_state.kafka_connected}')
        log.info(f'Health check. MQTT connected: {self.health_state.mqtt_connected}')

        recent = time.monotonic() - RATE_LIMITED_RECENT_SECONDS
        body = {
            "drops": dict(sorted(self.drops.items())),
            "rate_limited_gateways": sorted(g for g, at in self.rate_limited_at.items() if at >= recent),
            "discovery_candidates_sent": self.discovery_candidates_sent,
            "discovery_gateways_tracked": len(self.discovery_pacer),
        }
        if self.health_state.is_healthy():
            return web.json_response({"status": "ok", **body})
        return web.json_response({"status": "unhealthy", **body}, status=503)

    async def start_health_server(self):
        app = web.Application()
        app.router.add_get("/health", self.health_handler)
        log.info(f"Starting health server on 0.0.0.0:{int(os.environ['MQTT_BRIDGE__HEALTH__PORT'])}")

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", int(os.environ['MQTT_BRIDGE__HEALTH__PORT']))
        await site.start()
