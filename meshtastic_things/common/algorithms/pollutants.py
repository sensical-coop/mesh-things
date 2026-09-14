"""Gas-sensor algorithms"""
from . import POINTWISE, algorithm

# Molar volume of an ideal gas at 0 degC, 1013.25 hPa, in litres/mol.
MOLAR_VOLUME_STP = 22.414
STANDARD_PRESSURE_HPA = 1013.25
KELVIN_OFFSET = 273.15
REFERENCE_TEMPERATURE_C = 20.0


@algorithm(
    name="ec_sensor_ppb",
    inputs=("working", "auxiliary", "temperature"),
    outputs=("concentration_ppb",),
    params=("sensitivity",),
    optional_params=(
        "working_zero",
        "auxiliary_zero",
        "temperature_coefficient",
        "reference_temperature",
    ),
    mode=POINTWISE,
    output_units={"concentration_ppb": "ppb"},
)
def ec_sensor_ppb(
    working: float,
    auxiliary: float,
    temperature: float,
    *,
    sensitivity: float,
    working_zero: float = 0.0,
    auxiliary_zero: float = 0.0,
    temperature_coefficient: float = 0.0,
    reference_temperature: float = REFERENCE_TEMPERATURE_C,
) -> float:
    """Electrochemical four-electrode sensor -> concentration in ppb.

    The auxiliary electrode is not exposed to the target gas, so it tracks
    the same thermal/baseline drift as the working electrode without the
    signal. Subtracting it (after its own temperature correction) is what
    isolates the gas response:

        ppb = ((working - working_zero) - n_t * (auxiliary - auxiliary_zero))
              / sensitivity

    where n_t = 1 + temperature_coefficient * (temperature - reference).

    `sensitivity` is in the same units as the electrode readings per ppb
    (e.g. mV/ppb) - it must be non-zero.
    """
    if sensitivity == 0:
        raise ZeroDivisionError("sensitivity must be non-zero")
    n_t = 1.0 + temperature_coefficient * (temperature - reference_temperature)
    corrected_auxiliary = (auxiliary - auxiliary_zero) * n_t
    return ((working - working_zero) - corrected_auxiliary) / sensitivity


@algorithm(
    name="ppb_to_ugm3",
    inputs=("concentration_ppb", "temperature"),
    outputs=("concentration_ugm3",),
    params=("molecular_weight",),
    optional_params=("pressure_hpa",),
    mode=POINTWISE,
    output_units={"concentration_ugm3": "ug/m3"},
)
def ppb_to_ugm3(
    concentration_ppb: float,
    temperature: float,
    *,
    molecular_weight: float,
    pressure_hpa: float = STANDARD_PRESSURE_HPA,
) -> float:
    """Convert a volume mixing ratio (ppb) to a mass concentration (ug/m3).

    Needs temperature (and ideally pressure) because the conversion depends
    on the molar volume of air at the actual conditions, not at STP:

        molar_volume = 22.414 * (T/273.15) * (1013.25/P)
        ug/m3 = ppb * molecular_weight / molar_volume

    `molecular_weight` in g/mol - e.g. NO2 46.01, O3 48.00, CO 28.01,
    SO2 64.07.
    """
    if pressure_hpa <= 0:
        raise ValueError("pressure_hpa must be > 0")
    molar_volume = MOLAR_VOLUME_STP * ((temperature + KELVIN_OFFSET) / KELVIN_OFFSET) * (
        STANDARD_PRESSURE_HPA / pressure_hpa
    )
    return concentration_ppb * molecular_weight / molar_volume
