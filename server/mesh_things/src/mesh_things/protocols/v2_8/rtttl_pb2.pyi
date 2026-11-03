from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class RTTTLConfig(_message.Message):
    __slots__ = ("ringtone",)
    RINGTONE_FIELD_NUMBER: _ClassVar[int]
    ringtone: str
    def __init__(self, ringtone: _Optional[str] = ...) -> None: ...
