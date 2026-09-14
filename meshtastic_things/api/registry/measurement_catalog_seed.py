"""Units and descriptions for the Meshtastic Telemetry fields.

For now, manually generated...
"""
from common.units import OTHER, PHYSICAL_PROPERTY, RATIO, quantity_kind_for

# (payload_kind, field_name) -> (native_unit, description)
MEASUREMENT_TYPE_SEED: dict[tuple[str, str], tuple[str | None, str]] = {
    # telemetry:device_metrics
    ("telemetry:device_metrics", "battery_level"): ("%", "0-100 (>100 means powered)"),
    ("telemetry:device_metrics", "voltage"): ("V", "Voltage measured"),
    ("telemetry:device_metrics", "channel_utilization"): (
        "%", "Utilization for the current channel, including well formed TX, RX and malformed RX (aka noise)"
    ),
    ("telemetry:device_metrics", "air_util_tx"): (
        "%", "Percent of airtime for transmission used within the last hour"
    ),
    ("telemetry:device_metrics", "uptime_seconds"): (
        "s", "How long the device has been running since the last reboot (in seconds)"
    ),
    # telemetry:environment_metrics
    ("telemetry:environment_metrics", "temperature"): ("degC", "Temperature measured"),
    ("telemetry:environment_metrics", "relative_humidity"): ("%", "Relative humidity percent measured"),
    ("telemetry:environment_metrics", "barometric_pressure"): ("hPa", "Barometric pressure in hPA measured"),
    ("telemetry:environment_metrics", "gas_resistance"): ("MOhm", "Gas resistance in MOhm measured"),
    ("telemetry:environment_metrics", "voltage"): (
        "V", "Voltage measured (to be deprecated in favor of PowerMetrics)"
    ),
    ("telemetry:environment_metrics", "current"): (
        "A", "Current measured (to be deprecated in favor of PowerMetrics)"
    ),
    ("telemetry:environment_metrics", "iaq"): (
        None, "Relative scale IAQ value as measured by Bosch BME680, 0-500"
    ),
    ("telemetry:environment_metrics", "distance"): (
        "mm", "RCWL9620 Doppler Radar Distance Sensor, float value in mm"
    ),
    ("telemetry:environment_metrics", "lux"): ("lux", "VEML7700 high accuracy ambient light (Lux)"),
    ("telemetry:environment_metrics", "white_lux"): (
        "lux", "VEML7700 high accuracy white light (irradiance), not calibrated"
    ),
    ("telemetry:environment_metrics", "ir_lux"): ("lux", "Infrared lux"),
    ("telemetry:environment_metrics", "uv_lux"): ("lux", "Ultraviolet lux"),
    ("telemetry:environment_metrics", "wind_direction"): (
        "deg", "Wind direction in degrees, 0=North, 90=East, etc"
    ),
    ("telemetry:environment_metrics", "wind_speed"): ("m/s", "Wind speed in m/s"),
    ("telemetry:environment_metrics", "weight"): ("kg", "Weight in KG"),
    ("telemetry:environment_metrics", "wind_gust"): ("m/s", "Wind gust in m/s"),
    ("telemetry:environment_metrics", "wind_lull"): ("m/s", "Wind lull in m/s"),
    ("telemetry:environment_metrics", "radiation"): ("uR/h", "Radiation in microR/h"),
    ("telemetry:environment_metrics", "rainfall_1h"): ("mm", "Rainfall in the last hour in mm"),
    ("telemetry:environment_metrics", "rainfall_24h"): ("mm", "Rainfall in the last 24 hours in mm"),
    ("telemetry:environment_metrics", "soil_moisture"): ("%", "Soil moisture measured (percent, 1-100)"),
    ("telemetry:environment_metrics", "soil_temperature"): ("degC", "Soil temperature measured"),
    # telemetry:power_metrics - 8 channel pairs
    **{
        ("telemetry:power_metrics", f"ch{n}_{quantity}"): (unit, f"{label} (Ch{n})")
        for n in range(1, 9)
        for quantity, unit, label in (("voltage", "V", "Voltage"), ("current", "A", "Current"))
    },
    # telemetry:air_quality_metrics
    ("telemetry:air_quality_metrics", "pm10_standard"): ("ug/m3", "Concentration Units Standard PM1.0"),
    ("telemetry:air_quality_metrics", "pm25_standard"): ("ug/m3", "Concentration Units Standard PM2.5"),
    ("telemetry:air_quality_metrics", "pm100_standard"): ("ug/m3", "Concentration Units Standard PM10.0"),
    ("telemetry:air_quality_metrics", "pm10_environmental"): (
        "ug/m3", "Concentration Units Environmental PM1.0"
    ),
    ("telemetry:air_quality_metrics", "pm25_environmental"): (
        "ug/m3", "Concentration Units Environmental PM2.5"
    ),
    ("telemetry:air_quality_metrics", "pm100_environmental"): (
        "ug/m3", "Concentration Units Environmental PM10.0"
    ),
    ("telemetry:air_quality_metrics", "particles_03um"): ("#/0.1L", "0.3um Particle Count in #/0.1l"),
    ("telemetry:air_quality_metrics", "particles_05um"): ("#/0.1L", "0.5um Particle Count in #/0.1l"),
    ("telemetry:air_quality_metrics", "particles_10um"): ("#/0.1L", "1.0um Particle Count in #/0.1l"),
    ("telemetry:air_quality_metrics", "particles_25um"): ("#/0.1L", "2.5um Particle Count in #/0.1l"),
    ("telemetry:air_quality_metrics", "particles_50um"): ("#/0.1L", "5.0um Particle Count in #/0.1l"),
    ("telemetry:air_quality_metrics", "particles_100um"): ("#/0.1L", "10.0um Particle Count in #/0.1l"),
    ("telemetry:air_quality_metrics", "co2"): ("ppm", "CO2 concentration in ppm"),
    ("telemetry:air_quality_metrics", "co2_temperature"): ("degC", "CO2 sensor temperature in degC"),
    ("telemetry:air_quality_metrics", "co2_humidity"): ("%", "CO2 sensor relative humidity in %"),
    ("telemetry:air_quality_metrics", "form_formaldehyde"): (
        "ppb", "Formaldehyde sensor formaldehyde concentration in ppb"
    ),
    ("telemetry:air_quality_metrics", "form_humidity"): ("%", "Formaldehyde sensor relative humidity in %RH"),
    ("telemetry:air_quality_metrics", "form_temperature"): (
        "degC", "Formaldehyde sensor temperature in degrees Celsius"
    ),
    ("telemetry:air_quality_metrics", "pm40_standard"): ("ug/m3", "Concentration Units Standard PM4.0"),
    ("telemetry:air_quality_metrics", "particles_40um"): ("#/0.1L", "4.0um Particle Count in #/0.1l"),
    ("telemetry:air_quality_metrics", "pm_temperature"): (None, "PM Sensor Temperature"),
    ("telemetry:air_quality_metrics", "pm_humidity"): (None, "PM Sensor humidity"),
    ("telemetry:air_quality_metrics", "pm_voc_idx"): (None, "PM Sensor VOC Index"),
    ("telemetry:air_quality_metrics", "pm_nox_idx"): (None, "PM Sensor NOx Index"),
    ("telemetry:air_quality_metrics", "particles_tps"): ("um", "Typical Particle Size in um"),
    # telemetry:local_stats
    ("telemetry:local_stats", "uptime_seconds"): (
        "s", "How long the device has been running since the last reboot (in seconds)"
    ),
    ("telemetry:local_stats", "channel_utilization"): ("%", "Utilization for the current channel"),
    ("telemetry:local_stats", "air_util_tx"): (
        "%", "Percent of airtime for transmission used within the last hour"
    ),
    ("telemetry:local_stats", "num_packets_tx"): ("count", "Number of packets sent"),
    ("telemetry:local_stats", "num_packets_rx"): ("count", "Number of packets received (both good and bad)"),
    ("telemetry:local_stats", "num_packets_rx_bad"): (
        "count", "Number of packets received that are malformed or violate the protocol"
    ),
    ("telemetry:local_stats", "num_online_nodes"): ("count", "Number of nodes online (in the past 2 hours)"),
    ("telemetry:local_stats", "num_total_nodes"): ("count", "Number of nodes total"),
    ("telemetry:local_stats", "num_rx_dupe"): ("count", "Number of received packets that were duplicates"),
    ("telemetry:local_stats", "num_tx_relay"): (
        "count", "Number of packets we transmitted that were a relay for others"
    ),
    ("telemetry:local_stats", "num_tx_relay_canceled"): (
        "count", "Number of times we canceled a packet to be relayed"
    ),
    ("telemetry:local_stats", "heap_total_bytes"): ("bytes", "Number of bytes used in the heap"),
    ("telemetry:local_stats", "heap_free_bytes"): ("bytes", "Number of bytes free in the heap"),
    ("telemetry:local_stats", "num_tx_dropped"): (
        "count", "Number of packets that were dropped because the transmit queue was full"
    ),
    ("telemetry:local_stats", "noise_floor"): ("dBm", "Noise floor value measured in dBm"),
    # telemetry:traffic_management_stats
    ("telemetry:traffic_management_stats", "packets_inspected"): ("count", "Packets inspected"),
    ("telemetry:traffic_management_stats", "position_dedup_drops"): ("count", "Position dedup drops"),
    ("telemetry:traffic_management_stats", "nodeinfo_cache_hits"): ("count", "NodeInfo cache hits"),
    ("telemetry:traffic_management_stats", "rate_limit_drops"): ("count", "Rate limit drops"),
    ("telemetry:traffic_management_stats", "unknown_packet_drops"): ("count", "Unknown packet drops"),
    ("telemetry:traffic_management_stats", "hop_exhausted_packets"): ("count", "Hop exhausted packets"),
    ("telemetry:traffic_management_stats", "router_hops_preserved"): ("count", "Router hops preserved"),
    # telemetry:health_metrics
    ("telemetry:health_metrics", "heart_bpm"): ("bpm", "Heart rate (beats per minute)"),
    ("telemetry:health_metrics", "spO2"): ("%", "SpO2 (blood oxygen saturation) level"),
    ("telemetry:health_metrics", "temperature"): ("degC", "Body temperature in degrees Celsius"),
    # telemetry:host_metrics
    ("telemetry:host_metrics", "uptime_seconds"): ("s", "Host system uptime"),
    ("telemetry:host_metrics", "freemem_bytes"): ("bytes", "Host system free memory"),
    ("telemetry:host_metrics", "diskfree1_bytes"): ("bytes", "Host system disk space free for /"),
    ("telemetry:host_metrics", "diskfree2_bytes"): ("bytes", "Secondary system disk space free"),
    ("telemetry:host_metrics", "diskfree3_bytes"): ("bytes", "Tertiary disk space free"),
    ("telemetry:host_metrics", "load1"): ("1/100", "Host system one minute load in 1/100ths"),
    ("telemetry:host_metrics", "load5"): ("1/100", "Host system five minute load in 1/100ths"),
    ("telemetry:host_metrics", "load15"): ("1/100", "Host system fifteen minute load in 1/100ths"),
}


# Index and scale values with no unit to derive the kind from.
QUANTITY_KIND_WITHOUT_UNIT: dict[tuple[str, str], str] = {
    ("telemetry:environment_metrics", "iaq"): OTHER,
    ("telemetry:air_quality_metrics", "pm_temperature"): PHYSICAL_PROPERTY,
    ("telemetry:air_quality_metrics", "pm_humidity"): RATIO,
    ("telemetry:air_quality_metrics", "pm_voc_idx"): OTHER,
    ("telemetry:air_quality_metrics", "pm_nox_idx"): OTHER,
}


def defaults_for(payload_kind: str, field_name: str) -> dict:
    """Curated column values for one catalog row, all None for an unknown field."""
    native_unit, description = MEASUREMENT_TYPE_SEED.get((payload_kind, field_name), (None, None))
    return {
        "native_unit": native_unit,
        "quantity_kind": quantity_kind_for(native_unit)
        or QUANTITY_KIND_WITHOUT_UNIT.get((payload_kind, field_name)),
        "description": description,
    }
