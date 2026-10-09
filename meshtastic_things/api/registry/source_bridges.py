"""Keeping each source's EMQX bridge in step with the meshes and gateways that use it.

A change that can add a channel or gateway syncs inside its transaction, before it is
published to Kafka, so a refused bridge rolls it back rather than dropping that traffic.
A removal syncs after commit and only logs a failure: a bridge still passing a removed
gateway or channel costs bandwidth but changes nothing that is ingested. The lifecycle
pass reapplies every bridge, which repairs both.
"""
import structlog
from django.db import transaction

from common import node_ids

from .emqx_client import get_emqx_client
from .models import Device, Source

log = structlog.get_logger()


def channel_filters(source: Source) -> dict[str, list[str] | None]:
    """The channels the source must subscribe to, each mapped to the gateways its rule passes.

    A channel maps to None while one of its meshes discovers gateways, so every gateway
    on it reaches the bridge. A channel with neither is not subscribed at all.
    """
    channels: dict[str, list[str] | None] = {
        channel: None for channel in source.meshes.filter(discover_gateways=True).values_list("channel_id", flat=True)
    }
    gateways = Device.objects.filter(mesh__source=source, is_gateway=True, is_allowed=True)
    for channel, device_id in gateways.values_list("mesh__channel_id", "device_id"):
        if channel in channels and channels[channel] is None:
            continue
        channels.setdefault(channel, []).append(node_ids.to_hex(device_id))
    return channels


def sync_source(source: Source) -> None:
    """Apply the source's bridge. A paused source has none. Raises when EMQX refuses or cannot be reached."""
    if source.paused_at is not None:
        return
    get_emqx_client().apply_source(source, channel_filters(source))


def sync_sources(*source_ids) -> None:
    """Apply the bridges of the given sources; None, for the default broker, is skipped."""
    for source in Source.objects.filter(id__in={source_id for source_id in source_ids if source_id}):
        sync_source(source)


def sync_sources_after_commit(*source_ids) -> None:
    """Once the current transaction commits, apply the bridges of the given sources, logging failures."""
    ids = {source_id for source_id in source_ids if source_id}
    if ids:
        transaction.on_commit(lambda: _sync_logging_failures(Source.objects.filter(id__in=ids)))


def sync_all_sources() -> int:
    """Reapply every active source's bridge, logging failures. Returns how many failed."""
    return _sync_logging_failures(Source.objects.filter(paused_at__isnull=True))


def _sync_logging_failures(sources_qs) -> int:
    failed = 0
    for source in sources_qs:
        try:
            sync_source(source)
        except Exception as e:
            failed += 1
            log.warning("source_bridge_sync_failed", source_id=str(source.id), error=str(e))
    return failed
