"""Warn superusers before the disk fills up.

Inside a container, "/" is backed by the disk Docker keeps its images, logs and
volumes on, which is the one that fills.
"""
import shutil

import structlog
from django.conf import settings
from django.core.cache import cache

from .emailing import send_disk_space_email

log = structlog.get_logger()

ALERTED_KEY = "registry:disk-alerted"
ALERT_INTERVAL_SECONDS = 24 * 3600


def check_disk() -> bool:
    """Email every active superuser when the disk is fuller than DISK_ALERT_PERCENT, at most once a day."""
    if not settings.DISK_ALERT_PERCENT:
        return False
    usage = shutil.disk_usage(settings.DISK_ALERT_PATH)
    # As df reports it: blocks reserved for root count as neither used nor free.
    percent = usage.used * 100 / (usage.used + usage.free)
    if percent < settings.DISK_ALERT_PERCENT:
        return False
    try:
        first = cache.add(ALERTED_KEY, "1", timeout=ALERT_INTERVAL_SECONDS)
    except Exception as e:
        # Redis may be failing for the same reason; better an extra email than none.
        log.warning("disk_alert_cache_failed", error=str(e))
        first = True
    if not first:
        return False
    log.warning("disk_nearly_full", percent=round(percent, 1), free_bytes=usage.free)
    send_disk_space_email(percent, usage.free)
    return True
