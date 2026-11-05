from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TelemetrySensorType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SENSOR_UNSET: _ClassVar[TelemetrySensorType]
    BME280: _ClassVar[TelemetrySensorType]
    BME680: _ClassVar[TelemetrySensorType]
    MCP9808: _ClassVar[TelemetrySensorType]
    INA260: _ClassVar[TelemetrySensorType]
    INA219: _ClassVar[TelemetrySensorType]
    BMP280: _ClassVar[TelemetrySensorType]
    SHTC3: _ClassVar[TelemetrySensorType]
    LPS22: _ClassVar[TelemetrySensorType]
    QMC6310: _ClassVar[TelemetrySensorType]
    QMI8658: _ClassVar[TelemetrySensorType]
    QMC5883L: _ClassVar[TelemetrySensorType]
    SHT31: _ClassVar[TelemetrySensorType]
    PMSA003I: _ClassVar[TelemetrySensorType]
    INA3221: _ClassVar[TelemetrySensorType]
    BMP085: _ClassVar[TelemetrySensorType]
    RCWL9620: _ClassVar[TelemetrySensorType]
    SHT4X: _ClassVar[TelemetrySensorType]
    VEML7700: _ClassVar[TelemetrySensorType]
    MLX90632: _ClassVar[TelemetrySensorType]
    OPT3001: _ClassVar[TelemetrySensorType]
    LTR390UV: _ClassVar[TelemetrySensorType]
    TSL25911FN: _ClassVar[TelemetrySensorType]
    AHT10: _ClassVar[TelemetrySensorType]
    DFROBOT_LARK: _ClassVar[TelemetrySensorType]
    NAU7802: _ClassVar[TelemetrySensorType]
    BMP3XX: _ClassVar[TelemetrySensorType]
    ICM20948: _ClassVar[TelemetrySensorType]
    MAX17048: _ClassVar[TelemetrySensorType]
    CUSTOM_SENSOR: _ClassVar[TelemetrySensorType]
    MAX30102: _ClassVar[TelemetrySensorType]
    MLX90614: _ClassVar[TelemetrySensorType]
    SCD4X: _ClassVar[TelemetrySensorType]
    RADSENS: _ClassVar[TelemetrySensorType]
    INA226: _ClassVar[TelemetrySensorType]
    DFROBOT_RAIN: _ClassVar[TelemetrySensorType]
    DPS310: _ClassVar[TelemetrySensorType]
    RAK12035: _ClassVar[TelemetrySensorType]
    MAX17261: _ClassVar[TelemetrySensorType]
    PCT2075: _ClassVar[TelemetrySensorType]
    ADS1X15: _ClassVar[TelemetrySensorType]
    ADS1X15_ALT: _ClassVar[TelemetrySensorType]
    SFA30: _ClassVar[TelemetrySensorType]
    SEN5X: _ClassVar[TelemetrySensorType]
    TSL2561: _ClassVar[TelemetrySensorType]
    BH1750: _ClassVar[TelemetrySensorType]
    HDC1080: _ClassVar[TelemetrySensorType]
    SHT21: _ClassVar[TelemetrySensorType]
    STC31: _ClassVar[TelemetrySensorType]
    SCD30: _ClassVar[TelemetrySensorType]
    SHTXX: _ClassVar[TelemetrySensorType]
    DS248X: _ClassVar[TelemetrySensorType]
    MMC5983MA: _ClassVar[TelemetrySensorType]
    ICM42607P: _ClassVar[TelemetrySensorType]
    SPA06: _ClassVar[TelemetrySensorType]
    HM330X: _ClassVar[TelemetrySensorType]
    SEN6X: _ClassVar[TelemetrySensorType]
    AS3935: _ClassVar[TelemetrySensorType]
