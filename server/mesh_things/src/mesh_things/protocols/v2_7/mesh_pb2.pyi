from mesh_things.protocols.v2_7 import channel_pb2 as _channel_pb2
from mesh_things.protocols.v2_7 import config_pb2 as _config_pb2
from mesh_things.protocols.v2_7 import device_ui_pb2 as _device_ui_pb2
from mesh_things.protocols.v2_7 import module_config_pb2 as _module_config_pb2
from mesh_things.protocols.v2_7 import portnums_pb2 as _portnums_pb2
from mesh_things.protocols.v2_7 import telemetry_pb2 as _telemetry_pb2
from mesh_things.protocols.v2_7 import xmodem_pb2 as _xmodem_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HardwareModel(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UNSET: _ClassVar[HardwareModel]
    TLORA_V2: _ClassVar[HardwareModel]
    TLORA_V1: _ClassVar[HardwareModel]
    TLORA_V2_1_1P6: _ClassVar[HardwareModel]
    TBEAM: _ClassVar[HardwareModel]
    HELTEC_V2_0: _ClassVar[HardwareModel]
    TBEAM_V0P7: _ClassVar[HardwareModel]
    T_ECHO: _ClassVar[HardwareModel]
    TLORA_V1_1P3: _ClassVar[HardwareModel]
    RAK4631: _ClassVar[HardwareModel]
    HELTEC_V2_1: _ClassVar[HardwareModel]
    HELTEC_V1: _ClassVar[HardwareModel]
    LILYGO_TBEAM_S3_CORE: _ClassVar[HardwareModel]
    RAK11200: _ClassVar[HardwareModel]
    NANO_G1: _ClassVar[HardwareModel]
    TLORA_V2_1_1P8: _ClassVar[HardwareModel]
    TLORA_T3_S3: _ClassVar[HardwareModel]
    NANO_G1_EXPLORER: _ClassVar[HardwareModel]
    NANO_G2_ULTRA: _ClassVar[HardwareModel]
    LORA_TYPE: _ClassVar[HardwareModel]
    WIPHONE: _ClassVar[HardwareModel]
    WIO_WM1110: _ClassVar[HardwareModel]
    RAK2560: _ClassVar[HardwareModel]
    HELTEC_HRU_3601: _ClassVar[HardwareModel]
    HELTEC_WIRELESS_BRIDGE: _ClassVar[HardwareModel]
    STATION_G1: _ClassVar[HardwareModel]
    RAK11310: _ClassVar[HardwareModel]
    SENSELORA_RP2040: _ClassVar[HardwareModel]
    SENSELORA_S3: _ClassVar[HardwareModel]
    CANARYONE: _ClassVar[HardwareModel]
    RP2040_LORA: _ClassVar[HardwareModel]
    STATION_G2: _ClassVar[HardwareModel]
    LORA_RELAY_V1: _ClassVar[HardwareModel]
    T_ECHO_PLUS: _ClassVar[HardwareModel]
    PPR: _ClassVar[HardwareModel]
    GENIEBLOCKS: _ClassVar[HardwareModel]
    NRF52_UNKNOWN: _ClassVar[HardwareModel]
    PORTDUINO: _ClassVar[HardwareModel]
    ANDROID_SIM: _ClassVar[HardwareModel]
    DIY_V1: _ClassVar[HardwareModel]
    NRF52840_PCA10059: _ClassVar[HardwareModel]
    DR_DEV: _ClassVar[HardwareModel]
    M5STACK: _ClassVar[HardwareModel]
    HELTEC_V3: _ClassVar[HardwareModel]
    HELTEC_WSL_V3: _ClassVar[HardwareModel]
    BETAFPV_2400_TX: _ClassVar[HardwareModel]
    BETAFPV_900_NANO_TX: _ClassVar[HardwareModel]
    RPI_PICO: _ClassVar[HardwareModel]
    HELTEC_WIRELESS_TRACKER: _ClassVar[HardwareModel]
    HELTEC_WIRELESS_PAPER: _ClassVar[HardwareModel]
    T_DECK: _ClassVar[HardwareModel]
    T_WATCH_S3: _ClassVar[HardwareModel]
    PICOMPUTER_S3: _ClassVar[HardwareModel]
    HELTEC_HT62: _ClassVar[HardwareModel]
    EBYTE_ESP32_S3: _ClassVar[HardwareModel]
    ESP32_S3_PICO: _ClassVar[HardwareModel]
    CHATTER_2: _ClassVar[HardwareModel]
    HELTEC_WIRELESS_PAPER_V1_0: _ClassVar[HardwareModel]
    HELTEC_WIRELESS_TRACKER_V1_0: _ClassVar[HardwareModel]
    UNPHONE: _ClassVar[HardwareModel]
    TD_LORAC: _ClassVar[HardwareModel]
    CDEBYTE_EORA_S3: _ClassVar[HardwareModel]
    TWC_MESH_V4: _ClassVar[HardwareModel]
    NRF52_PROMICRO_DIY: _ClassVar[HardwareModel]
    RADIOMASTER_900_BANDIT_NANO: _ClassVar[HardwareModel]
    HELTEC_CAPSULE_SENSOR_V3: _ClassVar[HardwareModel]
    HELTEC_VISION_MASTER_T190: _ClassVar[HardwareModel]
    HELTEC_VISION_MASTER_E213: _ClassVar[HardwareModel]
    HELTEC_VISION_MASTER_E290: _ClassVar[HardwareModel]
    HELTEC_MESH_NODE_T114: _ClassVar[HardwareModel]
    SENSECAP_INDICATOR: _ClassVar[HardwareModel]
    TRACKER_T1000_E: _ClassVar[HardwareModel]
    RAK3172: _ClassVar[HardwareModel]
    WIO_E5: _ClassVar[HardwareModel]
    RADIOMASTER_900_BANDIT: _ClassVar[HardwareModel]
    ME25LS01_4Y10TD: _ClassVar[HardwareModel]
    RP2040_FEATHER_RFM95: _ClassVar[HardwareModel]
    M5STACK_COREBASIC: _ClassVar[HardwareModel]
    M5STACK_CORE2: _ClassVar[HardwareModel]
    RPI_PICO2: _ClassVar[HardwareModel]
    M5STACK_CORES3: _ClassVar[HardwareModel]
    SEEED_XIAO_S3: _ClassVar[HardwareModel]
    MS24SF1: _ClassVar[HardwareModel]
    TLORA_C6: _ClassVar[HardwareModel]
    WISMESH_TAP: _ClassVar[HardwareModel]
    ROUTASTIC: _ClassVar[HardwareModel]
    MESH_TAB: _ClassVar[HardwareModel]
    MESHLINK: _ClassVar[HardwareModel]
    XIAO_NRF52_KIT: _ClassVar[HardwareModel]
    THINKNODE_M1: _ClassVar[HardwareModel]
    THINKNODE_M2: _ClassVar[HardwareModel]
    T_ETH_ELITE: _ClassVar[HardwareModel]
    HELTEC_SENSOR_HUB: _ClassVar[HardwareModel]
    MUZI_BASE: _ClassVar[HardwareModel]
    HELTEC_MESH_POCKET: _ClassVar[HardwareModel]
    SEEED_SOLAR_NODE: _ClassVar[HardwareModel]
    NOMADSTAR_METEOR_PRO: _ClassVar[HardwareModel]
    CROWPANEL: _ClassVar[HardwareModel]
    LINK_32: _ClassVar[HardwareModel]
    SEEED_WIO_TRACKER_L1: _ClassVar[HardwareModel]
    SEEED_WIO_TRACKER_L1_EINK: _ClassVar[HardwareModel]
    MUZI_R1_NEO: _ClassVar[HardwareModel]
    T_DECK_PRO: _ClassVar[HardwareModel]
    T_LORA_PAGER: _ClassVar[HardwareModel]
    M5STACK_RESERVED: _ClassVar[HardwareModel]
    WISMESH_TAG: _ClassVar[HardwareModel]
    RAK3312: _ClassVar[HardwareModel]
    THINKNODE_M5: _ClassVar[HardwareModel]
    HELTEC_MESH_SOLAR: _ClassVar[HardwareModel]
    T_ECHO_LITE: _ClassVar[HardwareModel]
    HELTEC_V4: _ClassVar[HardwareModel]
    M5STACK_C6L: _ClassVar[HardwareModel]
    M5STACK_CARDPUTER_ADV: _ClassVar[HardwareModel]
    HELTEC_WIRELESS_TRACKER_V2: _ClassVar[HardwareModel]
    T_WATCH_ULTRA: _ClassVar[HardwareModel]
    THINKNODE_M3: _ClassVar[HardwareModel]
    WISMESH_TAP_V2: _ClassVar[HardwareModel]
    RAK3401: _ClassVar[HardwareModel]
    RAK6421: _ClassVar[HardwareModel]
    THINKNODE_M4: _ClassVar[HardwareModel]
    THINKNODE_M6: _ClassVar[HardwareModel]
    MESHSTICK_1262: _ClassVar[HardwareModel]
    TBEAM_1_WATT: _ClassVar[HardwareModel]
    T5_S3_EPAPER_PRO: _ClassVar[HardwareModel]
    TBEAM_BPF: _ClassVar[HardwareModel]
    MINI_EPAPER_S3: _ClassVar[HardwareModel]
    TDISPLAY_S3_PRO: _ClassVar[HardwareModel]
    HELTEC_MESH_NODE_T096: _ClassVar[HardwareModel]
    TRACKER_T1000_E_PRO: _ClassVar[HardwareModel]
    THINKNODE_M7: _ClassVar[HardwareModel]
    THINKNODE_M8: _ClassVar[HardwareModel]
    THINKNODE_M9: _ClassVar[HardwareModel]
    HELTEC_V4_R8: _ClassVar[HardwareModel]
    HELTEC_MESH_NODE_T1: _ClassVar[HardwareModel]
    STATION_G3: _ClassVar[HardwareModel]
    T_IMPULSE_PLUS: _ClassVar[HardwareModel]
    T_ECHO_CARD: _ClassVar[HardwareModel]
    SEEED_WIO_TRACKER_L2: _ClassVar[HardwareModel]
    CROWPANEL_P4: _ClassVar[HardwareModel]
    HELTEC_MESH_TOWER_V2: _ClassVar[HardwareModel]
    MESHNOLOGY_W10: _ClassVar[HardwareModel]
    PRIVATE_HW: _ClassVar[HardwareModel]

class Constants(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ZERO: _ClassVar[Constants]
    DATA_PAYLOAD_LEN: _ClassVar[Constants]

class CriticalErrorCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    NONE: _ClassVar[CriticalErrorCode]
    TX_WATCHDOG: _ClassVar[CriticalErrorCode]
    SLEEP_ENTER_WAIT: _ClassVar[CriticalErrorCode]
    NO_RADIO: _ClassVar[CriticalErrorCode]
    UNSPECIFIED: _ClassVar[CriticalErrorCode]
    UBLOX_UNIT_FAILED: _ClassVar[CriticalErrorCode]
    NO_AXP192: _ClassVar[CriticalErrorCode]
    INVALID_RADIO_SETTING: _ClassVar[CriticalErrorCode]
    TRANSMIT_FAILED: _ClassVar[CriticalErrorCode]
    BROWNOUT: _ClassVar[CriticalErrorCode]
    SX1262_FAILURE: _ClassVar[CriticalErrorCode]
    RADIO_SPI_BUG: _ClassVar[CriticalErrorCode]
    FLASH_CORRUPTION_RECOVERABLE: _ClassVar[CriticalErrorCode]
    FLASH_CORRUPTION_UNRECOVERABLE: _ClassVar[CriticalErrorCode]

class FirmwareEdition(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    VANILLA: _ClassVar[FirmwareEdition]
    SMART_CITIZEN: _ClassVar[FirmwareEdition]
    OPEN_SAUCE: _ClassVar[FirmwareEdition]
    DEFCON: _ClassVar[FirmwareEdition]
    BURNING_MAN: _ClassVar[FirmwareEdition]
    HAMVENTION: _ClassVar[FirmwareEdition]
    DIY_EDITION: _ClassVar[FirmwareEdition]

class ExcludedModules(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    EXCLUDED_NONE: _ClassVar[ExcludedModules]
    MQTT_CONFIG: _ClassVar[ExcludedModules]
    SERIAL_CONFIG: _ClassVar[ExcludedModules]
    EXTNOTIF_CONFIG: _ClassVar[ExcludedModules]
    STOREFORWARD_CONFIG: _ClassVar[ExcludedModules]
    RANGETEST_CONFIG: _ClassVar[ExcludedModules]
    TELEMETRY_CONFIG: _ClassVar[ExcludedModules]
    CANNEDMSG_CONFIG: _ClassVar[ExcludedModules]
    AUDIO_CONFIG: _ClassVar[ExcludedModules]
    REMOTEHARDWARE_CONFIG: _ClassVar[ExcludedModules]
    NEIGHBORINFO_CONFIG: _ClassVar[ExcludedModules]
    AMBIENTLIGHTING_CONFIG: _ClassVar[ExcludedModules]
    DETECTIONSENSOR_CONFIG: _ClassVar[ExcludedModules]
    PAXCOUNTER_CONFIG: _ClassVar[ExcludedModules]
    BLUETOOTH_CONFIG: _ClassVar[ExcludedModules]
    NETWORK_CONFIG: _ClassVar[ExcludedModules]
UNSET: HardwareModel
TLORA_V2: HardwareModel
TLORA_V1: HardwareModel
TLORA_V2_1_1P6: HardwareModel
TBEAM: HardwareModel
HELTEC_V2_0: HardwareModel
TBEAM_V0P7: HardwareModel
T_ECHO: HardwareModel
TLORA_V1_1P3: HardwareModel
RAK4631: HardwareModel
HELTEC_V2_1: HardwareModel
HELTEC_V1: HardwareModel
LILYGO_TBEAM_S3_CORE: HardwareModel
RAK11200: HardwareModel
NANO_G1: HardwareModel
TLORA_V2_1_1P8: HardwareModel
TLORA_T3_S3: HardwareModel
NANO_G1_EXPLORER: HardwareModel
NANO_G2_ULTRA: HardwareModel
LORA_TYPE: HardwareModel
WIPHONE: HardwareModel
WIO_WM1110: HardwareModel
RAK2560: HardwareModel
HELTEC_HRU_3601: HardwareModel
HELTEC_WIRELESS_BRIDGE: HardwareModel
STATION_G1: HardwareModel
RAK11310: HardwareModel
SENSELORA_RP2040: HardwareModel
SENSELORA_S3: HardwareModel
CANARYONE: HardwareModel
RP2040_LORA: HardwareModel
STATION_G2: HardwareModel
LORA_RELAY_V1: HardwareModel
T_ECHO_PLUS: HardwareModel
PPR: HardwareModel
GENIEBLOCKS: HardwareModel
NRF52_UNKNOWN: HardwareModel
PORTDUINO: HardwareModel
ANDROID_SIM: HardwareModel
DIY_V1: HardwareModel
NRF52840_PCA10059: HardwareModel
DR_DEV: HardwareModel
M5STACK: HardwareModel
HELTEC_V3: HardwareModel
HELTEC_WSL_V3: HardwareModel
BETAFPV_2400_TX: HardwareModel
BETAFPV_900_NANO_TX: HardwareModel
RPI_PICO: HardwareModel
HELTEC_WIRELESS_TRACKER: HardwareModel
HELTEC_WIRELESS_PAPER: HardwareModel
T_DECK: HardwareModel
T_WATCH_S3: HardwareModel
PICOMPUTER_S3: HardwareModel
HELTEC_HT62: HardwareModel
EBYTE_ESP32_S3: HardwareModel
ESP32_S3_PICO: HardwareModel
CHATTER_2: HardwareModel
HELTEC_WIRELESS_PAPER_V1_0: HardwareModel
HELTEC_WIRELESS_TRACKER_V1_0: HardwareModel
UNPHONE: HardwareModel
TD_LORAC: HardwareModel
CDEBYTE_EORA_S3: HardwareModel
TWC_MESH_V4: HardwareModel
NRF52_PROMICRO_DIY: HardwareModel
RADIOMASTER_900_BANDIT_NANO: HardwareModel
HELTEC_CAPSULE_SENSOR_V3: HardwareModel
HELTEC_VISION_MASTER_T190: HardwareModel
HELTEC_VISION_MASTER_E213: HardwareModel
HELTEC_VISION_MASTER_E290: HardwareModel
HELTEC_MESH_NODE_T114: HardwareModel
SENSECAP_INDICATOR: HardwareModel
TRACKER_T1000_E: HardwareModel
RAK3172: HardwareModel
WIO_E5: HardwareModel
RADIOMASTER_900_BANDIT: HardwareModel
ME25LS01_4Y10TD: HardwareModel
RP2040_FEATHER_RFM95: HardwareModel
M5STACK_COREBASIC: HardwareModel
M5STACK_CORE2: HardwareModel
RPI_PICO2: HardwareModel
M5STACK_CORES3: HardwareModel
SEEED_XIAO_S3: HardwareModel
MS24SF1: HardwareModel
TLORA_C6: HardwareModel
WISMESH_TAP: HardwareModel
ROUTASTIC: HardwareModel
MESH_TAB: HardwareModel
MESHLINK: HardwareModel
XIAO_NRF52_KIT: HardwareModel
THINKNODE_M1: HardwareModel
THINKNODE_M2: HardwareModel
T_ETH_ELITE: HardwareModel
HELTEC_SENSOR_HUB: HardwareModel
MUZI_BASE: HardwareModel
HELTEC_MESH_POCKET: HardwareModel
SEEED_SOLAR_NODE: HardwareModel
NOMADSTAR_METEOR_PRO: HardwareModel
CROWPANEL: HardwareModel
LINK_32: HardwareModel
SEEED_WIO_TRACKER_L1: HardwareModel
SEEED_WIO_TRACKER_L1_EINK: HardwareModel
MUZI_R1_NEO: HardwareModel
T_DECK_PRO: HardwareModel
T_LORA_PAGER: HardwareModel
M5STACK_RESERVED: HardwareModel
WISMESH_TAG: HardwareModel
RAK3312: HardwareModel
THINKNODE_M5: HardwareModel
HELTEC_MESH_SOLAR: HardwareModel
T_ECHO_LITE: HardwareModel
HELTEC_V4: HardwareModel
M5STACK_C6L: HardwareModel
M5STACK_CARDPUTER_ADV: HardwareModel
HELTEC_WIRELESS_TRACKER_V2: HardwareModel
T_WATCH_ULTRA: HardwareModel
THINKNODE_M3: HardwareModel
WISMESH_TAP_V2: HardwareModel
RAK3401: HardwareModel
RAK6421: HardwareModel
THINKNODE_M4: HardwareModel
THINKNODE_M6: HardwareModel
MESHSTICK_1262: HardwareModel
TBEAM_1_WATT: HardwareModel
T5_S3_EPAPER_PRO: HardwareModel
TBEAM_BPF: HardwareModel
MINI_EPAPER_S3: HardwareModel
TDISPLAY_S3_PRO: HardwareModel
HELTEC_MESH_NODE_T096: HardwareModel
TRACKER_T1000_E_PRO: HardwareModel
THINKNODE_M7: HardwareModel
THINKNODE_M8: HardwareModel
THINKNODE_M9: HardwareModel
HELTEC_V4_R8: HardwareModel
HELTEC_MESH_NODE_T1: HardwareModel
STATION_G3: HardwareModel
T_IMPULSE_PLUS: HardwareModel
T_ECHO_CARD: HardwareModel
SEEED_WIO_TRACKER_L2: HardwareModel
CROWPANEL_P4: HardwareModel
HELTEC_MESH_TOWER_V2: HardwareModel
MESHNOLOGY_W10: HardwareModel
PRIVATE_HW: HardwareModel
ZERO: Constants
DATA_PAYLOAD_LEN: Constants
NONE: CriticalErrorCode
TX_WATCHDOG: CriticalErrorCode
SLEEP_ENTER_WAIT: CriticalErrorCode
NO_RADIO: CriticalErrorCode
UNSPECIFIED: CriticalErrorCode
UBLOX_UNIT_FAILED: CriticalErrorCode
NO_AXP192: CriticalErrorCode
INVALID_RADIO_SETTING: CriticalErrorCode
TRANSMIT_FAILED: CriticalErrorCode
BROWNOUT: CriticalErrorCode
SX1262_FAILURE: CriticalErrorCode
RADIO_SPI_BUG: CriticalErrorCode
FLASH_CORRUPTION_RECOVERABLE: CriticalErrorCode
FLASH_CORRUPTION_UNRECOVERABLE: CriticalErrorCode
VANILLA: FirmwareEdition
SMART_CITIZEN: FirmwareEdition
OPEN_SAUCE: FirmwareEdition
DEFCON: FirmwareEdition
BURNING_MAN: FirmwareEdition
HAMVENTION: FirmwareEdition
DIY_EDITION: FirmwareEdition
EXCLUDED_NONE: ExcludedModules
MQTT_CONFIG: ExcludedModules
SERIAL_CONFIG: ExcludedModules
EXTNOTIF_CONFIG: ExcludedModules
STOREFORWARD_CONFIG: ExcludedModules
RANGETEST_CONFIG: ExcludedModules
TELEMETRY_CONFIG: ExcludedModules
CANNEDMSG_CONFIG: ExcludedModules
AUDIO_CONFIG: ExcludedModules
REMOTEHARDWARE_CONFIG: ExcludedModules
NEIGHBORINFO_CONFIG: ExcludedModules
AMBIENTLIGHTING_CONFIG: ExcludedModules
DETECTIONSENSOR_CONFIG: ExcludedModules
PAXCOUNTER_CONFIG: ExcludedModules
BLUETOOTH_CONFIG: ExcludedModules
NETWORK_CONFIG: ExcludedModules

class Position(_message.Message):
    __slots__ = ("latitude_i", "longitude_i", "altitude", "time", "location_source", "altitude_source", "timestamp", "timestamp_millis_adjust", "altitude_hae", "altitude_geoidal_separation", "PDOP", "HDOP", "VDOP", "gps_accuracy", "ground_speed", "ground_track", "fix_quality", "fix_type", "sats_in_view", "sensor_id", "next_update", "seq_number", "precision_bits")
    class LocSource(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        LOC_UNSET: _ClassVar[Position.LocSource]
        LOC_MANUAL: _ClassVar[Position.LocSource]
        LOC_INTERNAL: _ClassVar[Position.LocSource]
        LOC_EXTERNAL: _ClassVar[Position.LocSource]
    LOC_UNSET: Position.LocSource
    LOC_MANUAL: Position.LocSource
    LOC_INTERNAL: Position.LocSource
    LOC_EXTERNAL: Position.LocSource
    class AltSource(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        ALT_UNSET: _ClassVar[Position.AltSource]
        ALT_MANUAL: _ClassVar[Position.AltSource]
        ALT_INTERNAL: _ClassVar[Position.AltSource]
        ALT_EXTERNAL: _ClassVar[Position.AltSource]
        ALT_BAROMETRIC: _ClassVar[Position.AltSource]
    ALT_UNSET: Position.AltSource
    ALT_MANUAL: Position.AltSource
    ALT_INTERNAL: Position.AltSource
    ALT_EXTERNAL: Position.AltSource
    ALT_BAROMETRIC: Position.AltSource
    LATITUDE_I_FIELD_NUMBER: _ClassVar[int]
    LONGITUDE_I_FIELD_NUMBER: _ClassVar[int]
    ALTITUDE_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    LOCATION_SOURCE_FIELD_NUMBER: _ClassVar[int]
    ALTITUDE_SOURCE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_MILLIS_ADJUST_FIELD_NUMBER: _ClassVar[int]
    ALTITUDE_HAE_FIELD_NUMBER: _ClassVar[int]
    ALTITUDE_GEOIDAL_SEPARATION_FIELD_NUMBER: _ClassVar[int]
    PDOP_FIELD_NUMBER: _ClassVar[int]
    HDOP_FIELD_NUMBER: _ClassVar[int]
    VDOP_FIELD_NUMBER: _ClassVar[int]
    GPS_ACCURACY_FIELD_NUMBER: _ClassVar[int]
    GROUND_SPEED_FIELD_NUMBER: _ClassVar[int]
    GROUND_TRACK_FIELD_NUMBER: _ClassVar[int]
    FIX_QUALITY_FIELD_NUMBER: _ClassVar[int]
    FIX_TYPE_FIELD_NUMBER: _ClassVar[int]
    SATS_IN_VIEW_FIELD_NUMBER: _ClassVar[int]
    SENSOR_ID_FIELD_NUMBER: _ClassVar[int]
    NEXT_UPDATE_FIELD_NUMBER: _ClassVar[int]
    SEQ_NUMBER_FIELD_NUMBER: _ClassVar[int]
    PRECISION_BITS_FIELD_NUMBER: _ClassVar[int]
    latitude_i: int
    longitude_i: int
    altitude: int
    time: int
    location_source: Position.LocSource
    altitude_source: Position.AltSource
    timestamp: int
    timestamp_millis_adjust: int
    altitude_hae: int
    altitude_geoidal_separation: int
    PDOP: int
    HDOP: int
    VDOP: int
    gps_accuracy: int
    ground_speed: int
    ground_track: int
    fix_quality: int
    fix_type: int
    sats_in_view: int
    sensor_id: int
    next_update: int
    seq_number: int
    precision_bits: int
    def __init__(self, latitude_i: _Optional[int] = ..., longitude_i: _Optional[int] = ..., altitude: _Optional[int] = ..., time: _Optional[int] = ..., location_source: _Optional[_Union[Position.LocSource, str]] = ..., altitude_source: _Optional[_Union[Position.AltSource, str]] = ..., timestamp: _Optional[int] = ..., timestamp_millis_adjust: _Optional[int] = ..., altitude_hae: _Optional[int] = ..., altitude_geoidal_separation: _Optional[int] = ..., PDOP: _Optional[int] = ..., HDOP: _Optional[int] = ..., VDOP: _Optional[int] = ..., gps_accuracy: _Optional[int] = ..., ground_speed: _Optional[int] = ..., ground_track: _Optional[int] = ..., fix_quality: _Optional[int] = ..., fix_type: _Optional[int] = ..., sats_in_view: _Optional[int] = ..., sensor_id: _Optional[int] = ..., next_update: _Optional[int] = ..., seq_number: _Optional[int] = ..., precision_bits: _Optional[int] = ...) -> None: ...

class User(_message.Message):
    __slots__ = ("id", "long_name", "short_name", "macaddr", "hw_model", "is_licensed", "role", "public_key", "is_unmessagable")
    ID_FIELD_NUMBER: _ClassVar[int]
    LONG_NAME_FIELD_NUMBER: _ClassVar[int]
    SHORT_NAME_FIELD_NUMBER: _ClassVar[int]
    MACADDR_FIELD_NUMBER: _ClassVar[int]
    HW_MODEL_FIELD_NUMBER: _ClassVar[int]
    IS_LICENSED_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    IS_UNMESSAGABLE_FIELD_NUMBER: _ClassVar[int]
    id: str
    long_name: str
    short_name: str
    macaddr: bytes
    hw_model: HardwareModel
    is_licensed: bool
    role: _config_pb2.Config.DeviceConfig.Role
    public_key: bytes
    is_unmessagable: bool
    def __init__(self, id: _Optional[str] = ..., long_name: _Optional[str] = ..., short_name: _Optional[str] = ..., macaddr: _Optional[bytes] = ..., hw_model: _Optional[_Union[HardwareModel, str]] = ..., is_licensed: bool = ..., role: _Optional[_Union[_config_pb2.Config.DeviceConfig.Role, str]] = ..., public_key: _Optional[bytes] = ..., is_unmessagable: bool = ...) -> None: ...

class RouteDiscovery(_message.Message):
    __slots__ = ("route", "snr_towards", "route_back", "snr_back")
    ROUTE_FIELD_NUMBER: _ClassVar[int]
    SNR_TOWARDS_FIELD_NUMBER: _ClassVar[int]
    ROUTE_BACK_FIELD_NUMBER: _ClassVar[int]
    SNR_BACK_FIELD_NUMBER: _ClassVar[int]
    route: _containers.RepeatedScalarFieldContainer[int]
    snr_towards: _containers.RepeatedScalarFieldContainer[int]
    route_back: _containers.RepeatedScalarFieldContainer[int]
    snr_back: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, route: _Optional[_Iterable[int]] = ..., snr_towards: _Optional[_Iterable[int]] = ..., route_back: _Optional[_Iterable[int]] = ..., snr_back: _Optional[_Iterable[int]] = ...) -> None: ...

class Routing(_message.Message):
    __slots__ = ("route_request", "route_reply", "error_reason")
    class Error(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        NONE: _ClassVar[Routing.Error]
        NO_ROUTE: _ClassVar[Routing.Error]
        GOT_NAK: _ClassVar[Routing.Error]
        TIMEOUT: _ClassVar[Routing.Error]
        NO_INTERFACE: _ClassVar[Routing.Error]
        MAX_RETRANSMIT: _ClassVar[Routing.Error]
        NO_CHANNEL: _ClassVar[Routing.Error]
        TOO_LARGE: _ClassVar[Routing.Error]
        NO_RESPONSE: _ClassVar[Routing.Error]
        DUTY_CYCLE_LIMIT: _ClassVar[Routing.Error]
        BAD_REQUEST: _ClassVar[Routing.Error]
        NOT_AUTHORIZED: _ClassVar[Routing.Error]
        PKI_FAILED: _ClassVar[Routing.Error]
        PKI_UNKNOWN_PUBKEY: _ClassVar[Routing.Error]
        ADMIN_BAD_SESSION_KEY: _ClassVar[Routing.Error]
        ADMIN_PUBLIC_KEY_UNAUTHORIZED: _ClassVar[Routing.Error]
        RATE_LIMIT_EXCEEDED: _ClassVar[Routing.Error]
        PKI_SEND_FAIL_PUBLIC_KEY: _ClassVar[Routing.Error]
    NONE: Routing.Error
    NO_ROUTE: Routing.Error
    GOT_NAK: Routing.Error
    TIMEOUT: Routing.Error
    NO_INTERFACE: Routing.Error
    MAX_RETRANSMIT: Routing.Error
    NO_CHANNEL: Routing.Error
    TOO_LARGE: Routing.Error
    NO_RESPONSE: Routing.Error
    DUTY_CYCLE_LIMIT: Routing.Error
    BAD_REQUEST: Routing.Error
    NOT_AUTHORIZED: Routing.Error
    PKI_FAILED: Routing.Error
    PKI_UNKNOWN_PUBKEY: Routing.Error
    ADMIN_BAD_SESSION_KEY: Routing.Error
    ADMIN_PUBLIC_KEY_UNAUTHORIZED: Routing.Error
    RATE_LIMIT_EXCEEDED: Routing.Error
    PKI_SEND_FAIL_PUBLIC_KEY: Routing.Error
    ROUTE_REQUEST_FIELD_NUMBER: _ClassVar[int]
    ROUTE_REPLY_FIELD_NUMBER: _ClassVar[int]
    ERROR_REASON_FIELD_NUMBER: _ClassVar[int]
    route_request: RouteDiscovery
    route_reply: RouteDiscovery
    error_reason: Routing.Error
    def __init__(self, route_request: _Optional[_Union[RouteDiscovery, _Mapping]] = ..., route_reply: _Optional[_Union[RouteDiscovery, _Mapping]] = ..., error_reason: _Optional[_Union[Routing.Error, str]] = ...) -> None: ...

class Data(_message.Message):
    __slots__ = ("portnum", "payload", "want_response", "dest", "source", "request_id", "reply_id", "emoji", "bitfield")
    PORTNUM_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    WANT_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    DEST_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    REPLY_ID_FIELD_NUMBER: _ClassVar[int]
    EMOJI_FIELD_NUMBER: _ClassVar[int]
    BITFIELD_FIELD_NUMBER: _ClassVar[int]
    portnum: _portnums_pb2.PortNum
    payload: bytes
    want_response: bool
    dest: int
    source: int
    request_id: int
    reply_id: int
    emoji: int
    bitfield: int
    def __init__(self, portnum: _Optional[_Union[_portnums_pb2.PortNum, str]] = ..., payload: _Optional[bytes] = ..., want_response: bool = ..., dest: _Optional[int] = ..., source: _Optional[int] = ..., request_id: _Optional[int] = ..., reply_id: _Optional[int] = ..., emoji: _Optional[int] = ..., bitfield: _Optional[int] = ...) -> None: ...

class KeyVerification(_message.Message):
    __slots__ = ("nonce", "hash1", "hash2")
    NONCE_FIELD_NUMBER: _ClassVar[int]
    HASH1_FIELD_NUMBER: _ClassVar[int]
    HASH2_FIELD_NUMBER: _ClassVar[int]
    nonce: int
    hash1: bytes
    hash2: bytes
    def __init__(self, nonce: _Optional[int] = ..., hash1: _Optional[bytes] = ..., hash2: _Optional[bytes] = ...) -> None: ...

class StoreForwardPlusPlus(_message.Message):
    __slots__ = ("sfpp_message_type", "message_hash", "commit_hash", "root_hash", "message", "encapsulated_id", "encapsulated_to", "encapsulated_from", "encapsulated_rxtime", "chain_count")
    class SFPP_message_type(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        CANON_ANNOUNCE: _ClassVar[StoreForwardPlusPlus.SFPP_message_type]
        CHAIN_QUERY: _ClassVar[StoreForwardPlusPlus.SFPP_message_type]
        LINK_REQUEST: _ClassVar[StoreForwardPlusPlus.SFPP_message_type]
        LINK_PROVIDE: _ClassVar[StoreForwardPlusPlus.SFPP_message_type]
        LINK_PROVIDE_FIRSTHALF: _ClassVar[StoreForwardPlusPlus.SFPP_message_type]
        LINK_PROVIDE_SECONDHALF: _ClassVar[StoreForwardPlusPlus.SFPP_message_type]
    CANON_ANNOUNCE: StoreForwardPlusPlus.SFPP_message_type
    CHAIN_QUERY: StoreForwardPlusPlus.SFPP_message_type
    LINK_REQUEST: StoreForwardPlusPlus.SFPP_message_type
    LINK_PROVIDE: StoreForwardPlusPlus.SFPP_message_type
    LINK_PROVIDE_FIRSTHALF: StoreForwardPlusPlus.SFPP_message_type
    LINK_PROVIDE_SECONDHALF: StoreForwardPlusPlus.SFPP_message_type
    SFPP_MESSAGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_HASH_FIELD_NUMBER: _ClassVar[int]
    COMMIT_HASH_FIELD_NUMBER: _ClassVar[int]
    ROOT_HASH_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    ENCAPSULATED_ID_FIELD_NUMBER: _ClassVar[int]
    ENCAPSULATED_TO_FIELD_NUMBER: _ClassVar[int]
    ENCAPSULATED_FROM_FIELD_NUMBER: _ClassVar[int]
    ENCAPSULATED_RXTIME_FIELD_NUMBER: _ClassVar[int]
    CHAIN_COUNT_FIELD_NUMBER: _ClassVar[int]
    sfpp_message_type: StoreForwardPlusPlus.SFPP_message_type
    message_hash: bytes
    commit_hash: bytes
    root_hash: bytes
    message: bytes
    encapsulated_id: int
    encapsulated_to: int
    encapsulated_from: int
    encapsulated_rxtime: int
    chain_count: int
    def __init__(self, sfpp_message_type: _Optional[_Union[StoreForwardPlusPlus.SFPP_message_type, str]] = ..., message_hash: _Optional[bytes] = ..., commit_hash: _Optional[bytes] = ..., root_hash: _Optional[bytes] = ..., message: _Optional[bytes] = ..., encapsulated_id: _Optional[int] = ..., encapsulated_to: _Optional[int] = ..., encapsulated_from: _Optional[int] = ..., encapsulated_rxtime: _Optional[int] = ..., chain_count: _Optional[int] = ...) -> None: ...

class RemoteShell(_message.Message):
    __slots__ = ("op", "session_id", "seq", "ack_seq", "payload", "cols", "rows", "flags", "last_tx_seq", "last_rx_seq")
    class OpCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        OP_UNSET: _ClassVar[RemoteShell.OpCode]
        OPEN: _ClassVar[RemoteShell.OpCode]
        INPUT: _ClassVar[RemoteShell.OpCode]
        RESIZE: _ClassVar[RemoteShell.OpCode]
        CLOSE: _ClassVar[RemoteShell.OpCode]
        PING: _ClassVar[RemoteShell.OpCode]
        ACK: _ClassVar[RemoteShell.OpCode]
        OPEN_OK: _ClassVar[RemoteShell.OpCode]
        OUTPUT: _ClassVar[RemoteShell.OpCode]
        CLOSED: _ClassVar[RemoteShell.OpCode]
        ERROR: _ClassVar[RemoteShell.OpCode]
        PONG: _ClassVar[RemoteShell.OpCode]
    OP_UNSET: RemoteShell.OpCode
    OPEN: RemoteShell.OpCode
    INPUT: RemoteShell.OpCode
    RESIZE: RemoteShell.OpCode
    CLOSE: RemoteShell.OpCode
    PING: RemoteShell.OpCode
    ACK: RemoteShell.OpCode
    OPEN_OK: RemoteShell.OpCode
    OUTPUT: RemoteShell.OpCode
    CLOSED: RemoteShell.OpCode
    ERROR: RemoteShell.OpCode
    PONG: RemoteShell.OpCode
    OP_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    ACK_SEQ_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    COLS_FIELD_NUMBER: _ClassVar[int]
    ROWS_FIELD_NUMBER: _ClassVar[int]
    FLAGS_FIELD_NUMBER: _ClassVar[int]
    LAST_TX_SEQ_FIELD_NUMBER: _ClassVar[int]
    LAST_RX_SEQ_FIELD_NUMBER: _ClassVar[int]
    op: RemoteShell.OpCode
    session_id: int
    seq: int
    ack_seq: int
    payload: bytes
    cols: int
    rows: int
    flags: int
    last_tx_seq: int
    last_rx_seq: int
    def __init__(self, op: _Optional[_Union[RemoteShell.OpCode, str]] = ..., session_id: _Optional[int] = ..., seq: _Optional[int] = ..., ack_seq: _Optional[int] = ..., payload: _Optional[bytes] = ..., cols: _Optional[int] = ..., rows: _Optional[int] = ..., flags: _Optional[int] = ..., last_tx_seq: _Optional[int] = ..., last_rx_seq: _Optional[int] = ...) -> None: ...

class Waypoint(_message.Message):
    __slots__ = ("id", "latitude_i", "longitude_i", "expire", "locked_to", "name", "description", "icon")
    ID_FIELD_NUMBER: _ClassVar[int]
    LATITUDE_I_FIELD_NUMBER: _ClassVar[int]
    LONGITUDE_I_FIELD_NUMBER: _ClassVar[int]
    EXPIRE_FIELD_NUMBER: _ClassVar[int]
    LOCKED_TO_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    ICON_FIELD_NUMBER: _ClassVar[int]
    id: int
    latitude_i: int
    longitude_i: int
    expire: int
    locked_to: int
    name: str
    description: str
    icon: int
    def __init__(self, id: _Optional[int] = ..., latitude_i: _Optional[int] = ..., longitude_i: _Optional[int] = ..., expire: _Optional[int] = ..., locked_to: _Optional[int] = ..., name: _Optional[str] = ..., description: _Optional[str] = ..., icon: _Optional[int] = ...) -> None: ...

class StatusMessage(_message.Message):
    __slots__ = ("status",)
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: str
    def __init__(self, status: _Optional[str] = ...) -> None: ...

class MqttClientProxyMessage(_message.Message):
    __slots__ = ("topic", "data", "text", "retained")
    TOPIC_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    RETAINED_FIELD_NUMBER: _ClassVar[int]
    topic: str
    data: bytes
    text: str
    retained: bool
    def __init__(self, topic: _Optional[str] = ..., data: _Optional[bytes] = ..., text: _Optional[str] = ..., retained: bool = ...) -> None: ...

class MeshPacket(_message.Message):
    __slots__ = ("to", "channel", "decoded", "encrypted", "id", "rx_time", "rx_snr", "hop_limit", "want_ack", "priority", "rx_rssi", "delayed", "via_mqtt", "hop_start", "public_key", "pki_encrypted", "next_hop", "relay_node", "tx_after", "transport_mechanism")
    class Priority(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        UNSET: _ClassVar[MeshPacket.Priority]
        MIN: _ClassVar[MeshPacket.Priority]
        BACKGROUND: _ClassVar[MeshPacket.Priority]
        DEFAULT: _ClassVar[MeshPacket.Priority]
        RELIABLE: _ClassVar[MeshPacket.Priority]
        RESPONSE: _ClassVar[MeshPacket.Priority]
        HIGH: _ClassVar[MeshPacket.Priority]
        ALERT: _ClassVar[MeshPacket.Priority]
        ACK: _ClassVar[MeshPacket.Priority]
        MAX: _ClassVar[MeshPacket.Priority]
    UNSET: MeshPacket.Priority
    MIN: MeshPacket.Priority
    BACKGROUND: MeshPacket.Priority
    DEFAULT: MeshPacket.Priority
    RELIABLE: MeshPacket.Priority
    RESPONSE: MeshPacket.Priority
    HIGH: MeshPacket.Priority
    ALERT: MeshPacket.Priority
    ACK: MeshPacket.Priority
    MAX: MeshPacket.Priority
    class Delayed(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        NO_DELAY: _ClassVar[MeshPacket.Delayed]
        DELAYED_BROADCAST: _ClassVar[MeshPacket.Delayed]
        DELAYED_DIRECT: _ClassVar[MeshPacket.Delayed]
    NO_DELAY: MeshPacket.Delayed
    DELAYED_BROADCAST: MeshPacket.Delayed
    DELAYED_DIRECT: MeshPacket.Delayed
    class TransportMechanism(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        TRANSPORT_INTERNAL: _ClassVar[MeshPacket.TransportMechanism]
        TRANSPORT_LORA: _ClassVar[MeshPacket.TransportMechanism]
        TRANSPORT_LORA_ALT1: _ClassVar[MeshPacket.TransportMechanism]
        TRANSPORT_LORA_ALT2: _ClassVar[MeshPacket.TransportMechanism]
        TRANSPORT_LORA_ALT3: _ClassVar[MeshPacket.TransportMechanism]
        TRANSPORT_MQTT: _ClassVar[MeshPacket.TransportMechanism]
        TRANSPORT_MULTICAST_UDP: _ClassVar[MeshPacket.TransportMechanism]
        TRANSPORT_API: _ClassVar[MeshPacket.TransportMechanism]
    TRANSPORT_INTERNAL: MeshPacket.TransportMechanism
    TRANSPORT_LORA: MeshPacket.TransportMechanism
    TRANSPORT_LORA_ALT1: MeshPacket.TransportMechanism
    TRANSPORT_LORA_ALT2: MeshPacket.TransportMechanism
    TRANSPORT_LORA_ALT3: MeshPacket.TransportMechanism
    TRANSPORT_MQTT: MeshPacket.TransportMechanism
    TRANSPORT_MULTICAST_UDP: MeshPacket.TransportMechanism
    TRANSPORT_API: MeshPacket.TransportMechanism
    FROM_FIELD_NUMBER: _ClassVar[int]
    TO_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    DECODED_FIELD_NUMBER: _ClassVar[int]
    ENCRYPTED_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    RX_TIME_FIELD_NUMBER: _ClassVar[int]
    RX_SNR_FIELD_NUMBER: _ClassVar[int]
    HOP_LIMIT_FIELD_NUMBER: _ClassVar[int]
    WANT_ACK_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    RX_RSSI_FIELD_NUMBER: _ClassVar[int]
    DELAYED_FIELD_NUMBER: _ClassVar[int]
    VIA_MQTT_FIELD_NUMBER: _ClassVar[int]
    HOP_START_FIELD_NUMBER: _ClassVar[int]
    PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    PKI_ENCRYPTED_FIELD_NUMBER: _ClassVar[int]
    NEXT_HOP_FIELD_NUMBER: _ClassVar[int]
    RELAY_NODE_FIELD_NUMBER: _ClassVar[int]
    TX_AFTER_FIELD_NUMBER: _ClassVar[int]
    TRANSPORT_MECHANISM_FIELD_NUMBER: _ClassVar[int]
    to: int
    channel: int
    decoded: Data
    encrypted: bytes
    id: int
    rx_time: int
    rx_snr: float
    hop_limit: int
    want_ack: bool
    priority: MeshPacket.Priority
    rx_rssi: int
    delayed: MeshPacket.Delayed
    via_mqtt: bool
    hop_start: int
    public_key: bytes
    pki_encrypted: bool
    next_hop: int
    relay_node: int
    tx_after: int
    transport_mechanism: MeshPacket.TransportMechanism
    def __init__(self, to: _Optional[int] = ..., channel: _Optional[int] = ..., decoded: _Optional[_Union[Data, _Mapping]] = ..., encrypted: _Optional[bytes] = ..., id: _Optional[int] = ..., rx_time: _Optional[int] = ..., rx_snr: _Optional[float] = ..., hop_limit: _Optional[int] = ..., want_ack: bool = ..., priority: _Optional[_Union[MeshPacket.Priority, str]] = ..., rx_rssi: _Optional[int] = ..., delayed: _Optional[_Union[MeshPacket.Delayed, str]] = ..., via_mqtt: bool = ..., hop_start: _Optional[int] = ..., public_key: _Optional[bytes] = ..., pki_encrypted: bool = ..., next_hop: _Optional[int] = ..., relay_node: _Optional[int] = ..., tx_after: _Optional[int] = ..., transport_mechanism: _Optional[_Union[MeshPacket.TransportMechanism, str]] = ..., **kwargs) -> None: ...

class NodeInfo(_message.Message):
    __slots__ = ("num", "user", "position", "snr", "last_heard", "device_metrics", "channel", "via_mqtt", "hops_away", "is_favorite", "is_ignored", "is_key_manually_verified", "is_muted")
    NUM_FIELD_NUMBER: _ClassVar[int]
    USER_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    SNR_FIELD_NUMBER: _ClassVar[int]
    LAST_HEARD_FIELD_NUMBER: _ClassVar[int]
    DEVICE_METRICS_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    VIA_MQTT_FIELD_NUMBER: _ClassVar[int]
    HOPS_AWAY_FIELD_NUMBER: _ClassVar[int]
    IS_FAVORITE_FIELD_NUMBER: _ClassVar[int]
    IS_IGNORED_FIELD_NUMBER: _ClassVar[int]
    IS_KEY_MANUALLY_VERIFIED_FIELD_NUMBER: _ClassVar[int]
    IS_MUTED_FIELD_NUMBER: _ClassVar[int]
    num: int
    user: User
    position: Position
    snr: float
    last_heard: int
    device_metrics: _telemetry_pb2.DeviceMetrics
    channel: int
    via_mqtt: bool
    hops_away: int
    is_favorite: bool
    is_ignored: bool
    is_key_manually_verified: bool
    is_muted: bool
    def __init__(self, num: _Optional[int] = ..., user: _Optional[_Union[User, _Mapping]] = ..., position: _Optional[_Union[Position, _Mapping]] = ..., snr: _Optional[float] = ..., last_heard: _Optional[int] = ..., device_metrics: _Optional[_Union[_telemetry_pb2.DeviceMetrics, _Mapping]] = ..., channel: _Optional[int] = ..., via_mqtt: bool = ..., hops_away: _Optional[int] = ..., is_favorite: bool = ..., is_ignored: bool = ..., is_key_manually_verified: bool = ..., is_muted: bool = ...) -> None: ...

class MyNodeInfo(_message.Message):
    __slots__ = ("my_node_num", "reboot_count", "min_app_version", "device_id", "pio_env", "firmware_edition", "nodedb_count")
    MY_NODE_NUM_FIELD_NUMBER: _ClassVar[int]
    REBOOT_COUNT_FIELD_NUMBER: _ClassVar[int]
    MIN_APP_VERSION_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    PIO_ENV_FIELD_NUMBER: _ClassVar[int]
    FIRMWARE_EDITION_FIELD_NUMBER: _ClassVar[int]
    NODEDB_COUNT_FIELD_NUMBER: _ClassVar[int]
    my_node_num: int
    reboot_count: int
    min_app_version: int
    device_id: bytes
    pio_env: str
    firmware_edition: FirmwareEdition
    nodedb_count: int
    def __init__(self, my_node_num: _Optional[int] = ..., reboot_count: _Optional[int] = ..., min_app_version: _Optional[int] = ..., device_id: _Optional[bytes] = ..., pio_env: _Optional[str] = ..., firmware_edition: _Optional[_Union[FirmwareEdition, str]] = ..., nodedb_count: _Optional[int] = ...) -> None: ...

class LogRecord(_message.Message):
    __slots__ = ("message", "time", "source", "level")
    class Level(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        UNSET: _ClassVar[LogRecord.Level]
        CRITICAL: _ClassVar[LogRecord.Level]
        ERROR: _ClassVar[LogRecord.Level]
        WARNING: _ClassVar[LogRecord.Level]
        INFO: _ClassVar[LogRecord.Level]
        DEBUG: _ClassVar[LogRecord.Level]
        TRACE: _ClassVar[LogRecord.Level]
    UNSET: LogRecord.Level
    CRITICAL: LogRecord.Level
    ERROR: LogRecord.Level
    WARNING: LogRecord.Level
    INFO: LogRecord.Level
    DEBUG: LogRecord.Level
    TRACE: LogRecord.Level
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    LEVEL_FIELD_NUMBER: _ClassVar[int]
    message: str
    time: int
    source: str
    level: LogRecord.Level
    def __init__(self, message: _Optional[str] = ..., time: _Optional[int] = ..., source: _Optional[str] = ..., level: _Optional[_Union[LogRecord.Level, str]] = ...) -> None: ...

class QueueStatus(_message.Message):
    __slots__ = ("res", "free", "maxlen", "mesh_packet_id")
    RES_FIELD_NUMBER: _ClassVar[int]
    FREE_FIELD_NUMBER: _ClassVar[int]
    MAXLEN_FIELD_NUMBER: _ClassVar[int]
    MESH_PACKET_ID_FIELD_NUMBER: _ClassVar[int]
    res: int
    free: int
    maxlen: int
    mesh_packet_id: int
    def __init__(self, res: _Optional[int] = ..., free: _Optional[int] = ..., maxlen: _Optional[int] = ..., mesh_packet_id: _Optional[int] = ...) -> None: ...

class FromRadio(_message.Message):
    __slots__ = ("id", "packet", "my_info", "node_info", "config", "log_record", "config_complete_id", "rebooted", "moduleConfig", "channel", "queueStatus", "xmodemPacket", "metadata", "mqttClientProxyMessage", "fileInfo", "clientNotification", "deviceuiConfig", "lockdown_status")
    ID_FIELD_NUMBER: _ClassVar[int]
    PACKET_FIELD_NUMBER: _ClassVar[int]
    MY_INFO_FIELD_NUMBER: _ClassVar[int]
    NODE_INFO_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    LOG_RECORD_FIELD_NUMBER: _ClassVar[int]
    CONFIG_COMPLETE_ID_FIELD_NUMBER: _ClassVar[int]
    REBOOTED_FIELD_NUMBER: _ClassVar[int]
    MODULECONFIG_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    QUEUESTATUS_FIELD_NUMBER: _ClassVar[int]
    XMODEMPACKET_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    MQTTCLIENTPROXYMESSAGE_FIELD_NUMBER: _ClassVar[int]
    FILEINFO_FIELD_NUMBER: _ClassVar[int]
    CLIENTNOTIFICATION_FIELD_NUMBER: _ClassVar[int]
    DEVICEUICONFIG_FIELD_NUMBER: _ClassVar[int]
    LOCKDOWN_STATUS_FIELD_NUMBER: _ClassVar[int]
    id: int
    packet: MeshPacket
    my_info: MyNodeInfo
    node_info: NodeInfo
    config: _config_pb2.Config
    log_record: LogRecord
    config_complete_id: int
    rebooted: bool
    moduleConfig: _module_config_pb2.ModuleConfig
    channel: _channel_pb2.Channel
    queueStatus: QueueStatus
    xmodemPacket: _xmodem_pb2.XModem
    metadata: DeviceMetadata
    mqttClientProxyMessage: MqttClientProxyMessage
    fileInfo: FileInfo
    clientNotification: ClientNotification
    deviceuiConfig: _device_ui_pb2.DeviceUIConfig
    lockdown_status: LockdownStatus
    def __init__(self, id: _Optional[int] = ..., packet: _Optional[_Union[MeshPacket, _Mapping]] = ..., my_info: _Optional[_Union[MyNodeInfo, _Mapping]] = ..., node_info: _Optional[_Union[NodeInfo, _Mapping]] = ..., config: _Optional[_Union[_config_pb2.Config, _Mapping]] = ..., log_record: _Optional[_Union[LogRecord, _Mapping]] = ..., config_complete_id: _Optional[int] = ..., rebooted: bool = ..., moduleConfig: _Optional[_Union[_module_config_pb2.ModuleConfig, _Mapping]] = ..., channel: _Optional[_Union[_channel_pb2.Channel, _Mapping]] = ..., queueStatus: _Optional[_Union[QueueStatus, _Mapping]] = ..., xmodemPacket: _Optional[_Union[_xmodem_pb2.XModem, _Mapping]] = ..., metadata: _Optional[_Union[DeviceMetadata, _Mapping]] = ..., mqttClientProxyMessage: _Optional[_Union[MqttClientProxyMessage, _Mapping]] = ..., fileInfo: _Optional[_Union[FileInfo, _Mapping]] = ..., clientNotification: _Optional[_Union[ClientNotification, _Mapping]] = ..., deviceuiConfig: _Optional[_Union[_device_ui_pb2.DeviceUIConfig, _Mapping]] = ..., lockdown_status: _Optional[_Union[LockdownStatus, _Mapping]] = ...) -> None: ...

class LockdownStatus(_message.Message):
    __slots__ = ("state", "lock_reason", "boots_remaining", "valid_until_epoch", "backoff_seconds")
    class State(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        STATE_UNSPECIFIED: _ClassVar[LockdownStatus.State]
        NEEDS_PROVISION: _ClassVar[LockdownStatus.State]
        LOCKED: _ClassVar[LockdownStatus.State]
        UNLOCKED: _ClassVar[LockdownStatus.State]
        UNLOCK_FAILED: _ClassVar[LockdownStatus.State]
    STATE_UNSPECIFIED: LockdownStatus.State
    NEEDS_PROVISION: LockdownStatus.State
    LOCKED: LockdownStatus.State
    UNLOCKED: LockdownStatus.State
    UNLOCK_FAILED: LockdownStatus.State
    STATE_FIELD_NUMBER: _ClassVar[int]
    LOCK_REASON_FIELD_NUMBER: _ClassVar[int]
    BOOTS_REMAINING_FIELD_NUMBER: _ClassVar[int]
    VALID_UNTIL_EPOCH_FIELD_NUMBER: _ClassVar[int]
    BACKOFF_SECONDS_FIELD_NUMBER: _ClassVar[int]
    state: LockdownStatus.State
    lock_reason: str
    boots_remaining: int
    valid_until_epoch: int
    backoff_seconds: int
    def __init__(self, state: _Optional[_Union[LockdownStatus.State, str]] = ..., lock_reason: _Optional[str] = ..., boots_remaining: _Optional[int] = ..., valid_until_epoch: _Optional[int] = ..., backoff_seconds: _Optional[int] = ...) -> None: ...

class ClientNotification(_message.Message):
    __slots__ = ("reply_id", "time", "level", "message", "key_verification_number_inform", "key_verification_number_request", "key_verification_final", "duplicated_public_key", "low_entropy_key")
    REPLY_ID_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    LEVEL_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    KEY_VERIFICATION_NUMBER_INFORM_FIELD_NUMBER: _ClassVar[int]
    KEY_VERIFICATION_NUMBER_REQUEST_FIELD_NUMBER: _ClassVar[int]
    KEY_VERIFICATION_FINAL_FIELD_NUMBER: _ClassVar[int]
    DUPLICATED_PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    LOW_ENTROPY_KEY_FIELD_NUMBER: _ClassVar[int]
    reply_id: int
    time: int
    level: LogRecord.Level
    message: str
    key_verification_number_inform: KeyVerificationNumberInform
    key_verification_number_request: KeyVerificationNumberRequest
    key_verification_final: KeyVerificationFinal
    duplicated_public_key: DuplicatedPublicKey
    low_entropy_key: LowEntropyKey
    def __init__(self, reply_id: _Optional[int] = ..., time: _Optional[int] = ..., level: _Optional[_Union[LogRecord.Level, str]] = ..., message: _Optional[str] = ..., key_verification_number_inform: _Optional[_Union[KeyVerificationNumberInform, _Mapping]] = ..., key_verification_number_request: _Optional[_Union[KeyVerificationNumberRequest, _Mapping]] = ..., key_verification_final: _Optional[_Union[KeyVerificationFinal, _Mapping]] = ..., duplicated_public_key: _Optional[_Union[DuplicatedPublicKey, _Mapping]] = ..., low_entropy_key: _Optional[_Union[LowEntropyKey, _Mapping]] = ...) -> None: ...

class KeyVerificationNumberInform(_message.Message):
    __slots__ = ("nonce", "remote_longname", "security_number")
    NONCE_FIELD_NUMBER: _ClassVar[int]
    REMOTE_LONGNAME_FIELD_NUMBER: _ClassVar[int]
    SECURITY_NUMBER_FIELD_NUMBER: _ClassVar[int]
    nonce: int
    remote_longname: str
    security_number: int
    def __init__(self, nonce: _Optional[int] = ..., remote_longname: _Optional[str] = ..., security_number: _Optional[int] = ...) -> None: ...

class KeyVerificationNumberRequest(_message.Message):
    __slots__ = ("nonce", "remote_longname")
    NONCE_FIELD_NUMBER: _ClassVar[int]
    REMOTE_LONGNAME_FIELD_NUMBER: _ClassVar[int]
    nonce: int
    remote_longname: str
    def __init__(self, nonce: _Optional[int] = ..., remote_longname: _Optional[str] = ...) -> None: ...

class KeyVerificationFinal(_message.Message):
    __slots__ = ("nonce", "remote_longname", "isSender", "verification_characters")
    NONCE_FIELD_NUMBER: _ClassVar[int]
    REMOTE_LONGNAME_FIELD_NUMBER: _ClassVar[int]
    ISSENDER_FIELD_NUMBER: _ClassVar[int]
    VERIFICATION_CHARACTERS_FIELD_NUMBER: _ClassVar[int]
    nonce: int
    remote_longname: str
    isSender: bool
    verification_characters: str
    def __init__(self, nonce: _Optional[int] = ..., remote_longname: _Optional[str] = ..., isSender: bool = ..., verification_characters: _Optional[str] = ...) -> None: ...

class DuplicatedPublicKey(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class LowEntropyKey(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class FileInfo(_message.Message):
    __slots__ = ("file_name", "size_bytes")
    FILE_NAME_FIELD_NUMBER: _ClassVar[int]
    SIZE_BYTES_FIELD_NUMBER: _ClassVar[int]
    file_name: str
    size_bytes: int
    def __init__(self, file_name: _Optional[str] = ..., size_bytes: _Optional[int] = ...) -> None: ...

class ToRadio(_message.Message):
    __slots__ = ("packet", "want_config_id", "disconnect", "xmodemPacket", "mqttClientProxyMessage", "heartbeat")
    PACKET_FIELD_NUMBER: _ClassVar[int]
    WANT_CONFIG_ID_FIELD_NUMBER: _ClassVar[int]
    DISCONNECT_FIELD_NUMBER: _ClassVar[int]
    XMODEMPACKET_FIELD_NUMBER: _ClassVar[int]
    MQTTCLIENTPROXYMESSAGE_FIELD_NUMBER: _ClassVar[int]
    HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
    packet: MeshPacket
    want_config_id: int
    disconnect: bool
    xmodemPacket: _xmodem_pb2.XModem
    mqttClientProxyMessage: MqttClientProxyMessage
    heartbeat: Heartbeat
    def __init__(self, packet: _Optional[_Union[MeshPacket, _Mapping]] = ..., want_config_id: _Optional[int] = ..., disconnect: bool = ..., xmodemPacket: _Optional[_Union[_xmodem_pb2.XModem, _Mapping]] = ..., mqttClientProxyMessage: _Optional[_Union[MqttClientProxyMessage, _Mapping]] = ..., heartbeat: _Optional[_Union[Heartbeat, _Mapping]] = ...) -> None: ...

class Compressed(_message.Message):
    __slots__ = ("portnum", "data")
    PORTNUM_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    portnum: _portnums_pb2.PortNum
    data: bytes
    def __init__(self, portnum: _Optional[_Union[_portnums_pb2.PortNum, str]] = ..., data: _Optional[bytes] = ...) -> None: ...

class NeighborInfo(_message.Message):
    __slots__ = ("node_id", "last_sent_by_id", "node_broadcast_interval_secs", "neighbors")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    LAST_SENT_BY_ID_FIELD_NUMBER: _ClassVar[int]
    NODE_BROADCAST_INTERVAL_SECS_FIELD_NUMBER: _ClassVar[int]
    NEIGHBORS_FIELD_NUMBER: _ClassVar[int]
    node_id: int
    last_sent_by_id: int
    node_broadcast_interval_secs: int
    neighbors: _containers.RepeatedCompositeFieldContainer[Neighbor]
    def __init__(self, node_id: _Optional[int] = ..., last_sent_by_id: _Optional[int] = ..., node_broadcast_interval_secs: _Optional[int] = ..., neighbors: _Optional[_Iterable[_Union[Neighbor, _Mapping]]] = ...) -> None: ...

class Neighbor(_message.Message):
    __slots__ = ("node_id", "snr", "last_rx_time", "node_broadcast_interval_secs")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    SNR_FIELD_NUMBER: _ClassVar[int]
    LAST_RX_TIME_FIELD_NUMBER: _ClassVar[int]
    NODE_BROADCAST_INTERVAL_SECS_FIELD_NUMBER: _ClassVar[int]
    node_id: int
    snr: float
    last_rx_time: int
    node_broadcast_interval_secs: int
    def __init__(self, node_id: _Optional[int] = ..., snr: _Optional[float] = ..., last_rx_time: _Optional[int] = ..., node_broadcast_interval_secs: _Optional[int] = ...) -> None: ...

class DeviceMetadata(_message.Message):
    __slots__ = ("firmware_version", "device_state_version", "canShutdown", "hasWifi", "hasBluetooth", "hasEthernet", "role", "position_flags", "hw_model", "hasRemoteHardware", "hasPKC", "excluded_modules")
    FIRMWARE_VERSION_FIELD_NUMBER: _ClassVar[int]
    DEVICE_STATE_VERSION_FIELD_NUMBER: _ClassVar[int]
    CANSHUTDOWN_FIELD_NUMBER: _ClassVar[int]
    HASWIFI_FIELD_NUMBER: _ClassVar[int]
    HASBLUETOOTH_FIELD_NUMBER: _ClassVar[int]
    HASETHERNET_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    POSITION_FLAGS_FIELD_NUMBER: _ClassVar[int]
    HW_MODEL_FIELD_NUMBER: _ClassVar[int]
    HASREMOTEHARDWARE_FIELD_NUMBER: _ClassVar[int]
    HASPKC_FIELD_NUMBER: _ClassVar[int]
    EXCLUDED_MODULES_FIELD_NUMBER: _ClassVar[int]
    firmware_version: str
    device_state_version: int
    canShutdown: bool
    hasWifi: bool
    hasBluetooth: bool
    hasEthernet: bool
    role: _config_pb2.Config.DeviceConfig.Role
    position_flags: int
    hw_model: HardwareModel
    hasRemoteHardware: bool
    hasPKC: bool
    excluded_modules: int
    def __init__(self, firmware_version: _Optional[str] = ..., device_state_version: _Optional[int] = ..., canShutdown: bool = ..., hasWifi: bool = ..., hasBluetooth: bool = ..., hasEthernet: bool = ..., role: _Optional[_Union[_config_pb2.Config.DeviceConfig.Role, str]] = ..., position_flags: _Optional[int] = ..., hw_model: _Optional[_Union[HardwareModel, str]] = ..., hasRemoteHardware: bool = ..., hasPKC: bool = ..., excluded_modules: _Optional[int] = ...) -> None: ...

class Heartbeat(_message.Message):
    __slots__ = ("nonce",)
    NONCE_FIELD_NUMBER: _ClassVar[int]
    nonce: int
    def __init__(self, nonce: _Optional[int] = ...) -> None: ...

class NodeRemoteHardwarePin(_message.Message):
    __slots__ = ("node_num", "pin")
    NODE_NUM_FIELD_NUMBER: _ClassVar[int]
    PIN_FIELD_NUMBER: _ClassVar[int]
    node_num: int
    pin: _module_config_pb2.RemoteHardwarePin
    def __init__(self, node_num: _Optional[int] = ..., pin: _Optional[_Union[_module_config_pb2.RemoteHardwarePin, _Mapping]] = ...) -> None: ...

class ChunkedPayload(_message.Message):
    __slots__ = ("payload_id", "chunk_count", "chunk_index", "payload_chunk")
    PAYLOAD_ID_FIELD_NUMBER: _ClassVar[int]
    CHUNK_COUNT_FIELD_NUMBER: _ClassVar[int]
    CHUNK_INDEX_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_CHUNK_FIELD_NUMBER: _ClassVar[int]
    payload_id: int
    chunk_count: int
    chunk_index: int
    payload_chunk: bytes
    def __init__(self, payload_id: _Optional[int] = ..., chunk_count: _Optional[int] = ..., chunk_index: _Optional[int] = ..., payload_chunk: _Optional[bytes] = ...) -> None: ...

class resend_chunks(_message.Message):
    __slots__ = ("chunks",)
    CHUNKS_FIELD_NUMBER: _ClassVar[int]
    chunks: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, chunks: _Optional[_Iterable[int]] = ...) -> None: ...

class ChunkedPayloadResponse(_message.Message):
    __slots__ = ("payload_id", "request_transfer", "accept_transfer", "resend_chunks")
    PAYLOAD_ID_FIELD_NUMBER: _ClassVar[int]
    REQUEST_TRANSFER_FIELD_NUMBER: _ClassVar[int]
    ACCEPT_TRANSFER_FIELD_NUMBER: _ClassVar[int]
    RESEND_CHUNKS_FIELD_NUMBER: _ClassVar[int]
    payload_id: int
    request_transfer: bool
    accept_transfer: bool
    resend_chunks: resend_chunks
    def __init__(self, payload_id: _Optional[int] = ..., request_transfer: bool = ..., accept_transfer: bool = ..., resend_chunks: _Optional[_Union[resend_chunks, _Mapping]] = ...) -> None: ...
