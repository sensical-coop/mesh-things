"""Completeness alarms across repeated scans of the same 24 h of history.

Needs Celery, so it runs in the quality worker image rather than in CI.
"""
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("celery")

from quality_worker import tasks  # noqa: E402

CHANNEL = "environment_metrics.temperature"
START = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _every(minutes, start, end):
    t, out = start, []
    while t <= end:
        out.append((t, 20.0))
        t += timedelta(minutes=minutes)
    return out


class FakeRegistry:
    def __init__(self, interval, absence):
        self.interval = interval
        self.absence = absence
        self.calls = []

    def devices(self, **_):
        self.calls.append("devices")
        return [self.device("d")]

    def device(self, uuid):
        self.calls.append("device")
        if uuid != "d":
            return None
        return {
            "uuid": "d",
            "mesh_id": "m",
            "node_id": 1,
            "reading_interval_seconds": self.interval,
            "absence_detection_enabled": self.absence,
        }

    def telemetry_variants(self):
        self.calls.append("telemetry_variants")
        return []

    def device_measurements(self, _):
        return [
            {
                "id": "r",
                "measurement_type": {"channel": CHANNEL, "origin": "measured", "payload_kind": "telemetry:x"},
                "effective_detectors": ["completeness"],
            }
        ]


class FakeInflux:
    def __init__(self):
        self.series = []

    def read_channel(self, *_):
        return self.series

    def write_quality_metric(self, *_):
        pass


class FakePublisher:
    def __init__(self):
        self.alarms = []

    def publish(self, alarm):
        self.alarms.append(alarm)

    def publish_discovery(self, *_, **__):
        pass


class FakeMemory:
    def __init__(self):
        self.seen = set()

    def first_time(self, key, ttl_seconds):
        if key in self.seen:
            return False
        self.seen.add(key)
        return True


@pytest.fixture(autouse=True)
def _fresh_variants_cache(monkeypatch):
    monkeypatch.setattr(tasks, "_variants_cache", None)


@pytest.fixture
def worker(monkeypatch):
    def make(interval, absence=False):
        influx, publisher, memory = FakeInflux(), FakePublisher(), FakeMemory()
        # Scans run just after the last reading, as they would live.
        monkeypatch.setattr(tasks, "_utcnow", lambda: influx.series[-1][0] + timedelta(minutes=1))
        monkeypatch.setattr(tasks, "get_registry_client", lambda: FakeRegistry(interval, absence))
        monkeypatch.setattr(tasks, "get_influx_io", lambda: influx)
        monkeypatch.setattr(tasks, "get_alarm_publisher", lambda: publisher)
        monkeypatch.setattr(tasks, "get_alarm_memory", lambda: memory)
        return influx, publisher

    return make


def test_a_gap_alarms_once_across_hourly_scans(worker):
    influx, publisher = worker(interval=300)
    # 5 min readings with one 45 min hole, over 6 intervals and the 30 min floor.
    influx.series = _every(5, START, START + timedelta(hours=10)) + _every(
        5, START + timedelta(hours=10, minutes=45), START + timedelta(hours=24)
    )

    for _ in range(24):
        tasks.check_completeness("d")

    assert len(publisher.alarms) == 1
    assert publisher.alarms[0]["value"] == 45 * 60


def test_a_new_gap_alarms_after_an_old_one(worker):
    influx, publisher = worker(interval=300)
    influx.series = _every(5, START, START + timedelta(hours=10)) + _every(
        5, START + timedelta(hours=10, minutes=45), START + timedelta(hours=24)
    )
    tasks.check_completeness("d")

    influx.series = influx.series + _every(5, START + timedelta(hours=25), START + timedelta(hours=26))
    tasks.check_completeness("d")

    assert len(publisher.alarms) == 2


def test_the_gap_limit_scales_with_the_reading_interval(worker):
    influx, publisher = worker(interval=1800)
    # A 2.5 h hole at a 30 min interval is only 5 intervals: not a gap.
    influx.series = _every(30, START, START + timedelta(hours=10)) + _every(
        30, START + timedelta(hours=12, minutes=30), START + timedelta(hours=24)
    )

    tasks.check_completeness("d")

    assert publisher.alarms == []


def test_a_low_ratio_alarms_once_while_it_stays_low(worker):
    influx, publisher = worker(interval=300)
    # Half the expected readings, evenly spread, so no single gap.
    influx.series = _every(10, START, START + timedelta(hours=24))

    for _ in range(24):
        tasks.check_completeness("d")

    assert len(publisher.alarms) == 1
    assert publisher.alarms[0]["value"] < 0.8


def test_a_gap_absence_already_covers_does_not_alarm(worker):
    influx, publisher = worker(interval=300, absence=True)
    influx.series = _every(5, START, START + timedelta(hours=10)) + _every(
        5, START + timedelta(hours=10, minutes=45), START + timedelta(hours=24)
    )

    tasks.check_completeness("d")

    assert publisher.alarms == []


def test_a_silent_channel_is_left_to_absence(worker, monkeypatch):
    influx, publisher = worker(interval=300)
    influx.series = _every(5, START, START + timedelta(hours=10))
    monkeypatch.setattr(tasks, "_utcnow", lambda: START + timedelta(hours=24))

    tasks.check_completeness("d")

    assert publisher.alarms == []


def test_the_ratio_is_not_applied_to_slow_devices(worker):
    influx, publisher = worker(interval=7200)
    # 9 of 12 readings, spread out, so no gap over 6 intervals either.
    influx.series = [
        (START + timedelta(hours=h), 1.0) for h in range(0, 24, 2) if h not in (4, 12, 18)
    ]

    tasks.check_completeness("d")

    assert publisher.alarms == []


def test_an_outage_absence_reported_does_not_lower_the_ratio(worker):
    influx, publisher = worker(interval=300, absence=True)
    # Silent 8 h: 67% of the day, but absence already covered those hours.
    influx.series = _every(5, START, START + timedelta(hours=10)) + _every(
        5, START + timedelta(hours=18), START + timedelta(hours=24)
    )

    tasks.check_completeness("d")

    assert publisher.alarms == []


def test_a_check_fetches_its_own_device_and_shares_the_variants(monkeypatch):
    """A scan queues one check per device: none may list every device."""
    registry = FakeRegistry(60, False)
    influx = FakeInflux()
    influx.series = _every(1, START, START + timedelta(hours=1))
    monkeypatch.setattr(tasks, "_utcnow", lambda: influx.series[-1][0] + timedelta(minutes=1))
    monkeypatch.setattr(tasks, "get_registry_client", lambda: registry)
    monkeypatch.setattr(tasks, "get_influx_io", lambda: influx)
    monkeypatch.setattr(tasks, "get_alarm_publisher", lambda: FakePublisher())
    monkeypatch.setattr(tasks, "get_alarm_memory", lambda: FakeMemory())

    tasks.check_completeness("d")
    tasks.check_completeness("d")

    assert "devices" not in registry.calls
    assert registry.calls.count("telemetry_variants") == 1
    assert tasks.check_completeness("gone") == {"status": "device_not_found"}
