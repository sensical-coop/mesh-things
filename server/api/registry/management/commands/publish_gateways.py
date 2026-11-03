"""Send the decoder every allowed gateway's current state again.

  python manage.py publish_gateways

Needed after a data migration changes what a gateway upsert carries, such as moving
meshes to another protocol version, since a migration does not publish to Kafka.
"""
from django.core.management.base import BaseCommand

from registry.kafka_publisher import get_publisher, publish_gateway_state
from registry.models import Device


class Command(BaseCommand):
    help = "Republish every allowed gateway on mesh.keys.v1"

    def handle(self, *args, **options):
        publisher = get_publisher()
        gateways = Device.objects.filter(is_gateway=True, is_allowed=True).select_related("mesh", "mesh__source")
        count = 0
        for gateway in gateways:
            publish_gateway_state(publisher, gateway, gateway.mesh)
            count += 1
        self.stdout.write(f"Published {count} gateway(s)")
