from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class CompassMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DYNAMIC: _ClassVar[CompassMode]
    FIXED_RING: _ClassVar[CompassMode]
    FREEZE_HEADING: _ClassVar[CompassMode]

class Theme(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DARK: _ClassVar[Theme]
    LIGHT: _ClassVar[Theme]
    RED: _ClassVar[Theme]

class Language(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ENGLISH: _ClassVar[Language]
    FRENCH: _ClassVar[Language]
    GERMAN: _ClassVar[Language]
    ITALIAN: _ClassVar[Language]
    PORTUGUESE: _ClassVar[Language]
    SPANISH: _ClassVar[Language]
    SWEDISH: _ClassVar[Language]
    FINNISH: _ClassVar[Language]
    POLISH: _ClassVar[Language]
    TURKISH: _ClassVar[Language]
    SERBIAN: _ClassVar[Language]
    RUSSIAN: _ClassVar[Language]
    DUTCH: _ClassVar[Language]
    GREEK: _ClassVar[Language]
    NORWEGIAN: _ClassVar[Language]
    SLOVENIAN: _ClassVar[Language]
    UKRAINIAN: _ClassVar[Language]
    BULGARIAN: _ClassVar[Language]
    CZECH: _ClassVar[Language]
    DANISH: _ClassVar[Language]
    HUNGARIAN: _ClassVar[Language]
    AZERBAIJANI: _ClassVar[Language]
    SIMPLIFIED_CHINESE: _ClassVar[Language]
    TRADITIONAL_CHINESE: _ClassVar[Language]
DYNAMIC: CompassMode
FIXED_RING: CompassMode
FREEZE_HEADING: CompassMode
DARK: Theme
LIGHT: Theme
RED: Theme
ENGLISH: Language
FRENCH: Language
GERMAN: Language
ITALIAN: Language
PORTUGUESE: Language
SPANISH: Language
SWEDISH: Language
FINNISH: Language
POLISH: Language
TURKISH: Language
SERBIAN: Language
RUSSIAN: Language
DUTCH: Language
GREEK: Language
NORWEGIAN: Language
SLOVENIAN: Language
UKRAINIAN: Language
BULGARIAN: Language
CZECH: Language
DANISH: Language
HUNGARIAN: Language
AZERBAIJANI: Language
SIMPLIFIED_CHINESE: Language
TRADITIONAL_CHINESE: Language

class DeviceUIConfig(_message.Message):
    __slots__ = ("version", "screen_brightness", "screen_timeout", "screen_lock", "settings_lock", "pin_code", "theme", "alert_enabled", "banner_enabled", "ring_tone_id", "language", "node_filter", "node_highlight", "calibration_data", "map_data", "compass_mode", "screen_rgb_color", "is_clockface_analog", "gps_format")
    class GpsCoordinateFormat(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        DEC: _ClassVar[DeviceUIConfig.GpsCoordinateFormat]
        DMS: _ClassVar[DeviceUIConfig.GpsCoordinateFormat]
        UTM: _ClassVar[DeviceUIConfig.GpsCoordinateFormat]
        MGRS: _ClassVar[DeviceUIConfig.GpsCoordinateFormat]
        OLC: _ClassVar[DeviceUIConfig.GpsCoordinateFormat]
        OSGR: _ClassVar[DeviceUIConfig.GpsCoordinateFormat]
        MLS: _ClassVar[DeviceUIConfig.GpsCoordinateFormat]
    DEC: DeviceUIConfig.GpsCoordinateFormat
    DMS: DeviceUIConfig.GpsCoordinateFormat
    UTM: DeviceUIConfig.GpsCoordinateFormat
    MGRS: DeviceUIConfig.GpsCoordinateFormat
    OLC: DeviceUIConfig.GpsCoordinateFormat
    OSGR: DeviceUIConfig.GpsCoordinateFormat
    MLS: DeviceUIConfig.GpsCoordinateFormat
    VERSION_FIELD_NUMBER: _ClassVar[int]
    SCREEN_BRIGHTNESS_FIELD_NUMBER: _ClassVar[int]
    SCREEN_TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    SCREEN_LOCK_FIELD_NUMBER: _ClassVar[int]
    SETTINGS_LOCK_FIELD_NUMBER: _ClassVar[int]
    PIN_CODE_FIELD_NUMBER: _ClassVar[int]
    THEME_FIELD_NUMBER: _ClassVar[int]
    ALERT_ENABLED_FIELD_NUMBER: _ClassVar[int]
    BANNER_ENABLED_FIELD_NUMBER: _ClassVar[int]
    RING_TONE_ID_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    NODE_FILTER_FIELD_NUMBER: _ClassVar[int]
    NODE_HIGHLIGHT_FIELD_NUMBER: _ClassVar[int]
    CALIBRATION_DATA_FIELD_NUMBER: _ClassVar[int]
    MAP_DATA_FIELD_NUMBER: _ClassVar[int]
    COMPASS_MODE_FIELD_NUMBER: _ClassVar[int]
    SCREEN_RGB_COLOR_FIELD_NUMBER: _ClassVar[int]
    IS_CLOCKFACE_ANALOG_FIELD_NUMBER: _ClassVar[int]
    GPS_FORMAT_FIELD_NUMBER: _ClassVar[int]
    version: int
    screen_brightness: int
    screen_timeout: int
    screen_lock: bool
    settings_lock: bool
    pin_code: int
    theme: Theme
    alert_enabled: bool
    banner_enabled: bool
    ring_tone_id: int
    language: Language
    node_filter: NodeFilter
    node_highlight: NodeHighlight
    calibration_data: bytes
    map_data: Map
    compass_mode: CompassMode
    screen_rgb_color: int
    is_clockface_analog: bool
    gps_format: DeviceUIConfig.GpsCoordinateFormat
    def __init__(self, version: _Optional[int] = ..., screen_brightness: _Optional[int] = ..., screen_timeout: _Optional[int] = ..., screen_lock: bool = ..., settings_lock: bool = ..., pin_code: _Optional[int] = ..., theme: _Optional[_Union[Theme, str]] = ..., alert_enabled: bool = ..., banner_enabled: bool = ..., ring_tone_id: _Optional[int] = ..., language: _Optional[_Union[Language, str]] = ..., node_filter: _Optional[_Union[NodeFilter, _Mapping]] = ..., node_highlight: _Optional[_Union[NodeHighlight, _Mapping]] = ..., calibration_data: _Optional[bytes] = ..., map_data: _Optional[_Union[Map, _Mapping]] = ..., compass_mode: _Optional[_Union[CompassMode, str]] = ..., screen_rgb_color: _Optional[int] = ..., is_clockface_analog: bool = ..., gps_format: _Optional[_Union[DeviceUIConfig.GpsCoordinateFormat, str]] = ...) -> None: ...

class NodeFilter(_message.Message):
    __slots__ = ("unknown_switch", "offline_switch", "public_key_switch", "hops_away", "position_switch", "node_name", "channel")
    UNKNOWN_SWITCH_FIELD_NUMBER: _ClassVar[int]
    OFFLINE_SWITCH_FIELD_NUMBER: _ClassVar[int]
    PUBLIC_KEY_SWITCH_FIELD_NUMBER: _ClassVar[int]
    HOPS_AWAY_FIELD_NUMBER: _ClassVar[int]
    POSITION_SWITCH_FIELD_NUMBER: _ClassVar[int]
    NODE_NAME_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    unknown_switch: bool
    offline_switch: bool
    public_key_switch: bool
    hops_away: int
    position_switch: bool
    node_name: str
    channel: int
    def __init__(self, unknown_switch: bool = ..., offline_switch: bool = ..., public_key_switch: bool = ..., hops_away: _Optional[int] = ..., position_switch: bool = ..., node_name: _Optional[str] = ..., channel: _Optional[int] = ...) -> None: ...

class NodeHighlight(_message.Message):
    __slots__ = ("chat_switch", "position_switch", "telemetry_switch", "iaq_switch", "node_name")
    CHAT_SWITCH_FIELD_NUMBER: _ClassVar[int]
    POSITION_SWITCH_FIELD_NUMBER: _ClassVar[int]
    TELEMETRY_SWITCH_FIELD_NUMBER: _ClassVar[int]
    IAQ_SWITCH_FIELD_NUMBER: _ClassVar[int]
    NODE_NAME_FIELD_NUMBER: _ClassVar[int]
    chat_switch: bool
    position_switch: bool
    telemetry_switch: bool
    iaq_switch: bool
    node_name: str
    def __init__(self, chat_switch: bool = ..., position_switch: bool = ..., telemetry_switch: bool = ..., iaq_switch: bool = ..., node_name: _Optional[str] = ...) -> None: ...

class GeoPoint(_message.Message):
    __slots__ = ("zoom", "latitude", "longitude")
    ZOOM_FIELD_NUMBER: _ClassVar[int]
    LATITUDE_FIELD_NUMBER: _ClassVar[int]
    LONGITUDE_FIELD_NUMBER: _ClassVar[int]
    zoom: int
    latitude: int
    longitude: int
    def __init__(self, zoom: _Optional[int] = ..., latitude: _Optional[int] = ..., longitude: _Optional[int] = ...) -> None: ...

class Map(_message.Message):
    __slots__ = ("home", "style", "follow_gps")
    HOME_FIELD_NUMBER: _ClassVar[int]
    STYLE_FIELD_NUMBER: _ClassVar[int]
    FOLLOW_GPS_FIELD_NUMBER: _ClassVar[int]
    home: GeoPoint
    style: str
    follow_gps: bool
    def __init__(self, home: _Optional[_Union[GeoPoint, _Mapping]] = ..., style: _Optional[str] = ..., follow_gps: bool = ...) -> None: ...
