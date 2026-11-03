from mesh_things.protocols.v2_8 import channel_pb2 as _channel_pb2
from mesh_things.protocols.v2_8 import config_pb2 as _config_pb2
from mesh_things.protocols.v2_8 import connection_status_pb2 as _connection_status_pb2
from mesh_things.protocols.v2_8 import device_ui_pb2 as _device_ui_pb2
from mesh_things.protocols.v2_8 import mesh_pb2 as _mesh_pb2
from mesh_things.protocols.v2_8 import module_config_pb2 as _module_config_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class OTAMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    NO_REBOOT_OTA: _ClassVar[OTAMode]
    OTA_BLE: _ClassVar[OTAMode]
    OTA_WIFI: _ClassVar[OTAMode]
NO_REBOOT_OTA: OTAMode
OTA_BLE: OTAMode
OTA_WIFI: OTAMode

class AdminMessage(_message.Message):
    __slots__ = ("session_passkey", "get_channel_request", "get_channel_response", "get_owner_request", "get_owner_response", "get_config_request", "get_config_response", "get_module_config_request", "get_module_config_response", "get_canned_message_module_messages_request", "get_canned_message_module_messages_response", "get_device_metadata_request", "get_device_metadata_response", "get_ringtone_request", "get_ringtone_response", "get_device_connection_status_request", "get_device_connection_status_response", "set_ham_mode", "get_node_remote_hardware_pins_request", "get_node_remote_hardware_pins_response", "enter_dfu_mode_request", "delete_file_request", "set_scale", "backup_preferences", "restore_preferences", "remove_backup_preferences", "send_input_event", "set_owner", "set_channel", "set_config", "set_module_config", "set_canned_message_module_messages", "set_ringtone_message", "remove_by_nodenum", "set_favorite_node", "remove_favorite_node", "set_fixed_position", "remove_fixed_position", "set_time_only", "get_ui_config_request", "get_ui_config_response", "store_ui_config", "set_ignored_node", "remove_ignored_node", "toggle_muted_node", "get_display_frame_request", "set_display_mirror", "begin_edit_settings", "commit_edit_settings", "add_contact", "key_verification", "factory_reset_device", "reboot_ota_seconds", "exit_simulator", "reboot_seconds", "shutdown_seconds", "factory_reset_config", "nodedb_reset", "ota_request", "sensor_config", "lockdown_auth")
    class ConfigType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        DEVICE_CONFIG: _ClassVar[AdminMessage.ConfigType]
        POSITION_CONFIG: _ClassVar[AdminMessage.ConfigType]
        POWER_CONFIG: _ClassVar[AdminMessage.ConfigType]
        NETWORK_CONFIG: _ClassVar[AdminMessage.ConfigType]
        DISPLAY_CONFIG: _ClassVar[AdminMessage.ConfigType]
        LORA_CONFIG: _ClassVar[AdminMessage.ConfigType]
        BLUETOOTH_CONFIG: _ClassVar[AdminMessage.ConfigType]
        SECURITY_CONFIG: _ClassVar[AdminMessage.ConfigType]
        SESSIONKEY_CONFIG: _ClassVar[AdminMessage.ConfigType]
        DEVICEUI_CONFIG: _ClassVar[AdminMessage.ConfigType]
    DEVICE_CONFIG: AdminMessage.ConfigType
    POSITION_CONFIG: AdminMessage.ConfigType
    POWER_CONFIG: AdminMessage.ConfigType
    NETWORK_CONFIG: AdminMessage.ConfigType
    DISPLAY_CONFIG: AdminMessage.ConfigType
    LORA_CONFIG: AdminMessage.ConfigType
    BLUETOOTH_CONFIG: AdminMessage.ConfigType
    SECURITY_CONFIG: AdminMessage.ConfigType
    SESSIONKEY_CONFIG: AdminMessage.ConfigType
    DEVICEUI_CONFIG: AdminMessage.ConfigType
    class ModuleConfigType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        MQTT_CONFIG: _ClassVar[AdminMessage.ModuleConfigType]
        SERIAL_CONFIG: _ClassVar[AdminMessage.ModuleConfigType]
        EXTNOTIF_CONFIG: _ClassVar[AdminMessage.ModuleConfigType]
        STOREFORWARD_CONFIG: _ClassVar[AdminMessage.ModuleConfigType]
        RANGETEST_CONFIG: _ClassVar[AdminMessage.ModuleConfigType]
        TELEMETRY_CONFIG: _ClassVar[AdminMessage.ModuleConfigType]
        CANNEDMSG_CONFIG: _ClassVar[AdminMessage.ModuleConfigType]
        AUDIO_CONFIG: _ClassVar[AdminMessage.ModuleConfigType]
        REMOTEHARDWARE_CONFIG: _ClassVar[AdminMessage.ModuleConfigType]
        NEIGHBORINFO_CONFIG: _ClassVar[AdminMessage.ModuleConfigType]
        AMBIENTLIGHTING_CONFIG: _ClassVar[AdminMessage.ModuleConfigType]
        DETECTIONSENSOR_CONFIG: _ClassVar[AdminMessage.ModuleConfigType]
        PAXCOUNTER_CONFIG: _ClassVar[AdminMessage.ModuleConfigType]
        STATUSMESSAGE_CONFIG: _ClassVar[AdminMessage.ModuleConfigType]
        TRAFFICMANAGEMENT_CONFIG: _ClassVar[AdminMessage.ModuleConfigType]
        TAK_CONFIG: _ClassVar[AdminMessage.ModuleConfigType]
        MESHBEACON_CONFIG: _ClassVar[AdminMessage.ModuleConfigType]
    MQTT_CONFIG: AdminMessage.ModuleConfigType
    SERIAL_CONFIG: AdminMessage.ModuleConfigType
    EXTNOTIF_CONFIG: AdminMessage.ModuleConfigType
    STOREFORWARD_CONFIG: AdminMessage.ModuleConfigType
    RANGETEST_CONFIG: AdminMessage.ModuleConfigType
    TELEMETRY_CONFIG: AdminMessage.ModuleConfigType
    CANNEDMSG_CONFIG: AdminMessage.ModuleConfigType
    AUDIO_CONFIG: AdminMessage.ModuleConfigType
    REMOTEHARDWARE_CONFIG: AdminMessage.ModuleConfigType
    NEIGHBORINFO_CONFIG: AdminMessage.ModuleConfigType
    AMBIENTLIGHTING_CONFIG: AdminMessage.ModuleConfigType
    DETECTIONSENSOR_CONFIG: AdminMessage.ModuleConfigType
    PAXCOUNTER_CONFIG: AdminMessage.ModuleConfigType
    STATUSMESSAGE_CONFIG: AdminMessage.ModuleConfigType
    TRAFFICMANAGEMENT_CONFIG: AdminMessage.ModuleConfigType
    TAK_CONFIG: AdminMessage.ModuleConfigType
    MESHBEACON_CONFIG: AdminMessage.ModuleConfigType
    class BackupLocation(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        FLASH: _ClassVar[AdminMessage.BackupLocation]
        SD: _ClassVar[AdminMessage.BackupLocation]
    FLASH: AdminMessage.BackupLocation
    SD: AdminMessage.BackupLocation
    class InputEvent(_message.Message):
        __slots__ = ("event_code", "kb_char", "touch_x", "touch_y")
        EVENT_CODE_FIELD_NUMBER: _ClassVar[int]
        KB_CHAR_FIELD_NUMBER: _ClassVar[int]
        TOUCH_X_FIELD_NUMBER: _ClassVar[int]
        TOUCH_Y_FIELD_NUMBER: _ClassVar[int]
        event_code: int
        kb_char: int
        touch_x: int
        touch_y: int
        def __init__(self, event_code: _Optional[int] = ..., kb_char: _Optional[int] = ..., touch_x: _Optional[int] = ..., touch_y: _Optional[int] = ...) -> None: ...
    class OTAEvent(_message.Message):
        __slots__ = ("reboot_ota_mode", "ota_hash")
        REBOOT_OTA_MODE_FIELD_NUMBER: _ClassVar[int]
        OTA_HASH_FIELD_NUMBER: _ClassVar[int]
        reboot_ota_mode: OTAMode
        ota_hash: bytes
        def __init__(self, reboot_ota_mode: _Optional[_Union[OTAMode, str]] = ..., ota_hash: _Optional[bytes] = ...) -> None: ...
    SESSION_PASSKEY_FIELD_NUMBER: _ClassVar[int]
    GET_CHANNEL_REQUEST_FIELD_NUMBER: _ClassVar[int]
    GET_CHANNEL_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    GET_OWNER_REQUEST_FIELD_NUMBER: _ClassVar[int]
    GET_OWNER_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    GET_CONFIG_REQUEST_FIELD_NUMBER: _ClassVar[int]
    GET_CONFIG_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    GET_MODULE_CONFIG_REQUEST_FIELD_NUMBER: _ClassVar[int]
    GET_MODULE_CONFIG_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    GET_CANNED_MESSAGE_MODULE_MESSAGES_REQUEST_FIELD_NUMBER: _ClassVar[int]
    GET_CANNED_MESSAGE_MODULE_MESSAGES_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    GET_DEVICE_METADATA_REQUEST_FIELD_NUMBER: _ClassVar[int]
    GET_DEVICE_METADATA_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    GET_RINGTONE_REQUEST_FIELD_NUMBER: _ClassVar[int]
    GET_RINGTONE_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    GET_DEVICE_CONNECTION_STATUS_REQUEST_FIELD_NUMBER: _ClassVar[int]
    GET_DEVICE_CONNECTION_STATUS_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    SET_HAM_MODE_FIELD_NUMBER: _ClassVar[int]
    GET_NODE_REMOTE_HARDWARE_PINS_REQUEST_FIELD_NUMBER: _ClassVar[int]
    GET_NODE_REMOTE_HARDWARE_PINS_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    ENTER_DFU_MODE_REQUEST_FIELD_NUMBER: _ClassVar[int]
    DELETE_FILE_REQUEST_FIELD_NUMBER: _ClassVar[int]
    SET_SCALE_FIELD_NUMBER: _ClassVar[int]
    BACKUP_PREFERENCES_FIELD_NUMBER: _ClassVar[int]
    RESTORE_PREFERENCES_FIELD_NUMBER: _ClassVar[int]
    REMOVE_BACKUP_PREFERENCES_FIELD_NUMBER: _ClassVar[int]
    SEND_INPUT_EVENT_FIELD_NUMBER: _ClassVar[int]
    SET_OWNER_FIELD_NUMBER: _ClassVar[int]
    SET_CHANNEL_FIELD_NUMBER: _ClassVar[int]
    SET_CONFIG_FIELD_NUMBER: _ClassVar[int]
    SET_MODULE_CONFIG_FIELD_NUMBER: _ClassVar[int]
    SET_CANNED_MESSAGE_MODULE_MESSAGES_FIELD_NUMBER: _ClassVar[int]
    SET_RINGTONE_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    REMOVE_BY_NODENUM_FIELD_NUMBER: _ClassVar[int]
    SET_FAVORITE_NODE_FIELD_NUMBER: _ClassVar[int]
    REMOVE_FAVORITE_NODE_FIELD_NUMBER: _ClassVar[int]
    SET_FIXED_POSITION_FIELD_NUMBER: _ClassVar[int]
    REMOVE_FIXED_POSITION_FIELD_NUMBER: _ClassVar[int]
    SET_TIME_ONLY_FIELD_NUMBER: _ClassVar[int]
    GET_UI_CONFIG_REQUEST_FIELD_NUMBER: _ClassVar[int]
    GET_UI_CONFIG_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    STORE_UI_CONFIG_FIELD_NUMBER: _ClassVar[int]
    SET_IGNORED_NODE_FIELD_NUMBER: _ClassVar[int]
    REMOVE_IGNORED_NODE_FIELD_NUMBER: _ClassVar[int]
    TOGGLE_MUTED_NODE_FIELD_NUMBER: _ClassVar[int]
    GET_DISPLAY_FRAME_REQUEST_FIELD_NUMBER: _ClassVar[int]
    SET_DISPLAY_MIRROR_FIELD_NUMBER: _ClassVar[int]
    BEGIN_EDIT_SETTINGS_FIELD_NUMBER: _ClassVar[int]
    COMMIT_EDIT_SETTINGS_FIELD_NUMBER: _ClassVar[int]
    ADD_CONTACT_FIELD_NUMBER: _ClassVar[int]
    KEY_VERIFICATION_FIELD_NUMBER: _ClassVar[int]
    FACTORY_RESET_DEVICE_FIELD_NUMBER: _ClassVar[int]
    REBOOT_OTA_SECONDS_FIELD_NUMBER: _ClassVar[int]
    EXIT_SIMULATOR_FIELD_NUMBER: _ClassVar[int]
    REBOOT_SECONDS_FIELD_NUMBER: _ClassVar[int]
    SHUTDOWN_SECONDS_FIELD_NUMBER: _ClassVar[int]
    FACTORY_RESET_CONFIG_FIELD_NUMBER: _ClassVar[int]
    NODEDB_RESET_FIELD_NUMBER: _ClassVar[int]
    OTA_REQUEST_FIELD_NUMBER: _ClassVar[int]
    SENSOR_CONFIG_FIELD_NUMBER: _ClassVar[int]
    LOCKDOWN_AUTH_FIELD_NUMBER: _ClassVar[int]
    session_passkey: bytes
    get_channel_request: int
    get_channel_response: _channel_pb2.Channel
    get_owner_request: bool
    get_owner_response: _mesh_pb2.User
    get_config_request: AdminMessage.ConfigType
    get_config_response: _config_pb2.Config
    get_module_config_request: AdminMessage.ModuleConfigType
    get_module_config_response: _module_config_pb2.ModuleConfig
    get_canned_message_module_messages_request: bool
    get_canned_message_module_messages_response: str
    get_device_metadata_request: bool
    get_device_metadata_response: _mesh_pb2.DeviceMetadata
    get_ringtone_request: bool
    get_ringtone_response: str
    get_device_connection_status_request: bool
    get_device_connection_status_response: _connection_status_pb2.DeviceConnectionStatus
    set_ham_mode: HamParameters
    get_node_remote_hardware_pins_request: bool
    get_node_remote_hardware_pins_response: NodeRemoteHardwarePinsResponse
    enter_dfu_mode_request: bool
    delete_file_request: str
    set_scale: int
    backup_preferences: AdminMessage.BackupLocation
    restore_preferences: AdminMessage.BackupLocation
    remove_backup_preferences: AdminMessage.BackupLocation
    send_input_event: AdminMessage.InputEvent
    set_owner: _mesh_pb2.User
    set_channel: _channel_pb2.Channel
    set_config: _config_pb2.Config
    set_module_config: _module_config_pb2.ModuleConfig
    set_canned_message_module_messages: str
    set_ringtone_message: str
    remove_by_nodenum: int
    set_favorite_node: int
    remove_favorite_node: int
    set_fixed_position: _mesh_pb2.Position
    remove_fixed_position: bool
    set_time_only: int
    get_ui_config_request: bool
    get_ui_config_response: _device_ui_pb2.DeviceUIConfig
    store_ui_config: _device_ui_pb2.DeviceUIConfig
    set_ignored_node: int
    remove_ignored_node: int
    toggle_muted_node: int
    get_display_frame_request: bool
    set_display_mirror: bool
    begin_edit_settings: bool
    commit_edit_settings: bool
    add_contact: SharedContact
    key_verification: KeyVerificationAdmin
    factory_reset_device: int
    reboot_ota_seconds: int
    exit_simulator: bool
    reboot_seconds: int
    shutdown_seconds: int
    factory_reset_config: int
    nodedb_reset: bool
    ota_request: AdminMessage.OTAEvent
    sensor_config: SensorConfig
    lockdown_auth: LockdownAuth
    def __init__(self, session_passkey: _Optional[bytes] = ..., get_channel_request: _Optional[int] = ..., get_channel_response: _Optional[_Union[_channel_pb2.Channel, _Mapping]] = ..., get_owner_request: bool = ..., get_owner_response: _Optional[_Union[_mesh_pb2.User, _Mapping]] = ..., get_config_request: _Optional[_Union[AdminMessage.ConfigType, str]] = ..., get_config_response: _Optional[_Union[_config_pb2.Config, _Mapping]] = ..., get_module_config_request: _Optional[_Union[AdminMessage.ModuleConfigType, str]] = ..., get_module_config_response: _Optional[_Union[_module_config_pb2.ModuleConfig, _Mapping]] = ..., get_canned_message_module_messages_request: bool = ..., get_canned_message_module_messages_response: _Optional[str] = ..., get_device_metadata_request: bool = ..., get_device_metadata_response: _Optional[_Union[_mesh_pb2.DeviceMetadata, _Mapping]] = ..., get_ringtone_request: bool = ..., get_ringtone_response: _Optional[str] = ..., get_device_connection_status_request: bool = ..., get_device_connection_status_response: _Optional[_Union[_connection_status_pb2.DeviceConnectionStatus, _Mapping]] = ..., set_ham_mode: _Optional[_Union[HamParameters, _Mapping]] = ..., get_node_remote_hardware_pins_request: bool = ..., get_node_remote_hardware_pins_response: _Optional[_Union[NodeRemoteHardwarePinsResponse, _Mapping]] = ..., enter_dfu_mode_request: bool = ..., delete_file_request: _Optional[str] = ..., set_scale: _Optional[int] = ..., backup_preferences: _Optional[_Union[AdminMessage.BackupLocation, str]] = ..., restore_preferences: _Optional[_Union[AdminMessage.BackupLocation, str]] = ..., remove_backup_preferences: _Optional[_Union[AdminMessage.BackupLocation, str]] = ..., send_input_event: _Optional[_Union[AdminMessage.InputEvent, _Mapping]] = ..., set_owner: _Optional[_Union[_mesh_pb2.User, _Mapping]] = ..., set_channel: _Optional[_Union[_channel_pb2.Channel, _Mapping]] = ..., set_config: _Optional[_Union[_config_pb2.Config, _Mapping]] = ..., set_module_config: _Optional[_Union[_module_config_pb2.ModuleConfig, _Mapping]] = ..., set_canned_message_module_messages: _Optional[str] = ..., set_ringtone_message: _Optional[str] = ..., remove_by_nodenum: _Optional[int] = ..., set_favorite_node: _Optional[int] = ..., remove_favorite_node: _Optional[int] = ..., set_fixed_position: _Optional[_Union[_mesh_pb2.Position, _Mapping]] = ..., remove_fixed_position: bool = ..., set_time_only: _Optional[int] = ..., get_ui_config_request: bool = ..., get_ui_config_response: _Optional[_Union[_device_ui_pb2.DeviceUIConfig, _Mapping]] = ..., store_ui_config: _Optional[_Union[_device_ui_pb2.DeviceUIConfig, _Mapping]] = ..., set_ignored_node: _Optional[int] = ..., remove_ignored_node: _Optional[int] = ..., toggle_muted_node: _Optional[int] = ..., get_display_frame_request: bool = ..., set_display_mirror: bool = ..., begin_edit_settings: bool = ..., commit_edit_settings: bool = ..., add_contact: _Optional[_Union[SharedContact, _Mapping]] = ..., key_verification: _Optional[_Union[KeyVerificationAdmin, _Mapping]] = ..., factory_reset_device: _Optional[int] = ..., reboot_ota_seconds: _Optional[int] = ..., exit_simulator: bool = ..., reboot_seconds: _Optional[int] = ..., shutdown_seconds: _Optional[int] = ..., factory_reset_config: _Optional[int] = ..., nodedb_reset: bool = ..., ota_request: _Optional[_Union[AdminMessage.OTAEvent, _Mapping]] = ..., sensor_config: _Optional[_Union[SensorConfig, _Mapping]] = ..., lockdown_auth: _Optional[_Union[LockdownAuth, _Mapping]] = ...) -> None: ...

class LockdownAuth(_message.Message):
    __slots__ = ("passphrase", "boots_remaining", "valid_until_epoch", "lock_now", "max_session_seconds", "disable")
    PASSPHRASE_FIELD_NUMBER: _ClassVar[int]
    BOOTS_REMAINING_FIELD_NUMBER: _ClassVar[int]
    VALID_UNTIL_EPOCH_FIELD_NUMBER: _ClassVar[int]
    LOCK_NOW_FIELD_NUMBER: _ClassVar[int]
    MAX_SESSION_SECONDS_FIELD_NUMBER: _ClassVar[int]
    DISABLE_FIELD_NUMBER: _ClassVar[int]
    passphrase: bytes
    boots_remaining: int
    valid_until_epoch: int
    lock_now: bool
    max_session_seconds: int
    disable: bool
    def __init__(self, passphrase: _Optional[bytes] = ..., boots_remaining: _Optional[int] = ..., valid_until_epoch: _Optional[int] = ..., lock_now: bool = ..., max_session_seconds: _Optional[int] = ..., disable: bool = ...) -> None: ...

class HamParameters(_message.Message):
    __slots__ = ("call_sign", "tx_power", "frequency", "short_name", "long_name")
    CALL_SIGN_FIELD_NUMBER: _ClassVar[int]
    TX_POWER_FIELD_NUMBER: _ClassVar[int]
    FREQUENCY_FIELD_NUMBER: _ClassVar[int]
    SHORT_NAME_FIELD_NUMBER: _ClassVar[int]
    LONG_NAME_FIELD_NUMBER: _ClassVar[int]
    call_sign: str
    tx_power: int
    frequency: float
    short_name: str
    long_name: str
    def __init__(self, call_sign: _Optional[str] = ..., tx_power: _Optional[int] = ..., frequency: _Optional[float] = ..., short_name: _Optional[str] = ..., long_name: _Optional[str] = ...) -> None: ...

class NodeRemoteHardwarePinsResponse(_message.Message):
    __slots__ = ("node_remote_hardware_pins",)
    NODE_REMOTE_HARDWARE_PINS_FIELD_NUMBER: _ClassVar[int]
    node_remote_hardware_pins: _containers.RepeatedCompositeFieldContainer[_mesh_pb2.NodeRemoteHardwarePin]
    def __init__(self, node_remote_hardware_pins: _Optional[_Iterable[_Union[_mesh_pb2.NodeRemoteHardwarePin, _Mapping]]] = ...) -> None: ...

class SharedContact(_message.Message):
    __slots__ = ("node_num", "user", "should_ignore", "manually_verified")
    NODE_NUM_FIELD_NUMBER: _ClassVar[int]
    USER_FIELD_NUMBER: _ClassVar[int]
    SHOULD_IGNORE_FIELD_NUMBER: _ClassVar[int]
    MANUALLY_VERIFIED_FIELD_NUMBER: _ClassVar[int]
    node_num: int
    user: _mesh_pb2.User
    should_ignore: bool
    manually_verified: bool
    def __init__(self, node_num: _Optional[int] = ..., user: _Optional[_Union[_mesh_pb2.User, _Mapping]] = ..., should_ignore: bool = ..., manually_verified: bool = ...) -> None: ...

class KeyVerificationAdmin(_message.Message):
    __slots__ = ("message_type", "remote_nodenum", "nonce", "security_number")
    class MessageType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        INITIATE_VERIFICATION: _ClassVar[KeyVerificationAdmin.MessageType]
        PROVIDE_SECURITY_NUMBER: _ClassVar[KeyVerificationAdmin.MessageType]
        DO_VERIFY: _ClassVar[KeyVerificationAdmin.MessageType]
        DO_NOT_VERIFY: _ClassVar[KeyVerificationAdmin.MessageType]
    INITIATE_VERIFICATION: KeyVerificationAdmin.MessageType
    PROVIDE_SECURITY_NUMBER: KeyVerificationAdmin.MessageType
    DO_VERIFY: KeyVerificationAdmin.MessageType
    DO_NOT_VERIFY: KeyVerificationAdmin.MessageType
    MESSAGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    REMOTE_NODENUM_FIELD_NUMBER: _ClassVar[int]
    NONCE_FIELD_NUMBER: _ClassVar[int]
    SECURITY_NUMBER_FIELD_NUMBER: _ClassVar[int]
    message_type: KeyVerificationAdmin.MessageType
    remote_nodenum: int
    nonce: int
    security_number: int
    def __init__(self, message_type: _Optional[_Union[KeyVerificationAdmin.MessageType, str]] = ..., remote_nodenum: _Optional[int] = ..., nonce: _Optional[int] = ..., security_number: _Optional[int] = ...) -> None: ...

class SensorConfig(_message.Message):
    __slots__ = ("scd4x_config", "sen5x_config", "scd30_config", "shtxx_config", "ds248x_config", "sen6x_config", "as3935_config")
    SCD4X_CONFIG_FIELD_NUMBER: _ClassVar[int]
    SEN5X_CONFIG_FIELD_NUMBER: _ClassVar[int]
    SCD30_CONFIG_FIELD_NUMBER: _ClassVar[int]
    SHTXX_CONFIG_FIELD_NUMBER: _ClassVar[int]
    DS248X_CONFIG_FIELD_NUMBER: _ClassVar[int]
    SEN6X_CONFIG_FIELD_NUMBER: _ClassVar[int]
    AS3935_CONFIG_FIELD_NUMBER: _ClassVar[int]
    scd4x_config: SCD4X_config
    sen5x_config: SEN5X_config
    scd30_config: SCD30_config
    shtxx_config: SHTXX_config
    ds248x_config: DS248X_config
    sen6x_config: SEN6X_config
    as3935_config: AS3935_config
    def __init__(self, scd4x_config: _Optional[_Union[SCD4X_config, _Mapping]] = ..., sen5x_config: _Optional[_Union[SEN5X_config, _Mapping]] = ..., scd30_config: _Optional[_Union[SCD30_config, _Mapping]] = ..., shtxx_config: _Optional[_Union[SHTXX_config, _Mapping]] = ..., ds248x_config: _Optional[_Union[DS248X_config, _Mapping]] = ..., sen6x_config: _Optional[_Union[SEN6X_config, _Mapping]] = ..., as3935_config: _Optional[_Union[AS3935_config, _Mapping]] = ...) -> None: ...

class SCD4X_config(_message.Message):
    __slots__ = ("set_asc", "set_target_co2_conc", "set_temperature", "set_altitude", "set_ambient_pressure", "factory_reset", "set_power_mode")
    SET_ASC_FIELD_NUMBER: _ClassVar[int]
    SET_TARGET_CO2_CONC_FIELD_NUMBER: _ClassVar[int]
    SET_TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    SET_ALTITUDE_FIELD_NUMBER: _ClassVar[int]
    SET_AMBIENT_PRESSURE_FIELD_NUMBER: _ClassVar[int]
    FACTORY_RESET_FIELD_NUMBER: _ClassVar[int]
    SET_POWER_MODE_FIELD_NUMBER: _ClassVar[int]
    set_asc: bool
    set_target_co2_conc: int
    set_temperature: float
    set_altitude: int
    set_ambient_pressure: int
    factory_reset: bool
    set_power_mode: bool
    def __init__(self, set_asc: bool = ..., set_target_co2_conc: _Optional[int] = ..., set_temperature: _Optional[float] = ..., set_altitude: _Optional[int] = ..., set_ambient_pressure: _Optional[int] = ..., factory_reset: bool = ..., set_power_mode: bool = ...) -> None: ...

class SEN5X_config(_message.Message):
    __slots__ = ("set_temperature", "set_one_shot_mode", "start_fan_cleaning")
    SET_TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    SET_ONE_SHOT_MODE_FIELD_NUMBER: _ClassVar[int]
    START_FAN_CLEANING_FIELD_NUMBER: _ClassVar[int]
    set_temperature: float
    set_one_shot_mode: bool
    start_fan_cleaning: bool
    def __init__(self, set_temperature: _Optional[float] = ..., set_one_shot_mode: bool = ..., start_fan_cleaning: bool = ...) -> None: ...

class SEN6X_config(_message.Message):
    __slots__ = ("set_temperature", "set_one_shot_mode", "start_fan_cleaning", "set_asc", "set_target_co2_conc", "set_altitude", "set_ambient_pressure", "factory_reset")
    SET_TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    SET_ONE_SHOT_MODE_FIELD_NUMBER: _ClassVar[int]
    START_FAN_CLEANING_FIELD_NUMBER: _ClassVar[int]
    SET_ASC_FIELD_NUMBER: _ClassVar[int]
    SET_TARGET_CO2_CONC_FIELD_NUMBER: _ClassVar[int]
    SET_ALTITUDE_FIELD_NUMBER: _ClassVar[int]
    SET_AMBIENT_PRESSURE_FIELD_NUMBER: _ClassVar[int]
    FACTORY_RESET_FIELD_NUMBER: _ClassVar[int]
    set_temperature: float
    set_one_shot_mode: bool
    start_fan_cleaning: bool
    set_asc: bool
    set_target_co2_conc: int
    set_altitude: int
    set_ambient_pressure: int
    factory_reset: bool
    def __init__(self, set_temperature: _Optional[float] = ..., set_one_shot_mode: bool = ..., start_fan_cleaning: bool = ..., set_asc: bool = ..., set_target_co2_conc: _Optional[int] = ..., set_altitude: _Optional[int] = ..., set_ambient_pressure: _Optional[int] = ..., factory_reset: bool = ...) -> None: ...

class SCD30_config(_message.Message):
    __slots__ = ("set_asc", "set_target_co2_conc", "set_temperature", "set_altitude", "set_measurement_interval", "soft_reset")
    SET_ASC_FIELD_NUMBER: _ClassVar[int]
    SET_TARGET_CO2_CONC_FIELD_NUMBER: _ClassVar[int]
    SET_TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    SET_ALTITUDE_FIELD_NUMBER: _ClassVar[int]
    SET_MEASUREMENT_INTERVAL_FIELD_NUMBER: _ClassVar[int]
    SOFT_RESET_FIELD_NUMBER: _ClassVar[int]
    set_asc: bool
    set_target_co2_conc: int
    set_temperature: float
    set_altitude: int
    set_measurement_interval: int
    soft_reset: bool
    def __init__(self, set_asc: bool = ..., set_target_co2_conc: _Optional[int] = ..., set_temperature: _Optional[float] = ..., set_altitude: _Optional[int] = ..., set_measurement_interval: _Optional[int] = ..., soft_reset: bool = ...) -> None: ...

class SHTXX_config(_message.Message):
    __slots__ = ("set_accuracy",)
    SET_ACCURACY_FIELD_NUMBER: _ClassVar[int]
    set_accuracy: int
    def __init__(self, set_accuracy: _Optional[int] = ...) -> None: ...

class DS248X_config(_message.Message):
    __slots__ = ("main_temperature_channel",)
    MAIN_TEMPERATURE_CHANNEL_FIELD_NUMBER: _ClassVar[int]
    main_temperature_channel: int
    def __init__(self, main_temperature_channel: _Optional[int] = ...) -> None: ...

class AS3935_config(_message.Message):
    __slots__ = ("set_tuning_cap_pf",)
    SET_TUNING_CAP_PF_FIELD_NUMBER: _ClassVar[int]
    set_tuning_cap_pf: int
    def __init__(self, set_tuning_cap_pf: _Optional[int] = ...) -> None: ...
