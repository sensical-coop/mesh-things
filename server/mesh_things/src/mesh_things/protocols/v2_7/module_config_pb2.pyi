from mesh_things.protocols.v2_7 import atak_pb2 as _atak_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RemoteHardwarePinType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UNKNOWN: _ClassVar[RemoteHardwarePinType]
    DIGITAL_READ: _ClassVar[RemoteHardwarePinType]
    DIGITAL_WRITE: _ClassVar[RemoteHardwarePinType]
UNKNOWN: RemoteHardwarePinType
DIGITAL_READ: RemoteHardwarePinType
DIGITAL_WRITE: RemoteHardwarePinType

class ModuleConfig(_message.Message):
    __slots__ = ("mqtt", "serial", "external_notification", "store_forward", "range_test", "telemetry", "canned_message", "audio", "remote_hardware", "neighbor_info", "ambient_lighting", "detection_sensor", "paxcounter", "statusmessage", "traffic_management", "tak")
    class MQTTConfig(_message.Message):
        __slots__ = ("enabled", "address", "username", "password", "encryption_enabled", "json_enabled", "tls_enabled", "root", "proxy_to_client_enabled", "map_reporting_enabled", "map_report_settings")
        ENABLED_FIELD_NUMBER: _ClassVar[int]
        ADDRESS_FIELD_NUMBER: _ClassVar[int]
        USERNAME_FIELD_NUMBER: _ClassVar[int]
        PASSWORD_FIELD_NUMBER: _ClassVar[int]
        ENCRYPTION_ENABLED_FIELD_NUMBER: _ClassVar[int]
        JSON_ENABLED_FIELD_NUMBER: _ClassVar[int]
        TLS_ENABLED_FIELD_NUMBER: _ClassVar[int]
        ROOT_FIELD_NUMBER: _ClassVar[int]
        PROXY_TO_CLIENT_ENABLED_FIELD_NUMBER: _ClassVar[int]
        MAP_REPORTING_ENABLED_FIELD_NUMBER: _ClassVar[int]
        MAP_REPORT_SETTINGS_FIELD_NUMBER: _ClassVar[int]
        enabled: bool
        address: str
        username: str
        password: str
        encryption_enabled: bool
        json_enabled: bool
        tls_enabled: bool
        root: str
        proxy_to_client_enabled: bool
        map_reporting_enabled: bool
        map_report_settings: ModuleConfig.MapReportSettings
        def __init__(self, enabled: bool = ..., address: _Optional[str] = ..., username: _Optional[str] = ..., password: _Optional[str] = ..., encryption_enabled: bool = ..., json_enabled: bool = ..., tls_enabled: bool = ..., root: _Optional[str] = ..., proxy_to_client_enabled: bool = ..., map_reporting_enabled: bool = ..., map_report_settings: _Optional[_Union[ModuleConfig.MapReportSettings, _Mapping]] = ...) -> None: ...
    class MapReportSettings(_message.Message):
        __slots__ = ("publish_interval_secs", "position_precision", "should_report_location")
        PUBLISH_INTERVAL_SECS_FIELD_NUMBER: _ClassVar[int]
        POSITION_PRECISION_FIELD_NUMBER: _ClassVar[int]
        SHOULD_REPORT_LOCATION_FIELD_NUMBER: _ClassVar[int]
        publish_interval_secs: int
        position_precision: int
        should_report_location: bool
        def __init__(self, publish_interval_secs: _Optional[int] = ..., position_precision: _Optional[int] = ..., should_report_location: bool = ...) -> None: ...
    class RemoteHardwareConfig(_message.Message):
        __slots__ = ("enabled", "allow_undefined_pin_access", "available_pins")
        ENABLED_FIELD_NUMBER: _ClassVar[int]
        ALLOW_UNDEFINED_PIN_ACCESS_FIELD_NUMBER: _ClassVar[int]
        AVAILABLE_PINS_FIELD_NUMBER: _ClassVar[int]
        enabled: bool
        allow_undefined_pin_access: bool
        available_pins: _containers.RepeatedCompositeFieldContainer[RemoteHardwarePin]
        def __init__(self, enabled: bool = ..., allow_undefined_pin_access: bool = ..., available_pins: _Optional[_Iterable[_Union[RemoteHardwarePin, _Mapping]]] = ...) -> None: ...
    class NeighborInfoConfig(_message.Message):
        __slots__ = ("enabled", "update_interval", "transmit_over_lora")
        ENABLED_FIELD_NUMBER: _ClassVar[int]
        UPDATE_INTERVAL_FIELD_NUMBER: _ClassVar[int]
        TRANSMIT_OVER_LORA_FIELD_NUMBER: _ClassVar[int]
        enabled: bool
        update_interval: int
        transmit_over_lora: bool
        def __init__(self, enabled: bool = ..., update_interval: _Optional[int] = ..., transmit_over_lora: bool = ...) -> None: ...
    class DetectionSensorConfig(_message.Message):
        __slots__ = ("enabled", "minimum_broadcast_secs", "state_broadcast_secs", "send_bell", "name", "monitor_pin", "detection_trigger_type", "use_pullup")
        class TriggerType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            LOGIC_LOW: _ClassVar[ModuleConfig.DetectionSensorConfig.TriggerType]
            LOGIC_HIGH: _ClassVar[ModuleConfig.DetectionSensorConfig.TriggerType]
            FALLING_EDGE: _ClassVar[ModuleConfig.DetectionSensorConfig.TriggerType]
            RISING_EDGE: _ClassVar[ModuleConfig.DetectionSensorConfig.TriggerType]
            EITHER_EDGE_ACTIVE_LOW: _ClassVar[ModuleConfig.DetectionSensorConfig.TriggerType]
            EITHER_EDGE_ACTIVE_HIGH: _ClassVar[ModuleConfig.DetectionSensorConfig.TriggerType]
        LOGIC_LOW: ModuleConfig.DetectionSensorConfig.TriggerType
        LOGIC_HIGH: ModuleConfig.DetectionSensorConfig.TriggerType
        FALLING_EDGE: ModuleConfig.DetectionSensorConfig.TriggerType
        RISING_EDGE: ModuleConfig.DetectionSensorConfig.TriggerType
        EITHER_EDGE_ACTIVE_LOW: ModuleConfig.DetectionSensorConfig.TriggerType
        EITHER_EDGE_ACTIVE_HIGH: ModuleConfig.DetectionSensorConfig.TriggerType
        ENABLED_FIELD_NUMBER: _ClassVar[int]
        MINIMUM_BROADCAST_SECS_FIELD_NUMBER: _ClassVar[int]
        STATE_BROADCAST_SECS_FIELD_NUMBER: _ClassVar[int]
        SEND_BELL_FIELD_NUMBER: _ClassVar[int]
        NAME_FIELD_NUMBER: _ClassVar[int]
        MONITOR_PIN_FIELD_NUMBER: _ClassVar[int]
        DETECTION_TRIGGER_TYPE_FIELD_NUMBER: _ClassVar[int]
        USE_PULLUP_FIELD_NUMBER: _ClassVar[int]
        enabled: bool
        minimum_broadcast_secs: int
        state_broadcast_secs: int
        send_bell: bool
        name: str
        monitor_pin: int
        detection_trigger_type: ModuleConfig.DetectionSensorConfig.TriggerType
        use_pullup: bool
        def __init__(self, enabled: bool = ..., minimum_broadcast_secs: _Optional[int] = ..., state_broadcast_secs: _Optional[int] = ..., send_bell: bool = ..., name: _Optional[str] = ..., monitor_pin: _Optional[int] = ..., detection_trigger_type: _Optional[_Union[ModuleConfig.DetectionSensorConfig.TriggerType, str]] = ..., use_pullup: bool = ...) -> None: ...
    class AudioConfig(_message.Message):
        __slots__ = ("codec2_enabled", "ptt_pin", "bitrate", "i2s_ws", "i2s_sd", "i2s_din", "i2s_sck")
        class Audio_Baud(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            CODEC2_DEFAULT: _ClassVar[ModuleConfig.AudioConfig.Audio_Baud]
            CODEC2_3200: _ClassVar[ModuleConfig.AudioConfig.Audio_Baud]
            CODEC2_2400: _ClassVar[ModuleConfig.AudioConfig.Audio_Baud]
            CODEC2_1600: _ClassVar[ModuleConfig.AudioConfig.Audio_Baud]
            CODEC2_1400: _ClassVar[ModuleConfig.AudioConfig.Audio_Baud]
            CODEC2_1300: _ClassVar[ModuleConfig.AudioConfig.Audio_Baud]
            CODEC2_1200: _ClassVar[ModuleConfig.AudioConfig.Audio_Baud]
            CODEC2_700: _ClassVar[ModuleConfig.AudioConfig.Audio_Baud]
            CODEC2_700B: _ClassVar[ModuleConfig.AudioConfig.Audio_Baud]
        CODEC2_DEFAULT: ModuleConfig.AudioConfig.Audio_Baud
        CODEC2_3200: ModuleConfig.AudioConfig.Audio_Baud
        CODEC2_2400: ModuleConfig.AudioConfig.Audio_Baud
        CODEC2_1600: ModuleConfig.AudioConfig.Audio_Baud
        CODEC2_1400: ModuleConfig.AudioConfig.Audio_Baud
        CODEC2_1300: ModuleConfig.AudioConfig.Audio_Baud
        CODEC2_1200: ModuleConfig.AudioConfig.Audio_Baud
        CODEC2_700: ModuleConfig.AudioConfig.Audio_Baud
        CODEC2_700B: ModuleConfig.AudioConfig.Audio_Baud
        CODEC2_ENABLED_FIELD_NUMBER: _ClassVar[int]
        PTT_PIN_FIELD_NUMBER: _ClassVar[int]
        BITRATE_FIELD_NUMBER: _ClassVar[int]
        I2S_WS_FIELD_NUMBER: _ClassVar[int]
        I2S_SD_FIELD_NUMBER: _ClassVar[int]
        I2S_DIN_FIELD_NUMBER: _ClassVar[int]
        I2S_SCK_FIELD_NUMBER: _ClassVar[int]
        codec2_enabled: bool
        ptt_pin: int
        bitrate: ModuleConfig.AudioConfig.Audio_Baud
        i2s_ws: int
        i2s_sd: int
        i2s_din: int
        i2s_sck: int
        def __init__(self, codec2_enabled: bool = ..., ptt_pin: _Optional[int] = ..., bitrate: _Optional[_Union[ModuleConfig.AudioConfig.Audio_Baud, str]] = ..., i2s_ws: _Optional[int] = ..., i2s_sd: _Optional[int] = ..., i2s_din: _Optional[int] = ..., i2s_sck: _Optional[int] = ...) -> None: ...
    class PaxcounterConfig(_message.Message):
        __slots__ = ("enabled", "paxcounter_update_interval", "wifi_threshold", "ble_threshold")
        ENABLED_FIELD_NUMBER: _ClassVar[int]
        PAXCOUNTER_UPDATE_INTERVAL_FIELD_NUMBER: _ClassVar[int]
        WIFI_THRESHOLD_FIELD_NUMBER: _ClassVar[int]
        BLE_THRESHOLD_FIELD_NUMBER: _ClassVar[int]
        enabled: bool
        paxcounter_update_interval: int
        wifi_threshold: int
        ble_threshold: int
        def __init__(self, enabled: bool = ..., paxcounter_update_interval: _Optional[int] = ..., wifi_threshold: _Optional[int] = ..., ble_threshold: _Optional[int] = ...) -> None: ...
    class TrafficManagementConfig(_message.Message):
        __slots__ = ("enabled", "position_dedup_enabled", "position_precision_bits", "position_min_interval_secs", "nodeinfo_direct_response", "nodeinfo_direct_response_max_hops", "rate_limit_enabled", "rate_limit_window_secs", "rate_limit_max_packets", "drop_unknown_enabled", "unknown_packet_threshold", "exhaust_hop_telemetry", "exhaust_hop_position", "router_preserve_hops")
        ENABLED_FIELD_NUMBER: _ClassVar[int]
        POSITION_DEDUP_ENABLED_FIELD_NUMBER: _ClassVar[int]
        POSITION_PRECISION_BITS_FIELD_NUMBER: _ClassVar[int]
        POSITION_MIN_INTERVAL_SECS_FIELD_NUMBER: _ClassVar[int]
        NODEINFO_DIRECT_RESPONSE_FIELD_NUMBER: _ClassVar[int]
        NODEINFO_DIRECT_RESPONSE_MAX_HOPS_FIELD_NUMBER: _ClassVar[int]
        RATE_LIMIT_ENABLED_FIELD_NUMBER: _ClassVar[int]
        RATE_LIMIT_WINDOW_SECS_FIELD_NUMBER: _ClassVar[int]
        RATE_LIMIT_MAX_PACKETS_FIELD_NUMBER: _ClassVar[int]
        DROP_UNKNOWN_ENABLED_FIELD_NUMBER: _ClassVar[int]
        UNKNOWN_PACKET_THRESHOLD_FIELD_NUMBER: _ClassVar[int]
        EXHAUST_HOP_TELEMETRY_FIELD_NUMBER: _ClassVar[int]
        EXHAUST_HOP_POSITION_FIELD_NUMBER: _ClassVar[int]
        ROUTER_PRESERVE_HOPS_FIELD_NUMBER: _ClassVar[int]
        enabled: bool
        position_dedup_enabled: bool
        position_precision_bits: int
        position_min_interval_secs: int
        nodeinfo_direct_response: bool
        nodeinfo_direct_response_max_hops: int
        rate_limit_enabled: bool
        rate_limit_window_secs: int
        rate_limit_max_packets: int
        drop_unknown_enabled: bool
        unknown_packet_threshold: int
        exhaust_hop_telemetry: bool
        exhaust_hop_position: bool
        router_preserve_hops: bool
        def __init__(self, enabled: bool = ..., position_dedup_enabled: bool = ..., position_precision_bits: _Optional[int] = ..., position_min_interval_secs: _Optional[int] = ..., nodeinfo_direct_response: bool = ..., nodeinfo_direct_response_max_hops: _Optional[int] = ..., rate_limit_enabled: bool = ..., rate_limit_window_secs: _Optional[int] = ..., rate_limit_max_packets: _Optional[int] = ..., drop_unknown_enabled: bool = ..., unknown_packet_threshold: _Optional[int] = ..., exhaust_hop_telemetry: bool = ..., exhaust_hop_position: bool = ..., router_preserve_hops: bool = ...) -> None: ...
    class SerialConfig(_message.Message):
        __slots__ = ("enabled", "echo", "rxd", "txd", "baud", "timeout", "mode", "override_console_serial_port")
        class Serial_Baud(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            BAUD_DEFAULT: _ClassVar[ModuleConfig.SerialConfig.Serial_Baud]
            BAUD_110: _ClassVar[ModuleConfig.SerialConfig.Serial_Baud]
            BAUD_300: _ClassVar[ModuleConfig.SerialConfig.Serial_Baud]
            BAUD_600: _ClassVar[ModuleConfig.SerialConfig.Serial_Baud]
            BAUD_1200: _ClassVar[ModuleConfig.SerialConfig.Serial_Baud]
            BAUD_2400: _ClassVar[ModuleConfig.SerialConfig.Serial_Baud]
            BAUD_4800: _ClassVar[ModuleConfig.SerialConfig.Serial_Baud]
            BAUD_9600: _ClassVar[ModuleConfig.SerialConfig.Serial_Baud]
            BAUD_19200: _ClassVar[ModuleConfig.SerialConfig.Serial_Baud]
            BAUD_38400: _ClassVar[ModuleConfig.SerialConfig.Serial_Baud]
            BAUD_57600: _ClassVar[ModuleConfig.SerialConfig.Serial_Baud]
            BAUD_115200: _ClassVar[ModuleConfig.SerialConfig.Serial_Baud]
            BAUD_230400: _ClassVar[ModuleConfig.SerialConfig.Serial_Baud]
            BAUD_460800: _ClassVar[ModuleConfig.SerialConfig.Serial_Baud]
            BAUD_576000: _ClassVar[ModuleConfig.SerialConfig.Serial_Baud]
            BAUD_921600: _ClassVar[ModuleConfig.SerialConfig.Serial_Baud]
        BAUD_DEFAULT: ModuleConfig.SerialConfig.Serial_Baud
        BAUD_110: ModuleConfig.SerialConfig.Serial_Baud
        BAUD_300: ModuleConfig.SerialConfig.Serial_Baud
        BAUD_600: ModuleConfig.SerialConfig.Serial_Baud
        BAUD_1200: ModuleConfig.SerialConfig.Serial_Baud
        BAUD_2400: ModuleConfig.SerialConfig.Serial_Baud
        BAUD_4800: ModuleConfig.SerialConfig.Serial_Baud
        BAUD_9600: ModuleConfig.SerialConfig.Serial_Baud
        BAUD_19200: ModuleConfig.SerialConfig.Serial_Baud
        BAUD_38400: ModuleConfig.SerialConfig.Serial_Baud
        BAUD_57600: ModuleConfig.SerialConfig.Serial_Baud
        BAUD_115200: ModuleConfig.SerialConfig.Serial_Baud
        BAUD_230400: ModuleConfig.SerialConfig.Serial_Baud
        BAUD_460800: ModuleConfig.SerialConfig.Serial_Baud
        BAUD_576000: ModuleConfig.SerialConfig.Serial_Baud
        BAUD_921600: ModuleConfig.SerialConfig.Serial_Baud
        class Serial_Mode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            DEFAULT: _ClassVar[ModuleConfig.SerialConfig.Serial_Mode]
            SIMPLE: _ClassVar[ModuleConfig.SerialConfig.Serial_Mode]
            PROTO: _ClassVar[ModuleConfig.SerialConfig.Serial_Mode]
            TEXTMSG: _ClassVar[ModuleConfig.SerialConfig.Serial_Mode]
            NMEA: _ClassVar[ModuleConfig.SerialConfig.Serial_Mode]
            CALTOPO: _ClassVar[ModuleConfig.SerialConfig.Serial_Mode]
            WS85: _ClassVar[ModuleConfig.SerialConfig.Serial_Mode]
            VE_DIRECT: _ClassVar[ModuleConfig.SerialConfig.Serial_Mode]
            MS_CONFIG: _ClassVar[ModuleConfig.SerialConfig.Serial_Mode]
            LOG: _ClassVar[ModuleConfig.SerialConfig.Serial_Mode]
            LOGTEXT: _ClassVar[ModuleConfig.SerialConfig.Serial_Mode]
        DEFAULT: ModuleConfig.SerialConfig.Serial_Mode
        SIMPLE: ModuleConfig.SerialConfig.Serial_Mode
        PROTO: ModuleConfig.SerialConfig.Serial_Mode
        TEXTMSG: ModuleConfig.SerialConfig.Serial_Mode
        NMEA: ModuleConfig.SerialConfig.Serial_Mode
        CALTOPO: ModuleConfig.SerialConfig.Serial_Mode
        WS85: ModuleConfig.SerialConfig.Serial_Mode
        VE_DIRECT: ModuleConfig.SerialConfig.Serial_Mode
        MS_CONFIG: ModuleConfig.SerialConfig.Serial_Mode
        LOG: ModuleConfig.SerialConfig.Serial_Mode
        LOGTEXT: ModuleConfig.SerialConfig.Serial_Mode
        ENABLED_FIELD_NUMBER: _ClassVar[int]
        ECHO_FIELD_NUMBER: _ClassVar[int]
        RXD_FIELD_NUMBER: _ClassVar[int]
        TXD_FIELD_NUMBER: _ClassVar[int]
        BAUD_FIELD_NUMBER: _ClassVar[int]
        TIMEOUT_FIELD_NUMBER: _ClassVar[int]
        MODE_FIELD_NUMBER: _ClassVar[int]
        OVERRIDE_CONSOLE_SERIAL_PORT_FIELD_NUMBER: _ClassVar[int]
        enabled: bool
        echo: bool
        rxd: int
        txd: int
        baud: ModuleConfig.SerialConfig.Serial_Baud
        timeout: int
        mode: ModuleConfig.SerialConfig.Serial_Mode
        override_console_serial_port: bool
        def __init__(self, enabled: bool = ..., echo: bool = ..., rxd: _Optional[int] = ..., txd: _Optional[int] = ..., baud: _Optional[_Union[ModuleConfig.SerialConfig.Serial_Baud, str]] = ..., timeout: _Optional[int] = ..., mode: _Optional[_Union[ModuleConfig.SerialConfig.Serial_Mode, str]] = ..., override_console_serial_port: bool = ...) -> None: ...
    class ExternalNotificationConfig(_message.Message):
        __slots__ = ("enabled", "output_ms", "output", "output_vibra", "output_buzzer", "active", "alert_message", "alert_message_vibra", "alert_message_buzzer", "alert_bell", "alert_bell_vibra", "alert_bell_buzzer", "use_pwm", "nag_timeout", "use_i2s_as_buzzer")
        ENABLED_FIELD_NUMBER: _ClassVar[int]
        OUTPUT_MS_FIELD_NUMBER: _ClassVar[int]
        OUTPUT_FIELD_NUMBER: _ClassVar[int]
        OUTPUT_VIBRA_FIELD_NUMBER: _ClassVar[int]
        OUTPUT_BUZZER_FIELD_NUMBER: _ClassVar[int]
        ACTIVE_FIELD_NUMBER: _ClassVar[int]
        ALERT_MESSAGE_FIELD_NUMBER: _ClassVar[int]
        ALERT_MESSAGE_VIBRA_FIELD_NUMBER: _ClassVar[int]
        ALERT_MESSAGE_BUZZER_FIELD_NUMBER: _ClassVar[int]
        ALERT_BELL_FIELD_NUMBER: _ClassVar[int]
        ALERT_BELL_VIBRA_FIELD_NUMBER: _ClassVar[int]
        ALERT_BELL_BUZZER_FIELD_NUMBER: _ClassVar[int]
        USE_PWM_FIELD_NUMBER: _ClassVar[int]
        NAG_TIMEOUT_FIELD_NUMBER: _ClassVar[int]
        USE_I2S_AS_BUZZER_FIELD_NUMBER: _ClassVar[int]
        enabled: bool
        output_ms: int
        output: int
        output_vibra: int
        output_buzzer: int
        active: bool
        alert_message: bool
        alert_message_vibra: bool
        alert_message_buzzer: bool
        alert_bell: bool
        alert_bell_vibra: bool
        alert_bell_buzzer: bool
        use_pwm: bool
        nag_timeout: int
        use_i2s_as_buzzer: bool
        def __init__(self, enabled: bool = ..., output_ms: _Optional[int] = ..., output: _Optional[int] = ..., output_vibra: _Optional[int] = ..., output_buzzer: _Optional[int] = ..., active: bool = ..., alert_message: bool = ..., alert_message_vibra: bool = ..., alert_message_buzzer: bool = ..., alert_bell: bool = ..., alert_bell_vibra: bool = ..., alert_bell_buzzer: bool = ..., use_pwm: bool = ..., nag_timeout: _Optional[int] = ..., use_i2s_as_buzzer: bool = ...) -> None: ...
    class StoreForwardConfig(_message.Message):
        __slots__ = ("enabled", "heartbeat", "records", "history_return_max", "history_return_window", "is_server")
        ENABLED_FIELD_NUMBER: _ClassVar[int]
        HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
        RECORDS_FIELD_NUMBER: _ClassVar[int]
        HISTORY_RETURN_MAX_FIELD_NUMBER: _ClassVar[int]
        HISTORY_RETURN_WINDOW_FIELD_NUMBER: _ClassVar[int]
        IS_SERVER_FIELD_NUMBER: _ClassVar[int]
        enabled: bool
        heartbeat: bool
        records: int
        history_return_max: int
        history_return_window: int
        is_server: bool
        def __init__(self, enabled: bool = ..., heartbeat: bool = ..., records: _Optional[int] = ..., history_return_max: _Optional[int] = ..., history_return_window: _Optional[int] = ..., is_server: bool = ...) -> None: ...
    class RangeTestConfig(_message.Message):
        __slots__ = ("enabled", "sender", "save", "clear_on_reboot")
        ENABLED_FIELD_NUMBER: _ClassVar[int]
        SENDER_FIELD_NUMBER: _ClassVar[int]
        SAVE_FIELD_NUMBER: _ClassVar[int]
        CLEAR_ON_REBOOT_FIELD_NUMBER: _ClassVar[int]
        enabled: bool
        sender: int
        save: bool
        clear_on_reboot: bool
        def __init__(self, enabled: bool = ..., sender: _Optional[int] = ..., save: bool = ..., clear_on_reboot: bool = ...) -> None: ...
    class TelemetryConfig(_message.Message):
        __slots__ = ("device_update_interval", "environment_update_interval", "environment_measurement_enabled", "environment_screen_enabled", "environment_display_fahrenheit", "air_quality_enabled", "air_quality_interval", "power_measurement_enabled", "power_update_interval", "power_screen_enabled", "health_measurement_enabled", "health_update_interval", "health_screen_enabled", "device_telemetry_enabled", "air_quality_screen_enabled")
        DEVICE_UPDATE_INTERVAL_FIELD_NUMBER: _ClassVar[int]
        ENVIRONMENT_UPDATE_INTERVAL_FIELD_NUMBER: _ClassVar[int]
        ENVIRONMENT_MEASUREMENT_ENABLED_FIELD_NUMBER: _ClassVar[int]
        ENVIRONMENT_SCREEN_ENABLED_FIELD_NUMBER: _ClassVar[int]
        ENVIRONMENT_DISPLAY_FAHRENHEIT_FIELD_NUMBER: _ClassVar[int]
        AIR_QUALITY_ENABLED_FIELD_NUMBER: _ClassVar[int]
        AIR_QUALITY_INTERVAL_FIELD_NUMBER: _ClassVar[int]
        POWER_MEASUREMENT_ENABLED_FIELD_NUMBER: _ClassVar[int]
        POWER_UPDATE_INTERVAL_FIELD_NUMBER: _ClassVar[int]
        POWER_SCREEN_ENABLED_FIELD_NUMBER: _ClassVar[int]
        HEALTH_MEASUREMENT_ENABLED_FIELD_NUMBER: _ClassVar[int]
        HEALTH_UPDATE_INTERVAL_FIELD_NUMBER: _ClassVar[int]
        HEALTH_SCREEN_ENABLED_FIELD_NUMBER: _ClassVar[int]
        DEVICE_TELEMETRY_ENABLED_FIELD_NUMBER: _ClassVar[int]
        AIR_QUALITY_SCREEN_ENABLED_FIELD_NUMBER: _ClassVar[int]
        device_update_interval: int
        environment_update_interval: int
        environment_measurement_enabled: bool
        environment_screen_enabled: bool
        environment_display_fahrenheit: bool
        air_quality_enabled: bool
        air_quality_interval: int
        power_measurement_enabled: bool
        power_update_interval: int
        power_screen_enabled: bool
        health_measurement_enabled: bool
        health_update_interval: int
        health_screen_enabled: bool
        device_telemetry_enabled: bool
        air_quality_screen_enabled: bool
        def __init__(self, device_update_interval: _Optional[int] = ..., environment_update_interval: _Optional[int] = ..., environment_measurement_enabled: bool = ..., environment_screen_enabled: bool = ..., environment_display_fahrenheit: bool = ..., air_quality_enabled: bool = ..., air_quality_interval: _Optional[int] = ..., power_measurement_enabled: bool = ..., power_update_interval: _Optional[int] = ..., power_screen_enabled: bool = ..., health_measurement_enabled: bool = ..., health_update_interval: _Optional[int] = ..., health_screen_enabled: bool = ..., device_telemetry_enabled: bool = ..., air_quality_screen_enabled: bool = ...) -> None: ...
    class CannedMessageConfig(_message.Message):
        __slots__ = ("rotary1_enabled", "inputbroker_pin_a", "inputbroker_pin_b", "inputbroker_pin_press", "inputbroker_event_cw", "inputbroker_event_ccw", "inputbroker_event_press", "updown1_enabled", "enabled", "allow_input_source", "send_bell")
        class InputEventChar(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            NONE: _ClassVar[ModuleConfig.CannedMessageConfig.InputEventChar]
            UP: _ClassVar[ModuleConfig.CannedMessageConfig.InputEventChar]
            DOWN: _ClassVar[ModuleConfig.CannedMessageConfig.InputEventChar]
            LEFT: _ClassVar[ModuleConfig.CannedMessageConfig.InputEventChar]
            RIGHT: _ClassVar[ModuleConfig.CannedMessageConfig.InputEventChar]
            SELECT: _ClassVar[ModuleConfig.CannedMessageConfig.InputEventChar]
            BACK: _ClassVar[ModuleConfig.CannedMessageConfig.InputEventChar]
            CANCEL: _ClassVar[ModuleConfig.CannedMessageConfig.InputEventChar]
        NONE: ModuleConfig.CannedMessageConfig.InputEventChar
        UP: ModuleConfig.CannedMessageConfig.InputEventChar
        DOWN: ModuleConfig.CannedMessageConfig.InputEventChar
        LEFT: ModuleConfig.CannedMessageConfig.InputEventChar
        RIGHT: ModuleConfig.CannedMessageConfig.InputEventChar
        SELECT: ModuleConfig.CannedMessageConfig.InputEventChar
        BACK: ModuleConfig.CannedMessageConfig.InputEventChar
        CANCEL: ModuleConfig.CannedMessageConfig.InputEventChar
        ROTARY1_ENABLED_FIELD_NUMBER: _ClassVar[int]
        INPUTBROKER_PIN_A_FIELD_NUMBER: _ClassVar[int]
        INPUTBROKER_PIN_B_FIELD_NUMBER: _ClassVar[int]
        INPUTBROKER_PIN_PRESS_FIELD_NUMBER: _ClassVar[int]
        INPUTBROKER_EVENT_CW_FIELD_NUMBER: _ClassVar[int]
        INPUTBROKER_EVENT_CCW_FIELD_NUMBER: _ClassVar[int]
        INPUTBROKER_EVENT_PRESS_FIELD_NUMBER: _ClassVar[int]
        UPDOWN1_ENABLED_FIELD_NUMBER: _ClassVar[int]
        ENABLED_FIELD_NUMBER: _ClassVar[int]
        ALLOW_INPUT_SOURCE_FIELD_NUMBER: _ClassVar[int]
        SEND_BELL_FIELD_NUMBER: _ClassVar[int]
        rotary1_enabled: bool
        inputbroker_pin_a: int
        inputbroker_pin_b: int
        inputbroker_pin_press: int
        inputbroker_event_cw: ModuleConfig.CannedMessageConfig.InputEventChar
        inputbroker_event_ccw: ModuleConfig.CannedMessageConfig.InputEventChar
        inputbroker_event_press: ModuleConfig.CannedMessageConfig.InputEventChar
        updown1_enabled: bool
        enabled: bool
        allow_input_source: str
        send_bell: bool
        def __init__(self, rotary1_enabled: bool = ..., inputbroker_pin_a: _Optional[int] = ..., inputbroker_pin_b: _Optional[int] = ..., inputbroker_pin_press: _Optional[int] = ..., inputbroker_event_cw: _Optional[_Union[ModuleConfig.CannedMessageConfig.InputEventChar, str]] = ..., inputbroker_event_ccw: _Optional[_Union[ModuleConfig.CannedMessageConfig.InputEventChar, str]] = ..., inputbroker_event_press: _Optional[_Union[ModuleConfig.CannedMessageConfig.InputEventChar, str]] = ..., updown1_enabled: bool = ..., enabled: bool = ..., allow_input_source: _Optional[str] = ..., send_bell: bool = ...) -> None: ...
    class AmbientLightingConfig(_message.Message):
        __slots__ = ("led_state", "current", "red", "green", "blue")
        LED_STATE_FIELD_NUMBER: _ClassVar[int]
        CURRENT_FIELD_NUMBER: _ClassVar[int]
        RED_FIELD_NUMBER: _ClassVar[int]
        GREEN_FIELD_NUMBER: _ClassVar[int]
        BLUE_FIELD_NUMBER: _ClassVar[int]
        led_state: bool
        current: int
        red: int
        green: int
        blue: int
        def __init__(self, led_state: bool = ..., current: _Optional[int] = ..., red: _Optional[int] = ..., green: _Optional[int] = ..., blue: _Optional[int] = ...) -> None: ...
    class StatusMessageConfig(_message.Message):
        __slots__ = ("node_status",)
        NODE_STATUS_FIELD_NUMBER: _ClassVar[int]
        node_status: str
        def __init__(self, node_status: _Optional[str] = ...) -> None: ...
    class TAKConfig(_message.Message):
        __slots__ = ("team", "role")
        TEAM_FIELD_NUMBER: _ClassVar[int]
        ROLE_FIELD_NUMBER: _ClassVar[int]
        team: _atak_pb2.Team
        role: _atak_pb2.MemberRole
        def __init__(self, team: _Optional[_Union[_atak_pb2.Team, str]] = ..., role: _Optional[_Union[_atak_pb2.MemberRole, str]] = ...) -> None: ...
    MQTT_FIELD_NUMBER: _ClassVar[int]
    SERIAL_FIELD_NUMBER: _ClassVar[int]
    EXTERNAL_NOTIFICATION_FIELD_NUMBER: _ClassVar[int]
    STORE_FORWARD_FIELD_NUMBER: _ClassVar[int]
    RANGE_TEST_FIELD_NUMBER: _ClassVar[int]
    TELEMETRY_FIELD_NUMBER: _ClassVar[int]
    CANNED_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    AUDIO_FIELD_NUMBER: _ClassVar[int]
    REMOTE_HARDWARE_FIELD_NUMBER: _ClassVar[int]
    NEIGHBOR_INFO_FIELD_NUMBER: _ClassVar[int]
    AMBIENT_LIGHTING_FIELD_NUMBER: _ClassVar[int]
    DETECTION_SENSOR_FIELD_NUMBER: _ClassVar[int]
    PAXCOUNTER_FIELD_NUMBER: _ClassVar[int]
    STATUSMESSAGE_FIELD_NUMBER: _ClassVar[int]
    TRAFFIC_MANAGEMENT_FIELD_NUMBER: _ClassVar[int]
    TAK_FIELD_NUMBER: _ClassVar[int]
    mqtt: ModuleConfig.MQTTConfig
    serial: ModuleConfig.SerialConfig
    external_notification: ModuleConfig.ExternalNotificationConfig
    store_forward: ModuleConfig.StoreForwardConfig
    range_test: ModuleConfig.RangeTestConfig
    telemetry: ModuleConfig.TelemetryConfig
    canned_message: ModuleConfig.CannedMessageConfig
    audio: ModuleConfig.AudioConfig
    remote_hardware: ModuleConfig.RemoteHardwareConfig
    neighbor_info: ModuleConfig.NeighborInfoConfig
    ambient_lighting: ModuleConfig.AmbientLightingConfig
    detection_sensor: ModuleConfig.DetectionSensorConfig
    paxcounter: ModuleConfig.PaxcounterConfig
    statusmessage: ModuleConfig.StatusMessageConfig
    traffic_management: ModuleConfig.TrafficManagementConfig
    tak: ModuleConfig.TAKConfig
    def __init__(self, mqtt: _Optional[_Union[ModuleConfig.MQTTConfig, _Mapping]] = ..., serial: _Optional[_Union[ModuleConfig.SerialConfig, _Mapping]] = ..., external_notification: _Optional[_Union[ModuleConfig.ExternalNotificationConfig, _Mapping]] = ..., store_forward: _Optional[_Union[ModuleConfig.StoreForwardConfig, _Mapping]] = ..., range_test: _Optional[_Union[ModuleConfig.RangeTestConfig, _Mapping]] = ..., telemetry: _Optional[_Union[ModuleConfig.TelemetryConfig, _Mapping]] = ..., canned_message: _Optional[_Union[ModuleConfig.CannedMessageConfig, _Mapping]] = ..., audio: _Optional[_Union[ModuleConfig.AudioConfig, _Mapping]] = ..., remote_hardware: _Optional[_Union[ModuleConfig.RemoteHardwareConfig, _Mapping]] = ..., neighbor_info: _Optional[_Union[ModuleConfig.NeighborInfoConfig, _Mapping]] = ..., ambient_lighting: _Optional[_Union[ModuleConfig.AmbientLightingConfig, _Mapping]] = ..., detection_sensor: _Optional[_Union[ModuleConfig.DetectionSensorConfig, _Mapping]] = ..., paxcounter: _Optional[_Union[ModuleConfig.PaxcounterConfig, _Mapping]] = ..., statusmessage: _Optional[_Union[ModuleConfig.StatusMessageConfig, _Mapping]] = ..., traffic_management: _Optional[_Union[ModuleConfig.TrafficManagementConfig, _Mapping]] = ..., tak: _Optional[_Union[ModuleConfig.TAKConfig, _Mapping]] = ...) -> None: ...

class RemoteHardwarePin(_message.Message):
    __slots__ = ("gpio_pin", "name", "type")
    GPIO_PIN_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    gpio_pin: int
    name: str
    type: RemoteHardwarePinType
    def __init__(self, gpio_pin: _Optional[int] = ..., name: _Optional[str] = ..., type: _Optional[_Union[RemoteHardwarePinType, str]] = ...) -> None: ...