SENSOR_UNSET: TelemetrySensorType
BME280: TelemetrySensorType
BME680: TelemetrySensorType
MCP9808: TelemetrySensorType
INA260: TelemetrySensorType
INA219: TelemetrySensorType
BMP280: TelemetrySensorType
SHTC3: TelemetrySensorType
LPS22: TelemetrySensorType
QMC6310: TelemetrySensorType
QMI8658: TelemetrySensorType
QMC5883L: TelemetrySensorType
SHT31: TelemetrySensorType
PMSA003I: TelemetrySensorType
INA3221: TelemetrySensorType
BMP085: TelemetrySensorType
RCWL9620: TelemetrySensorType
SHT4X: TelemetrySensorType
VEML7700: TelemetrySensorType
MLX90632: TelemetrySensorType
OPT3001: TelemetrySensorType
LTR390UV: TelemetrySensorType
TSL25911FN: TelemetrySensorType
AHT10: TelemetrySensorType
DFROBOT_LARK: TelemetrySensorType
NAU7802: TelemetrySensorType
BMP3XX: TelemetrySensorType
ICM20948: TelemetrySensorType
MAX17048: TelemetrySensorType
CUSTOM_SENSOR: TelemetrySensorType
MAX30102: TelemetrySensorType
MLX90614: TelemetrySensorType
SCD4X: TelemetrySensorType
RADSENS: TelemetrySensorType
INA226: TelemetrySensorType
DFROBOT_RAIN: TelemetrySensorType
DPS310: TelemetrySensorType
RAK12035: TelemetrySensorType
MAX17261: TelemetrySensorType
PCT2075: TelemetrySensorType
ADS1X15: TelemetrySensorType
ADS1X15_ALT: TelemetrySensorType
SFA30: TelemetrySensorType
SEN5X: TelemetrySensorType
TSL2561: TelemetrySensorType
BH1750: TelemetrySensorType
HDC1080: TelemetrySensorType
SHT21: TelemetrySensorType
STC31: TelemetrySensorType
SCD30: TelemetrySensorType
SHTXX: TelemetrySensorType
DS248X: TelemetrySensorType
MMC5983MA: TelemetrySensorType
ICM42607P: TelemetrySensorType
SPA06: TelemetrySensorType
HM330X: TelemetrySensorType
SEN6X: TelemetrySensorType
AS3935: TelemetrySensorType

class DeviceMetrics(_message.Message):
    __slots__ = ("battery_level", "voltage", "channel_utilization", "air_util_tx", "uptime_seconds")
    BATTERY_LEVEL_FIELD_NUMBER: _ClassVar[int]
    VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_UTILIZATION_FIELD_NUMBER: _ClassVar[int]
    AIR_UTIL_TX_FIELD_NUMBER: _ClassVar[int]
    UPTIME_SECONDS_FIELD_NUMBER: _ClassVar[int]
    battery_level: int
    voltage: float
    channel_utilization: float
    air_util_tx: float
    uptime_seconds: int
    def __init__(self, battery_level: _Optional[int] = ..., voltage: _Optional[float] = ..., channel_utilization: _Optional[float] = ..., air_util_tx: _Optional[float] = ..., uptime_seconds: _Optional[int] = ...) -> None: ...

