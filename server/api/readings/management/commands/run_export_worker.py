import structlog
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from readings import export_worker, exports

log = structlog.get_logger()


class Command(BaseCommand):
    help = "Build queued exports one at a time, failing those a stopped worker left behind."

    def handle(self, *args, **options):
        if not (settings.ARCHIVE_BUCKET and settings.EXPORT_ACCESS_KEY and settings.EXPORT_SECRET_KEY):
            raise ImproperlyConfigured(
                "Exports need READINGS__ARCHIVE_BUCKET, READINGS__EXPORT_ACCESS_KEY and READINGS__EXPORT_SECRET_KEY"
            )
        log.info("export_worker_started")
        while True:
            export_worker.recover()
            job = exports.take(timeout=5)
            if job:
                close_old_connections()
                export_worker.run(job)
