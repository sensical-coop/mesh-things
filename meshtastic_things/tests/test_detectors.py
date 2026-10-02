from common.detectors import (
    REPLAY_BURST_READINGS,
    REPLAY_BURST_SECONDS,
    absence_on_timer,
    alarm_due,
    flat_value_triggered,
    range_check_triggered,
    range_readings_for,
    track_arrival,
    track_condition,
    track_flat,
)


HOUR = 3600


def _flat(values_at):
    state = None
    for value, t in values_at:
        state = track_flat(state, value, t)
    return state


def test_flat_value_triggered_after_the_configured_hours():
    assert flat_value_triggered(_flat([(1.0, 0), (1.0, 6 * HOUR), (1.0, 12 * HOUR)]), hours=12) is True

def test_flat_value_not_triggered_before_the_configured_hours():
    assert flat_value_triggered(_flat([(1.0, 0), (1.0, 6 * HOUR), (1.0, 11 * HOUR)]), hours=12) is False

def test_flat_value_needs_enough_readings_as_well_as_time():
    assert flat_value_triggered(_flat([(1.0, 0), (1.0, 13 * HOUR)]), hours=12) is False

def test_a_changed_value_starts_a_new_flat_stretch():
    state = _flat([(1.0, 0), (1.0, 6 * HOUR), (2.0, 7 * HOUR), (2.0, 12 * HOUR), (2.0, 13 * HOUR)])
    assert state["since"] == 7 * HOUR
    assert flat_value_triggered(state, hours=12) is False

def test_range_check_triggered_below_min():
    assert range_check_triggered(-5.0, min_value=0.0, max_value=100.0) is True

def test_range_check_triggered_above_max():
    assert range_check_triggered(150.0, min_value=0.0, max_value=100.0) is True

def test_range_check_not_triggered_within_range():
    assert range_check_triggered(50.0, min_value=0.0, max_value=100.0) is False

def test_range_check_with_no_bounds_never_triggers():
    assert range_check_triggered(999999.0, min_value=None, max_value=None) is False

def test_alarm_due_on_onset():
    assert alarm_due(None, reading_time=1000.0, repeat_seconds=3600) is True

def test_alarm_not_due_within_the_repeat_interval():
    assert alarm_due(1000.0, reading_time=1000.0 + 3599, repeat_seconds=3600) is False

def test_alarm_due_again_after_the_repeat_interval():
    assert alarm_due(1000.0, reading_time=1000.0 + 3600, repeat_seconds=3600) is True

def test_alarm_not_due_for_a_reading_older_than_the_last_alarm():
    assert alarm_due(1000.0, reading_time=500.0, repeat_seconds=3600) is False

def test_absence_alarms_on_the_first_silence():
    assert absence_on_timer(None, now=1000.0, repeat_seconds=2700) is None

def test_absence_holds_a_silence_too_soon_after_the_previous_alarm():
    assert absence_on_timer(1000.0, now=2000.0, repeat_seconds=2700) == 3700.0

def test_absence_alarms_once_the_repeat_interval_has_passed():
    assert absence_on_timer(1000.0, now=3700.0, repeat_seconds=2700) is None


class TestReplayBurst:
    def _feed(self, times):
        arrivals, replay = [], False
        for now in times:
            arrivals, replay = track_arrival(arrivals, now)
        return arrivals, replay

    def test_a_live_channel_is_not_a_replay(self):
        _, replay = self._feed([i * 60.0 for i in range(50)])
        assert replay is False

    def test_one_packet_heard_by_several_gateways_is_not_a_replay(self):
        _, replay = self._feed([0.0, 0.01, 0.02, 60.0, 60.01, 60.02])
        assert replay is False

    def test_readings_arriving_milliseconds_apart_are_a_replay(self):
        _, replay = self._feed([i * 0.001 for i in range(REPLAY_BURST_READINGS)])
        assert replay is True

    def test_the_burst_ends_once_readings_slow_down(self):
        arrivals, _ = self._feed([i * 0.001 for i in range(REPLAY_BURST_READINGS)])
        _, replay = track_arrival(arrivals, REPLAY_BURST_SECONDS + 1)
        assert replay is False

    def test_the_kept_arrivals_stay_bounded(self):
        arrivals, _ = self._feed([i * 0.001 for i in range(1000)])
        assert len(arrivals) == REPLAY_BURST_READINGS


def _conditions(readings, repeat_seconds=3600):
    state, out = None, []
    for t, holds in readings:
        state, repeat = track_condition(state, holds, t, repeat_seconds)
        if holds:
            out.append(repeat)
    return out


def test_a_condition_that_never_held_is_new():
    assert _conditions([(0, False), (300, True)]) == [False]

def test_a_condition_that_keeps_holding_is_a_repeat_whatever_the_reading_interval():
    assert _conditions([(0, True), (6 * 3600, True), (12 * 3600, True)]) == [False, True, True]

def test_a_condition_cleared_briefly_is_the_same_one():
    assert _conditions([(0, True), (600, False), (1800, True)]) == [False, True]

def test_a_condition_cleared_for_the_repeat_interval_is_new():
    assert _conditions([(0, True), (600, False), (600 + 3600, True)]) == [False, False]

def test_a_condition_seen_again_after_a_day_without_readings_is_new():
    assert _conditions([(0, True), (25 * 3600, True)]) == [False, False]


def test_range_needs_three_readings_normally():
    assert range_readings_for(300) == 3
    assert range_readings_for(None) == 3

def test_range_needs_two_readings_on_slow_devices():
    assert range_readings_for(1800) == 2
    assert range_readings_for(3600) == 2
