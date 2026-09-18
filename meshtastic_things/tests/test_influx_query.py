"""Validation of anything interpolated into a Flux query - common/influx_query.py."""
import pytest

from common.influx_query import validate_range_bound


@pytest.mark.parametrize("value", ["-1h", "-30d", "-500ms", "now()"])
def test_relative_bounds_pass_through_unchanged(value):
    # Flux understands these directly, so rewriting them would only lose meaning.
    assert validate_range_bound(value, "start") == value


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026-09-01", "2026-09-01T00:00:00Z"),          # a date is midnight
        ("2026-09-01T13:45:00Z", "2026-09-01T13:45:00Z"),
        ("2026-09-01T13:45Z", "2026-09-01T13:45:00Z"),   # seconds optional
        ("2026-09-01 13:45:00", "2026-09-01T13:45:00Z"), # no offset means UTC
        ("2026-09-01T13:45:00.123Z", "2026-09-01T13:45:00Z"),
    ],
)
def test_absolute_bounds_are_normalized_to_utc_timestamps(value, expected):
    assert validate_range_bound(value, "start") == expected

def test_offsets_are_converted_rather_than_dropped():
    """Dropping the offset instead of applying it would silently shift the window by hours."""
    assert validate_range_bound("2026-09-01T13:45:00+02:00", "start") == "2026-09-01T11:45:00Z"

def test_surrounding_whitespace_is_tolerated():
    assert validate_range_bound("  2026-09-01  ", "start") == "2026-09-01T00:00:00Z"


@pytest.mark.parametrize(
    "value",
    [
        "now()) |> drop() //",
        "2026-09-01T00:00:00Z) |> drop() //",
        '2026-09-01" |> drop() //',
        "-1h) |> yield(",
    ],
)
def test_flux_injection_attempts_are_rejected(value):
    """The real security boundary: these end up inside a raw Flux query, so anything that isn't
    a bound on its own must fail rather than be trimmed into something valid."""
    with pytest.raises(ValueError):
        validate_range_bound(value, "start")


@pytest.mark.parametrize(
    "value",
    [
        "2026-13-01",   # month 13
        "2026-02-30",   # not a real day, caught by parsing rather than the regex
        "2026-09-01T99:99:99Z",
        "2026/09/01",
        "not-a-date",
        "-1x",
        "",
        None,
    ],
)
def test_malformed_bounds_are_rejected(value):
    with pytest.raises(ValueError):
        validate_range_bound(value, "start")

def test_the_error_names_the_parameter_and_the_accepted_forms():
    with pytest.raises(ValueError) as excinfo:
        validate_range_bound("yesterday", "stop")

    message = str(excinfo.value)
    assert "stop" in message
    assert "-1h" in message and "2026-09-01" in message
