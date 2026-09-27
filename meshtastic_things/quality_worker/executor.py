"""Pure logic of the batch tier: completeness analysis and postprocessing backfills.

Kept free of IO so it is testable without Celery, InfluxDB or Kafka; tasks.py
is the shell around it.
"""
from datetime import datetime

from common.channels import DERIVED_KIND, ORIGIN_MEASURED
from common.postprocessing import Observation, ResolvedPlan, apply
from common.postprocessing.stream import derived_events

# Observations run through the engine, and derived events published, per batch.
BACKFILL_BATCH_SIZE = 5000


def backfill_channels(plans: list[ResolvedPlan]) -> set[str]:
    """Channels a backfill reads from storage: every input the plans do not produce themselves."""
    produced = {channel for plan in plans for channel in plan.output_channels}
    return {channel for plan in plans for channel in plan.input_channels} - produced


def backfill_batches(
    plans: list[ResolvedPlan],
    series_by_channel: dict[str, list[tuple[datetime, float]]],
    mesh_id: str,
    node_id: int,
    batch_size: int = BACKFILL_BATCH_SIZE,
):
    """Run stored history through the plans, yielding (derived events, failures) per batch.

    Every channel is merged into one time-ordered stream first, which is the
    order the stream joiner expects, and join state carries across batches.
    """
    observations = sorted(
        (
            Observation(channel, time.timestamp(), value)
            for channel, series in series_by_channel.items()
            for time, value in series
        ),
        key=lambda o: o.time,
    )
    state: dict = {}
    for i in range(0, len(observations), batch_size):
        result = apply(plans, state, observations[i:i + batch_size])
        yield derived_events(mesh_id, node_id, result.derived, plans, backfill=True), result.failures


def completeness_applies(measurement_type: dict) -> bool:
    """Sensor channels and derived ones, which are held to their inputs'
    reading interval. Device diagnostics and quality metrics are not."""
    return measurement_type["origin"] == ORIGIN_MEASURED or measurement_type["payload_kind"] == DERIVED_KIND


def derived_reading_interval(
    produced_by: str,
    rows_by_id: dict[str, dict],
    bindings_by_postprocessing: dict[str, dict[str, str]],
    interval_for_kind,
    seen: frozenset = frozenset(),
) -> int | None:
    """Expected interval of a derived channel: its slowest input's, since a
    derived sample needs every input at once. Follows chained postprocessings.

    Args:
        produced_by: The postprocessing producing the channel.
        rows_by_id: The device's measurement rows by id.
        bindings_by_postprocessing: {postprocessing id: {slot: measurement id}}.
        interval_for_kind: Reading interval of a sensor channel's payload_kind.
    """
    if produced_by in seen:
        return None
    intervals = []
    for measurement_id in bindings_by_postprocessing.get(produced_by, {}).values():
        row = rows_by_id.get(measurement_id)
        if row is None:
            continue
        if row.get("produced_by"):
            interval = derived_reading_interval(
                row["produced_by"], rows_by_id, bindings_by_postprocessing, interval_for_kind, seen | {produced_by}
            )
        else:
            interval = interval_for_kind(row["measurement_type"]["payload_kind"])
        if interval:
            intervals.append(interval)
    return max(intervals) if intervals else None


def analyse_completeness(
    series: list[tuple], window_seconds: int, reading_interval_seconds: int
) -> dict:
    """Returns observed/expected counts, and the largest
    gap in seconds.
    """
    expected = max(1, int(window_seconds // max(1, reading_interval_seconds)))
    observed = len(series)
    largest_gap = 0.0
    if len(series) >= 2:
        for (earlier, _), (later, _) in zip(series, series[1:]):
            largest_gap = max(largest_gap, (later - earlier).total_seconds())
    return {
        "observed": observed,
        "expected": expected,
        # Capped at 1.0: more samples than expected (faster than expected)
        "ratio": min(1.0, observed / expected) if expected else 0.0,
        "largest_gap_seconds": largest_gap,
    }
