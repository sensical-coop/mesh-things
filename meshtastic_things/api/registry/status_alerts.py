"""Tell operators who opted in when a source stays disconnected or a sink has nobody connected.

Each lifecycle pass reads EMQX's view and keeps, in the cache, when a problem was first
seen. The operator is emailed once per outage, after it lasts the configured hours, and
again only after it recovers and fails anew. State expires a week after the last pass
that saw the problem, so deleted sources and sinks leave nothing behind.
"""
from datetime import datetime, timedelta

import structlog
from django.conf import settings
from django.core.cache import cache
from django.db.models import Exists, OuterRef

from common.env import env_str

from .emailing import send_sink_unused_email, send_source_disconnected_email
from .emqx_client import get_emqx_client
from .models import DeviceSink, MeshSink, Sink, Source

log = structlog.get_logger()

STATE_SECONDS = 7 * 24 * 3600


def _keys(kind: str, obj_id) -> tuple[str, str]:
    return f"registry:status-down:{kind}:{obj_id}", f"registry:status-alerted:{kind}:{obj_id}"


def _outage_due(kind: str, obj_id, down: bool, now: datetime, hours: int) -> datetime | None:
    """When the outage started, if it has lasted `hours` and is not reported yet."""
    down_key, alerted_key = _keys(kind, obj_id)
    if not down:
        cache.delete_many([down_key, alerted_key])
        return None
    since = datetime.fromisoformat(cache.get(down_key) or now.isoformat())
    cache.set(down_key, since.isoformat(), timeout=STATE_SECONDS)
    if cache.get(alerted_key):
        cache.touch(alerted_key, timeout=STATE_SECONDS)
        return None
    return since if now - since >= timedelta(hours=hours) else None


def _alerted(kind: str, obj_id, send, *args) -> bool:
    try:
        send(*args)
    except Exception as e:
        log.warning("status_alert_failed", kind=kind, id=str(obj_id), error=str(e))
        return False
    cache.set(_keys(kind, obj_id)[1], "1", timeout=STATE_SECONDS)
    return True


def check_sources(now: datetime) -> int:
    """Email the operator, if opted in, of every source not connected for SOURCE_ALERT_HOURS."""
    if not settings.SOURCE_ALERT_HOURS or not env_str("REGISTRY__EMQX_API_URL"):
        return 0
    try:
        statuses = get_emqx_client().source_statuses()
    except Exception as e:
        log.warning("source_statuses_unavailable", error=str(e))
        return 0
    sent = 0
    sources = Source.objects.filter(paused_at__isnull=True, created_by__status_alerts_enabled=True)
    for source in sources.select_related("created_by"):
        status = statuses.get(str(source.id), "missing")
        since = _outage_due("source", source.id, status != "connected", now, settings.SOURCE_ALERT_HOURS)
        if since and _alerted("source", source.id, send_source_disconnected_email, source, status, since):
            log.warning("source_disconnected", source_id=str(source.id), status=status, since=since.isoformat())
            sent += 1
    return sent


def check_sinks(now: datetime) -> int:
    """Email the operator, if opted in, of every sink in use nobody has been connected to for SINK_ALERT_HOURS.

    A sink counts as in use while it has a mesh or a device attached.
    """
    if not settings.SINK_ALERT_HOURS or not env_str("REGISTRY__EMQX_API_URL"):
        return 0
    try:
        connections = get_emqx_client().sink_connections()
    except Exception as e:
        log.warning("sink_connections_unavailable", error=str(e))
        return 0
    sinks = (
        Sink.objects.filter(paused_at__isnull=True, created_by__status_alerts_enabled=True)
        .annotate(
            has_meshes=Exists(MeshSink.objects.filter(sink=OuterRef("pk"))),
            has_devices=Exists(DeviceSink.objects.filter(sink=OuterRef("pk"))),
        )
        .select_related("created_by")
    )
    sent = 0
    for sink in sinks:
        unused = (sink.has_meshes or sink.has_devices) and not connections.get(str(sink.id))
        since = _outage_due("sink", sink.id, unused, now, settings.SINK_ALERT_HOURS)
        if since and _alerted("sink", sink.id, send_sink_unused_email, sink, since):
            log.warning("sink_unused", sink_id=str(sink.id), since=since.isoformat())
            sent += 1
    return sent
