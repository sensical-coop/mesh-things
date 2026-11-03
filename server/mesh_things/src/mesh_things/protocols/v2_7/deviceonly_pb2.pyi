from mesh_things.protocols.v2_7 import channel_pb2 as _channel_pb2
from mesh_things.protocols.v2_7 import config_pb2 as _config_pb2
from mesh_things.protocols.v2_7 import localonly_pb2 as _localonly_pb2
from mesh_things.protocols.v2_7 import mesh_pb2 as _mesh_pb2
from mesh_things.protocols.v2_7 import telemetry_pb2 as _telemetry_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PositionLite(_message.Message):
    __slots__ = ("latitude_i", "longitude_i", "altitude", "time", "location_source")
    LATITUDE_I_FIELD_NUMBER: _ClassVar[int]
    LONGITUDE_I_FIELD_NUMBER: _ClassVar[int]
    ALTITUDE_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    LOCATION_SOURCE_FIELD_NUMBER: _ClassVar[int]
    latitude_i: int
    longitude_i: int
    altitude: int
    time: int
    location_source: _mesh_pb2.Position.LocSource
    def __init__(self, latitude_i: _Optional[int] = ..., longitude_i: _Optional[int] = ..., altitude: _Optional[int] = ..., time: _Optional[int] = ..., location_source: _Optional[_Union[_mesh_pb2.Position.LocSource, str]] = ...) -> None: ...

class UserLite(_message.Message):
    __slots__ = ("macaddr", "long_name", "short_name", "hw_model", "is_licensed", "role", "public_key", "is_unmessagable")
    MACADDR_FIELD_NUMBER: _ClassVar[int]
    LONG_NAME_FIELD_NUMBER: _ClassVar[int]
    SHORT_NAME_FIELD_NUMBER: _ClassVar[int]
    HW_MODEL_FIELD_NUMBER: _ClassVar[int]
    IS_LICENSED_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    IS_UNMESSAGABLE_FIELD_NUMBER: _ClassVar[int]
    macaddr: bytes
    long_name: str
    short_name: str
    hw_model: _mesh_pb2.HardwareModel
    is_licensed: bool
    role: _config_pb2.Config.DeviceConfig.Role
    public_key: bytes
    is_unmessagable: bool
    def __init__(self, macaddr: _Optional[bytes] = ..., long_name: _Optional[str] = ..., short_name: _Optional[str] = ..., hw_model: _Optional[_Union[_mesh_pb2.HardwareModel, str]] = ..., is_licensed: bool = ..., role: _Optional[_Union[_config_pb2.Config.DeviceConfig.Role, str]] = ..., public_key: _Optional[bytes] = ..., is_unmessagable: bool = ...) -> None: ...

class NodeInfoLite(_message.Message):
    __slots__ = ("num", "user", "position", "snr", "last_heard", "device_metrics", "channel", "via_mqtt", "hops_away", "is_favorite", "is_ignored", "next_hop", "bitfield")
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
    NEXT_HOP_FIELD_NUMBER: _ClassVar[int]
    BITFIELD_FIELD_NUMBER: _ClassVar[int]
    num: int
    user: UserLite
    position: PositionLite
    snr: float
    last_heard: int
    device_metrics: _telemetry_pb2.DeviceMetrics
    channel: int
    via_mqtt: bool
    hops_away: int
    is_favorite: bool
    is_ignored: bool
    next_hop: int
    bitfield: int
    def __init__(self, num: _Optional[int] = ..., user: _Optional[_Union[UserLite, _Mapping]] = ..., position: _Optional[_Union[PositionLite, _Mapping]] = ..., snr: _Optional[float] = ..., last_heard: _Optional[int] = ..., device_metrics: _Optional[_Union[_telemetry_pb2.DeviceMetrics, _Mapping]] = ..., channel: _Optional[int] = ..., via_mqtt: bool = ..., hops_away: _Optional[int] = ..., is_favorite: bool = ..., is_ignored: bool = ..., next_hop: _Optional[int] = ..., bitfield: _Optional[int] = ...) -> None: ...