class EnvironmentMetrics(_message.Message):
    __slots__ = ("temperature", "relative_humidity", "barometric_pressure", "gas_resistance", "voltage", "current", "iaq", "distance", "lux", "white_lux", "ir_lux", "uv_lux", "wind_direction", "wind_speed", "weight", "wind_gust", "wind_lull", "radiation", "rainfall_1h", "rainfall_24h", "soil_moisture", "soil_temperature", "one_wire_temperature", "adc_voltage_ch0", "adc_voltage_ch1", "adc_voltage_ch2", "adc_voltage_ch3", "adc_voltage_ch4", "adc_voltage_ch5", "adc_voltage_ch6", "adc_voltage_ch7", "one_wire_temperature_ch0", "one_wire_temperature_ch1", "one_wire_temperature_ch2", "one_wire_temperature_ch3", "one_wire_temperature_ch4", "one_wire_temperature_ch5", "one_wire_temperature_ch6", "one_wire_temperature_ch7", "lightning_strike_count_1h", "lightning_distance_km")
    TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    RELATIVE_HUMIDITY_FIELD_NUMBER: _ClassVar[int]
    BAROMETRIC_PRESSURE_FIELD_NUMBER: _ClassVar[int]
    GAS_RESISTANCE_FIELD_NUMBER: _ClassVar[int]
    VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    CURRENT_FIELD_NUMBER: _ClassVar[int]
    IAQ_FIELD_NUMBER: _ClassVar[int]
    DISTANCE_FIELD_NUMBER: _ClassVar[int]
    LUX_FIELD_NUMBER: _ClassVar[int]
    WHITE_LUX_FIELD_NUMBER: _ClassVar[int]
    IR_LUX_FIELD_NUMBER: _ClassVar[int]
    UV_LUX_FIELD_NUMBER: _ClassVar[int]
    WIND_DIRECTION_FIELD_NUMBER: _ClassVar[int]
    WIND_SPEED_FIELD_NUMBER: _ClassVar[int]
    WEIGHT_FIELD_NUMBER: _ClassVar[int]
    WIND_GUST_FIELD_NUMBER: _ClassVar[int]
    WIND_LULL_FIELD_NUMBER: _ClassVar[int]
    RADIATION_FIELD_NUMBER: _ClassVar[int]
    RAINFALL_1H_FIELD_NUMBER: _ClassVar[int]
    RAINFALL_24H_FIELD_NUMBER: _ClassVar[int]
    SOIL_MOISTURE_FIELD_NUMBER: _ClassVar[int]
    SOIL_TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    ONE_WIRE_TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    ADC_VOLTAGE_CH0_FIELD_NUMBER: _ClassVar[int]
    ADC_VOLTAGE_CH1_FIELD_NUMBER: _ClassVar[int]
    ADC_VOLTAGE_CH2_FIELD_NUMBER: _ClassVar[int]
    ADC_VOLTAGE_CH3_FIELD_NUMBER: _ClassVar[int]
    ADC_VOLTAGE_CH4_FIELD_NUMBER: _ClassVar[int]
    ADC_VOLTAGE_CH5_FIELD_NUMBER: _ClassVar[int]
    ADC_VOLTAGE_CH6_FIELD_NUMBER: _ClassVar[int]
    ADC_VOLTAGE_CH7_FIELD_NUMBER: _ClassVar[int]
    ONE_WIRE_TEMPERATURE_CH0_FIELD_NUMBER: _ClassVar[int]
    ONE_WIRE_TEMPERATURE_CH1_FIELD_NUMBER: _ClassVar[int]
    ONE_WIRE_TEMPERATURE_CH2_FIELD_NUMBER: _ClassVar[int]
    ONE_WIRE_TEMPERATURE_CH3_FIELD_NUMBER: _ClassVar[int]
    ONE_WIRE_TEMPERATURE_CH4_FIELD_NUMBER: _ClassVar[int]
    ONE_WIRE_TEMPERATURE_CH5_FIELD_NUMBER: _ClassVar[int]
    ONE_WIRE_TEMPERATURE_CH6_FIELD_NUMBER: _ClassVar[int]
    ONE_WIRE_TEMPERATURE_CH7_FIELD_NUMBER: _ClassVar[int]
    LIGHTNING_STRIKE_COUNT_1H_FIELD_NUMBER: _ClassVar[int]
    LIGHTNING_DISTANCE_KM_FIELD_NUMBER: _ClassVar[int]
    temperature: float
    relative_humidity: float
    barometric_pressure: float
    gas_resistance: float
    voltage: float
    current: float
    iaq: int
    distance: float
    lux: float
    white_lux: float
    ir_lux: float
    uv_lux: float
    wind_direction: int
    wind_speed: float
    weight: float
    wind_gust: float
    wind_lull: float
    radiation: float
    rainfall_1h: float
    rainfall_24h: float
    soil_moisture: int
    soil_temperature: float
    one_wire_temperature: _containers.RepeatedScalarFieldContainer[float]
    adc_voltage_ch0: float
    adc_voltage_ch1: float
    adc_voltage_ch2: float
    adc_voltage_ch3: float
    adc_voltage_ch4: float
    adc_voltage_ch5: float
    adc_voltage_ch6: float
    adc_voltage_ch7: float
    one_wire_temperature_ch0: float
    one_wire_temperature_ch1: float
    one_wire_temperature_ch2: float
    one_wire_temperature_ch3: float
    one_wire_temperature_ch4: float
    one_wire_temperature_ch5: float
    one_wire_temperature_ch6: float
    one_wire_temperature_ch7: float
    lightning_strike_count_1h: int
    lightning_distance_km: float
    def __init__(self, temperature: _Optional[float] = ..., relative_humidity: _Optional[float] = ..., barometric_pressure: _Optional[float] = ..., gas_resistance: _Optional[float] = ..., voltage: _Optional[float] = ..., current: _Optional[float] = ..., iaq: _Optional[int] = ..., distance: _Optional[float] = ..., lux: _Optional[float] = ..., white_lux: _Optional[float] = ..., ir_lux: _Optional[float] = ..., uv_lux: _Optional[float] = ..., wind_direction: _Optional[int] = ..., wind_speed: _Optional[float] = ..., weight: _Optional[float] = ..., wind_gust: _Optional[float] = ..., wind_lull: _Optional[float] = ..., radiation: _Optional[float] = ..., rainfall_1h: _Optional[float] = ..., rainfall_24h: _Optional[float] = ..., soil_moisture: _Optional[int] = ..., soil_temperature: _Optional[float] = ..., one_wire_temperature: _Optional[_Iterable[float]] = ..., adc_voltage_ch0: _Optional[float] = ..., adc_voltage_ch1: _Optional[float] = ..., adc_voltage_ch2: _Optional[float] = ..., adc_voltage_ch3: _Optional[float] = ..., adc_voltage_ch4: _Optional[float] = ..., adc_voltage_ch5: _Optional[float] = ..., adc_voltage_ch6: _Optional[float] = ..., adc_voltage_ch7: _Optional[float] = ..., one_wire_temperature_ch0: _Optional[float] = ..., one_wire_temperature_ch1: _Optional[float] = ..., one_wire_temperature_ch2: _Optional[float] = ..., one_wire_temperature_ch3: _Optional[float] = ..., one_wire_temperature_ch4: _Optional[float] = ..., one_wire_temperature_ch5: _Optional[float] = ..., one_wire_temperature_ch6: _Optional[float] = ..., one_wire_temperature_ch7: _Optional[float] = ..., lightning_strike_count_1h: _Optional[int] = ..., lightning_distance_km: _Optional[float] = ...) -> None: ...

