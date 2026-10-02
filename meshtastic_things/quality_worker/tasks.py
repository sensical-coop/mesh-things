"""Celery tasks: the scheduling/IO shell around executor.py's pure logic."""
import os
from datetime import datetime, timedelta, timezone

import structlog
from celery import shared_task

from common.alarm_counts import ALARM_COUNTS_BUCKET, ALARMS_BUCKET, ALARMS_RETENTION_DAYS, DAY, daily_counts
from common.channels import QUALITY_KIND
from common.detectors import ABSENCE, COMPLETENESS
from common.influx_query import duration_seconds
from common.postprocessing import ResolvedPlan
from common.units import QUALITY_CHANNELS

from .alarm_memory import get_alarm_memory
from .alarms import build_alarm, get_alarm_publisher
from .executor import (
    analyse_completeness,
    backfill_batches,
    backfill_channels,
    completeness_applies,
    derived_reading_interval,
    gaps_over,
    silent_seconds,
)
from .influx_io import get_influx_io
from .registry_client import get_registry_client

log = structlog.get_logger()

COMPLETENESS_LOOKBACK = os.environ.get("QUALITY_WORKER__COMPLETENESS_LOOKBACK", "-24h")
# Below this fraction of expected samples, the history is patchy enough to alarm.
COMPLETENESS_THRESHOLD = float(os.environ.get("QUALITY_WORKER__COMPLETENESS_THRESHOLD", "0.8"))
# A gap longer than this many reading intervals, and than GAP_MIN_SECONDS, is a
# fault on its own, even if the overall ratio still looks healthy.
GAP_INTERVALS_THRESHOLD = float(os.environ.get("QUALITY_WORKER__GAP_INTERVALS_THRESHOLD", "6"))
GAP_MIN_SECONDS = float(os.environ.get("QUALITY_WORKER__GAP_MIN_SECONDS", "1800"))
# A low ratio is re-raised at most this often while it stays low.
RATIO_ALARM_REPEAT_SECONDS = 24 * 3600
# Below this many expected readings, a few lost packets already look like a low ratio.
RATIO_MIN_EXPECTED = int(os.environ.get("QUALITY_WORKER__RATIO_MIN_EXPECTED", "24"))
# Mirrors the absence job, whose alarm already covers a silence this long.
ABSENCE_MISSED_INTERVALS = float(os.environ.get("ABSENCE_DETECTION__MISSED_INTERVALS", "3"))
ABSENCE_MIN_SECONDS = 60

# The fields write_quality_metric emits and their units
QUALITY_FIELDS = tuple(QUALITY_CHANNELS)
QUALITY_FIELD_UNITS = {field: unit for field, (unit, _) in QUALITY_CHANNELS.items()}


