"""Background worker: upserts a Device row per mesh.devices.v1 sighting

  python manage.py consume_device_sightings
"""
import json
import os

import structlog
from django.core.management.base import BaseCommand
from django.utils import timezone
from kafka import KafkaConsumer

from registry.consumer_loop import consume_forever
from registry.models import Device, Mesh

log = structlog.get_logger()


class Command(BaseCommand):
    help = "Consume mesh.devices.v1 and upsert Device rows"

    def handle(self, *args, **options):
        bootstrap_servers = os.environ["KAFKA_BOOTSTRAP"]
        topic = os.environ.get("REGISTRY__DEVICES_KAFKA_TOPIC", "mesh.devices.v1")
        consumer = KafkaConsumer(
            bootstrap_servers=bootstrap_servers,
            group_id="registry-device-catalog-group",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        consumer.subscribe([topic])
        log.info("Starting device-sightings consumer", topic=topic)
        consume_forever(consumer, self._handle_record, "upsert device sighting")

    @staticmethod
    def _handle_record(value: bytes) -> None:
        event = json.loads(value)
        if event.get("op") == "upsert":
            Command._upsert(event)

    @staticmethod
    def _upsert(event: dict) -> None:
        try:
            mesh = Mesh.objects.get(pk=event["mesh_id"])
        except (Mesh.DoesNotExist, ValueError):
            return
        device, _ = Device.objects.get_or_create(
            # is_gateway defaults to False on the model (an auto-discovered
            # sighting is always a node)
            mesh=mesh, device_id=int(event["device_id"]), defaults={"is_allowed": True}
        )
        device.last_seen = timezone.now()
        update_fields = ["last_seen"]
        if "latitude" in event and "longitude" in event and not device.location_overridden:
            device.latitude = event["latitude"]
            device.longitude = event["longitude"]
            update_fields += ["latitude", "longitude"]
        if not device.nodeinfo_overridden:
            for key in ("name", "short_name", "hardware_type", "role"):
                if key in event:
                    setattr(device, key, event[key])
                    update_fields.append(key)
        device.save(update_fields=update_fields)