class SoilWaterMetrics(_message.Message):
    __slots__ = ("soil_ph", "ph", "electrical_conductivity", "salinity", "nitrogen", "phosphorus", "potassium", "dissolved_oxygen", "orp", "chemical_oxygen_demand", "turbidity", "nitrate", "ammonium", "biochemical_oxygen_demand", "solar_irradiance")
    SOIL_PH_FIELD_NUMBER: _ClassVar[int]
    PH_FIELD_NUMBER: _ClassVar[int]
    ELECTRICAL_CONDUCTIVITY_FIELD_NUMBER: _ClassVar[int]
    SALINITY_FIELD_NUMBER: _ClassVar[int]
    NITROGEN_FIELD_NUMBER: _ClassVar[int]
    PHOSPHORUS_FIELD_NUMBER: _ClassVar[int]
    POTASSIUM_FIELD_NUMBER: _ClassVar[int]
    DISSOLVED_OXYGEN_FIELD_NUMBER: _ClassVar[int]
    ORP_FIELD_NUMBER: _ClassVar[int]
    CHEMICAL_OXYGEN_DEMAND_FIELD_NUMBER: _ClassVar[int]
    TURBIDITY_FIELD_NUMBER: _ClassVar[int]
    NITRATE_FIELD_NUMBER: _ClassVar[int]
    AMMONIUM_FIELD_NUMBER: _ClassVar[int]
    BIOCHEMICAL_OXYGEN_DEMAND_FIELD_NUMBER: _ClassVar[int]
    SOLAR_IRRADIANCE_FIELD_NUMBER: _ClassVar[int]
    soil_ph: float
    ph: float
    electrical_conductivity: float
    salinity: float
    nitrogen: float
    phosphorus: float
    potassium: float
    dissolved_oxygen: float
    orp: float
    chemical_oxygen_demand: float
    turbidity: float
    nitrate: float
    ammonium: float
    biochemical_oxygen_demand: float
    solar_irradiance: float
    def __init__(self, soil_ph: _Optional[float] = ..., ph: _Optional[float] = ..., electrical_conductivity: _Optional[float] = ..., salinity: _Optional[float] = ..., nitrogen: _Optional[float] = ..., phosphorus: _Optional[float] = ..., potassium: _Optional[float] = ..., dissolved_oxygen: _Optional[float] = ..., orp: _Optional[float] = ..., chemical_oxygen_demand: _Optional[float] = ..., turbidity: _Optional[float] = ..., nitrate: _Optional[float] = ..., ammonium: _Optional[float] = ..., biochemical_oxygen_demand: _Optional[float] = ..., solar_irradiance: _Optional[float] = ...) -> None: ...

