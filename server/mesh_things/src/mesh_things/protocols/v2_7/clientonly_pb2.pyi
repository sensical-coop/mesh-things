from mesh_things.protocols.v2_7 import localonly_pb2 as _localonly_pb2
from mesh_things.protocols.v2_7 import mesh_pb2 as _mesh_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DeviceProfile(_message.Message):
    __slots__ = ("long_name", "short_name", "channel_url", "config", "module_config", "fixed_position", "ringtone", "canned_messages")
    LONG_NAME_FIELD_NUMBER: _ClassVar[int]
    SHORT_NAME_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_URL_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    MODULE_CONFIG_FIELD_NUMBER: _ClassVar[int]
    FIXED_POSITION_FIELD_NUMBER: _ClassVar[int]
    RINGTONE_FIELD_NUMBER: _ClassVar[int]
    CANNED_MESSAGES_FIELD_NUMBER: _ClassVar[int]
    long_name: str
    short_name: str
    channel_url: str
    config: _localonly_pb2.LocalConfig
    module_config: _localonly_pb2.LocalModuleConfig
    fixed_position: _mesh_pb2.Position
    ringtone: str
    canned_messages: str
    def __init__(self, long_name: _Optional[str] = ..., short_name: _Optional[str] = ..., channel_url: _Optional[str] = ..., config: _Optional[_Union[_localonly_pb2.LocalConfig, _Mapping]] = ..., module_config: _Optional[_Union[_localonly_pb2.LocalModuleConfig, _Mapping]] = ..., fixed_position: _Optional[_Union[_mesh_pb2.Position, _Mapping]] = ..., ringtone: _Optional[str] = ..., canned_messages: _Optional[str] = ...) -> None: ...
