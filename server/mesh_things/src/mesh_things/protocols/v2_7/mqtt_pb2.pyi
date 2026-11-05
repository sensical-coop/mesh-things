from mesh_things.protocols.v2_7 import config_pb2 as _config_pb2
from mesh_things.protocols.v2_7 import mesh_pb2 as _mesh_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ServiceEnvelope(_message.Message):
    __slots__ = ("packet", "channel_id", "gateway_id")
    PACKET_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    GATEWAY_ID_FIELD_NUMBER: _ClassVar[int]
    packet: _mesh_pb2.MeshPacket
    channel_id: str
    gateway_id: str
    def __init__(self, packet: _Optional[_Union[_mesh_pb2.MeshPacket, _Mapping]] = ..., channel_id: _Optional[str] = ..., gateway_id: _Optional[str] = ...) -> None: ...

class MapReport(_message.Message):
    __slots__ = ("long_name", "short_name", "role", "hw_model", "firmware_version", "region", "modem_preset", "has_default_channel", "latitude_i", "longitude_i", "altitude", "position_precision", "num_online_local_nodes", "has_opted_report_location")
    LONG_NAME_FIELD_NUMBER: _ClassVar[int]
    SHORT_NAME_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    HW_MODEL_FIELD_NUMBER: _ClassVar[int]
    FIRMWARE_VERSION_FIELD_NUMBER: _ClassVar[int]
    REGION_FIELD_NUMBER: _ClassVar[int]
    MODEM_PRESET_FIELD_NUMBER: _ClassVar[int]
    HAS_DEFAULT_CHANNEL_FIELD_NUMBER: _ClassVar[int]
    LATITUDE_I_FIELD_NUMBER: _ClassVar[int]
    LONGITUDE_I_FIELD_NUMBER: _ClassVar[int]
    ALTITUDE_FIELD_NUMBER: _ClassVar[int]
    POSITION_PRECISION_FIELD_NUMBER: _ClassVar[int]
    NUM_ONLINE_LOCAL_NODES_FIELD_NUMBER: _ClassVar[int]
    HAS_OPTED_REPORT_LOCATION_FIELD_NUMBER: _ClassVar[int]
    long_name: str
    short_name: str
    role: _config_pb2.Config.DeviceConfig.Role
    hw_model: _mesh_pb2.HardwareModel
    firmware_version: str
    region: _config_pb2.Config.LoRaConfig.RegionCode
    modem_preset: _config_pb2.Config.LoRaConfig.ModemPreset
    has_default_channel: bool
    latitude_i: int
    longitude_i: int
    altitude: int
    position_precision: int
    num_online_local_nodes: int
    has_opted_report_location: bool
    def __init__(self, long_name: _Optional[str] = ..., short_name: _Optional[str] = ..., role: _Optional[_Union[_config_pb2.Config.DeviceConfig.Role, str]] = ..., hw_model: _Optional[_Union[_mesh_pb2.HardwareModel, str]] = ..., firmware_version: _Optional[str] = ..., region: _Optional[_Union[_config_pb2.Config.LoRaConfig.RegionCode, str]] = ..., modem_preset: _Optional[_Union[_config_pb2.Config.LoRaConfig.ModemPreset, str]] = ..., has_default_channel: bool = ..., latitude_i: _Optional[int] = ..., longitude_i: _Optional[int] = ..., altitude: _Optional[int] = ..., position_precision: _Optional[int] = ..., num_online_local_nodes: _Optional[int] = ..., has_opted_report_location: bool = ...) -> None: ...