class PowerMetrics(_message.Message):
    __slots__ = ("ch1_voltage", "ch1_current", "ch2_voltage", "ch2_current", "ch3_voltage", "ch3_current", "ch4_voltage", "ch4_current", "ch5_voltage", "ch5_current", "ch6_voltage", "ch6_current", "ch7_voltage", "ch7_current", "ch8_voltage", "ch8_current")
    CH1_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    CH1_CURRENT_FIELD_NUMBER: _ClassVar[int]
    CH2_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    CH2_CURRENT_FIELD_NUMBER: _ClassVar[int]
    CH3_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    CH3_CURRENT_FIELD_NUMBER: _ClassVar[int]
    CH4_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    CH4_CURRENT_FIELD_NUMBER: _ClassVar[int]
    CH5_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    CH5_CURRENT_FIELD_NUMBER: _ClassVar[int]
    CH6_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    CH6_CURRENT_FIELD_NUMBER: _ClassVar[int]
    CH7_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    CH7_CURRENT_FIELD_NUMBER: _ClassVar[int]
    CH8_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    CH8_CURRENT_FIELD_NUMBER: _ClassVar[int]
    ch1_voltage: float
    ch1_current: float
    ch2_voltage: float
    ch2_current: float
    ch3_voltage: float
    ch3_current: float
    ch4_voltage: float
    ch4_current: float
    ch5_voltage: float
    ch5_current: float
    ch6_voltage: float
    ch6_current: float
    ch7_voltage: float
    ch7_current: float
    ch8_voltage: float
    ch8_current: float
    def __init__(self, ch1_voltage: _Optional[float] = ..., ch1_current: _Optional[float] = ..., ch2_voltage: _Optional[float] = ..., ch2_current: _Optional[float] = ..., ch3_voltage: _Optional[float] = ..., ch3_current: _Optional[float] = ..., ch4_voltage: _Optional[float] = ..., ch4_current: _Optional[float] = ..., ch5_voltage: _Optional[float] = ..., ch5_current: _Optional[float] = ..., ch6_voltage: _Optional[float] = ..., ch6_current: _Optional[float] = ..., ch7_voltage: _Optional[float] = ..., ch7_current: _Optional[float] = ..., ch8_voltage: _Optional[float] = ..., ch8_current: _Optional[float] = ...) -> None: ...

class AirQualityMetrics(_message.Message):
    __slots__ = ("pm10_standard", "pm25_standard", "pm100_standard", "pm10_environmental", "pm25_environmental", "pm100_environmental", "particles_03um", "particles_05um", "particles_10um", "particles_25um", "particles_50um", "particles_100um", "co2", "co2_temperature", "co2_humidity", "form_formaldehyde", "form_humidity", "form_temperature", "pm40_standard", "particles_40um", "pm_temperature", "pm_humidity", "pm_voc_idx", "pm_nox_idx", "particles_tps", "pm_status_flags")
    PM10_STANDARD_FIELD_NUMBER: _ClassVar[int]
    PM25_STANDARD_FIELD_NUMBER: _ClassVar[int]
    PM100_STANDARD_FIELD_NUMBER: _ClassVar[int]
    PM10_ENVIRONMENTAL_FIELD_NUMBER: _ClassVar[int]
    PM25_ENVIRONMENTAL_FIELD_NUMBER: _ClassVar[int]
    PM100_ENVIRONMENTAL_FIELD_NUMBER: _ClassVar[int]
    PARTICLES_03UM_FIELD_NUMBER: _ClassVar[int]
    PARTICLES_05UM_FIELD_NUMBER: _ClassVar[int]
    PARTICLES_10UM_FIELD_NUMBER: _ClassVar[int]
    PARTICLES_25UM_FIELD_NUMBER: _ClassVar[int]
    PARTICLES_50UM_FIELD_NUMBER: _ClassVar[int]
    PARTICLES_100UM_FIELD_NUMBER: _ClassVar[int]
    CO2_FIELD_NUMBER: _ClassVar[int]
    CO2_TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    CO2_HUMIDITY_FIELD_NUMBER: _ClassVar[int]
    FORM_FORMALDEHYDE_FIELD_NUMBER: _ClassVar[int]
    FORM_HUMIDITY_FIELD_NUMBER: _ClassVar[int]
    FORM_TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    PM40_STANDARD_FIELD_NUMBER: _ClassVar[int]
    PARTICLES_40UM_FIELD_NUMBER: _ClassVar[int]
    PM_TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    PM_HUMIDITY_FIELD_NUMBER: _ClassVar[int]
    PM_VOC_IDX_FIELD_NUMBER: _ClassVar[int]
    PM_NOX_IDX_FIELD_NUMBER: _ClassVar[int]
    PARTICLES_TPS_FIELD_NUMBER: _ClassVar[int]
    PM_STATUS_FLAGS_FIELD_NUMBER: _ClassVar[int]
    pm10_standard: int
    pm25_standard: int
    pm100_standard: int
    pm10_environmental: int
    pm25_environmental: int
    pm100_environmental: int
    particles_03um: int
    particles_05um: int
    particles_10um: int
    particles_25um: int
    particles_50um: int
    particles_100um: int
    co2: int
    co2_temperature: float
    co2_humidity: float
    form_formaldehyde: float
    form_humidity: float
    form_temperature: float
    pm40_standard: int
    particles_40um: int
    pm_temperature: float
    pm_humidity: float
    pm_voc_idx: float
    pm_nox_idx: float
    particles_tps: float
    pm_status_flags: int
    def __init__(self, pm10_standard: _Optional[int] = ..., pm25_standard: _Optional[int] = ..., pm100_standard: _Optional[int] = ..., pm10_environmental: _Optional[int] = ..., pm25_environmental: _Optional[int] = ..., pm100_environmental: _Optional[int] = ..., particles_03um: _Optional[int] = ..., particles_05um: _Optional[int] = ..., particles_10um: _Optional[int] = ..., particles_25um: _Optional[int] = ..., particles_50um: _Optional[int] = ..., particles_100um: _Optional[int] = ..., co2: _Optional[int] = ..., co2_temperature: _Optional[float] = ..., co2_humidity: _Optional[float] = ..., form_formaldehyde: _Optional[float] = ..., form_humidity: _Optional[float] = ..., form_temperature: _Optional[float] = ..., pm40_standard: _Optional[int] = ..., particles_40um: _Optional[int] = ..., pm_temperature: _Optional[float] = ..., pm_humidity: _Optional[float] = ..., pm_voc_idx: _Optional[float] = ..., pm_nox_idx: _Optional[float] = ..., particles_tps: _Optional[float] = ..., pm_status_flags: _Optional[int] = ...) -> None: ...

