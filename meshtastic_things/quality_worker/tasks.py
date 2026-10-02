"""Celery tasks: the scheduling/IO shell around executor.py's pure logic."""
import os

import structlog
from celery import shared_task

from common.channels import QUALITY_KIND
from common.detectors import COMPLETENESS
from common.influx_query import duration_seconds
from common.postprocessing import ResolvedPlan
from common.units import QUALITY_CHANNELS

from .alarms import build_alarm, get_alarm_publisher
from .executor import (
    analyse_completeness,
    backfill_batches,
    backfill_channels,
    completeness_applies,
    derived_reading_interval,
)
from .influx_io import get_influx_io
from .registry_client import get_registry_client

log = structlog.get_logger()

COMPLETENESS_LOOKBACK = os.environ.get("QUALITY_WORKER__COMPLETENESS_LOOKBACK", "-24h")
# Below this fraction of expected samples, the history is patchy enough to alarm.
COMPLETENESS_THRESHOLD = float(os.environ.get("QUALITY_WORKER__COMPLETENESS_THRESHOLD", "0.8"))
# A gap longer than this many reading intervals is a fault on its own, even if
# the overall ratio still looks healthy.
GAP_INTERVALS_THRESHOLD = float(os.environ.get("QUALITY_WORKER__GAP_INTERVALS_THRESHOLD", "3"))

# The fields write_quality_metric emits and their units
QUALITY_FIELDS = tuple(QUALITY_CHANNELS)
QUALITY_FIELD_UNITS = {field: unit for field, (unit, _) in QUALITY_CHANNELS.items()}


def _variant_intervals() -> dict[str, int | None]:
    """payload_kind -> default_reading_interval_seconds, the per-device fallback."""
    return {
        variant["payload_kind"]: variant.get("default_reading_interval_seconds")
        for variant in get_registry_client().telemetry_variants()
    }


def _reading_interval_for(device: dict, payload_kind: str | None, variant_intervals: dict) -> int | None:
    if device.get("reading_interval_seconds"):
        return device["reading_interval_seconds"]
    if payload_kind:
        return variant_intervals.get(payload_kind)
    return None

@shared_task(name="quality_worker.tasks.scan_devices")
def scan_devices() -> dict:
    """Enqueues per-device work"""
    devices = get_registry_client().devices(is_allowed="true")
    for device in devices:
        check_completeness.delay(device["uuid"])
    log.info("scan_complete", devices=len(devices))
    return {"devices": len(devices), "completeness_runs": len(devices)}


@shared_task(name="quality_worker.tasks.dispatch_backfills")
def dispatch_backfills() -> dict:
    """Enqueue every pending backfill. A backfill queued twice runs once, since
    only one run can claim it."""
    pending = get_registry_client().pending_backfills()
    for backfill in pending:
        run_backfill.delay(backfill["id"])
    return {"dispatched": len(pending)}


@shared_task(name="quality_worker.tasks.run_backfill")
def run_backfill(backfill_id: str) -> dict:
    """Recompute a postprocessing over stored history and publish the results
    to the derived topic, which stores and archives them like live values."""
    registry = get_registry_client()
    claimed = registry.claim_backfill(backfill_id)
    if claimed is None:
        return {"status": "not_claimed"}

    published = 0
    try:
        plans = [ResolvedPlan.from_dict(plan) for plan in claimed["plans"]]
        mesh_id, node_id = claimed["mesh_id"], claimed["node_id"]
        influx, publisher = get_influx_io(), get_alarm_publisher()
        series = {
            channel: influx.read_range(mesh_id, node_id, channel, claimed["start"], claimed["stop"])
            for channel in sorted(backfill_channels(plans))
        }
        failures = {}
        for events, batch_failures in backfill_batches(plans, series, mesh_id, node_id):
            publisher.publish_derived(events)
            published += sum(len(event["payload"]["derived"]) for event in events)
            for key, (count, first) in batch_failures.items():
                seen, earliest = failures.get(key, (0, first))
                failures[key] = (seen + count, earliest)
        for key, (count, first) in failures.items():
            log.warning("backfill_rows_skipped", backfill_id=backfill_id, step=key, rows=count, error=first)
    except Exception as e:
        log.exception("backfill_failed", backfill_id=backfill_id)
        registry.finish_backfill(backfill_id, "failed", published, f"{type(e).__name__}: {e}")
        return {"status": "failed", "points_published": published}

    registry.finish_backfill(backfill_id, "done", published)
    log.info("backfill_complete", backfill_id=backfill_id, points=published)
    return {"status": "done", "points_published": published}


