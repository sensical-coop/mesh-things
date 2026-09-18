import pytest

from common.calibration import apply_calibration
from common.detectors import range_check_triggered, stuck_value_triggered

def test_identity_calibration_is_default():
    assert apply_calibration("identity", 42.0, {}) == 42.0
    assert apply_calibration("unknown_function", 42.0, {}) == 42.0

def test_offset_scale_calibration():
    assert apply_calibration("offset_scale", 10.0, {"scale": 2.0, "offset": 5.0}) == 25.0

def test_calibration_failure_falls_back_to_original_value():
    # lookup_table with no points raises - apply_calibration swallows it and
    # passes the value through rather than killing the job.
    assert apply_calibration("lookup_table", 42.0, {}) == 42.0

def test_lookup_table_interpolates_between_points():
    params = {"points": [[0.0, 0.0], [10.0, 100.0]]}
    assert apply_calibration("lookup_table", 5.0, params) == 50.0
    assert apply_calibration("lookup_table", 2.5, params) == 25.0

def test_lookup_table_returns_exact_value_at_a_defined_point():
    params = {"points": [[0.0, 1.0], [10.0, 5.0], [20.0, 2.0]]}
    assert apply_calibration("lookup_table", 10.0, params) == 5.0

def test_lookup_table_clamps_outside_its_range():
    # Deliberately clamped, not extrapolated - see lookup_table's docstring.
    params = {"points": [[10.0, 100.0], [20.0, 200.0]]}
    assert apply_calibration("lookup_table", 5.0, params) == 100.0
    assert apply_calibration("lookup_table", 50.0, params) == 200.0

def test_lookup_table_accepts_unsorted_points():
    params = {"points": [[20.0, 200.0], [0.0, 0.0], [10.0, 100.0]]}
    assert apply_calibration("lookup_table", 15.0, params) == 150.0

def test_lookup_table_with_a_single_point_is_a_constant():
    assert apply_calibration("lookup_table", 999.0, {"points": [[1.0, 7.0]]}) == 7.0

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
