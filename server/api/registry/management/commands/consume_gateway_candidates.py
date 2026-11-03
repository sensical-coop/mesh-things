"""Background worker: registers gateways from the bridge's mesh.gateway_candidates.v1 samples

  python manage.py consume_gateway_candidates
"""
import json
import os

import structlog
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from kafka import KafkaConsumer

from registry.consumer_loop import consume_forever
from registry.exceptions import BadGateway
from registry.gateways import discover_gateway

log = structlog.get_logger()


class Command(BaseCommand):
    help = "Consume mesh.gateway_candidates.v1 and register gateways for meshes with discovery on"

    def handle(self, *args, **options):
        topic = os.environ.get("REGISTRY__GATEWAY_CANDIDATES_KAFKA_TOPIC", "mesh.gateway_candidates.v1")
        consumer = KafkaConsumer(
            bootstrap_servers=os.environ["KAFKA_BOOTSTRAP"],
            group_id="registry-gateway-discovery-group",
            enable_auto_commit=False,
            # Samples are retried by the bridge, so old ones are not worth replaying.
            auto_offset_reset="latest",
        )
        consumer.subscribe([topic])
        log.info("Starting gateway discovery consumer", topic=topic)
        consume_forever(consumer, self._handle_record, "discover gateway")

    @staticmethod
    def _handle_record(value: bytes) -> None:
        event = json.loads(value)
        try:
            discover_gateway(event)
        except IntegrityError:
            log.info("Gateway discovery raced another registration", gateway_id=event.get("gateway_id"))
        except BadGateway as e:
            log.warning("Gateway discovery could not publish", gateway_id=event.get("gateway_id"), error=str(e))
