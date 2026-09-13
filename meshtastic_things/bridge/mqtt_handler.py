import asyncio
import os

import aiomqtt
from aiohttp import web
import structlog
from kafka import KafkaProducer
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties
from tools.healthcheck import HealthState, KakfaProducerHealth, MQTTHealth
from tools.env import get_bool_env


def _client_id() -> str:
    """The MQTT client id: stable across restarts, unique per pool member."""
    return os.environ.get('MQTT_BRIDGE__CLIENT_ID', '').strip() or 'mesh-bridge'


def session_expiry_seconds() -> int:
    """How long the broker keeps a member's session after it disconnects.

    A single-member deployment wants this generous.
    """
    return int(os.environ.get('MQTT_BRIDGE__SESSION_EXPIRY', 3600))


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
    tls_params = aiomqtt.TLSParameters() if get_bool_env('MQTT_BRIDGE__SSL', default=True) else None
    properties = Properties(PacketTypes.CONNECT)
    properties.SessionExpiryInterval = 0
    async with aiomqtt.Client(
        broker,
        port=int(os.environ.get('MQTT_BRIDGE__PORT', 8883)),
        username=os.environ['MQTT_BRIDGE__USER'],
        password=os.environ['MQTT_BRIDGE__PASS'],
        identifier=client_id,
        protocol=aiomqtt.ProtocolVersion.V5,
        clean_start=True,
        properties=properties,
        tls_params=tls_params,
    ):
        log.info(f'Retired MQTT session for client_id={client_id}')


def _partition_key(topic):
    # The last topic segment is the relaying gateway's node id (e.g.
    # msh/.../2/e/LongFast/!aabbccdd) for the encrypted feed this bridge
    # subscribes to - matches ServiceEnvelope.gateway_id, which is what
    # decode_job.py's broadcast-state lookup keys off of.
    return topic.value.split('/')[-1].encode()

log = structlog.get_logger()

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

    async def bridge_mqtt_kafka(self, topic, shared_sub=False):

        if shared_sub:
            shared_group = os.environ.get('MQTT_BRIDGE__SHARED_GROUP', 'kafka-bridge')
            topic = f'$share/{shared_group}/{topic}'

        qos = int(os.environ.get('MQTT_BRIDGE__QOS', 1))
        tls_params = None
        if get_bool_env('MQTT_BRIDGE__SSL', default=True):
            tls_params = aiomqtt.TLSParameters()

        client = aiomqtt.Client(
            self.mqtt_broker,
            port=int(os.environ.get('MQTT_BRIDGE__PORT', 8883)),
            username=os.environ['MQTT_BRIDGE__USER'],
            password=os.environ['MQTT_BRIDGE__PASS'],
            identifier=self.client_id,
            protocol=aiomqtt.ProtocolVersion.V5,
            # Resume the session
            clean_start=False,
            properties=_session_properties(),
            tls_params=tls_params,
        )

        while True:
            try:
                async with client:
                    self.mqtt_health.mark_connected()
                    log.info(f'Subscription: {self.mqtt_broker}, topic: {topic}, client_id: {self.client_id}, qos: {qos}')
                    await client.subscribe(topic, qos=qos)
                    async for message in client.messages:
                        self.mqtt_health.mark_connected()
                        log.debug(f'Got message: {message.topic}: {message.payload}')
                        self.kafka_producer.send(os.environ['MQTT_BRIDGE__KAFKA_TOPIC'], key=_partition_key(message.topic), value=message.payload)
            except aiomqtt.MqttError:
                self.mqtt_health.mark_disconnected()
                log.info(f"Connection lost; Reconnecting in {int(os.environ['MQTT_BRIDGE__RECONNECT'])} seconds ...")
                await asyncio.sleep(int(os.environ['MQTT_BRIDGE__RECONNECT']))
            except Exception as e:
                log.exception("An error occurred", exc_info=e)

    async def monitor_publish(self):
        while True:
            log.debug('MQTT monitor sending health ping')
            try:
                await self.publish_to_mqtt("health/ping", "ok")
            except aiomqtt.MqttError:
                self.mqtt_health.mark_disconnected()
            await asyncio.sleep(10)

    async def publish_to_mqtt(self, topic, payload):
        async with aiomqtt.Client(self.mqtt_broker) as client:
            await client.publish(topic, payload=payload)
            self.mqtt_health.mark_connected()

    async def health_handler(self, request):

        self.health_state.kafka_connected = self.producer_health.is_healthy()
        self.health_state.mqtt_connected = self.mqtt_health.is_healthy()
        log.info(f'Health check. Kafka connected: {self.health_state.kafka_connected}')
        log.info(f'Health check. MQTT connected: {self.health_state.mqtt_connected}')

        if self.health_state.is_healthy():
            return web.json_response({"status": "ok"})
        return web.json_response({"status": "unhealthy"}, status=503)

    async def start_health_server(self):
        app = web.Application()
        app.router.add_get("/health", self.health_handler)
        log.info(f"Starting health server on 0.0.0.0:{int(os.environ['MQTT_BRIDGE__HEALTH__PORT'])}")

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", int(os.environ['MQTT_BRIDGE__HEALTH__PORT']))
        await site.start()
