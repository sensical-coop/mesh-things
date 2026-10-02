"""Single-channel calibration curves"""
from . import POINTWISE, Param, algorithm


@algorithm(
    name="offset_scale",
    inputs=("value",),
    outputs=("calibrated",),
    params=(
        Param("scale", calibration=True, doc="Multiplier applied before the offset."),
        Param("offset", calibration=True, doc="Added after scaling, in the channel's unit."),
    ),
    mode=POINTWISE,
    output_units={"calibrated": "@value"},
)
def offset_scale(value: float, *, scale: float = 1.0, offset: float = 0.0) -> float:
    """Linear calibration: value * scale + offset."""
    return value * scale + offset


@algorithm(
    name="lookup_table",
    inputs=("value",),
    outputs=("calibrated",),
    params=(
        Param(
            "points",
            calibration=True,
            doc="[[raw, calibrated], ...] pairs, at least one. Interpolated linearly, clamped at the ends.",
        ),
    ),
    mode=POINTWISE,
    output_units={"calibrated": "@value"},
)
def lookup_table(value: float, *, points: list) -> float:
    """Non-linear calibration curve, linearly interpolated between points."""
    if not points:
        raise ValueError("lookup_table needs at least one [raw, calibrated] point")

    table = sorted((float(raw), float(calibrated)) for raw, calibrated in points)
    if len(table) == 1 or value <= table[0][0]:
        return table[0][1]
    if value >= table[-1][0]:
        return table[-1][1]

    for (raw_low, cal_low), (raw_high, cal_high) in zip(table, table[1:]):
        if raw_low <= value <= raw_high:
            if raw_high == raw_low:
                return cal_low
            ratio = (value - raw_low) / (raw_high - raw_low)
            return cal_low + ratio * (cal_high - cal_low)
    # Unreachable: the clamps above cover everything outside the table.
    return table[-1][1]
