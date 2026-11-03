"""Background worker: stores traceroutes and RF links

  python manage.py consume_topology

Reads decoded packets for traceroutes and neighbor info, and mesh.links.v1 for
the direct links mesh_stats_writer summarises every hour.
"""
import json
import os

import structlog
from django.core.management.base import BaseCommand
from kafka import KafkaConsumer

from registry.consumer_loop import consume_forever
from registry.topology import record_decoded, record_link

log = structlog.get_logger()


class Command(BaseCommand):
    help = "Consume decoded packets and mesh.links.v1 into traceroutes and RF links"

    def handle(self, *args, **options):
        topics = [
            os.environ["PROTO_DECODE__KAFKA_TOPIC"],
            os.environ.get("MESH_STATS_WRITER__LINKS_KAFKA_TOPIC") or "mesh.links.v1",
        ]
        consumer = KafkaConsumer(
            bootstrap_servers=os.environ["KAFKA_BOOTSTRAP"],
            group_id="registry-topology-group",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        consumer.subscribe(topics)
        log.info("Starting topology consumer", topics=topics)
        consume_forever(consumer, self._handle_record, "store topology")

    @staticmethod
    def _handle_record(value: bytes) -> None:
        event = json.loads(value)
        # Direct-link summaries carry a source; decoded packets a portnum.
        if "source" in event:
            record_link(event)
        else:
            record_decoded(event)
