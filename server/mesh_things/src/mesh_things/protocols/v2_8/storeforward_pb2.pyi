from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class StoreAndForward(_message.Message):
    __slots__ = ("rr", "stats", "history", "heartbeat", "text", "original_id")
    class RequestResponse(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        UNSET: _ClassVar[StoreAndForward.RequestResponse]
        ROUTER_ERROR: _ClassVar[StoreAndForward.RequestResponse]
        ROUTER_HEARTBEAT: _ClassVar[StoreAndForward.RequestResponse]
        ROUTER_PING: _ClassVar[StoreAndForward.RequestResponse]
        ROUTER_PONG: _ClassVar[StoreAndForward.RequestResponse]
        ROUTER_BUSY: _ClassVar[StoreAndForward.RequestResponse]
        ROUTER_HISTORY: _ClassVar[StoreAndForward.RequestResponse]
        ROUTER_STATS: _ClassVar[StoreAndForward.RequestResponse]
        ROUTER_TEXT_DIRECT: _ClassVar[StoreAndForward.RequestResponse]
        ROUTER_TEXT_BROADCAST: _ClassVar[StoreAndForward.RequestResponse]
        CLIENT_ERROR: _ClassVar[StoreAndForward.RequestResponse]
        CLIENT_HISTORY: _ClassVar[StoreAndForward.RequestResponse]
        CLIENT_STATS: _ClassVar[StoreAndForward.RequestResponse]
        CLIENT_PING: _ClassVar[StoreAndForward.RequestResponse]
        CLIENT_PONG: _ClassVar[StoreAndForward.RequestResponse]
        CLIENT_ABORT: _ClassVar[StoreAndForward.RequestResponse]
    UNSET: StoreAndForward.RequestResponse
    ROUTER_ERROR: StoreAndForward.RequestResponse
    ROUTER_HEARTBEAT: StoreAndForward.RequestResponse
    ROUTER_PING: StoreAndForward.RequestResponse
    ROUTER_PONG: StoreAndForward.RequestResponse
    ROUTER_BUSY: StoreAndForward.RequestResponse
    ROUTER_HISTORY: StoreAndForward.RequestResponse
    ROUTER_STATS: StoreAndForward.RequestResponse
    ROUTER_TEXT_DIRECT: StoreAndForward.RequestResponse
    ROUTER_TEXT_BROADCAST: StoreAndForward.RequestResponse
    CLIENT_ERROR: StoreAndForward.RequestResponse
    CLIENT_HISTORY: StoreAndForward.RequestResponse
    CLIENT_STATS: StoreAndForward.RequestResponse
    CLIENT_PING: StoreAndForward.RequestResponse
    CLIENT_PONG: StoreAndForward.RequestResponse
    CLIENT_ABORT: StoreAndForward.RequestResponse
    class Statistics(_message.Message):
        __slots__ = ("messages_total", "messages_saved", "messages_max", "up_time", "requests", "requests_history", "heartbeat", "return_max", "return_window")
        MESSAGES_TOTAL_FIELD_NUMBER: _ClassVar[int]
        MESSAGES_SAVED_FIELD_NUMBER: _ClassVar[int]
        MESSAGES_MAX_FIELD_NUMBER: _ClassVar[int]
        UP_TIME_FIELD_NUMBER: _ClassVar[int]
        REQUESTS_FIELD_NUMBER: _ClassVar[int]
        REQUESTS_HISTORY_FIELD_NUMBER: _ClassVar[int]
        HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
        RETURN_MAX_FIELD_NUMBER: _ClassVar[int]
        RETURN_WINDOW_FIELD_NUMBER: _ClassVar[int]
        messages_total: int
        messages_saved: int
        messages_max: int
        up_time: int
        requests: int
        requests_history: int
        heartbeat: bool
        return_max: int
        return_window: int
        def __init__(self, messages_total: _Optional[int] = ..., messages_saved: _Optional[int] = ..., messages_max: _Optional[int] = ..., up_time: _Optional[int] = ..., requests: _Optional[int] = ..., requests_history: _Optional[int] = ..., heartbeat: bool = ..., return_max: _Optional[int] = ..., return_window: _Optional[int] = ...) -> None: ...
    class History(_message.Message):
        __slots__ = ("history_messages", "window", "last_request")
        HISTORY_MESSAGES_FIELD_NUMBER: _ClassVar[int]
        WINDOW_FIELD_NUMBER: _ClassVar[int]
        LAST_REQUEST_FIELD_NUMBER: _ClassVar[int]
        history_messages: int
        window: int
        last_request: int
        def __init__(self, history_messages: _Optional[int] = ..., window: _Optional[int] = ..., last_request: _Optional[int] = ...) -> None: ...
    class Heartbeat(_message.Message):
        __slots__ = ("period", "secondary")
        PERIOD_FIELD_NUMBER: _ClassVar[int]
        SECONDARY_FIELD_NUMBER: _ClassVar[int]
        period: int
        secondary: int
        def __init__(self, period: _Optional[int] = ..., secondary: _Optional[int] = ...) -> None: ...
    RR_FIELD_NUMBER: _ClassVar[int]
    STATS_FIELD_NUMBER: _ClassVar[int]
    HISTORY_FIELD_NUMBER: _ClassVar[int]
    HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    ORIGINAL_ID_FIELD_NUMBER: _ClassVar[int]
    rr: StoreAndForward.RequestResponse
    stats: StoreAndForward.Statistics
    history: StoreAndForward.History
    heartbeat: StoreAndForward.Heartbeat
    text: bytes
    original_id: int
    def __init__(self, rr: _Optional[_Union[StoreAndForward.RequestResponse, str]] = ..., stats: _Optional[_Union[StoreAndForward.Statistics, _Mapping]] = ..., history: _Optional[_Union[StoreAndForward.History, _Mapping]] = ..., heartbeat: _Optional[_Union[StoreAndForward.Heartbeat, _Mapping]] = ..., text: _Optional[bytes] = ..., original_id: _Optional[int] = ...) -> None: ...
