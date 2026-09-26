"""Celery tasks: the scheduling/IO shell around executor.py's pure logic."""
import os

import structlog
from celery import shared_task

from common.channels import DERIVED_KIND, QUALITY_KIND
from common.detectors import COMPLETENESS
from common.units import QUALITY_CHANNELS
from common.influx_query import duration_seconds, split_channel

from .alarms import build_alarm, get_alarm_publisher
from .executor import (
    align_series,
    analyse_completeness,
    completeness_applies,
    derived_reading_interval,
    resolve_output_units,
    run_steps,
)
from .influx_io import get_influx_io
from .registry_client import get_registry_client

log = structlog.get_logger()

# Blueprints get the longer window because their
# algorithms are the reason this to exist in the first place.
BLUEPRINT_LOOKBACK = os.environ.get("QUALITY_WORKER__BLUEPRINT_LOOKBACK", "-7d")
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

# TODO Here we should store last postprocessing date, so that we can recover failing jobs later
@shared_task(name="quality_worker.tasks.scan_devices")
def scan_devices() -> dict:
    """Enqueues per-device work"""
    client = get_registry_client()
    devices = client.devices(is_allowed="true")
    blueprint_runs = completeness_runs = 0
    for device in devices:
        if device.get("postprocessing_blueprint_id"):
            run_blueprint.delay(device["uuid"])
            blueprint_runs += 1
        check_completeness.delay(device["uuid"])
        completeness_runs += 1
    log.info("scan_complete", devices=len(devices), blueprints=blueprint_runs, completeness=completeness_runs)
    return {"devices": len(devices), "blueprint_runs": blueprint_runs, "completeness_runs": completeness_runs}


@shared_task(name="quality_worker.tasks.run_blueprint")
def run_blueprint(device_uuid: str, lookback: str | None = None) -> dict:
    """Load the device's referenced channels, align them, run every step in
    order, and write the derived channels back."""
    lookback = lookback or BLUEPRINT_LOOKBACK
    registry, influx = get_registry_client(), get_influx_io()

    devices = {d["uuid"]: d for d in registry.devices()}
    device = devices.get(device_uuid)
    if device is None:
        log.warning("device_not_found", device_uuid=device_uuid)
        return {"status": "device_not_found"}
    blueprint_id = device.get("postprocessing_blueprint_id")
    if not blueprint_id:
        return {"status": "no_blueprint"}

    blueprint = registry.blueprint(blueprint_id)
    steps = blueprint.get("steps") or []
    mesh_id, device_id = device["mesh_id"], device["node_id"]

    # Only load channels that no other step produces - the rest come from the
    # namespace as the run proceeds.
    produced = {channel for step in steps for channel in (step.get("outputs") or {}).values()}
    required = {
        channel
        for step in steps
        for channel in (step.get("inputs") or {}).values()
        if channel not in produced
    }

    named_series = {}
    for channel in sorted(required):
        try:
            series = influx.read_channel(mesh_id, device_id, channel, lookback)
        except ValueError as e:
            log.warning("invalid_channel_reference", channel=channel, error=str(e))
            return {"status": "invalid_channel", "channel": channel}
        if not series:
            log.info("channel_has_no_data", channel=channel, device_id=device_id)
            return {"status": "no_data", "channel": channel}
        named_series[channel] = series

    variant_intervals = _variant_intervals()
    interval = _reading_interval_for(device, None, variant_intervals) or 60
    rows = align_series(named_series, interval)
    if not rows:
        return {"status": "no_aligned_rows"}

    outputs = run_steps(steps, rows)

    written = 0
    step_order_by_channel = {
        channel: step["order"] for step in steps for channel in (step.get("outputs") or {}).values()
    }
    for channel, series in outputs.items():
        written += influx.write_derived(
            mesh_id, device_id, blueprint_id, step_order_by_channel.get(channel, 0), channel, series
        )
    # Register the derived channels against this device, so they show up in
    # GET /devices/{id}/measurements


    # Units come with them
    if outputs:
        catalog_units = {
            row["channel"]: row.get("native_unit")
            for row in registry.measurement_types()
            if row.get("channel")
        }
        get_alarm_publisher().publish_discovery(
            mesh_id, device_id, DERIVED_KIND, list(outputs), resolve_output_units(steps, catalog_units)
        )

    log.info(
        "blueprint_complete",
        device_id=device_id,
        blueprint=blueprint["name"],
        rows=len(rows),
        channels=len(outputs),
        points=written,
    )
    return {
        "status": "ok",
        "rows": len(rows),
        "channels": sorted(outputs),
        "points_written": written,
    }


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