def _variant_intervals() -> dict[str, int | None]:
    """payload_kind -> default_reading_interval_seconds, the per-device fallback."""
    return {
        variant["payload_kind"]: variant.get("default_reading_interval_seconds")
        for variant in get_registry_client().telemetry_variants()
    }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _absence_limit(device: dict) -> float | None:
    """Seconds of silence after which the absence job alarms on this device, if it watches it."""
    interval = device.get("publish_interval_seconds") or device.get("reading_interval_seconds")
    if not device.get("absence_detection_enabled") or not interval:
        return None
    return max(ABSENCE_MIN_SECONDS, interval * ABSENCE_MISSED_INTERVALS)


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
    now = _utcnow()
    publisher, memory = get_alarm_publisher(), get_alarm_memory()
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
        if not alarm_on_gaps:
            continue
        alarm_key = f"{mesh_id}:{device_id}:{channel}"
        gap_limit = max(interval * GAP_INTERVALS_THRESHOLD, GAP_MIN_SECONDS)
        absence_limit = _absence_limit(device)
        # Every gap is marked seen, so one hidden behind a low ratio does not alarm later.
        new_gaps = [
            (start, end)
            for start, end in gaps_over(series, gap_limit)
            if memory.first_time(f"gap:{alarm_key}:{int(end.timestamp())}", ttl_seconds=window)
            and not (absence_limit and (end - start).total_seconds() >= absence_limit)
        ]
        silent_now = not series or (now - series[-1][0]).total_seconds() > gap_limit
        # Time the absence alarm already reported is not counted against the ratio.
        excluded = silent_seconds(series, now - timedelta(seconds=window), absence_limit) if absence_limit else 0
        expected = max(1, int((window - excluded) // interval))
        ratio = min(1.0, stats["observed"] / expected)
        if ratio < COMPLETENESS_THRESHOLD and expected >= RATIO_MIN_EXPECTED and not silent_now:
            if not memory.first_time(f"ratio:{alarm_key}", ttl_seconds=RATIO_ALARM_REPEAT_SECONDS):
                continue
            publisher.publish(
                build_alarm(
                    mesh_id,
                    device_id,
                    channel,
                    detector="completeness",
                    value=ratio,
                    message=(
                        f"Only {stats['observed']} of ~{expected} expected readings in "
                        f"{lookback} ({ratio:.0%}) - the device published, but its "
                        f"history has gaps at the configured {interval}s reading interval"
                    ),
                )
            )
        elif new_gaps:
            start, end = max(new_gaps, key=lambda gap: gap[1] - gap[0])
            gap_seconds = (end - start).total_seconds()
            publisher.publish(
                build_alarm(
                    mesh_id,
                    device_id,
                    channel,
                    detector="completeness",
                    value=gap_seconds,
                    message=(
                        f"No readings from {start.isoformat()} to {end.isoformat()} "
                        f"({gap_seconds:.0f}s, limit {gap_limit:.0f}s at the {interval}s reading interval)"
                    ),
                )
            )

    # Register the quality channels against this device so they appear in
    # GET /devices/{id}/measurements too
    if results:
        publisher.publish_discovery(mesh_id, device_id, QUALITY_KIND, list(QUALITY_FIELDS), QUALITY_FIELD_UNITS)

    return {"status": "ok", "channels": results}


def _day_start(day: str | None) -> datetime:
    """Midnight UTC of `day` (YYYY-MM-DD), or of yesterday."""
    if day:
        return datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return _utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - DAY


def absence_silences(influx, day_start: datetime) -> dict[tuple[str, str], list[tuple[datetime, datetime]]]:
    """Per device, the intervals from each absence alarm to its next reading that reach into the day.

    A device still silent at the end of the day is silent until then.
    """
    day_end = day_start + DAY
    silences: dict[tuple[str, str], list[tuple[datetime, datetime]]] = {}
    for alarm in influx.read_alarms(ALARMS_BUCKET, day_end - ALARMS_RETENTION_DAYS * DAY, day_end, detector=ABSENCE):
        back = influx.first_reading_after(alarm["mesh_id"], alarm["node_id"], alarm["time"], day_end) or day_end
        if back > day_start:
            silences.setdefault((alarm["mesh_id"], alarm["node_id"]), []).append((alarm["time"], back))
    return silences


@shared_task(name="quality_worker.tasks.count_alarms")
def count_alarms(day: str | None = None) -> dict:
    """Write one UTC day's alarm counts, yesterday's by default. Rerunning a day replaces its counts."""
    day_start = _day_start(day)
    influx = get_influx_io()
    alarms = influx.read_alarms(ALARMS_BUCKET, day_start, day_start + DAY)
    rows = daily_counts(alarms, day_start, absence_silences(influx, day_start))
    influx.write_alarm_counts(ALARM_COUNTS_BUCKET, day_start, rows)
    log.info("alarm_counts_written", day=day_start.date().isoformat(), rows=len(rows), alarms=len(alarms))
    return {"day": day_start.date().isoformat(), "rows": len(rows)}
