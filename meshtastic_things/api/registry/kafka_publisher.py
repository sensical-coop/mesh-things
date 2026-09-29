import json
import os
from datetime import datetime, timezone

import structlog
from kafka import KafkaProducer

from common import node_ids

# Definition of the "<measurement>.<field>"
from common.channels import channel_name

from .models import Device, Mesh

log = structlog.get_logger()


def gateway_kafka_key(device: Device) -> str:
    """Return the gateway's key, which must match ServiceEnvelope.gateway_id."""
    return node_ids.to_hex(device.device_id)


def node_rejection_kafka_key(device: Device) -> str:
    """Compound mesh_id:device_id key - matches decode_job.py's
    NODE_REJECTED_STATE key."""
    return f"{device.mesh_id}:{device.device_id}"


def device_intervals_kafka_key(device: Device) -> str:
    return f"{device.mesh_id}:{device.device_id}"


def measurement_alarms_kafka_key(device: Device, channel: str) -> str:
    return f"{device.mesh_id}:{device.device_id}:{channel}"


def postprocessing_kafka_key(device: Device) -> str:
    return f"{device.mesh_id}:{device.device_id}"


def sink_config_kafka_key(mesh_id, device_id: int) -> str:
    return f"{mesh_id}:{device_id}"


def mesh_sink_config_kafka_key(mesh_id) -> str:
    return f"mesh:{mesh_id}"


