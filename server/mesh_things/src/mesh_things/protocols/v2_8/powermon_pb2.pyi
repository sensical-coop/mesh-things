from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PowerMon(_message.Message):
    __slots__ = ()
    class State(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        None: _ClassVar[PowerMon.State]
        CPU_DeepSleep: _ClassVar[PowerMon.State]
        CPU_LightSleep: _ClassVar[PowerMon.State]
        Vext1_On: _ClassVar[PowerMon.State]
        Lora_RXOn: _ClassVar[PowerMon.State]
        Lora_TXOn: _ClassVar[PowerMon.State]
        Lora_RXActive: _ClassVar[PowerMon.State]
        BT_On: _ClassVar[PowerMon.State]
        LED_On: _ClassVar[PowerMon.State]
        Screen_On: _ClassVar[PowerMon.State]
        Screen_Drawing: _ClassVar[PowerMon.State]
        Wifi_On: _ClassVar[PowerMon.State]
        GPS_Active: _ClassVar[PowerMon.State]
    None: PowerMon.State
    CPU_DeepSleep: PowerMon.State
    CPU_LightSleep: PowerMon.State
    Vext1_On: PowerMon.State
    Lora_RXOn: PowerMon.State
    Lora_TXOn: PowerMon.State
    Lora_RXActive: PowerMon.State
    BT_On: PowerMon.State
    LED_On: PowerMon.State
    Screen_On: PowerMon.State
    Screen_Drawing: PowerMon.State
    Wifi_On: PowerMon.State
    GPS_Active: PowerMon.State
    def __init__(self) -> None: ...

class PowerStressMessage(_message.Message):
    __slots__ = ("cmd", "num_seconds")
    class Opcode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        UNSET: _ClassVar[PowerStressMessage.Opcode]
        PRINT_INFO: _ClassVar[PowerStressMessage.Opcode]
        FORCE_QUIET: _ClassVar[PowerStressMessage.Opcode]
        END_QUIET: _ClassVar[PowerStressMessage.Opcode]
        SCREEN_ON: _ClassVar[PowerStressMessage.Opcode]
        SCREEN_OFF: _ClassVar[PowerStressMessage.Opcode]
        CPU_IDLE: _ClassVar[PowerStressMessage.Opcode]
        CPU_DEEPSLEEP: _ClassVar[PowerStressMessage.Opcode]
        CPU_FULLON: _ClassVar[PowerStressMessage.Opcode]
        LED_ON: _ClassVar[PowerStressMessage.Opcode]
        LED_OFF: _ClassVar[PowerStressMessage.Opcode]
        LORA_OFF: _ClassVar[PowerStressMessage.Opcode]
        LORA_TX: _ClassVar[PowerStressMessage.Opcode]
        LORA_RX: _ClassVar[PowerStressMessage.Opcode]
        BT_OFF: _ClassVar[PowerStressMessage.Opcode]
        BT_ON: _ClassVar[PowerStressMessage.Opcode]
        WIFI_OFF: _ClassVar[PowerStressMessage.Opcode]
        WIFI_ON: _ClassVar[PowerStressMessage.Opcode]
        GPS_OFF: _ClassVar[PowerStressMessage.Opcode]
        GPS_ON: _ClassVar[PowerStressMessage.Opcode]
    UNSET: PowerStressMessage.Opcode
    PRINT_INFO: PowerStressMessage.Opcode
    FORCE_QUIET: PowerStressMessage.Opcode
    END_QUIET: PowerStressMessage.Opcode
    SCREEN_ON: PowerStressMessage.Opcode
    SCREEN_OFF: PowerStressMessage.Opcode
    CPU_IDLE: PowerStressMessage.Opcode
    CPU_DEEPSLEEP: PowerStressMessage.Opcode
    CPU_FULLON: PowerStressMessage.Opcode
    LED_ON: PowerStressMessage.Opcode
    LED_OFF: PowerStressMessage.Opcode
    LORA_OFF: PowerStressMessage.Opcode
    LORA_TX: PowerStressMessage.Opcode
    LORA_RX: PowerStressMessage.Opcode
    BT_OFF: PowerStressMessage.Opcode
    BT_ON: PowerStressMessage.Opcode
    WIFI_OFF: PowerStressMessage.Opcode
    WIFI_ON: PowerStressMessage.Opcode
    GPS_OFF: PowerStressMessage.Opcode
    GPS_ON: PowerStressMessage.Opcode
    CMD_FIELD_NUMBER: _ClassVar[int]
    NUM_SECONDS_FIELD_NUMBER: _ClassVar[int]
    cmd: PowerStressMessage.Opcode
    num_seconds: float
    def __init__(self, cmd: _Optional[_Union[PowerStressMessage.Opcode, str]] = ..., num_seconds: _Optional[float] = ...) -> None: ...
