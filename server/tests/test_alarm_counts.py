"""Daily alarm counts."""
from datetime import datetime, timedelta, timezone

from common.alarm_counts import daily_counts

DAY = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _alarm(hour, minute=0, detector="range", channel="environment_metrics.temperature", repeat=False, node="1"):
    return {"time": DAY + timedelta(hours=hour, minutes=minute), "mesh_id": "m", "node_id": node,
            "channel": channel, "detector": detector, "repeat": repeat}


def _by(rows, detector, channel="environment_metrics.temperature"):
    return next(r for r in rows if r["detector"] == detector and r["channel"] == channel)


def test_a_condition_active_for_six_hours():
    alarms = [_alarm(1, 10)] + [_alarm(h, 10, repeat=True) for h in range(2, 7)]

    row = _by(daily_counts(alarms, DAY, {}), "range")

    assert row == {"mesh_id": "m", "node_id": "1", "channel": "environment_metrics.temperature",
                   "detector": "range", "alarms": 6, "new_conditions": 1, "hours_active": 6}


def test_two_alarms_in_one_hour_count_one_hour():
    row = _by(daily_counts([_alarm(1, 10), _alarm(1, 50)], DAY, {}), "range")

    assert row["hours_active"] == 1
    assert row["new_conditions"] == 2


def test_channels_and_detectors_are_counted_apart():
    rows = daily_counts([_alarm(1), _alarm(1, channel="environment_metrics.humidity"),
                         _alarm(2, detector="flat_value")], DAY, {})

    assert len(rows) == 3


def test_absence_counts_the_hours_until_the_device_was_back():
    silences = {("m", "1"): [(DAY + timedelta(hours=10), DAY + timedelta(hours=13, minutes=30))]}

    row = _by(daily_counts([_alarm(10, detector="absence", channel=None)], DAY, silences), "absence", None)

    assert row["hours_active"] == 3.5
    assert row["alarms"] == 1


def test_a_silence_from_an_earlier_day_counts_without_an_alarm_that_day():
    silences = {("m", "1"): [(DAY - timedelta(days=2), DAY + timedelta(days=1))]}

    row = _by(daily_counts([], DAY, silences), "absence", None)

    assert row["hours_active"] == 24
    assert row["alarms"] == 0


def test_overlapping_silences_are_not_counted_twice():
    silences = {("m", "1"): [(DAY + timedelta(hours=1), DAY + timedelta(hours=5)),
                             (DAY + timedelta(hours=3), DAY + timedelta(hours=6))]}

    row = _by(daily_counts([], DAY, silences), "absence", None)

    assert row["hours_active"] == 5


def test_completeness_counts_only_alarms():
    row = _by(daily_counts([_alarm(3, detector="completeness")], DAY, {}), "completeness")

    assert "hours_active" not in row
    assert row["alarms"] == 1


def test_old_alarms_without_repeat_marks_leave_new_conditions_out():
    rows = daily_counts([_alarm(1), _alarm(2), _alarm(5, detector="absence", channel=None)], DAY, {},
                        know_repeats=False)

    assert "new_conditions" not in _by(rows, "range")
    assert _by(rows, "range")["hours_active"] == 2
    # Without measured silences, absence falls back to the hours it alarmed in.
    assert _by(rows, "absence", None)["hours_active"] == 1
