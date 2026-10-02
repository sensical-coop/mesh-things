"""Republish every archived device's sinks to mesh.sink_config.v1

The topic is compacted and rebuilt from Postgres, so this recovers it after it
is lost, or after a role changed outside the API (the admin, createsuperuser).

  python manage.py publish_sink_config
"""
from django.core.management.base import BaseCommand

from registry import sinks
from registry.models import Device


class Command(BaseCommand):
    help = "Republish the sinks of every device that opted in to one."

    def handle(self, *args, **options):
        published = 0
        for device in Device.objects.filter(archive_enabled=True).select_related("mesh__owner"):
            sinks.publish_device(device)
            published += 1
        self.stdout.write(f"Published sinks for {published} device(s)")
