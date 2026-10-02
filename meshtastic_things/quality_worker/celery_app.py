"""Celery app for the batch tier

This exists for work that fundamentally needs history: gap analysis that can
only be seen across a window, and postprocessing backfills over stored data.
Per-point checks and live postprocessing belong in Flink instead.
"""
import os

from celery import Celery
from celery.schedules import crontab

BROKER_URL = os.environ.get("QUALITY_WORKER__REDIS_URL", "redis://redis:6379/2")
SCAN_INTERVAL_SECONDS = float(os.environ.get("QUALITY_WORKER__SCAN_INTERVAL_SECONDS", 3600))
BACKFILL_POLL_SECONDS = float(os.environ.get("QUALITY_WORKER__BACKFILL_POLL_SECONDS", 60))

app = Celery("quality_worker", broker=BROKER_URL, backend=BROKER_URL)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "scan-devices": {
            "task": "quality_worker.tasks.scan_devices",
            "schedule": SCAN_INTERVAL_SECONDS,
        },
        "dispatch-backfills": {
            "task": "quality_worker.tasks.dispatch_backfills",
            "schedule": BACKFILL_POLL_SECONDS,
        },
        # Yesterday's alarm counts, once the day's last alarms have been written.
        "count-alarms": {
            "task": "quality_worker.tasks.count_alarms",
            "schedule": crontab(hour=0, minute=30),
        },
    },
)

# Registers the tasks named in beat_schedule above.
from quality_worker import tasks  # noqa: E402,F401