class DeviceState(_message.Message):
    __slots__ = ("my_node", "owner", "receive_queue", "version", "rx_text_message", "no_save", "did_gps_reset", "rx_waypoint", "node_remote_hardware_pins")
    MY_NODE_FIELD_NUMBER: _ClassVar[int]
    OWNER_FIELD_NUMBER: _ClassVar[int]
    RECEIVE_QUEUE_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    RX_TEXT_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    NO_SAVE_FIELD_NUMBER: _ClassVar[int]
    DID_GPS_RESET_FIELD_NUMBER: _ClassVar[int]
    RX_WAYPOINT_FIELD_NUMBER: _ClassVar[int]
    NODE_REMOTE_HARDWARE_PINS_FIELD_NUMBER: _ClassVar[int]
    my_node: _mesh_pb2.MyNodeInfo
    owner: _mesh_pb2.User
    receive_queue: _containers.RepeatedCompositeFieldContainer[_mesh_pb2.MeshPacket]
    version: int
    rx_text_message: _mesh_pb2.MeshPacket
    no_save: bool
    did_gps_reset: bool
    rx_waypoint: _mesh_pb2.MeshPacket
    node_remote_hardware_pins: _containers.RepeatedCompositeFieldContainer[_mesh_pb2.NodeRemoteHardwarePin]
    def __init__(self, my_node: _Optional[_Union[_mesh_pb2.MyNodeInfo, _Mapping]] = ..., owner: _Optional[_Union[_mesh_pb2.User, _Mapping]] = ..., receive_queue: _Optional[_Iterable[_Union[_mesh_pb2.MeshPacket, _Mapping]]] = ..., version: _Optional[int] = ..., rx_text_message: _Optional[_Union[_mesh_pb2.MeshPacket, _Mapping]] = ..., no_save: bool = ..., did_gps_reset: bool = ..., rx_waypoint: _Optional[_Union[_mesh_pb2.MeshPacket, _Mapping]] = ..., node_remote_hardware_pins: _Optional[_Iterable[_Union[_mesh_pb2.NodeRemoteHardwarePin, _Mapping]]] = ...) -> None: ...

class NodeDatabase(_message.Message):
    __slots__ = ("version", "nodes")
    VERSION_FIELD_NUMBER: _ClassVar[int]
    NODES_FIELD_NUMBER: _ClassVar[int]
    version: int
    nodes: _containers.RepeatedCompositeFieldContainer[NodeInfoLite]
    def __init__(self, version: _Optional[int] = ..., nodes: _Optional[_Iterable[_Union[NodeInfoLite, _Mapping]]] = ...) -> None: ...

class ChannelFile(_message.Message):
    __slots__ = ("channels", "version")
    CHANNELS_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    channels: _containers.RepeatedCompositeFieldContainer[_channel_pb2.Channel]
    version: int
    def __init__(self, channels: _Optional[_Iterable[_Union[_channel_pb2.Channel, _Mapping]]] = ..., version: _Optional[int] = ...) -> None: ...

class BackupPreferences(_message.Message):
    __slots__ = ("version", "timestamp", "config", "module_config", "channels", "owner")
    VERSION_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    MODULE_CONFIG_FIELD_NUMBER: _ClassVar[int]
    CHANNELS_FIELD_NUMBER: _ClassVar[int]
    OWNER_FIELD_NUMBER: _ClassVar[int]
    version: int
    timestamp: int
    config: _localonly_pb2.LocalConfig
    module_config: _localonly_pb2.LocalModuleConfig
    channels: ChannelFile
    owner: _mesh_pb2.User
    def __init__(self, version: _Optional[int] = ..., timestamp: _Optional[int] = ..., config: _Optional[_Union[_localonly_pb2.LocalConfig, _Mapping]] = ..., module_config: _Optional[_Union[_localonly_pb2.LocalModuleConfig, _Mapping]] = ..., channels: _Optional[_Union[ChannelFile, _Mapping]] = ..., owner: _Optional[_Union[_mesh_pb2.User, _Mapping]] = ...) -> None: ...
