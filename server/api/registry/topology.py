"""Stores traceroutes and RF links from decoded packets and mesh_stats_writer's direct links."""
from datetime import datetime, timedelta, timezone as dt_timezone

from django.db import transaction
from django.db.models import F
from django.db.models.functions import Greatest, Least
from django.utils import timezone

from common.topology import (
    NEIGHBORINFO,
    NEIGHBORINFO_PORTNUM,
    TRACEROUTE,
    TRACEROUTE_PORTNUM,
    UNKNOWN_SNR,
    neighborinfo_links,
    snr_db,
    traceroute_links,
    traceroute_paths,
)
from registry.models import Mesh, RfLink, Traceroute

RETENTION = timedelta(days=30)


def record_decoded(event: dict, now: datetime | None = None) -> None:
    """Keep what a decoded traceroute or neighbor info packet says about the mesh."""
    portnum = event.get("portnum")
    if portnum not in (TRACEROUTE_PORTNUM, NEIGHBORINFO_PORTNUM) or not event.get("mesh_id"):
        return
    if not Mesh.objects.filter(pk=event["mesh_id"]).exists():
        return
    now = now or timezone.now()
    if portnum == TRACEROUTE_PORTNUM:
        record_traceroute(event, now)
    else:
        for from_node, to_node, snr in neighborinfo_links(event):
            add_link(event["mesh_id"], from_node, to_node, NEIGHBORINFO, 1, snr, snr, now, now)


@transaction.atomic
def record_traceroute(event: dict, now: datetime) -> None:
    """Store a traceroute once, and count each of its hops as a link once.

    Gateways hear a traceroute at different points of its journey, each copy
    with the hops taken so far. The longest route seen is kept, and only hops
    the stored copy did not already hold are added as links.
    """
    payload = event.get("payload") or {}
    stored = (
        Traceroute.objects.select_for_update()
        .filter(mesh_id=event["mesh_id"], from_node=event["node_id"], packet_id=event["packet_id"])
        .first()
    )
    known = set()
    if stored is not None:
        known = set(traceroute_links(traceroute_paths(as_event(stored))))
    else:
        stored = Traceroute(
            mesh_id=event["mesh_id"],
            from_node=event["node_id"],
            to_node=event.get("to") or 0,
            packet_id=event["packet_id"],
            request_id=event.get("request_id"),
            heard_at=now,
        )

    route, route_back = payload.get("route") or [], payload.get("route_back") or []
    snr_towards, snr_back = snr_db(payload.get("snr_towards") or []), snr_db(payload.get("snr_back") or [])
    if len(snr_towards) >= len(stored.snr_towards):
        stored.route, stored.snr_towards = route, snr_towards
    if len(snr_back) >= len(stored.snr_back):
        stored.route_back, stored.snr_back = route_back, snr_back
    gateway = event.get("gateway_id")
    if gateway is not None and gateway not in stored.gateway_ids:
        stored.gateway_ids = [*stored.gateway_ids, gateway]
    stored.save()

    for from_node, to_node, snr in traceroute_links(traceroute_paths(event)):
        if (from_node, to_node, snr) not in known:
            add_link(event["mesh_id"], from_node, to_node, TRACEROUTE, 1, snr, snr, now, now)


def as_event(stored: Traceroute) -> dict:
    """A stored traceroute in the decoded shape traceroute_paths reads, SNRs back in quarter-dB steps."""

    def scaled(snrs):
        return [UNKNOWN_SNR if v is None else round(v * 4) for v in snrs]

    return {
        "node_id": stored.from_node,
        "to": stored.to_node,
        "request_id": stored.request_id,
        "payload": {
            "route": stored.route,
            "snr_towards": scaled(stored.snr_towards),
            "route_back": stored.route_back,
            "snr_back": scaled(stored.snr_back),
        },
    }


def record_link(event: dict) -> None:
    """Add one of mesh_stats_writer's hourly direct-link summaries."""
    if not Mesh.objects.filter(pk=event["mesh_id"]).exists() or not event.get("samples"):
        return
    add_link(
        event["mesh_id"],
        event["from_node"],
        event["to_node"],
        event["source"],
        event["samples"],
        event["snr_sum"],
        event["snr_sum"] / event["samples"],
        _from_ms(event["first_seen"]),
        _from_ms(event["last_seen"]),
    )


def _from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=dt_timezone.utc)


def add_link(
    mesh_id, from_node: int, to_node: int, source: str, samples: int, snr_sum: float, last_snr: float,
    first_seen: datetime, last_seen: datetime,
) -> None:
    link, created = RfLink.objects.get_or_create(
        mesh_id=mesh_id,
        from_node=from_node,
        to_node=to_node,
        source=source,
        defaults={
            "samples": samples,
            "snr_sum": snr_sum,
            "last_snr": last_snr,
            "first_seen": first_seen,
            "last_seen": last_seen,
        },
    )
    if created:
        return
    RfLink.objects.filter(pk=link.pk).update(
        samples=F("samples") + samples,
        snr_sum=F("snr_sum") + snr_sum,
        first_seen=Least("first_seen", first_seen),
        last_seen=Greatest("last_seen", last_seen),
    )
    # Only a newer sample replaces the last SNR; a late summary keeps the current one.
    RfLink.objects.filter(pk=link.pk, last_seen__lte=last_seen).update(last_snr=last_snr)


def prune(now: datetime) -> int:
    """Delete traceroutes and links not heard within the retention period."""
    cutoff = now - RETENTION
    traceroutes, _ = Traceroute.objects.filter(heard_at__lt=cutoff).delete()
    links, _ = RfLink.objects.filter(last_seen__lt=cutoff).delete()
    return traceroutes + links
