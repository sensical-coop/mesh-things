"""Environmental corrections and derived meteorological quantities"""
import math

from . import POINTWISE, algorithm

# Most sensor datasheets quote coefficients relative to lab conditions.
REFERENCE_TEMPERATURE_C = 20.0


@algorithm(
    name="linear_temperature_correction",
    inputs=("value", "temperature"),
    outputs=("corrected",),
    params=("coefficient",),
    optional_params=("reference_temperature",),
    mode=POINTWISE,
    # Preserves units
    output_units={"corrected": "@value"},
)
def linear_temperature_correction(
    value: float,
    temperature: float,
    *,
    coefficient: float,
    reference_temperature: float = REFERENCE_TEMPERATURE_C,
) -> float:
    """Remove a linear temperature dependence from a reading.

    corrected = value / (1 + coefficient * (temperature - reference))

    `coefficient` is the fractional change in reading per degree C.
    """
    denominator = 1.0 + coefficient * (temperature - reference_temperature)
    if denominator == 0:
        raise ZeroDivisionError("temperature correction denominator is zero. Check `coefficient`")
    return value / denominator


@algorithm(
    name="dew_point",
    inputs=("temperature", "relative_humidity"),
    outputs=("dew_point",),
    mode=POINTWISE,
    output_units={"dew_point": "degC"},
)
def dew_point(temperature: float, relative_humidity: float) -> float:
    """Dew point in degC from temperature (degC) and relative humidity (%).

    Magnus-Tetens approximation, accurate to about 0.4 degC over
    0-60 degC / 1-100 %RH.
    """
    if relative_humidity <= 0:
        raise ValueError("relative_humidity must be > 0 to compute a dew point")
    a, b = 17.62, 243.12
    gamma = (a * temperature) / (b + temperature) + math.log(relative_humidity / 100.0)
    return (b * gamma) / (a - gamma)


@algorithm(
    name="absolute_humidity",
    inputs=("temperature", "relative_humidity"),
    outputs=("absolute_humidity",),
    mode=POINTWISE,
    output_units={"absolute_humidity": "g/m3"},
)
def absolute_humidity(temperature: float, relative_humidity: float) -> float:
    """Absolute humidity in g/m3 from temperature (degC) and RH (%)."""

    saturation_pressure = 6.112 * math.exp((17.67 * temperature) / (temperature + 243.5))
    return (saturation_pressure * relative_humidity * 2.1674) / (273.15 + temperature)
