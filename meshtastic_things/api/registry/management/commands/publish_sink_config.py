"""Republish every sink, and every device and mesh that uses one, to mesh.sink_config.v1

The topic is compacted and rebuilt from Postgres, so this recovers it after it
is lost, or after a role changed outside the API (the admin, createsuperuser).

  python manage.py publish_sink_config
"""
from django.core.management.base import BaseCommand

from registry import sinks
from registry.kafka_publisher import get_publisher
from registry.models import Device, Mesh, Sink


class Command(BaseCommand):
    help = "Republish every sink, and the sinks of every device and mesh that uses one."

    def handle(self, *args, **options):
        publisher = get_publisher()
        for sink in Sink.objects.all():
            publisher.publish_sink(sink.id, None if sink.paused_at else sink.streams)
        devices = sinks.with_sinks(Device.objects.select_related("mesh__owner"))
        for device in devices:
            sinks.publish_device(device)
        meshes = Mesh.objects.filter(sink_links__isnull=False).distinct().select_related("owner")
        for mesh in meshes:
            sinks.publish_mesh(mesh)
        self.stdout.write(f"Published {len(devices)} device(s) and {len(meshes)} mesh(es) with sinks")
