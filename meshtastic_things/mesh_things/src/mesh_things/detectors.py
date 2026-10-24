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
        "description": "Fires when a channel reports exactly the same value for hours on end.",
    },
    {
        "name": RANGE,
        "scope": MEASUREMENT_SCOPE,
        "requires": ("valid_min", "valid_max"),
        "description": "Fires when several readings in a row fall outside the range configured for this device.",
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
        "description": "Fires once when a device stops publishing for several of its publish intervals.",
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


# A flat stretch needs this many readings as well as its duration, so two
# readings a day apart are not a flat channel.
MIN_FLAT_READINGS = 3


def track_flat(state: dict | None, value: float, reading_time: float) -> dict:
    """Update a channel's flat stretch: its value, since when, and how many readings it spans."""
    if state and state["value"] == value:
        return {
            "value": value,
            "since": min(state["since"], reading_time),
            "last": max(state["last"], reading_time),
            "count": state["count"] + 1,
        }
    return {"value": value, "since": reading_time, "last": reading_time, "count": 1}


def flat_value_triggered(state: dict, hours: float) -> bool:
    """Fires when a channel has reported the same value for at least `hours`."""
    return state["count"] >= MIN_FLAT_READINGS and state["last"] - state["since"] >= hours * 3600


# Consecutive out-of-range readings before `range` fires. Slow devices need
# fewer, or the alarm would wait hours for its readings.
RANGE_READINGS = 3
RANGE_READINGS_SLOW = 2
SLOW_READING_INTERVAL_SECONDS = 1800


def range_readings_for(interval_seconds: float | None) -> int:
    """How many readings in a row must fall outside the range before it alarms."""
    if interval_seconds and interval_seconds >= SLOW_READING_INTERVAL_SECONDS:
        return RANGE_READINGS_SLOW
    return RANGE_READINGS


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


def alarm_due(last_raised_at: float | None, reading_time: float, repeat_seconds: float) -> bool:
    """Whether a condition holding at `reading_time` raises an alarm, at most once per `repeat_seconds`.

    Only readings after the last alarm count, so a replayed backlog raises at
    most one alarm per `repeat_seconds` of data.
    """
    return last_raised_at is None or reading_time - last_raised_at >= repeat_seconds


# A condition with no reading at all for this long is treated as new when it shows again.
STALE_CONDITION_SECONDS = 24 * 3600


def track_condition(state: dict | None, holds: bool, reading_time: float, repeat_seconds: float) -> tuple[dict, bool]:
    """Follow one detector's condition across a channel's readings.

    Returns the new state and, when the condition holds, whether it continues
    one already raised. A condition that cleared, by a reading where it did not
    hold, for less than `repeat_seconds` is the same one, so values hovering at
    a bound do not count as new conditions.
    """
    state = dict(state or {"last_active": None, "cleared_at": None})
    if not holds:
        if state["last_active"] is not None and state["cleared_at"] is None:
            state["cleared_at"] = reading_time
        return state, False
    last_active, cleared_at = state["last_active"], state["cleared_at"]
    if last_active is None:
        repeat = False
    elif cleared_at is None:
        repeat = reading_time - last_active < STALE_CONDITION_SECONDS
    else:
        repeat = reading_time - cleared_at < repeat_seconds
    return {"last_active": reading_time, "cleared_at": None}, repeat


def absence_on_timer(last_alarm_at: float | None, now: float, repeat_seconds: float) -> float | None:
    """What a device's silence timer firing at `now` does.

    Returns None to alarm now, or the time to check again: a silence within
    `repeat_seconds` of the previous alarm is held until that much has passed.
    The timer only runs again after the device publishes, so a device that
    stays silent alarms once.
    """
    if alarm_due(last_alarm_at, now, repeat_seconds):
        return None
    return last_alarm_at + repeat_seconds
