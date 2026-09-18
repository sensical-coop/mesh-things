"""Channel naming convention: "<measurement>.<field>".

A *channel* is one addressable timeseries.
This vocabulary is shared by (all need to be the same):

  - blueprint inputs/outputs (registry's PostprocessingStep)
  - quality thresholds (mesh.quality_config.v1's key)
  - the streams per-channel keying (flink/pattern_detection_job.py)
  - the batches (quality_worker/influx_io.py)

Naming must be the same as writer/point_builders.py, which is what defines
the InfluxDB measurement name. Each telemetry sub-metric dict becomes its own
measurement, and everything else uses its payload kind.
"""

# A payload_kind is always "<namespace>:<measurement>".
# The measurement half is the InfluxDB measurement name
TELEMETRY = "telemetry"  # a sensor reading
DEVICE = "device"        # the device describing itself
COMPUTED = "computed"    # produced by this pipeline

# The measurement bit for everything that is NOT a telemetry variant. Telemetry
# variants are dynamic (one per Telemetry sub-metric), so they are not listed.
# These must match writer/point_builders.py, which is what names each measurement.
DERIVED = "derived"  # all blueprint outputs, attributed by the point's blueprint_id tag
QUALITY = "quality"
ALARMS = "alarms"
POSITION = "position" # Not telemetry, but coming from the device
NODEINFO = "nodeinfo" # Not telemetry
PORTNUM_PREFIX = "portnum_"  # an undecoded portnum, e.g. portnum_67

DEVICE_MEASUREMENTS = frozenset({POSITION, NODEINFO})
COMPUTED_MEASUREMENTS = frozenset({DERIVED, QUALITY, ALARMS})

# The full payload_kinds that are fixed rather than per-variant.
DERIVED_KIND = f"{COMPUTED}:{DERIVED}"
QUALITY_KIND = f"{COMPUTED}:{QUALITY}"
ALARMS_KIND = f"{COMPUTED}:{ALARMS}"
POSITION_KIND = f"{DEVICE}:{POSITION}"
NODEINFO_KIND = f"{DEVICE}:{NODEINFO}"

# channel_origins
# Who produced the value. Part of the namespace, and exposed on the API.
ORIGIN_MEASURED = "measured"
ORIGIN_DEVICE = "device"
ORIGIN_COMPUTED = "computed"
ORIGIN_OTHER = "other"

def channel_name(payload_kind: str, field_name: str) -> str:
    """Gets the channel name for a payload_kind and field name

    Example:
        channel_name("telemetry:environment_metrics", "temperature")
        -> "environment_metrics.temperature".
    """
    return f"{measurement_of(payload_kind)}.{field_name}"


def measurement_of(payload_kind: str) -> str:
    """The InfluxDB measurement a payload_kind is stored under.

    Storage drops the namespace: telemetry:environment_metrics -> environment_metrics.
    """
    return (payload_kind or "unknown").split(":", 1)[-1]


def payload_kind_of_measurement(measurement: str) -> str:
    """The payload_kind an InfluxDB measurement was written from.

    Inverse of measurement_of: storage keeps only the measurement half, so the
    namespace has to be put back on. Anything not named here is a telemetry
    variant, since those are dynamic.
    """
    return f"{namespace_of_measurement(measurement)}:{measurement}"


def namespace_of_measurement(measurement: str) -> str:
    """Which of the three producers an InfluxDB measurement came from."""
    if measurement in COMPUTED_MEASUREMENTS:
        return COMPUTED
    if measurement in DEVICE_MEASUREMENTS or measurement.startswith(PORTNUM_PREFIX):
        return DEVICE
    return TELEMETRY


def split_channel(channel: str) -> tuple[str, str]:
    """Inverse of channel_name: "environment_metrics.temperature" -> the pair."""
    measurement, _, field = (channel or "").partition(".")
    if not measurement or not field:
        raise ValueError(f"Invalid channel: {channel!r}, expected '<measurement>.<field>'")
    return measurement, field


def namespace_of(payload_kind: str) -> str:
    """The part before the colon, or the whole thing when ""."""
    return (payload_kind or "").split(":", 1)[0]


def origin_of(payload_kind: str) -> str:
    """Who produced the value from the payload_kind's namespace."""
    return {
        TELEMETRY: ORIGIN_MEASURED,
        DEVICE: ORIGIN_DEVICE,
        COMPUTED: ORIGIN_COMPUTED,
    }.get(namespace_of(payload_kind), ORIGIN_OTHER)


def origin_of_measurement(measurement: str) -> str:
    """Get origin of an InfluxDB measurement"""
    return origin_of(payload_kind_of_measurement(measurement))


def channels_in(payload_kind: str, payload: dict):
    """Yield ("<measurement>.<field>", value) for every numeric value of a
    decoded payload, matching build_telemetry_points' measurement choice."""
    fallback = (payload_kind or "unknown").split(":", 1)[-1]
    for key, value in (payload or {}).items():
        if key == "time":
            continue
        if isinstance(value, dict):
            for field, leaf in numeric_leaves(value):
                yield f"{key}.{field}", leaf
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            yield f"{fallback}.{key}", value


def numeric_leaves(d: dict):
    """Recursive numeric-leaf walk.
    bools are excluded."""
    for key, value in d.items():
        if isinstance(value, dict):
            yield from numeric_leaves(value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            yield key, value