class LocalStats(_message.Message):
    __slots__ = ("uptime_seconds", "channel_utilization", "air_util_tx", "num_packets_tx", "num_packets_rx", "num_packets_rx_bad", "num_online_nodes", "num_total_nodes", "num_rx_dupe", "num_tx_relay", "num_tx_relay_canceled", "heap_total_bytes", "heap_free_bytes", "num_tx_dropped", "noise_floor")
    UPTIME_SECONDS_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_UTILIZATION_FIELD_NUMBER: _ClassVar[int]
    AIR_UTIL_TX_FIELD_NUMBER: _ClassVar[int]
    NUM_PACKETS_TX_FIELD_NUMBER: _ClassVar[int]
    NUM_PACKETS_RX_FIELD_NUMBER: _ClassVar[int]
    NUM_PACKETS_RX_BAD_FIELD_NUMBER: _ClassVar[int]
    NUM_ONLINE_NODES_FIELD_NUMBER: _ClassVar[int]
    NUM_TOTAL_NODES_FIELD_NUMBER: _ClassVar[int]
    NUM_RX_DUPE_FIELD_NUMBER: _ClassVar[int]
    NUM_TX_RELAY_FIELD_NUMBER: _ClassVar[int]
    NUM_TX_RELAY_CANCELED_FIELD_NUMBER: _ClassVar[int]
    HEAP_TOTAL_BYTES_FIELD_NUMBER: _ClassVar[int]
    HEAP_FREE_BYTES_FIELD_NUMBER: _ClassVar[int]
    NUM_TX_DROPPED_FIELD_NUMBER: _ClassVar[int]
    NOISE_FLOOR_FIELD_NUMBER: _ClassVar[int]
    uptime_seconds: int
    channel_utilization: float
    air_util_tx: float
    num_packets_tx: int
    num_packets_rx: int
    num_packets_rx_bad: int
    num_online_nodes: int
    num_total_nodes: int
    num_rx_dupe: int
    num_tx_relay: int
    num_tx_relay_canceled: int
    heap_total_bytes: int
    heap_free_bytes: int
    num_tx_dropped: int
    noise_floor: int
    def __init__(self, uptime_seconds: _Optional[int] = ..., channel_utilization: _Optional[float] = ..., air_util_tx: _Optional[float] = ..., num_packets_tx: _Optional[int] = ..., num_packets_rx: _Optional[int] = ..., num_packets_rx_bad: _Optional[int] = ..., num_online_nodes: _Optional[int] = ..., num_total_nodes: _Optional[int] = ..., num_rx_dupe: _Optional[int] = ..., num_tx_relay: _Optional[int] = ..., num_tx_relay_canceled: _Optional[int] = ..., heap_total_bytes: _Optional[int] = ..., heap_free_bytes: _Optional[int] = ..., num_tx_dropped: _Optional[int] = ..., noise_floor: _Optional[int] = ...) -> None: ...

