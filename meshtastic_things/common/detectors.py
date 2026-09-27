"""The alarm detectors
"""

# The registry validates writes against these
FLAT_VALUE = "flat_value"
RANGE = "range"
COMPLETENESS = "completeness"
ABSENCE = "absence"

MEASUREMENT_SCOPE = "measurement"
DEVICE_SCOPE = "device"

# GET /detectors options, so a UI can build its options without hardcoding
# them. `requires` is the config a detector also needs before it can trigger
DETECTOR_SPECS = (
    {
        "name": FLAT_VALUE,
        "scope": MEASUREMENT_SCOPE,
        "requires": (),
        "description": "Fires when a channel reports the same value for a whole window.",
    },
    {
        "name": RANGE,
        "scope": MEASUREMENT_SCOPE,
        "requires": ("valid_min", "valid_max"),
        "description": "Fires when a reading falls outside the range configured for this device.",
    },
    {
        "name": COMPLETENESS,
        "scope": MEASUREMENT_SCOPE,
        "requires": ("reading_interval_seconds",),
        "description": "Fires when a channel's history has gaps against its expected reading interval.",
    },
    {
        "name": ABSENCE,
        "scope": DEVICE_SCOPE,
        "requires": ("publish_interval_seconds",),
        "description": "Fires when a device stops publishing for several of its publish intervals.",
    },
)

MEASUREMENT_DETECTORS = tuple(d["name"] for d in DETECTOR_SPECS if d["scope"] == MEASUREMENT_SCOPE)
# Device-wide: it has no channel, so it hangs off Device.absence_detection_enabled.
DEVICE_DETECTORS = tuple(d["name"] for d in DETECTOR_SPECS if d["scope"] == DEVICE_SCOPE)

# DRF choice pairs, shared by both serializers so the schema names one enum.
DETECTOR_CHOICES = [(name, name) for name in sorted(MEASUREMENT_DETECTORS)]


def enabled_detectors_for(override: list[str] | None, catalog_default: list[str] | None) -> set[str]:
    """`None` inherits the catalog default, `[]` means none - the same
    distinction the interval fields make."""
    chosen = override if override is not None else catalog_default
    return set(chosen or ())


# Used when a channel has no reading interval
DEFAULT_FLAT_WINDOW = 5
MIN_FLAT_WINDOW = 3
MAX_FLAT_WINDOW = 240


def stuck_value_triggered(recent_values: list[float], window: int = 5) -> bool:
    """Triggers when a sensor reports the same value N times in a row."""
    if len(recent_values) < window:
        return False
    return len(set(recent_values[-window:])) == 1


def flat_window_for(interval_seconds: float | None, hours: float = 3.0) -> int:
    if not interval_seconds:
        return DEFAULT_FLAT_WINDOW
    return max(MIN_FLAT_WINDOW, min(MAX_FLAT_WINDOW, int(hours * 3600 / interval_seconds)))


def range_check_triggered(value: float, min_value: float | None, max_value: float | None) -> bool:
    """Fires when a value falls outside a configured [min, max] range."""
    if min_value is not None and value < min_value:
        return True
    if max_value is not None and value > max_value:
        return True
    return False


# A device never reports one channel this fast. Only a replay of stored history
# does. Duplicates of one packet heard by several gateways stay well below it.
REPLAY_BURST_READINGS = 10
REPLAY_BURST_SECONDS = 10.0
# How long an alarm waits for its channel to show a burst before it is sent.
REPLAY_HOLD_SECONDS = 5.0


def track_arrival(arrivals: list[float], now: float) -> tuple[list[float], bool]:
    """Record a reading's arrival and report whether its channel is being replayed.

    Args:
        arrivals: Processing times, in seconds, of the channel's recent readings.
        now: Processing time of this reading.

    Returns:
        The arrivals to keep, and whether they amount to a replay burst.
    """
    recent = [t for t in arrivals if now - t < REPLAY_BURST_SECONDS]
    recent.append(now)
    recent = recent[-REPLAY_BURST_READINGS:]
    return recent, len(recent) >= REPLAY_BURST_READINGS


DETECTORS = {
    "stuck_value": stuck_value_triggered,
    "range_check": range_check_triggered,
}
