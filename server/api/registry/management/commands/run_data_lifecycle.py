import time

import structlog
from django.conf import settings
from django.core.management.base import BaseCommand

from registry.data_lifecycle import run_pass
from registry.data_store import get_data_store

log = structlog.get_logger()


class Command(BaseCommand):
    help = (
        "Send terms renewal notices, pause owners and sources whose terms lapsed, delete readings "
        "whose grace period ended, and expire archived readings with no mesh. Loops unless --once."
    )

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run one pass and exit.")

    def handle(self, *args, once: bool, **options):
        while True:
            try:
                result = run_pass()
                log.info("Data lifecycle pass", **result)
                if once:
                    self.stdout.write(", ".join(f"{k}={v}" for k, v in result.items()))
            except Exception as e:
                if once:
                    raise
                log.warning("Data lifecycle pass failed", error=str(e))
            if once:
                # Closed here, or the client's finaliser fails during interpreter shutdown.
                get_data_store().close()
                return
            time.sleep(settings.DATA_LIFECYCLE_INTERVAL_SECONDS)
