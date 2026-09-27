from common.detectors import (
    REPLAY_BURST_READINGS,
    REPLAY_BURST_SECONDS,
    range_check_triggered,
    stuck_value_triggered,
    track_arrival,
)


def test_stuck_value_not_triggered_below_window():
    assert stuck_value_triggered([1.0, 1.0, 1.0], window=5) is False

def test_stuck_value_triggered_when_flatlined():
    assert stuck_value_triggered([1.0, 1.0, 1.0, 1.0, 1.0], window=5) is True

def test_stuck_value_not_triggered_when_varying():
    assert stuck_value_triggered([1.0, 2.0, 1.0, 2.0, 1.0], window=5) is False

def test_range_check_triggered_below_min():
    assert range_check_triggered(-5.0, min_value=0.0, max_value=100.0) is True

def test_range_check_triggered_above_max():
    assert range_check_triggered(150.0, min_value=0.0, max_value=100.0) is True

def test_range_check_not_triggered_within_range():
    assert range_check_triggered(50.0, min_value=0.0, max_value=100.0) is False

def test_range_check_with_no_bounds_never_triggers():
    assert range_check_triggered(999999.0, min_value=None, max_value=None) is False


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
