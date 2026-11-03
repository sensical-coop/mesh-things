from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SerialHalCommand(_message.Message):
    __slots__ = ("transaction_id", "type", "pin", "value", "mode", "data")
    class Type(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        UNSET: _ClassVar[SerialHalCommand.Type]
        PIN_MODE: _ClassVar[SerialHalCommand.Type]
        DIGITAL_WRITE: _ClassVar[SerialHalCommand.Type]
        DIGITAL_READ: _ClassVar[SerialHalCommand.Type]
        ATTACH_INTERRUPT: _ClassVar[SerialHalCommand.Type]
        DETACH_INTERRUPT: _ClassVar[SerialHalCommand.Type]
        SPI_TRANSFER: _ClassVar[SerialHalCommand.Type]
        NOOP: _ClassVar[SerialHalCommand.Type]
    UNSET: SerialHalCommand.Type
    PIN_MODE: SerialHalCommand.Type
    DIGITAL_WRITE: SerialHalCommand.Type
    DIGITAL_READ: SerialHalCommand.Type
    ATTACH_INTERRUPT: SerialHalCommand.Type
    DETACH_INTERRUPT: SerialHalCommand.Type
    SPI_TRANSFER: SerialHalCommand.Type
    NOOP: SerialHalCommand.Type
    TRANSACTION_ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    PIN_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    transaction_id: int
    type: SerialHalCommand.Type
    pin: int
    value: int
    mode: int
    data: bytes
    def __init__(self, transaction_id: _Optional[int] = ..., type: _Optional[_Union[SerialHalCommand.Type, str]] = ..., pin: _Optional[int] = ..., value: _Optional[int] = ..., mode: _Optional[int] = ..., data: _Optional[bytes] = ...) -> None: ...

class SerialHalResponse(_message.Message):
    __slots__ = ("transaction_id", "result", "value", "data", "error")
    class Result(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        OK: _ClassVar[SerialHalResponse.Result]
        ERROR: _ClassVar[SerialHalResponse.Result]
        BAD_REQUEST: _ClassVar[SerialHalResponse.Result]
        UNSUPPORTED: _ClassVar[SerialHalResponse.Result]
    OK: SerialHalResponse.Result
    ERROR: SerialHalResponse.Result
    BAD_REQUEST: SerialHalResponse.Result
    UNSUPPORTED: SerialHalResponse.Result
    TRANSACTION_ID_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    transaction_id: int
    result: SerialHalResponse.Result
    value: int
    data: bytes
    error: str
    def __init__(self, transaction_id: _Optional[int] = ..., result: _Optional[_Union[SerialHalResponse.Result, str]] = ..., value: _Optional[int] = ..., data: _Optional[bytes] = ..., error: _Optional[str] = ...) -> None: ...
