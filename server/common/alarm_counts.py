"""Alarm storage: each alarm for a limited time, and daily counts for good.

Counts are one point per UTC day per device, channel and detector:
  - hours_active: hours of the day the condition held. flat_value and range
    re-raise hourly while they hold, so these are the hours with an alarm;
    absence counts the hours from an alarm to the device's next reading.
  - new_conditions: alarms that started a condition rather than repeated one.
  - alarms: every alarm that day.
"""
import os
from collections import defaultdict
from datetime import datetime, timedelta

from mesh_things.detectors import ABSENCE, FLAT_VALUE, RANGE

ALARMS_BUCKET = os.environ.get("INFLUX__ALARMS_BUCKET") or "alarms"
ALARM_COUNTS_BUCKET = os.environ.get("INFLUX__ALARM_COUNTS_BUCKET") or "alarm_counts"
ALARMS_RETENTION_DAYS = int(os.environ.get("INFLUX__ALARMS_RETENTION_DAYS") or 30)

# Measurement of the daily counts.
ALARM_COUNTS = "alarm_counts"

# Detectors whose alarms repeat hourly while their condition holds.
HOURLY_DETECTORS = (FLAT_VALUE, RANGE)

DAY = timedelta(days=1)


def _overlap_hours(intervals: list[tuple[datetime, datetime]], start: datetime, end: datetime) -> float:
    """Hours of [start, end) covered by the union of `intervals`."""
    clipped = sorted((max(a, start), min(b, end)) for a, b in intervals if a < end and b > start)
    covered, cursor = timedelta(0), start
    for a, b in clipped:
        a = max(a, cursor)
        if b > a:
            covered += b - a
            cursor = b
    return covered.total_seconds() / 3600


def daily_counts(
    alarms: list[dict],
    day_start: datetime,
    silences: dict[tuple[str, str], list[tuple[datetime, datetime]]],
    know_repeats: bool = True,
) -> list[dict]:
    """The counts for one UTC day.

    Args:
        alarms: That day's alarms, each with time, mesh_id, node_id, channel,
            detector and repeat.
        day_start: Midnight UTC of the day.
        silences: Per (mesh_id, node_id), the intervals from each absence alarm
            to the device's next reading, which may start on an earlier day.
        know_repeats: False for alarms stored before repeats were marked, whose
            new_conditions cannot be told apart and are left out.

    Returns:
        One row per device, channel and detector with any alarm or silence.
    """
    day_end = day_start + DAY
    rows: dict[tuple, dict] = defaultdict(lambda: {"alarms": 0, "new_conditions": 0, "hours": set()})
    for alarm in alarms:
        key = (alarm["mesh_id"], alarm["node_id"], alarm.get("channel"), alarm["detector"])
        row = rows[key]
        row["alarms"] += 1
        if not alarm.get("repeat"):
            row["new_conditions"] += 1
        row["hours"].add(alarm["time"].replace(minute=0, second=0, microsecond=0))
    for (mesh_id, node_id), intervals in silences.items():
        hours = _overlap_hours(intervals, day_start, day_end)
        if hours:
            rows[(mesh_id, node_id, None, ABSENCE)]["silent_hours"] = hours

    out = []
    for (mesh_id, node_id, channel, detector), row in sorted(rows.items(), key=lambda kv: tuple(map(str, kv[0]))):
        counts = {"alarms": row["alarms"]}
        if know_repeats:
            counts["new_conditions"] = row["new_conditions"]
        if detector == ABSENCE:
            # Alarms stored before silences were measured still give the hours they covered.
            counts["hours_active"] = round(row.get("silent_hours", len(row["hours"])), 2)
        elif detector in HOURLY_DETECTORS:
            counts["hours_active"] = len(row["hours"])
        out.append({"mesh_id": mesh_id, "node_id": node_id, "channel": channel, "detector": detector, **counts})
    return out