@shared_task(name="quality_worker.tasks.check_completeness")
def check_completeness(device_uuid: str, lookback: str | None = None) -> dict:
    """Device completeness check"""

    lookback = lookback or COMPLETENESS_LOOKBACK
    registry, influx = get_registry_client(), get_influx_io()

    devices = {d["uuid"]: d for d in registry.devices()}
    device = devices.get(device_uuid)
    if device is None:
        return {"status": "device_not_found"}

    mesh_id, device_id = device["mesh_id"], device["node_id"]
    if not mesh_id:
        return {"status": "no_mesh_id"}

    variant_intervals = _variant_intervals()
    window = duration_seconds(lookback)
    publisher = get_alarm_publisher()
    results = []

    rows = registry.device_measurements(device_uuid)
    rows_by_id = {row["id"]: row for row in rows}
    bindings = {}
    if any(row.get("produced_by") for row in rows):
        bindings = {pp["id"]: pp["input_bindings"] for pp in registry.device_postprocessings(device_uuid)}

    def interval_for_kind(payload_kind):
        return _reading_interval_for(device, payload_kind, variant_intervals)

    for row in rows:
        measurement_type = row["measurement_type"]
        if not completeness_applies(measurement_type):
            continue
        channel = measurement_type["channel"]
        interval = interval_for_kind(measurement_type["payload_kind"])
        if not interval and row.get("produced_by"):
            interval = derived_reading_interval(row["produced_by"], rows_by_id, bindings, interval_for_kind)
        if not interval:
            continue
        # Resolved server-side, so this worker cannot drift from the stream job.
        alarm_on_gaps = COMPLETENESS in (row.get("effective_detectors") or [])
        try:
            series = influx.read_channel(mesh_id, device_id, channel, lookback)
        except ValueError:
            continue
        stats = analyse_completeness(series, window, interval)
        influx.write_quality_metric(
            mesh_id,
            device_id,
            channel,
            {
                "completeness_ratio": stats["ratio"],
                "observed": stats["observed"],
                "expected": stats["expected"],
                "largest_gap_seconds": stats["largest_gap_seconds"],
            },
        )
        results.append({"channel": channel, **stats})

        # The metric is always written; only the alarm is opt-in.
        gap_limit = interval * GAP_INTERVALS_THRESHOLD
        if not alarm_on_gaps:
            continue
        if stats["ratio"] < COMPLETENESS_THRESHOLD:
            publisher.publish(
                build_alarm(
                    mesh_id,
                    device_id,
                    channel,
                    detector="completeness",
                    value=stats["ratio"],
                    message=(
                        f"Only {stats['observed']} of ~{stats['expected']} expected readings in "
                        f"{lookback} ({stats['ratio']:.0%}) - the device published, but its "
                        f"history has gaps at the configured {interval}s reading interval"
                    ),
                )
            )
        elif stats["largest_gap_seconds"] > gap_limit:
            publisher.publish(
                build_alarm(
                    mesh_id,
                    device_id,
                    channel,
                    detector="completeness",
                    value=stats["largest_gap_seconds"],
                    message=(
                        f"Overall completeness is fine but there is a "
                        f"{stats['largest_gap_seconds']:.0f}s hole, over "
                        f"{GAP_INTERVALS_THRESHOLD:g}x the {interval}s reading interval"
                    ),
                )
            )

    # Register the quality channels against this device so they appear in
    # GET /devices/{id}/measurements too
    if results:
        publisher.publish_discovery(mesh_id, device_id, QUALITY_KIND, list(QUALITY_FIELDS), QUALITY_FIELD_UNITS)

    return {"status": "ok", "channels": results}
