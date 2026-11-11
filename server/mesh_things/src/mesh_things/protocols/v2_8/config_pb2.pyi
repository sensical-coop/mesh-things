from mesh_things.protocols.v2_8 import device_ui_pb2 as _device_ui_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Config(_message.Message):
    __slots__ = ("device", "position", "power", "network", "display", "lora", "bluetooth", "security", "sessionkey", "device_ui")
    class DeviceConfig(_message.Message):
        __slots__ = ("role", "serial_enabled", "button_gpio", "buzzer_gpio", "rebroadcast_mode", "node_info_broadcast_secs", "double_tap_as_button_press", "is_managed", "disable_triple_click", "tzdef", "led_heartbeat_disabled", "buzzer_mode")
        class Role(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            CLIENT: _ClassVar[Config.DeviceConfig.Role]
            CLIENT_MUTE: _ClassVar[Config.DeviceConfig.Role]
            ROUTER: _ClassVar[Config.DeviceConfig.Role]
            ROUTER_CLIENT: _ClassVar[Config.DeviceConfig.Role]
            REPEATER: _ClassVar[Config.DeviceConfig.Role]
            TRACKER: _ClassVar[Config.DeviceConfig.Role]
            SENSOR: _ClassVar[Config.DeviceConfig.Role]
            TAK: _ClassVar[Config.DeviceConfig.Role]
            CLIENT_HIDDEN: _ClassVar[Config.DeviceConfig.Role]
            LOST_AND_FOUND: _ClassVar[Config.DeviceConfig.Role]
            TAK_TRACKER: _ClassVar[Config.DeviceConfig.Role]
            ROUTER_LATE: _ClassVar[Config.DeviceConfig.Role]
            CLIENT_BASE: _ClassVar[Config.DeviceConfig.Role]
        CLIENT: Config.DeviceConfig.Role
        CLIENT_MUTE: Config.DeviceConfig.Role
        ROUTER: Config.DeviceConfig.Role
        ROUTER_CLIENT: Config.DeviceConfig.Role
        REPEATER: Config.DeviceConfig.Role
        TRACKER: Config.DeviceConfig.Role
        SENSOR: Config.DeviceConfig.Role
        TAK: Config.DeviceConfig.Role
        CLIENT_HIDDEN: Config.DeviceConfig.Role
        LOST_AND_FOUND: Config.DeviceConfig.Role
        TAK_TRACKER: Config.DeviceConfig.Role
        ROUTER_LATE: Config.DeviceConfig.Role
        CLIENT_BASE: Config.DeviceConfig.Role
        class RebroadcastMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            ALL: _ClassVar[Config.DeviceConfig.RebroadcastMode]
            ALL_SKIP_DECODING: _ClassVar[Config.DeviceConfig.RebroadcastMode]
            LOCAL_ONLY: _ClassVar[Config.DeviceConfig.RebroadcastMode]
            KNOWN_ONLY: _ClassVar[Config.DeviceConfig.RebroadcastMode]
            NONE: _ClassVar[Config.DeviceConfig.RebroadcastMode]
            CORE_PORTNUMS_ONLY: _ClassVar[Config.DeviceConfig.RebroadcastMode]
        ALL: Config.DeviceConfig.RebroadcastMode
        ALL_SKIP_DECODING: Config.DeviceConfig.RebroadcastMode
        LOCAL_ONLY: Config.DeviceConfig.RebroadcastMode
        KNOWN_ONLY: Config.DeviceConfig.RebroadcastMode
        NONE: Config.DeviceConfig.RebroadcastMode
        CORE_PORTNUMS_ONLY: Config.DeviceConfig.RebroadcastMode
        class BuzzerMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            ALL_ENABLED: _ClassVar[Config.DeviceConfig.BuzzerMode]
            DISABLED: _ClassVar[Config.DeviceConfig.BuzzerMode]
            NOTIFICATIONS_ONLY: _ClassVar[Config.DeviceConfig.BuzzerMode]
            SYSTEM_ONLY: _ClassVar[Config.DeviceConfig.BuzzerMode]
            DIRECT_MSG_ONLY: _ClassVar[Config.DeviceConfig.BuzzerMode]
        ALL_ENABLED: Config.DeviceConfig.BuzzerMode
        DISABLED: Config.DeviceConfig.BuzzerMode
        NOTIFICATIONS_ONLY: Config.DeviceConfig.BuzzerMode
        SYSTEM_ONLY: Config.DeviceConfig.BuzzerMode
        DIRECT_MSG_ONLY: Config.DeviceConfig.BuzzerMode
        ROLE_FIELD_NUMBER: _ClassVar[int]
        SERIAL_ENABLED_FIELD_NUMBER: _ClassVar[int]
        BUTTON_GPIO_FIELD_NUMBER: _ClassVar[int]
        BUZZER_GPIO_FIELD_NUMBER: _ClassVar[int]
        REBROADCAST_MODE_FIELD_NUMBER: _ClassVar[int]
        NODE_INFO_BROADCAST_SECS_FIELD_NUMBER: _ClassVar[int]
        DOUBLE_TAP_AS_BUTTON_PRESS_FIELD_NUMBER: _ClassVar[int]
        IS_MANAGED_FIELD_NUMBER: _ClassVar[int]
        DISABLE_TRIPLE_CLICK_FIELD_NUMBER: _ClassVar[int]
        TZDEF_FIELD_NUMBER: _ClassVar[int]
        LED_HEARTBEAT_DISABLED_FIELD_NUMBER: _ClassVar[int]
        BUZZER_MODE_FIELD_NUMBER: _ClassVar[int]
        role: Config.DeviceConfig.Role
        serial_enabled: bool
        button_gpio: int
        buzzer_gpio: int
        rebroadcast_mode: Config.DeviceConfig.RebroadcastMode
        node_info_broadcast_secs: int
        double_tap_as_button_press: bool
        is_managed: bool
        disable_triple_click: bool
        tzdef: str
        led_heartbeat_disabled: bool
        buzzer_mode: Config.DeviceConfig.BuzzerMode
        def __init__(self, role: _Optional[_Union[Config.DeviceConfig.Role, str]] = ..., serial_enabled: bool = ..., button_gpio: _Optional[int] = ..., buzzer_gpio: _Optional[int] = ..., rebroadcast_mode: _Optional[_Union[Config.DeviceConfig.RebroadcastMode, str]] = ..., node_info_broadcast_secs: _Optional[int] = ..., double_tap_as_button_press: bool = ..., is_managed: bool = ..., disable_triple_click: bool = ..., tzdef: _Optional[str] = ..., led_heartbeat_disabled: bool = ..., buzzer_mode: _Optional[_Union[Config.DeviceConfig.BuzzerMode, str]] = ...) -> None: ...
    class PositionConfig(_message.Message):
        __slots__ = ("position_broadcast_secs", "position_broadcast_smart_enabled", "fixed_position", "gps_enabled", "gps_update_interval", "gps_attempt_time", "position_flags", "rx_gpio", "tx_gpio", "broadcast_smart_minimum_distance", "broadcast_smart_minimum_interval_secs", "gps_en_gpio", "gps_mode")
        class PositionFlags(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            UNSET: _ClassVar[Config.PositionConfig.PositionFlags]
            ALTITUDE: _ClassVar[Config.PositionConfig.PositionFlags]
            ALTITUDE_MSL: _ClassVar[Config.PositionConfig.PositionFlags]
            GEOIDAL_SEPARATION: _ClassVar[Config.PositionConfig.PositionFlags]
            DOP: _ClassVar[Config.PositionConfig.PositionFlags]
            HVDOP: _ClassVar[Config.PositionConfig.PositionFlags]
            SATINVIEW: _ClassVar[Config.PositionConfig.PositionFlags]
            SEQ_NO: _ClassVar[Config.PositionConfig.PositionFlags]
            TIMESTAMP: _ClassVar[Config.PositionConfig.PositionFlags]
            HEADING: _ClassVar[Config.PositionConfig.PositionFlags]
            SPEED: _ClassVar[Config.PositionConfig.PositionFlags]
        UNSET: Config.PositionConfig.PositionFlags
        ALTITUDE: Config.PositionConfig.PositionFlags
        ALTITUDE_MSL: Config.PositionConfig.PositionFlags
        GEOIDAL_SEPARATION: Config.PositionConfig.PositionFlags
        DOP: Config.PositionConfig.PositionFlags
        HVDOP: Config.PositionConfig.PositionFlags
        SATINVIEW: Config.PositionConfig.PositionFlags
        SEQ_NO: Config.PositionConfig.PositionFlags
        TIMESTAMP: Config.PositionConfig.PositionFlags
        HEADING: Config.PositionConfig.PositionFlags
        SPEED: Config.PositionConfig.PositionFlags
        class GpsMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            DISABLED: _ClassVar[Config.PositionConfig.GpsMode]
            ENABLED: _ClassVar[Config.PositionConfig.GpsMode]
            NOT_PRESENT: _ClassVar[Config.PositionConfig.GpsMode]
        DISABLED: Config.PositionConfig.GpsMode
        ENABLED: Config.PositionConfig.GpsMode
        NOT_PRESENT: Config.PositionConfig.GpsMode
        POSITION_BROADCAST_SECS_FIELD_NUMBER: _ClassVar[int]
        POSITION_BROADCAST_SMART_ENABLED_FIELD_NUMBER: _ClassVar[int]
        FIXED_POSITION_FIELD_NUMBER: _ClassVar[int]
        GPS_ENABLED_FIELD_NUMBER: _ClassVar[int]
        GPS_UPDATE_INTERVAL_FIELD_NUMBER: _ClassVar[int]
        GPS_ATTEMPT_TIME_FIELD_NUMBER: _ClassVar[int]
        POSITION_FLAGS_FIELD_NUMBER: _ClassVar[int]
        RX_GPIO_FIELD_NUMBER: _ClassVar[int]
        TX_GPIO_FIELD_NUMBER: _ClassVar[int]
        BROADCAST_SMART_MINIMUM_DISTANCE_FIELD_NUMBER: _ClassVar[int]
        BROADCAST_SMART_MINIMUM_INTERVAL_SECS_FIELD_NUMBER: _ClassVar[int]
        GPS_EN_GPIO_FIELD_NUMBER: _ClassVar[int]
        GPS_MODE_FIELD_NUMBER: _ClassVar[int]
        position_broadcast_secs: int
        position_broadcast_smart_enabled: bool
        fixed_position: bool
        gps_enabled: bool
        gps_update_interval: int
        gps_attempt_time: int
        position_flags: int
        rx_gpio: int
        tx_gpio: int
        broadcast_smart_minimum_distance: int
        broadcast_smart_minimum_interval_secs: int
        gps_en_gpio: int
        gps_mode: Config.PositionConfig.GpsMode
        def __init__(self, position_broadcast_secs: _Optional[int] = ..., position_broadcast_smart_enabled: bool = ..., fixed_position: bool = ..., gps_enabled: bool = ..., gps_update_interval: _Optional[int] = ..., gps_attempt_time: _Optional[int] = ..., position_flags: _Optional[int] = ..., rx_gpio: _Optional[int] = ..., tx_gpio: _Optional[int] = ..., broadcast_smart_minimum_distance: _Optional[int] = ..., broadcast_smart_minimum_interval_secs: _Optional[int] = ..., gps_en_gpio: _Optional[int] = ..., gps_mode: _Optional[_Union[Config.PositionConfig.GpsMode, str]] = ...) -> None: ...
    class PowerConfig(_message.Message):
        __slots__ = ("is_power_saving", "on_battery_shutdown_after_secs", "adc_multiplier_override", "wait_bluetooth_secs", "sds_secs", "ls_secs", "min_wake_secs", "device_battery_ina_address", "powermon_enables")
        IS_POWER_SAVING_FIELD_NUMBER: _ClassVar[int]
        ON_BATTERY_SHUTDOWN_AFTER_SECS_FIELD_NUMBER: _ClassVar[int]
        ADC_MULTIPLIER_OVERRIDE_FIELD_NUMBER: _ClassVar[int]
        WAIT_BLUETOOTH_SECS_FIELD_NUMBER: _ClassVar[int]
        SDS_SECS_FIELD_NUMBER: _ClassVar[int]
        LS_SECS_FIELD_NUMBER: _ClassVar[int]
        MIN_WAKE_SECS_FIELD_NUMBER: _ClassVar[int]
        DEVICE_BATTERY_INA_ADDRESS_FIELD_NUMBER: _ClassVar[int]
        POWERMON_ENABLES_FIELD_NUMBER: _ClassVar[int]
        is_power_saving: bool
        on_battery_shutdown_after_secs: int
        adc_multiplier_override: float
        wait_bluetooth_secs: int
        sds_secs: int
        ls_secs: int
        min_wake_secs: int
        device_battery_ina_address: int
        powermon_enables: int
        def __init__(self, is_power_saving: bool = ..., on_battery_shutdown_after_secs: _Optional[int] = ..., adc_multiplier_override: _Optional[float] = ..., wait_bluetooth_secs: _Optional[int] = ..., sds_secs: _Optional[int] = ..., ls_secs: _Optional[int] = ..., min_wake_secs: _Optional[int] = ..., device_battery_ina_address: _Optional[int] = ..., powermon_enables: _Optional[int] = ...) -> None: ...
    class NetworkConfig(_message.Message):
        __slots__ = ("wifi_enabled", "wifi_ssid", "wifi_psk", "ntp_server", "eth_enabled", "address_mode", "ipv4_config", "rsyslog_server", "enabled_protocols", "ipv6_enabled")
        class AddressMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            DHCP: _ClassVar[Config.NetworkConfig.AddressMode]
            STATIC: _ClassVar[Config.NetworkConfig.AddressMode]
        DHCP: Config.NetworkConfig.AddressMode
        STATIC: Config.NetworkConfig.AddressMode
        class ProtocolFlags(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            NO_BROADCAST: _ClassVar[Config.NetworkConfig.ProtocolFlags]
            UDP_BROADCAST: _ClassVar[Config.NetworkConfig.ProtocolFlags]
        NO_BROADCAST: Config.NetworkConfig.ProtocolFlags
        UDP_BROADCAST: Config.NetworkConfig.ProtocolFlags
        class IpV4Config(_message.Message):
            __slots__ = ("ip", "gateway", "subnet", "dns")
            IP_FIELD_NUMBER: _ClassVar[int]
            GATEWAY_FIELD_NUMBER: _ClassVar[int]
            SUBNET_FIELD_NUMBER: _ClassVar[int]
            DNS_FIELD_NUMBER: _ClassVar[int]
            ip: int
            gateway: int
            subnet: int
            dns: int
            def __init__(self, ip: _Optional[int] = ..., gateway: _Optional[int] = ..., subnet: _Optional[int] = ..., dns: _Optional[int] = ...) -> None: ...
        WIFI_ENABLED_FIELD_NUMBER: _ClassVar[int]
        WIFI_SSID_FIELD_NUMBER: _ClassVar[int]
        WIFI_PSK_FIELD_NUMBER: _ClassVar[int]
        NTP_SERVER_FIELD_NUMBER: _ClassVar[int]
        ETH_ENABLED_FIELD_NUMBER: _ClassVar[int]
        ADDRESS_MODE_FIELD_NUMBER: _ClassVar[int]
        IPV4_CONFIG_FIELD_NUMBER: _ClassVar[int]
        RSYSLOG_SERVER_FIELD_NUMBER: _ClassVar[int]
        ENABLED_PROTOCOLS_FIELD_NUMBER: _ClassVar[int]
        IPV6_ENABLED_FIELD_NUMBER: _ClassVar[int]
        wifi_enabled: bool
        wifi_ssid: str
        wifi_psk: str
        ntp_server: str
        eth_enabled: bool
        address_mode: Config.NetworkConfig.AddressMode
        ipv4_config: Config.NetworkConfig.IpV4Config
        rsyslog_server: str
        enabled_protocols: int
        ipv6_enabled: bool
        def __init__(self, wifi_enabled: bool = ..., wifi_ssid: _Optional[str] = ..., wifi_psk: _Optional[str] = ..., ntp_server: _Optional[str] = ..., eth_enabled: bool = ..., address_mode: _Optional[_Union[Config.NetworkConfig.AddressMode, str]] = ..., ipv4_config: _Optional[_Union[Config.NetworkConfig.IpV4Config, _Mapping]] = ..., rsyslog_server: _Optional[str] = ..., enabled_protocols: _Optional[int] = ..., ipv6_enabled: bool = ...) -> None: ...
    class DisplayConfig(_message.Message):
        __slots__ = ("screen_on_secs", "gps_format", "auto_screen_carousel_secs", "compass_north_top", "flip_screen", "units", "oled", "displaymode", "heading_bold", "wake_on_tap_or_motion", "compass_orientation", "use_12h_clock", "use_long_node_name", "enable_message_bubbles")
        class DeprecatedGpsCoordinateFormat(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            UNUSED: _ClassVar[Config.DisplayConfig.DeprecatedGpsCoordinateFormat]
        UNUSED: Config.DisplayConfig.DeprecatedGpsCoordinateFormat
        class DisplayUnits(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            METRIC: _ClassVar[Config.DisplayConfig.DisplayUnits]
            IMPERIAL: _ClassVar[Config.DisplayConfig.DisplayUnits]
        METRIC: Config.DisplayConfig.DisplayUnits
        IMPERIAL: Config.DisplayConfig.DisplayUnits
        class OledType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            OLED_AUTO: _ClassVar[Config.DisplayConfig.OledType]
            OLED_SSD1306: _ClassVar[Config.DisplayConfig.OledType]
            OLED_SH1106: _ClassVar[Config.DisplayConfig.OledType]
            OLED_SH1107: _ClassVar[Config.DisplayConfig.OledType]
            OLED_SH1107_128_128: _ClassVar[Config.DisplayConfig.OledType]
            OLED_SH1107_ROTATED: _ClassVar[Config.DisplayConfig.OledType]
        OLED_AUTO: Config.DisplayConfig.OledType
        OLED_SSD1306: Config.DisplayConfig.OledType
        OLED_SH1106: Config.DisplayConfig.OledType
        OLED_SH1107: Config.DisplayConfig.OledType
        OLED_SH1107_128_128: Config.DisplayConfig.OledType
        OLED_SH1107_ROTATED: Config.DisplayConfig.OledType
        class DisplayMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            DEFAULT: _ClassVar[Config.DisplayConfig.DisplayMode]
            TWOCOLOR: _ClassVar[Config.DisplayConfig.DisplayMode]
            INVERTED: _ClassVar[Config.DisplayConfig.DisplayMode]
            COLOR: _ClassVar[Config.DisplayConfig.DisplayMode]
        DEFAULT: Config.DisplayConfig.DisplayMode
        TWOCOLOR: Config.DisplayConfig.DisplayMode
        INVERTED: Config.DisplayConfig.DisplayMode
        COLOR: Config.DisplayConfig.DisplayMode
        class CompassOrientation(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            DEGREES_0: _ClassVar[Config.DisplayConfig.CompassOrientation]
            DEGREES_90: _ClassVar[Config.DisplayConfig.CompassOrientation]
            DEGREES_180: _ClassVar[Config.DisplayConfig.CompassOrientation]
            DEGREES_270: _ClassVar[Config.DisplayConfig.CompassOrientation]
            DEGREES_0_INVERTED: _ClassVar[Config.DisplayConfig.CompassOrientation]
            DEGREES_90_INVERTED: _ClassVar[Config.DisplayConfig.CompassOrientation]
            DEGREES_180_INVERTED: _ClassVar[Config.DisplayConfig.CompassOrientation]
            DEGREES_270_INVERTED: _ClassVar[Config.DisplayConfig.CompassOrientation]
        DEGREES_0: Config.DisplayConfig.CompassOrientation
        DEGREES_90: Config.DisplayConfig.CompassOrientation
        DEGREES_180: Config.DisplayConfig.CompassOrientation
        DEGREES_270: Config.DisplayConfig.CompassOrientation
        DEGREES_0_INVERTED: Config.DisplayConfig.CompassOrientation
        DEGREES_90_INVERTED: Config.DisplayConfig.CompassOrientation
        DEGREES_180_INVERTED: Config.DisplayConfig.CompassOrientation
        DEGREES_270_INVERTED: Config.DisplayConfig.CompassOrientation
        SCREEN_ON_SECS_FIELD_NUMBER: _ClassVar[int]
        GPS_FORMAT_FIELD_NUMBER: _ClassVar[int]
        AUTO_SCREEN_CAROUSEL_SECS_FIELD_NUMBER: _ClassVar[int]
        COMPASS_NORTH_TOP_FIELD_NUMBER: _ClassVar[int]
        FLIP_SCREEN_FIELD_NUMBER: _ClassVar[int]
        UNITS_FIELD_NUMBER: _ClassVar[int]
        OLED_FIELD_NUMBER: _ClassVar[int]
        DISPLAYMODE_FIELD_NUMBER: _ClassVar[int]
        HEADING_BOLD_FIELD_NUMBER: _ClassVar[int]
        WAKE_ON_TAP_OR_MOTION_FIELD_NUMBER: _ClassVar[int]
        COMPASS_ORIENTATION_FIELD_NUMBER: _ClassVar[int]
        USE_12H_CLOCK_FIELD_NUMBER: _ClassVar[int]
        USE_LONG_NODE_NAME_FIELD_NUMBER: _ClassVar[int]
        ENABLE_MESSAGE_BUBBLES_FIELD_NUMBER: _ClassVar[int]
        screen_on_secs: int
        gps_format: Config.DisplayConfig.DeprecatedGpsCoordinateFormat
        auto_screen_carousel_secs: int
        compass_north_top: bool
        flip_screen: bool
        units: Config.DisplayConfig.DisplayUnits
        oled: Config.DisplayConfig.OledType
        displaymode: Config.DisplayConfig.DisplayMode
        heading_bold: bool
        wake_on_tap_or_motion: bool
        compass_orientation: Config.DisplayConfig.CompassOrientation
        use_12h_clock: bool
        use_long_node_name: bool
        enable_message_bubbles: bool
        def __init__(self, screen_on_secs: _Optional[int] = ..., gps_format: _Optional[_Union[Config.DisplayConfig.DeprecatedGpsCoordinateFormat, str]] = ..., auto_screen_carousel_secs: _Optional[int] = ..., compass_north_top: bool = ..., flip_screen: bool = ..., units: _Optional[_Union[Config.DisplayConfig.DisplayUnits, str]] = ..., oled: _Optional[_Union[Config.DisplayConfig.OledType, str]] = ..., displaymode: _Optional[_Union[Config.DisplayConfig.DisplayMode, str]] = ..., heading_bold: bool = ..., wake_on_tap_or_motion: bool = ..., compass_orientation: _Optional[_Union[Config.DisplayConfig.CompassOrientation, str]] = ..., use_12h_clock: bool = ..., use_long_node_name: bool = ..., enable_message_bubbles: bool = ...) -> None: ...
    class LoRaConfig(_message.Message):
        __slots__ = ("use_preset", "modem_preset", "bandwidth", "spread_factor", "coding_rate", "frequency_offset", "region", "hop_limit", "tx_enabled", "tx_power", "channel_num", "override_duty_cycle", "sx126x_rx_boosted_gain", "override_frequency", "pa_fan_disabled", "ignore_incoming", "ignore_mqtt", "config_ok_to_mqtt", "fem_lna_mode", "serial_hal_only")
        class RegionCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            UNSET: _ClassVar[Config.LoRaConfig.RegionCode]
            US: _ClassVar[Config.LoRaConfig.RegionCode]
            EU_433: _ClassVar[Config.LoRaConfig.RegionCode]
            EU_868: _ClassVar[Config.LoRaConfig.RegionCode]
            CN: _ClassVar[Config.LoRaConfig.RegionCode]
            JP: _ClassVar[Config.LoRaConfig.RegionCode]
            ANZ: _ClassVar[Config.LoRaConfig.RegionCode]
            KR: _ClassVar[Config.LoRaConfig.RegionCode]
            TW: _ClassVar[Config.LoRaConfig.RegionCode]
            RU: _ClassVar[Config.LoRaConfig.RegionCode]
            IN: _ClassVar[Config.LoRaConfig.RegionCode]
            NZ_865: _ClassVar[Config.LoRaConfig.RegionCode]
            TH: _ClassVar[Config.LoRaConfig.RegionCode]
            LORA_24: _ClassVar[Config.LoRaConfig.RegionCode]
            UA_433: _ClassVar[Config.LoRaConfig.RegionCode]
            UA_868: _ClassVar[Config.LoRaConfig.RegionCode]
            MY_433: _ClassVar[Config.LoRaConfig.RegionCode]
            MY_919: _ClassVar[Config.LoRaConfig.RegionCode]
            SG_923: _ClassVar[Config.LoRaConfig.RegionCode]
            PH_433: _ClassVar[Config.LoRaConfig.RegionCode]
            PH_868: _ClassVar[Config.LoRaConfig.RegionCode]
            PH_915: _ClassVar[Config.LoRaConfig.RegionCode]
            ANZ_433: _ClassVar[Config.LoRaConfig.RegionCode]
            KZ_433: _ClassVar[Config.LoRaConfig.RegionCode]
            KZ_863: _ClassVar[Config.LoRaConfig.RegionCode]
            NP_865: _ClassVar[Config.LoRaConfig.RegionCode]
            BR_902: _ClassVar[Config.LoRaConfig.RegionCode]
            ITU1_2M: _ClassVar[Config.LoRaConfig.RegionCode]
            ITU2_2M: _ClassVar[Config.LoRaConfig.RegionCode]
            EU_866: _ClassVar[Config.LoRaConfig.RegionCode]
            EU_874: _ClassVar[Config.LoRaConfig.RegionCode]
            EU_917: _ClassVar[Config.LoRaConfig.RegionCode]
            EU_N_868: _ClassVar[Config.LoRaConfig.RegionCode]
            ITU3_2M: _ClassVar[Config.LoRaConfig.RegionCode]
            ITU1_70CM: _ClassVar[Config.LoRaConfig.RegionCode]
            ITU2_70CM: _ClassVar[Config.LoRaConfig.RegionCode]
            ITU3_70CM: _ClassVar[Config.LoRaConfig.RegionCode]
            ITU2_125CM: _ClassVar[Config.LoRaConfig.RegionCode]
        UNSET: Config.LoRaConfig.RegionCode
        US: Config.LoRaConfig.RegionCode
        EU_433: Config.LoRaConfig.RegionCode
        EU_868: Config.LoRaConfig.RegionCode
        CN: Config.LoRaConfig.RegionCode
        JP: Config.LoRaConfig.RegionCode
        ANZ: Config.LoRaConfig.RegionCode
        KR: Config.LoRaConfig.RegionCode
        TW: Config.LoRaConfig.RegionCode
        RU: Config.LoRaConfig.RegionCode
        IN: Config.LoRaConfig.RegionCode
        NZ_865: Config.LoRaConfig.RegionCode
        TH: Config.LoRaConfig.RegionCode
        LORA_24: Config.LoRaConfig.RegionCode
        UA_433: Config.LoRaConfig.RegionCode
        UA_868: Config.LoRaConfig.RegionCode
        MY_433: Config.LoRaConfig.RegionCode
        MY_919: Config.LoRaConfig.RegionCode
        SG_923: Config.LoRaConfig.RegionCode
        PH_433: Config.LoRaConfig.RegionCode
        PH_868: Config.LoRaConfig.RegionCode
        PH_915: Config.LoRaConfig.RegionCode
        ANZ_433: Config.LoRaConfig.RegionCode
        KZ_433: Config.LoRaConfig.RegionCode
        KZ_863: Config.LoRaConfig.RegionCode
        NP_865: Config.LoRaConfig.RegionCode
        BR_902: Config.LoRaConfig.RegionCode
        ITU1_2M: Config.LoRaConfig.RegionCode
        ITU2_2M: Config.LoRaConfig.RegionCode
        EU_866: Config.LoRaConfig.RegionCode
        EU_874: Config.LoRaConfig.RegionCode
        EU_917: Config.LoRaConfig.RegionCode
        EU_N_868: Config.LoRaConfig.RegionCode
        ITU3_2M: Config.LoRaConfig.RegionCode
        ITU1_70CM: Config.LoRaConfig.RegionCode
        ITU2_70CM: Config.LoRaConfig.RegionCode
        ITU3_70CM: Config.LoRaConfig.RegionCode
        ITU2_125CM: Config.LoRaConfig.RegionCode
        class ModemPreset(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            LONG_FAST: _ClassVar[Config.LoRaConfig.ModemPreset]
            LONG_SLOW: _ClassVar[Config.LoRaConfig.ModemPreset]
            VERY_LONG_SLOW: _ClassVar[Config.LoRaConfig.ModemPreset]
            MEDIUM_SLOW: _ClassVar[Config.LoRaConfig.ModemPreset]
            MEDIUM_FAST: _ClassVar[Config.LoRaConfig.ModemPreset]
            SHORT_SLOW: _ClassVar[Config.LoRaConfig.ModemPreset]
            SHORT_FAST: _ClassVar[Config.LoRaConfig.ModemPreset]
            LONG_MODERATE: _ClassVar[Config.LoRaConfig.ModemPreset]
            SHORT_TURBO: _ClassVar[Config.LoRaConfig.ModemPreset]
            LONG_TURBO: _ClassVar[Config.LoRaConfig.ModemPreset]
            LITE_FAST: _ClassVar[Config.LoRaConfig.ModemPreset]
            LITE_SLOW: _ClassVar[Config.LoRaConfig.ModemPreset]
            NARROW_FAST: _ClassVar[Config.LoRaConfig.ModemPreset]
            NARROW_SLOW: _ClassVar[Config.LoRaConfig.ModemPreset]
            TINY_FAST: _ClassVar[Config.LoRaConfig.ModemPreset]
            TINY_SLOW: _ClassVar[Config.LoRaConfig.ModemPreset]
            MEDIUM_TURBO: _ClassVar[Config.LoRaConfig.ModemPreset]
        LONG_FAST: Config.LoRaConfig.ModemPreset
        LONG_SLOW: Config.LoRaConfig.ModemPreset
        VERY_LONG_SLOW: Config.LoRaConfig.ModemPreset
        MEDIUM_SLOW: Config.LoRaConfig.ModemPreset
        MEDIUM_FAST: Config.LoRaConfig.ModemPreset
        SHORT_SLOW: Config.LoRaConfig.ModemPreset
        SHORT_FAST: Config.LoRaConfig.ModemPreset
        LONG_MODERATE: Config.LoRaConfig.ModemPreset
        SHORT_TURBO: Config.LoRaConfig.ModemPreset
        LONG_TURBO: Config.LoRaConfig.ModemPreset
        LITE_FAST: Config.LoRaConfig.ModemPreset
        LITE_SLOW: Config.LoRaConfig.ModemPreset
        NARROW_FAST: Config.LoRaConfig.ModemPreset
        NARROW_SLOW: Config.LoRaConfig.ModemPreset
        TINY_FAST: Config.LoRaConfig.ModemPreset
        TINY_SLOW: Config.LoRaConfig.ModemPreset
        MEDIUM_TURBO: Config.LoRaConfig.ModemPreset
        class FEM_LNA_Mode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            DISABLED: _ClassVar[Config.LoRaConfig.FEM_LNA_Mode]
            ENABLED: _ClassVar[Config.LoRaConfig.FEM_LNA_Mode]
            NOT_PRESENT: _ClassVar[Config.LoRaConfig.FEM_LNA_Mode]
        DISABLED: Config.LoRaConfig.FEM_LNA_Mode
        ENABLED: Config.LoRaConfig.FEM_LNA_Mode
        NOT_PRESENT: Config.LoRaConfig.FEM_LNA_Mode
        USE_PRESET_FIELD_NUMBER: _ClassVar[int]
        MODEM_PRESET_FIELD_NUMBER: _ClassVar[int]
        BANDWIDTH_FIELD_NUMBER: _ClassVar[int]
        SPREAD_FACTOR_FIELD_NUMBER: _ClassVar[int]
        CODING_RATE_FIELD_NUMBER: _ClassVar[int]
        FREQUENCY_OFFSET_FIELD_NUMBER: _ClassVar[int]
        REGION_FIELD_NUMBER: _ClassVar[int]
        HOP_LIMIT_FIELD_NUMBER: _ClassVar[int]
        TX_ENABLED_FIELD_NUMBER: _ClassVar[int]
        TX_POWER_FIELD_NUMBER: _ClassVar[int]
        CHANNEL_NUM_FIELD_NUMBER: _ClassVar[int]
        OVERRIDE_DUTY_CYCLE_FIELD_NUMBER: _ClassVar[int]
        SX126X_RX_BOOSTED_GAIN_FIELD_NUMBER: _ClassVar[int]
        OVERRIDE_FREQUENCY_FIELD_NUMBER: _ClassVar[int]
        PA_FAN_DISABLED_FIELD_NUMBER: _ClassVar[int]
        IGNORE_INCOMING_FIELD_NUMBER: _ClassVar[int]
        IGNORE_MQTT_FIELD_NUMBER: _ClassVar[int]
        CONFIG_OK_TO_MQTT_FIELD_NUMBER: _ClassVar[int]
        FEM_LNA_MODE_FIELD_NUMBER: _ClassVar[int]
        SERIAL_HAL_ONLY_FIELD_NUMBER: _ClassVar[int]
        use_preset: bool
        modem_preset: Config.LoRaConfig.ModemPreset
        bandwidth: int
        spread_factor: int
        coding_rate: int
        frequency_offset: float
        region: Config.LoRaConfig.RegionCode
        hop_limit: int
        tx_enabled: bool
        tx_power: int
        channel_num: int
        override_duty_cycle: bool
        sx126x_rx_boosted_gain: bool
        override_frequency: float
        pa_fan_disabled: bool
        ignore_incoming: _containers.RepeatedScalarFieldContainer[int]
        ignore_mqtt: bool
        config_ok_to_mqtt: bool
        fem_lna_mode: Config.LoRaConfig.FEM_LNA_Mode
        serial_hal_only: bool
        def __init__(self, use_preset: bool = ..., modem_preset: _Optional[_Union[Config.LoRaConfig.ModemPreset, str]] = ..., bandwidth: _Optional[int] = ..., spread_factor: _Optional[int] = ..., coding_rate: _Optional[int] = ..., frequency_offset: _Optional[float] = ..., region: _Optional[_Union[Config.LoRaConfig.RegionCode, str]] = ..., hop_limit: _Optional[int] = ..., tx_enabled: bool = ..., tx_power: _Optional[int] = ..., channel_num: _Optional[int] = ..., override_duty_cycle: bool = ..., sx126x_rx_boosted_gain: bool = ..., override_frequency: _Optional[float] = ..., pa_fan_disabled: bool = ..., ignore_incoming: _Optional[_Iterable[int]] = ..., ignore_mqtt: bool = ..., config_ok_to_mqtt: bool = ..., fem_lna_mode: _Optional[_Union[Config.LoRaConfig.FEM_LNA_Mode, str]] = ..., serial_hal_only: bool = ...) -> None: ...
    class BluetoothConfig(_message.Message):
        __slots__ = ("enabled", "mode", "fixed_pin")
        class PairingMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            RANDOM_PIN: _ClassVar[Config.BluetoothConfig.PairingMode]
            FIXED_PIN: _ClassVar[Config.BluetoothConfig.PairingMode]
            NO_PIN: _ClassVar[Config.BluetoothConfig.PairingMode]
        RANDOM_PIN: Config.BluetoothConfig.PairingMode
        FIXED_PIN: Config.BluetoothConfig.PairingMode
        NO_PIN: Config.BluetoothConfig.PairingMode
        ENABLED_FIELD_NUMBER: _ClassVar[int]
        MODE_FIELD_NUMBER: _ClassVar[int]
        FIXED_PIN_FIELD_NUMBER: _ClassVar[int]
        enabled: bool
        mode: Config.BluetoothConfig.PairingMode
        fixed_pin: int
        def __init__(self, enabled: bool = ..., mode: _Optional[_Union[Config.BluetoothConfig.PairingMode, str]] = ..., fixed_pin: _Optional[int] = ...) -> None: ...
    class SecurityConfig(_message.Message):
        __slots__ = ("public_key", "private_key", "admin_key", "is_managed", "serial_enabled", "debug_log_api_enabled", "admin_channel_enabled", "packet_signature_policy")
        class PacketSignaturePolicy(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            PACKET_SIGNATURE_POLICY_COMPATIBLE: _ClassVar[Config.SecurityConfig.PacketSignaturePolicy]
            PACKET_SIGNATURE_POLICY_BALANCED: _ClassVar[Config.SecurityConfig.PacketSignaturePolicy]
            PACKET_SIGNATURE_POLICY_STRICT: _ClassVar[Config.SecurityConfig.PacketSignaturePolicy]
        PACKET_SIGNATURE_POLICY_COMPATIBLE: Config.SecurityConfig.PacketSignaturePolicy
        PACKET_SIGNATURE_POLICY_BALANCED: Config.SecurityConfig.PacketSignaturePolicy
        PACKET_SIGNATURE_POLICY_STRICT: Config.SecurityConfig.PacketSignaturePolicy
        PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
        PRIVATE_KEY_FIELD_NUMBER: _ClassVar[int]
        ADMIN_KEY_FIELD_NUMBER: _ClassVar[int]
        IS_MANAGED_FIELD_NUMBER: _ClassVar[int]
        SERIAL_ENABLED_FIELD_NUMBER: _ClassVar[int]
        DEBUG_LOG_API_ENABLED_FIELD_NUMBER: _ClassVar[int]
        ADMIN_CHANNEL_ENABLED_FIELD_NUMBER: _ClassVar[int]
        PACKET_SIGNATURE_POLICY_FIELD_NUMBER: _ClassVar[int]
        public_key: bytes
        private_key: bytes
        admin_key: _containers.RepeatedScalarFieldContainer[bytes]
        is_managed: bool
        serial_enabled: bool
        debug_log_api_enabled: bool
        admin_channel_enabled: bool
        packet_signature_policy: Config.SecurityConfig.PacketSignaturePolicy
        def __init__(self, public_key: _Optional[bytes] = ..., private_key: _Optional[bytes] = ..., admin_key: _Optional[_Iterable[bytes]] = ..., is_managed: bool = ..., serial_enabled: bool = ..., debug_log_api_enabled: bool = ..., admin_channel_enabled: bool = ..., packet_signature_policy: _Optional[_Union[Config.SecurityConfig.PacketSignaturePolicy, str]] = ...) -> None: ...
    class SessionkeyConfig(_message.Message):
        __slots__ = ()
        def __init__(self) -> None: ...
    DEVICE_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    POWER_FIELD_NUMBER: _ClassVar[int]
    NETWORK_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_FIELD_NUMBER: _ClassVar[int]
    LORA_FIELD_NUMBER: _ClassVar[int]
    BLUETOOTH_FIELD_NUMBER: _ClassVar[int]
    SECURITY_FIELD_NUMBER: _ClassVar[int]
    SESSIONKEY_FIELD_NUMBER: _ClassVar[int]
    DEVICE_UI_FIELD_NUMBER: _ClassVar[int]
    device: Config.DeviceConfig
    position: Config.PositionConfig
    power: Config.PowerConfig
    network: Config.NetworkConfig
    display: Config.DisplayConfig
    lora: Config.LoRaConfig
    bluetooth: Config.BluetoothConfig
    security: Config.SecurityConfig
    sessionkey: Config.SessionkeyConfig
    device_ui: _device_ui_pb2.DeviceUIConfig
    def __init__(self, device: _Optional[_Union[Config.DeviceConfig, _Mapping]] = ..., position: _Optional[_Union[Config.PositionConfig, _Mapping]] = ..., power: _Optional[_Union[Config.PowerConfig, _Mapping]] = ..., network: _Optional[_Union[Config.NetworkConfig, _Mapping]] = ..., display: _Optional[_Union[Config.DisplayConfig, _Mapping]] = ..., lora: _Optional[_Union[Config.LoRaConfig, _Mapping]] = ..., bluetooth: _Optional[_Union[Config.BluetoothConfig, _Mapping]] = ..., security: _Optional[_Union[Config.SecurityConfig, _Mapping]] = ..., sessionkey: _Optional[_Union[Config.SessionkeyConfig, _Mapping]] = ..., device_ui: _Optional[_Union[_device_ui_pb2.DeviceUIConfig, _Mapping]] = ...) -> None: ...
