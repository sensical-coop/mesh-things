from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class XModem(_message.Message):
    __slots__ = ("control", "seq", "crc16", "buffer")
    class Control(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        NUL: _ClassVar[XModem.Control]
        SOH: _ClassVar[XModem.Control]
        STX: _ClassVar[XModem.Control]
        EOT: _ClassVar[XModem.Control]
        ACK: _ClassVar[XModem.Control]
        NAK: _ClassVar[XModem.Control]
        CAN: _ClassVar[XModem.Control]
        CTRLZ: _ClassVar[XModem.Control]
    NUL: XModem.Control
    SOH: XModem.Control
    STX: XModem.Control
    EOT: XModem.Control
    ACK: XModem.Control
    NAK: XModem.Control
    CAN: XModem.Control
    CTRLZ: XModem.Control
    CONTROL_FIELD_NUMBER: _ClassVar[int]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    CRC16_FIELD_NUMBER: _ClassVar[int]
    BUFFER_FIELD_NUMBER: _ClassVar[int]
    control: XModem.Control
    seq: int
    crc16: int
    buffer: bytes
    def __init__(self, control: _Optional[_Union[XModem.Control, str]] = ..., seq: _Optional[int] = ..., crc16: _Optional[int] = ..., buffer: _Optional[bytes] = ...) -> None: ...
