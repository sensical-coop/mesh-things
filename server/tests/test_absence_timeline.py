"""The absence job's alarm timeline, driven through DetectAbsence with a fake clock.

Needs PyFlink, so it runs in the Flink image rather than in CI.
"""
import json

import pytest

pytest.importorskip("pyflink")

from flink import absence_detection_job as job  # noqa: E402

MINUTE = 60_000
INTERVAL = 300  # 5 min publish interval; with 3 missed intervals, silent for 15 min alarms.


class FakeState:
    def __init__(self):
        self._value = None

    def value(self):
        return self._value

    def update(self, value):
        self._value = value

    def clear(self):
        self._value = None


class FakeRuntimeContext:
    def get_state(self, descriptor):
        return FakeState()


class FakeTimerService:
    def __init__(self, clock):
        self.clock = clock
        self.timers = set()

    def current_processing_time(self):
        return self.clock.now

    def register_processing_time_timer(self, timestamp):
        self.timers.add(timestamp)

    def delete_processing_time_timer(self, timestamp):
        self.timers.discard(timestamp)


class FakeContext:
    def __init__(self, clock):
        self._timer_service = FakeTimerService(clock)
        self._config = {"1:2": json.dumps({"absence_detection_enabled": True, "publish_interval_seconds": INTERVAL})}

    def timer_service(self):
        return self._timer_service

    def get_broadcast_state(self, descriptor):
        return self._config


class Clock:
    def __init__(self, now):
        self.now = now


class Device:
    """One device's absence detector, with the clock starting at 10:00."""

    def __init__(self, started_at=10 * 60):
        self.clock = Clock(started_at * MINUTE)
        self.ctx = FakeContext(self.clock)
        self.detector = job.DetectAbsence()
        self.detector.open(FakeRuntimeContext())
        self.detector._started_ms = self.clock.now
        self.alarms = []

    def run_until(self, minute):
        """Advance the clock to `minute` past midnight, firing timers on the way."""
        end = minute * MINUTE
        while True:
            due = sorted(t for t in self.ctx.timer_service().timers if t <= end)
            if not due:
                break
            timestamp = due[0]
            self.ctx.timer_service().timers.discard(timestamp)
            self.clock.now = max(self.clock.now, timestamp)
            for alarm in self.detector.on_timer(timestamp, self.ctx):
                self.alarms.append((timestamp // MINUTE, json.loads(alarm)["value"]))
        self.clock.now = end

    def publish_at(self, minute):
        self.run_until(minute)
        list(self.detector.process_element(json.dumps({"mesh_id": 1, "device_id": 2}), self.ctx))


def hhmm(minute):
    return f"{minute // 60:02d}:{minute % 60:02d}"


def at(hour, minute):
    return hour * 60 + minute


def test_a_silent_device_alarms_once():
    device = Device()
    device.publish_at(at(10, 0))

    device.run_until(at(23, 0))

    assert [(hhmm(m), s) for m, s in device.alarms] == [("10:15", 900)]


def test_a_second_silence_soon_after_is_held_until_three_limits_past_the_first_alarm():
    device = Device()
    device.publish_at(at(10, 0))
    device.publish_at(at(10, 20))
    device.publish_at(at(10, 25))

    device.run_until(at(12, 0))

    # 10:40 is only 25 min after the first alarm; held to 11:00 (45 min).
    assert [(hhmm(m), s) for m, s in device.alarms] == [("10:15", 900), ("11:00", 2100)]


def test_a_held_silence_does_not_alarm_if_the_device_publishes_meanwhile():
    device = Device()
    device.publish_at(at(10, 0))
    device.publish_at(at(10, 20))
    device.publish_at(at(10, 25))
    device.publish_at(at(10, 50))
    for minute in range(55, 120, 5):
        device.publish_at(at(10, 0) + minute)

    device.run_until(at(12, 0))

    assert [hhmm(m) for m, _ in device.alarms] == ["10:15"]


def test_a_second_silence_long_after_alarms_straight_away():
    device = Device()
    device.publish_at(at(10, 0))
    device.publish_at(at(11, 0))

    device.run_until(at(12, 0))

    assert [hhmm(m) for m, _ in device.alarms] == ["10:15", "11:15"]


def test_a_timer_due_while_the_job_was_down_restarts_the_countdown():
    device = Device()
    device.publish_at(at(10, 0))
    # The job restarts at 10:30, with the 10:15 timer restored overdue.
    device.detector._started_ms = at(10, 30) * MINUTE
    device.clock.now = at(10, 30) * MINUTE

    device.run_until(at(11, 0))

    assert [(hhmm(m), s) for m, s in device.alarms] == [("10:45", 2700)]


def test_a_timer_fired_after_it_was_replaced_is_ignored():
    device = Device()
    device.publish_at(at(10, 0))
    stale = next(iter(device.ctx.timer_service().timers))
    device.publish_at(at(10, 14))

    device.clock.now = at(10, 15) * MINUTE
    alarms = list(device.detector.on_timer(stale, device.ctx))

    assert alarms == []
    assert device.alarms == []
