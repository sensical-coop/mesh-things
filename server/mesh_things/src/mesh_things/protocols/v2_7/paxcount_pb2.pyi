from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class Paxcount(_message.Message):
    __slots__ = ("wifi", "ble", "uptime")
    WIFI_FIELD_NUMBER: _ClassVar[int]
    BLE_FIELD_NUMBER: _ClassVar[int]
    UPTIME_FIELD_NUMBER: _ClassVar[int]
    wifi: int
    ble: int
    uptime: int
    def __init__(self, wifi: _Optional[int] = ..., ble: _Optional[int] = ..., uptime: _Optional[int] = ...) -> None: ...