class KeyEventPublisher:
    """Publishes to mesh.keys.v1, mesh.node_rejections.v1, mesh.quality_config.v1,
    mesh.postprocessing_config.v1 and mesh.sink_config.v1."""

    def __init__(
        self,
        bootstrap_servers: str,
        keys_topic: str,
        node_rejections_topic: str,
        quality_config_topic: str,
        postprocessing_config_topic: str,
        sink_config_topic: str,
    ):
        self._keys_topic = keys_topic
        self._node_rejections_topic = node_rejections_topic
        self._quality_config_topic = quality_config_topic
        self._postprocessing_config_topic = postprocessing_config_topic
        self._sink_config_topic = sink_config_topic
        self._producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8"),
        )

    def publish_gateway_upsert(self, device: Device, mesh: Mesh) -> None:
        """psk_b64/channel_id/source_id come from the mesh"""
        key = gateway_kafka_key(device)
        event = {
            "kind": "gateway_key",
            "key": key,
            "gateway_id": key,
            "device_id": device.device_id,
            "mesh_id": str(device.mesh_id),
            "channel_id": mesh.channel_id,
            "psk_b64": mesh.psk_b64,
            "owner_id": str(mesh.owner_id),
            # Null for the instance's own broker. The MQTT bridge only accepts the gateway through this source.
            "source_id": str(mesh.source_id) if mesh.source_id else None,
            "op": "upsert",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        future = self._producer.send(self._keys_topic, key=key, value=event)
        future.get(timeout=10)
        log.info("Published gateway upsert", key=key)

    def publish_gateway_delete(self, device: Device) -> None:
        key = gateway_kafka_key(device)
        event = {
            "kind": "gateway_key",
            "key": key,
            "gateway_id": key,
            "device_id": device.device_id,
            "mesh_id": str(device.mesh_id),
            "op": "delete",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        future = self._producer.send(self._keys_topic, key=key, value=event)
        future.get(timeout=10)
        log.info("Published gateway delete", key=key)

    def publish_node_reject(self, device: Device) -> None:
        """Adds device_id to the mesh's reject-list broadcast state to
        stops attempting to decrypt this device's future packets."""
        key = node_rejection_kafka_key(device)
        event = {
            "kind": "node_rejection",
            "key": key,
            "mesh_id": str(device.mesh_id),
            "device_id": device.device_id,
            "op": "upsert",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        future = self._producer.send(self._node_rejections_topic, key=key, value=event)
        future.get(timeout=10)
        log.info("Published node rejection", key=key)

    def publish_node_unreject(self, device: Device) -> None:
        """Removes device_id from the reject-list"""
        key = node_rejection_kafka_key(device)
        event = {
            "kind": "node_rejection",
            "key": key,
            "mesh_id": str(device.mesh_id),
            "device_id": device.device_id,
            "op": "delete",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        future = self._producer.send(self._node_rejections_topic, key=key, value=event)
        future.get(timeout=10)
        log.info("Published node unreject", key=key)

    def publish_variant_measurement_config(self, link) -> None:
        """Publish default detectors and expected reading interval for a variant"""
        key = channel_name(link.measurement_type.payload_kind, link.measurement_type.field_name)
        event = {
            "kind": "variant_config",
            "key": key,
            "payload_kind": link.measurement_type.payload_kind,
            "field_name": link.measurement_type.field_name,
            "default_reading_interval_seconds": link.telemetry_variant.default_reading_interval_seconds,
            "default_enabled_detectors": list(link.default_enabled_detectors or []),
            "op": "upsert",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        future = self._producer.send(self._quality_config_topic, key=key, value=event)
        future.get(timeout=10)
        log.info("Published variant measurement config", key=key)

    def publish_measurement_alarms(self, device: Device, measurement) -> None:
        """A null enabled_detectors override hands the channel back to the
        catalog default rather than silencing it. valid_min/valid_max have no
        catalog default - they only ever come from here."""
        channel = channel_name(
            measurement.measurement_type.payload_kind, measurement.measurement_type.field_name
        )
        key = measurement_alarms_kafka_key(device, channel)
        cleared = (
            measurement.enabled_detectors is None
            and measurement.valid_min is None
            and measurement.valid_max is None
        )
        event = {
            "kind": "measurement_alarms",
            "key": key,
            "mesh_id": str(device.mesh_id),
            "device_id": device.device_id,
            "channel": channel,
            "enabled_detectors": measurement.enabled_detectors,
            "valid_min": measurement.valid_min,
            "valid_max": measurement.valid_max,
            "op": "delete" if cleared else "upsert",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        future = self._producer.send(self._quality_config_topic, key=key, value=event)
        future.get(timeout=10)
        log.info("Published measurement alarms", key=key)

    def publish_device_intervals(self, device: Device) -> None:
        """Publish device's own reading/publish intervals."""
        key = device_intervals_kafka_key(device)
        cleared = device.reading_interval_seconds is None and device.publish_interval_seconds is None
        event = {
            "kind": "device_intervals",
            "key": key,
            "mesh_id": str(device.mesh_id),
            "device_id": device.device_id,
            "reading_interval_seconds": device.reading_interval_seconds,
            "publish_interval_seconds": device.publish_interval_seconds,
            "absence_detection_enabled": device.absence_detection_enabled,
            "op": "delete" if cleared else "upsert",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        future = self._producer.send(self._quality_config_topic, key=key, value=event)
        future.get(timeout=10)
        log.info("Published device intervals", key=key)

    def publish_postprocessing_plans(self, device: Device, plans: list[dict]) -> None:
        """Replace every plan the stream job runs for this device. An empty list
        stops postprocessing on it."""
        key = postprocessing_kafka_key(device)
        event = {
            "kind": "postprocessing_plans",
            "key": key,
            "mesh_id": str(device.mesh_id),
            "device_id": device.device_id,
            "plans": plans,
            "op": "upsert" if plans else "delete",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        future = self._producer.send(self._postprocessing_config_topic, key=key, value=event)
        future.get(timeout=10)
        log.info("Published postprocessing plans", key=key, plans=len(plans))

    def publish_device_sinks(self, mesh_id, device_id: int, sinks: list[str]) -> None:
        """Replace the sinks a device's readings are sent to. An empty list sends them nowhere."""
        key = sink_config_kafka_key(mesh_id, device_id)
        event = {
            "kind": "device_sinks",
            "key": key,
            "mesh_id": str(mesh_id),
            "device_id": device_id,
            "sinks": sinks,
            "op": "upsert" if sinks else "delete",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        future = self._producer.send(self._sink_config_topic, key=key, value=event)
        future.get(timeout=10)
        log.info("Published device sinks", key=key, sinks=sinks)

    def publish_mesh_sinks(self, mesh_id, sinks: list[str]) -> None:
        """Replace the sinks every node of a mesh is sent to, on top of each device's own."""
        key = mesh_sink_config_kafka_key(mesh_id)
        event = {
            "kind": "mesh_sinks",
            "key": key,
            "mesh_id": str(mesh_id),
            "sinks": sinks,
            "op": "upsert" if sinks else "delete",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        future = self._producer.send(self._sink_config_topic, key=key, value=event)
        future.get(timeout=10)
        log.info("Published mesh sinks", key=key, sinks=sinks)

    def publish_sink(self, sink_id, streams: list[str] | None) -> None:
        """Replace which streams an MQTT sink carries. None removes the sink."""
        key = f"sink:{sink_id}"
        event = {
            "kind": "sink",
            "key": key,
            "sink_id": str(sink_id),
            "streams": streams or [],
            "op": "delete" if streams is None else "upsert",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        future = self._producer.send(self._sink_config_topic, key=key, value=event)
        future.get(timeout=10)
        log.info("Published sink", key=key, streams=streams)

    def close(self) -> None:
        self._producer.flush()
        self._producer.close()


_publisher: KeyEventPublisher | None = None


def get_publisher() -> KeyEventPublisher:
    """For gunicorn workers."""
    global _publisher
    if _publisher is None:
        _publisher = KeyEventPublisher(
            bootstrap_servers=os.environ["KAFKA_BOOTSTRAP"],
            keys_topic=os.environ.get("REGISTRY__KAFKA_TOPIC", "mesh.keys.v1"),
            node_rejections_topic=os.environ.get(
                "REGISTRY__NODE_REJECTIONS_KAFKA_TOPIC", "mesh.node_rejections.v1"
            ),
            quality_config_topic=os.environ.get("REGISTRY__QUALITY_CONFIG_KAFKA_TOPIC", "mesh.quality_config.v1"),
            postprocessing_config_topic=os.environ.get(
                "REGISTRY__POSTPROCESSING_CONFIG_KAFKA_TOPIC", "mesh.postprocessing_config.v1"
            ),
            sink_config_topic=os.environ.get("REGISTRY__SINK_CONFIG_KAFKA_TOPIC", "mesh.sink_config.v1"),
        )
    return _publisher


def publish_gateway_state(publisher: KeyEventPublisher, device: Device, mesh: Mesh) -> None:
    """Register an allowed gateway with the decoder, or deregister it while its mesh's ingest is paused."""
    if mesh.ingest_paused:
        publisher.publish_gateway_delete(device)
    else:
        publisher.publish_gateway_upsert(device, mesh)
