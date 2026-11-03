"""Republish every device's postprocessing plans to mesh.postprocessing_config.v1

The topic is compacted and rebuilt from Postgres, so this recovers it after it
is lost or after plans change shape between releases.

  python manage.py publish_postprocessing_config
"""
from django.core.management.base import BaseCommand

from registry import postprocessing
from registry.models import Device


class Command(BaseCommand):
    help = "Republish the postprocessing plans of every device that has any."

    def handle(self, *args, **options):
        devices = Device.objects.filter(postprocessings__isnull=False).distinct().select_related("mesh")
        published = 0
        for device in devices:
            postprocessing.publish_device(device)
            published += 1
        self.stdout.write(f"Published postprocessing plans for {published} device(s)")
