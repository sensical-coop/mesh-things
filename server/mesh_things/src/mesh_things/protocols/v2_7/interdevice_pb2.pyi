from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class MessageType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ACK: _ClassVar[MessageType]
    COLLECT_INTERVAL: _ClassVar[MessageType]
    BEEP_ON: _ClassVar[MessageType]
    BEEP_OFF: _ClassVar[MessageType]
    SHUTDOWN: _ClassVar[MessageType]
    POWER_ON: _ClassVar[MessageType]
    SCD41_TEMP: _ClassVar[MessageType]
    SCD41_HUMIDITY: _ClassVar[MessageType]
    SCD41_CO2: _ClassVar[MessageType]
    AHT20_TEMP: _ClassVar[MessageType]
    AHT20_HUMIDITY: _ClassVar[MessageType]
    TVOC_INDEX: _ClassVar[MessageType]
ACK: MessageType
COLLECT_INTERVAL: MessageType
BEEP_ON: MessageType
BEEP_OFF: MessageType
SHUTDOWN: MessageType
POWER_ON: MessageType
SCD41_TEMP: MessageType
SCD41_HUMIDITY: MessageType
SCD41_CO2: MessageType
AHT20_TEMP: MessageType
AHT20_HUMIDITY: MessageType
TVOC_INDEX: MessageType

class SensorData(_message.Message):
    __slots__ = ("type", "float_value", "uint32_value")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    FLOAT_VALUE_FIELD_NUMBER: _ClassVar[int]
    UINT32_VALUE_FIELD_NUMBER: _ClassVar[int]
    type: MessageType
    float_value: float
    uint32_value: int
    def __init__(self, type: _Optional[_Union[MessageType, str]] = ..., float_value: _Optional[float] = ..., uint32_value: _Optional[int] = ...) -> None: ...

class InterdeviceMessage(_message.Message):
    __slots__ = ("nmea", "sensor")
    NMEA_FIELD_NUMBER: _ClassVar[int]
    SENSOR_FIELD_NUMBER: _ClassVar[int]
    nmea: str
    sensor: SensorData
    def __init__(self, nmea: _Optional[str] = ..., sensor: _Optional[_Union[SensorData, _Mapping]] = ...) -> None: ...