class TrafficManagementStats(_message.Message):
    __slots__ = ("packets_inspected", "position_dedup_drops", "nodeinfo_cache_hits", "rate_limit_drops", "unknown_packet_drops", "hop_exhausted_packets", "router_hops_preserved")
    PACKETS_INSPECTED_FIELD_NUMBER: _ClassVar[int]
    POSITION_DEDUP_DROPS_FIELD_NUMBER: _ClassVar[int]
    NODEINFO_CACHE_HITS_FIELD_NUMBER: _ClassVar[int]
    RATE_LIMIT_DROPS_FIELD_NUMBER: _ClassVar[int]
    UNKNOWN_PACKET_DROPS_FIELD_NUMBER: _ClassVar[int]
    HOP_EXHAUSTED_PACKETS_FIELD_NUMBER: _ClassVar[int]
    ROUTER_HOPS_PRESERVED_FIELD_NUMBER: _ClassVar[int]
    packets_inspected: int
    position_dedup_drops: int
    nodeinfo_cache_hits: int
    rate_limit_drops: int
    unknown_packet_drops: int
    hop_exhausted_packets: int
    router_hops_preserved: int
    def __init__(self, packets_inspected: _Optional[int] = ..., position_dedup_drops: _Optional[int] = ..., nodeinfo_cache_hits: _Optional[int] = ..., rate_limit_drops: _Optional[int] = ..., unknown_packet_drops: _Optional[int] = ..., hop_exhausted_packets: _Optional[int] = ..., router_hops_preserved: _Optional[int] = ...) -> None: ...

class HealthMetrics(_message.Message):
    __slots__ = ("heart_bpm", "spO2", "temperature")
    HEART_BPM_FIELD_NUMBER: _ClassVar[int]
    SPO2_FIELD_NUMBER: _ClassVar[int]
    TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    heart_bpm: int
    spO2: int
    temperature: float
    def __init__(self, heart_bpm: _Optional[int] = ..., spO2: _Optional[int] = ..., temperature: _Optional[float] = ...) -> None: ...

class HostMetrics(_message.Message):
    __slots__ = ("uptime_seconds", "freemem_bytes", "diskfree1_bytes", "diskfree2_bytes", "diskfree3_bytes", "load1", "load5", "load15", "user_string")
    UPTIME_SECONDS_FIELD_NUMBER: _ClassVar[int]
    FREEMEM_BYTES_FIELD_NUMBER: _ClassVar[int]
    DISKFREE1_BYTES_FIELD_NUMBER: _ClassVar[int]
    DISKFREE2_BYTES_FIELD_NUMBER: _ClassVar[int]
    DISKFREE3_BYTES_FIELD_NUMBER: _ClassVar[int]
    LOAD1_FIELD_NUMBER: _ClassVar[int]
    LOAD5_FIELD_NUMBER: _ClassVar[int]
    LOAD15_FIELD_NUMBER: _ClassVar[int]
    USER_STRING_FIELD_NUMBER: _ClassVar[int]
    uptime_seconds: int
    freemem_bytes: int
    diskfree1_bytes: int
    diskfree2_bytes: int
    diskfree3_bytes: int
    load1: int
    load5: int
    load15: int
    user_string: str
    def __init__(self, uptime_seconds: _Optional[int] = ..., freemem_bytes: _Optional[int] = ..., diskfree1_bytes: _Optional[int] = ..., diskfree2_bytes: _Optional[int] = ..., diskfree3_bytes: _Optional[int] = ..., load1: _Optional[int] = ..., load5: _Optional[int] = ..., load15: _Optional[int] = ..., user_string: _Optional[str] = ...) -> None: ...

