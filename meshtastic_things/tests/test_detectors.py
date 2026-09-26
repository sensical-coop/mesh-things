from common.detectors import range_check_triggered, stuck_value_triggered


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
