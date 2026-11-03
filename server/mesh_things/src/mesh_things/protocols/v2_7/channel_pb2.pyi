from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ChannelSettings(_message.Message):
    __slots__ = ("channel_num", "psk", "name", "id", "uplink_enabled", "downlink_enabled", "module_settings")
    CHANNEL_NUM_FIELD_NUMBER: _ClassVar[int]
    PSK_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    UPLINK_ENABLED_FIELD_NUMBER: _ClassVar[int]
    DOWNLINK_ENABLED_FIELD_NUMBER: _ClassVar[int]
    MODULE_SETTINGS_FIELD_NUMBER: _ClassVar[int]
    channel_num: int
    psk: bytes
    name: str
    id: int
    uplink_enabled: bool
    downlink_enabled: bool
    module_settings: ModuleSettings
    def __init__(self, channel_num: _Optional[int] = ..., psk: _Optional[bytes] = ..., name: _Optional[str] = ..., id: _Optional[int] = ..., uplink_enabled: bool = ..., downlink_enabled: bool = ..., module_settings: _Optional[_Union[ModuleSettings, _Mapping]] = ...) -> None: ...

class ModuleSettings(_message.Message):
    __slots__ = ("position_precision", "is_muted")
    POSITION_PRECISION_FIELD_NUMBER: _ClassVar[int]
    IS_MUTED_FIELD_NUMBER: _ClassVar[int]
    position_precision: int
    is_muted: bool
    def __init__(self, position_precision: _Optional[int] = ..., is_muted: bool = ...) -> None: ...

class Channel(_message.Message):
    __slots__ = ("index", "settings", "role")
    class Role(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        DISABLED: _ClassVar[Channel.Role]
        PRIMARY: _ClassVar[Channel.Role]
        SECONDARY: _ClassVar[Channel.Role]
    DISABLED: Channel.Role
    PRIMARY: Channel.Role
    SECONDARY: Channel.Role
    INDEX_FIELD_NUMBER: _ClassVar[int]
    SETTINGS_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    index: int
    settings: ChannelSettings
    role: Channel.Role
    def __init__(self, index: _Optional[int] = ..., settings: _Optional[_Union[ChannelSettings, _Mapping]] = ..., role: _Optional[_Union[Channel.Role, str]] = ...) -> None: ...