class Telemetry(_message.Message):
    __slots__ = ("time", "device_metrics", "environment_metrics", "air_quality_metrics", "power_metrics", "local_stats", "health_metrics", "host_metrics", "traffic_management_stats", "soil_water_metrics")
    TIME_FIELD_NUMBER: _ClassVar[int]
    DEVICE_METRICS_FIELD_NUMBER: _ClassVar[int]
    ENVIRONMENT_METRICS_FIELD_NUMBER: _ClassVar[int]
    AIR_QUALITY_METRICS_FIELD_NUMBER: _ClassVar[int]
    POWER_METRICS_FIELD_NUMBER: _ClassVar[int]
    LOCAL_STATS_FIELD_NUMBER: _ClassVar[int]
    HEALTH_METRICS_FIELD_NUMBER: _ClassVar[int]
    HOST_METRICS_FIELD_NUMBER: _ClassVar[int]
    TRAFFIC_MANAGEMENT_STATS_FIELD_NUMBER: _ClassVar[int]
    SOIL_WATER_METRICS_FIELD_NUMBER: _ClassVar[int]
    time: int
    device_metrics: DeviceMetrics
    environment_metrics: EnvironmentMetrics
    air_quality_metrics: AirQualityMetrics
    power_metrics: PowerMetrics
    local_stats: LocalStats
    health_metrics: HealthMetrics
    host_metrics: HostMetrics
    traffic_management_stats: TrafficManagementStats
    soil_water_metrics: SoilWaterMetrics
    def __init__(self, time: _Optional[int] = ..., device_metrics: _Optional[_Union[DeviceMetrics, _Mapping]] = ..., environment_metrics: _Optional[_Union[EnvironmentMetrics, _Mapping]] = ..., air_quality_metrics: _Optional[_Union[AirQualityMetrics, _Mapping]] = ..., power_metrics: _Optional[_Union[PowerMetrics, _Mapping]] = ..., local_stats: _Optional[_Union[LocalStats, _Mapping]] = ..., health_metrics: _Optional[_Union[HealthMetrics, _Mapping]] = ..., host_metrics: _Optional[_Union[HostMetrics, _Mapping]] = ..., traffic_management_stats: _Optional[_Union[TrafficManagementStats, _Mapping]] = ..., soil_water_metrics: _Optional[_Union[SoilWaterMetrics, _Mapping]] = ...) -> None: ...

class Nau7802Config(_message.Message):
    __slots__ = ("zeroOffset", "calibrationFactor")
    ZEROOFFSET_FIELD_NUMBER: _ClassVar[int]
    CALIBRATIONFACTOR_FIELD_NUMBER: _ClassVar[int]
    zeroOffset: int
    calibrationFactor: float
    def __init__(self, zeroOffset: _Optional[int] = ..., calibrationFactor: _Optional[float] = ...) -> None: ...

class AS3935State(_message.Message):
    __slots__ = ("tuning_cap_pf",)
    TUNING_CAP_PF_FIELD_NUMBER: _ClassVar[int]
    tuning_cap_pf: int
    def __init__(self, tuning_cap_pf: _Optional[int] = ...) -> None: ...

class SEN5XState(_message.Message):
    __slots__ = ("last_cleaning_time", "last_cleaning_valid", "one_shot_mode", "voc_state_time", "voc_state_valid", "voc_state_array")
    LAST_CLEANING_TIME_FIELD_NUMBER: _ClassVar[int]
    LAST_CLEANING_VALID_FIELD_NUMBER: _ClassVar[int]
    ONE_SHOT_MODE_FIELD_NUMBER: _ClassVar[int]
    VOC_STATE_TIME_FIELD_NUMBER: _ClassVar[int]
    VOC_STATE_VALID_FIELD_NUMBER: _ClassVar[int]
    VOC_STATE_ARRAY_FIELD_NUMBER: _ClassVar[int]
    last_cleaning_time: int
    last_cleaning_valid: bool
    one_shot_mode: bool
    voc_state_time: int
    voc_state_valid: bool
    voc_state_array: int
    def __init__(self, last_cleaning_time: _Optional[int] = ..., last_cleaning_valid: bool = ..., one_shot_mode: bool = ..., voc_state_time: _Optional[int] = ..., voc_state_valid: bool = ..., voc_state_array: _Optional[int] = ...) -> None: ...

class SEN6XState(_message.Message):
    __slots__ = ("last_cleaning_time", "last_cleaning_valid", "one_shot_mode", "voc_state_time", "voc_state_valid", "voc_state_array")
    LAST_CLEANING_TIME_FIELD_NUMBER: _ClassVar[int]
    LAST_CLEANING_VALID_FIELD_NUMBER: _ClassVar[int]
    ONE_SHOT_MODE_FIELD_NUMBER: _ClassVar[int]
    VOC_STATE_TIME_FIELD_NUMBER: _ClassVar[int]
    VOC_STATE_VALID_FIELD_NUMBER: _ClassVar[int]
    VOC_STATE_ARRAY_FIELD_NUMBER: _ClassVar[int]
    last_cleaning_time: int
    last_cleaning_valid: bool
    one_shot_mode: bool
    voc_state_time: int
    voc_state_valid: bool
    voc_state_array: int
    def __init__(self, last_cleaning_time: _Optional[int] = ..., last_cleaning_valid: bool = ..., one_shot_mode: bool = ..., voc_state_time: _Optional[int] = ..., voc_state_valid: bool = ..., voc_state_array: _Optional[int] = ...) -> None: ...
