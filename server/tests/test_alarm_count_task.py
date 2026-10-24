"""The daily alarm count task against a fake InfluxDB.

Needs Celery, so it runs in the quality worker image rather than in CI.
"""
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("celery")

from common.alarm_counts import ALARM_COUNTS_BUCKET  # noqa: E402
from quality_worker import tasks  # noqa: E402

DAY = datetime(2026, 9, 1, tzinfo=timezone.utc)


class FakeInflux:
    def __init__(self, alarms, readings):
        self.alarms, self.readings, self.written = alarms, readings, {}

    def read_alarms(self, bucket, start, stop, detector=None):
        return [a for a in self.alarms if start <= a["time"] < stop and detector in (None, a["detector"])]

    def first_reading_after(self, mesh_id, node_id, start, stop):
        return next((t for t in sorted(self.readings) if start <= t < stop), None)

    def write_alarm_counts(self, bucket, day_start, rows):
        self.written[(bucket, day_start)] = rows


def _absence(at):
    return {"time": at, "mesh_id": "m", "node_id": "1", "channel": None, "detector": "absence", "repeat": False}


def _run(monkeypatch, alarms, readings, day=DAY):
    influx = FakeInflux(alarms, readings)
    monkeypatch.setattr(tasks, "get_influx_io", lambda: influx)
    tasks.count_alarms(day.date().isoformat())
    return influx.written[(ALARM_COUNTS_BUCKET, day)]


def test_a_device_silent_for_part_of_the_day(monkeypatch):
    rows = _run(monkeypatch, [_absence(DAY + timedelta(hours=10))], [DAY + timedelta(hours=16)])

    assert rows[0]["hours_active"] == 6


def test_a_device_silent_since_an_earlier_day_counts_the_whole_day(monkeypatch):
    rows = _run(monkeypatch, [_absence(DAY - timedelta(days=3))], [])

    assert rows[0]["hours_active"] == 24
    assert rows[0]["alarms"] == 0


def test_a_silence_that_ended_before_the_day_is_not_counted(monkeypatch):
    rows = _run(monkeypatch, [_absence(DAY - timedelta(days=3))], [DAY - timedelta(days=2)])

    assert rows == []


def test_yesterday_by_default(monkeypatch):
    influx = FakeInflux([], [])
    monkeypatch.setattr(tasks, "get_influx_io", lambda: influx)
    monkeypatch.setattr(tasks, "_utcnow", lambda: DAY + timedelta(days=1, hours=0, minutes=30))

    tasks.count_alarms()

    assert list(influx.written) == [(ALARM_COUNTS_BUCKET, DAY)]
