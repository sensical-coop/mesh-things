from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class LoRaWANBridge(_message.Message):
    __slots__ = ("uplink", "downlink", "tx_result", "chunk")
    class Uplink(_message.Message):
        __slots__ = ("freq_hz", "tmst", "rssi_x10", "snr_x10", "radio_params", "fsk_bitrate", "payload", "payload_id", "chunk_count")
        FREQ_HZ_FIELD_NUMBER: _ClassVar[int]
        TMST_FIELD_NUMBER: _ClassVar[int]
        RSSI_X10_FIELD_NUMBER: _ClassVar[int]
        SNR_X10_FIELD_NUMBER: _ClassVar[int]
        RADIO_PARAMS_FIELD_NUMBER: _ClassVar[int]
        FSK_BITRATE_FIELD_NUMBER: _ClassVar[int]
        PAYLOAD_FIELD_NUMBER: _ClassVar[int]
        PAYLOAD_ID_FIELD_NUMBER: _ClassVar[int]
        CHUNK_COUNT_FIELD_NUMBER: _ClassVar[int]
        freq_hz: int
        tmst: int
        rssi_x10: int
        snr_x10: int
        radio_params: int
        fsk_bitrate: int
        payload: bytes
        payload_id: int
        chunk_count: int
        def __init__(self, freq_hz: _Optional[int] = ..., tmst: _Optional[int] = ..., rssi_x10: _Optional[int] = ..., snr_x10: _Optional[int] = ..., radio_params: _Optional[int] = ..., fsk_bitrate: _Optional[int] = ..., payload: _Optional[bytes] = ..., payload_id: _Optional[int] = ..., chunk_count: _Optional[int] = ...) -> None: ...
    class Downlink(_message.Message):
        __slots__ = ("freq_hz", "tmst", "radio_params", "power_dbm", "immediate", "invert_polarity", "no_crc", "may_defer", "request_id", "payload", "payload_id", "chunk_count")
        FREQ_HZ_FIELD_NUMBER: _ClassVar[int]
        TMST_FIELD_NUMBER: _ClassVar[int]
        RADIO_PARAMS_FIELD_NUMBER: _ClassVar[int]
        POWER_DBM_FIELD_NUMBER: _ClassVar[int]
        IMMEDIATE_FIELD_NUMBER: _ClassVar[int]
        INVERT_POLARITY_FIELD_NUMBER: _ClassVar[int]
        NO_CRC_FIELD_NUMBER: _ClassVar[int]
        MAY_DEFER_FIELD_NUMBER: _ClassVar[int]
        REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
        PAYLOAD_FIELD_NUMBER: _ClassVar[int]
        PAYLOAD_ID_FIELD_NUMBER: _ClassVar[int]
        CHUNK_COUNT_FIELD_NUMBER: _ClassVar[int]
        freq_hz: int
        tmst: int
        radio_params: int
        power_dbm: int
        immediate: bool
        invert_polarity: bool
        no_crc: bool
        may_defer: bool
        request_id: int
        payload: bytes
        payload_id: int
        chunk_count: int
        def __init__(self, freq_hz: _Optional[int] = ..., tmst: _Optional[int] = ..., radio_params: _Optional[int] = ..., power_dbm: _Optional[int] = ..., immediate: bool = ..., invert_polarity: bool = ..., no_crc: bool = ..., may_defer: bool = ..., request_id: _Optional[int] = ..., payload: _Optional[bytes] = ..., payload_id: _Optional[int] = ..., chunk_count: _Optional[int] = ...) -> None: ...
    class PayloadChunk(_message.Message):
        __slots__ = ("payload_id", "chunk_index", "payload_chunk")
        PAYLOAD_ID_FIELD_NUMBER: _ClassVar[int]
        CHUNK_INDEX_FIELD_NUMBER: _ClassVar[int]
        PAYLOAD_CHUNK_FIELD_NUMBER: _ClassVar[int]
        payload_id: int
        chunk_index: int
        payload_chunk: bytes
        def __init__(self, payload_id: _Optional[int] = ..., chunk_index: _Optional[int] = ..., payload_chunk: _Optional[bytes] = ...) -> None: ...
    class TxResult(_message.Message):
        __slots__ = ("tmst", "status", "request_id")
        class Status(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            NONE: _ClassVar[LoRaWANBridge.TxResult.Status]
            TOO_LATE: _ClassVar[LoRaWANBridge.TxResult.Status]
            TOO_EARLY: _ClassVar[LoRaWANBridge.TxResult.Status]
            COLLISION_PACKET: _ClassVar[LoRaWANBridge.TxResult.Status]
            COLLISION_BEACON: _ClassVar[LoRaWANBridge.TxResult.Status]
            TX_FREQ: _ClassVar[LoRaWANBridge.TxResult.Status]
            TX_POWER: _ClassVar[LoRaWANBridge.TxResult.Status]
            GPS_UNLOCKED: _ClassVar[LoRaWANBridge.TxResult.Status]
            DEFERRED: _ClassVar[LoRaWANBridge.TxResult.Status]
            DROPPED: _ClassVar[LoRaWANBridge.TxResult.Status]
        NONE: LoRaWANBridge.TxResult.Status
        TOO_LATE: LoRaWANBridge.TxResult.Status
        TOO_EARLY: LoRaWANBridge.TxResult.Status
        COLLISION_PACKET: LoRaWANBridge.TxResult.Status
        COLLISION_BEACON: LoRaWANBridge.TxResult.Status
        TX_FREQ: LoRaWANBridge.TxResult.Status
        TX_POWER: LoRaWANBridge.TxResult.Status
        GPS_UNLOCKED: LoRaWANBridge.TxResult.Status
        DEFERRED: LoRaWANBridge.TxResult.Status
        DROPPED: LoRaWANBridge.TxResult.Status
        TMST_FIELD_NUMBER: _ClassVar[int]
        STATUS_FIELD_NUMBER: _ClassVar[int]
        REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
        tmst: int
        status: LoRaWANBridge.TxResult.Status
        request_id: int
        def __init__(self, tmst: _Optional[int] = ..., status: _Optional[_Union[LoRaWANBridge.TxResult.Status, str]] = ..., request_id: _Optional[int] = ...) -> None: ...
    UPLINK_FIELD_NUMBER: _ClassVar[int]
    DOWNLINK_FIELD_NUMBER: _ClassVar[int]
    TX_RESULT_FIELD_NUMBER: _ClassVar[int]
    CHUNK_FIELD_NUMBER: _ClassVar[int]
    uplink: LoRaWANBridge.Uplink
    downlink: LoRaWANBridge.Downlink
    tx_result: LoRaWANBridge.TxResult
    chunk: LoRaWANBridge.PayloadChunk
    def __init__(self, uplink: _Optional[_Union[LoRaWANBridge.Uplink, _Mapping]] = ..., downlink: _Optional[_Union[LoRaWANBridge.Downlink, _Mapping]] = ..., tx_result: _Optional[_Union[LoRaWANBridge.TxResult, _Mapping]] = ..., chunk: _Optional[_Union[LoRaWANBridge.PayloadChunk, _Mapping]] = ...) -> None: ...
