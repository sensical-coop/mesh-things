from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class InterdeviceVersion(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    INTERDEVICE_VERSION_UNSPECIFIED: _ClassVar[InterdeviceVersion]
    INTERDEVICE_VERSION_CURRENT: _ClassVar[InterdeviceVersion]

class FileOperation(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    GET: _ClassVar[FileOperation]
    POST: _ClassVar[FileOperation]
    PUT: _ClassVar[FileOperation]
    DELETE: _ClassVar[FileOperation]

class FileStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    FILE_UNSPECIFIED: _ClassVar[FileStatus]
    FILE_OK: _ClassVar[FileStatus]
    FILE_BUSY: _ClassVar[FileStatus]
    FILE_NO_CARD: _ClassVar[FileStatus]
    FILE_NOT_FOUND: _ClassVar[FileStatus]
    FILE_OFFSET_CONFLICT: _ClassVar[FileStatus]
    FILE_IO_ERROR: _ClassVar[FileStatus]
    FILE_NOT_A_FILE: _ClassVar[FileStatus]

class SdCommand(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SD_COMMAND_UNSPECIFIED: _ClassVar[SdCommand]
    SD_MOUNT: _ClassVar[SdCommand]
    SD_EJECT: _ClassVar[SdCommand]
    SD_FORMAT: _ClassVar[SdCommand]
INTERDEVICE_VERSION_UNSPECIFIED: InterdeviceVersion
INTERDEVICE_VERSION_CURRENT: InterdeviceVersion
GET: FileOperation
POST: FileOperation
PUT: FileOperation
DELETE: FileOperation
FILE_UNSPECIFIED: FileStatus
FILE_OK: FileStatus
FILE_BUSY: FileStatus
FILE_NO_CARD: FileStatus
FILE_NOT_FOUND: FileStatus
FILE_OFFSET_CONFLICT: FileStatus
FILE_IO_ERROR: FileStatus
FILE_NOT_A_FILE: FileStatus
SD_COMMAND_UNSPECIFIED: SdCommand
SD_MOUNT: SdCommand
SD_EJECT: SdCommand
SD_FORMAT: SdCommand

class FileTransfer(_message.Message):
    __slots__ = ("operation", "filepath", "filedata", "status", "message", "offset", "length", "file_size")
    OPERATION_FIELD_NUMBER: _ClassVar[int]
    FILEPATH_FIELD_NUMBER: _ClassVar[int]
    FILEDATA_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    LENGTH_FIELD_NUMBER: _ClassVar[int]
    FILE_SIZE_FIELD_NUMBER: _ClassVar[int]
    operation: FileOperation
    filepath: str
    filedata: bytes
    status: FileStatus
    message: str
    offset: int
    length: int
    file_size: int
    def __init__(self, operation: _Optional[_Union[FileOperation, str]] = ..., filepath: _Optional[str] = ..., filedata: _Optional[bytes] = ..., status: _Optional[_Union[FileStatus, str]] = ..., message: _Optional[str] = ..., offset: _Optional[int] = ..., length: _Optional[int] = ..., file_size: _Optional[int] = ...) -> None: ...

class DirectoryListing(_message.Message):
    __slots__ = ("directory", "filenames", "status", "message", "offset", "total_count")
    DIRECTORY_FIELD_NUMBER: _ClassVar[int]
    FILENAMES_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    TOTAL_COUNT_FIELD_NUMBER: _ClassVar[int]
    directory: str
    filenames: _containers.RepeatedScalarFieldContainer[str]
    status: FileStatus
    message: str
    offset: int
    total_count: int
    def __init__(self, directory: _Optional[str] = ..., filenames: _Optional[_Iterable[str]] = ..., status: _Optional[_Union[FileStatus, str]] = ..., message: _Optional[str] = ..., offset: _Optional[int] = ..., total_count: _Optional[int] = ...) -> None: ...

class I2CTransaction(_message.Message):
    __slots__ = ("address", "write_data", "read_len")
    ADDRESS_FIELD_NUMBER: _ClassVar[int]
    WRITE_DATA_FIELD_NUMBER: _ClassVar[int]
    READ_LEN_FIELD_NUMBER: _ClassVar[int]
    address: int
    write_data: bytes
    read_len: int
    def __init__(self, address: _Optional[int] = ..., write_data: _Optional[bytes] = ..., read_len: _Optional[int] = ...) -> None: ...

class SdCardInfo(_message.Message):
    __slots__ = ("present", "card_type", "fat_type", "card_size", "used_bytes", "free_bytes", "stats_valid", "busy", "unformatted")
    class CardType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        NONE: _ClassVar[SdCardInfo.CardType]
        MMC: _ClassVar[SdCardInfo.CardType]
        SD: _ClassVar[SdCardInfo.CardType]
        SDHC: _ClassVar[SdCardInfo.CardType]
        SDXC: _ClassVar[SdCardInfo.CardType]
        UNKNOWN_CARD: _ClassVar[SdCardInfo.CardType]
    NONE: SdCardInfo.CardType
    MMC: SdCardInfo.CardType
    SD: SdCardInfo.CardType
    SDHC: SdCardInfo.CardType
    SDXC: SdCardInfo.CardType
    UNKNOWN_CARD: SdCardInfo.CardType
    class FatType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        UNKNOWN_FAT: _ClassVar[SdCardInfo.FatType]
        FAT16: _ClassVar[SdCardInfo.FatType]
        FAT32: _ClassVar[SdCardInfo.FatType]
        EXFAT: _ClassVar[SdCardInfo.FatType]
    UNKNOWN_FAT: SdCardInfo.FatType
    FAT16: SdCardInfo.FatType
    FAT32: SdCardInfo.FatType
    EXFAT: SdCardInfo.FatType
    PRESENT_FIELD_NUMBER: _ClassVar[int]
    CARD_TYPE_FIELD_NUMBER: _ClassVar[int]
    FAT_TYPE_FIELD_NUMBER: _ClassVar[int]
    CARD_SIZE_FIELD_NUMBER: _ClassVar[int]
    USED_BYTES_FIELD_NUMBER: _ClassVar[int]
    FREE_BYTES_FIELD_NUMBER: _ClassVar[int]
    STATS_VALID_FIELD_NUMBER: _ClassVar[int]
    BUSY_FIELD_NUMBER: _ClassVar[int]
    UNFORMATTED_FIELD_NUMBER: _ClassVar[int]
    present: bool
    card_type: SdCardInfo.CardType
    fat_type: SdCardInfo.FatType
    card_size: int
    used_bytes: int
    free_bytes: int
    stats_valid: bool
    busy: bool
    unformatted: bool
    def __init__(self, present: bool = ..., card_type: _Optional[_Union[SdCardInfo.CardType, str]] = ..., fat_type: _Optional[_Union[SdCardInfo.FatType, str]] = ..., card_size: _Optional[int] = ..., used_bytes: _Optional[int] = ..., free_bytes: _Optional[int] = ..., stats_valid: bool = ..., busy: bool = ..., unformatted: bool = ...) -> None: ...

class I2CResult(_message.Message):
    __slots__ = ("status", "read_data")
    class Status(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        UNSPECIFIED: _ClassVar[I2CResult.Status]
        OK: _ClassVar[I2CResult.Status]
        NACK_ADDRESS: _ClassVar[I2CResult.Status]
        NACK_DATA: _ClassVar[I2CResult.Status]
        ERROR: _ClassVar[I2CResult.Status]
    UNSPECIFIED: I2CResult.Status
    OK: I2CResult.Status
    NACK_ADDRESS: I2CResult.Status
    NACK_DATA: I2CResult.Status
    ERROR: I2CResult.Status
    STATUS_FIELD_NUMBER: _ClassVar[int]
    READ_DATA_FIELD_NUMBER: _ClassVar[int]
    status: I2CResult.Status
    read_data: bytes
    def __init__(self, status: _Optional[_Union[I2CResult.Status, str]] = ..., read_data: _Optional[bytes] = ...) -> None: ...

class InterdeviceMessage(_message.Message):
    __slots__ = ("id", "nmea", "beep", "i2c_transaction", "i2c_result", "i2c_scan", "i2c_scan_result", "file_transfer", "directory_listing", "get_sd_info", "sd_info", "ping", "pong", "nack", "sd_command")
    ID_FIELD_NUMBER: _ClassVar[int]
    NMEA_FIELD_NUMBER: _ClassVar[int]
    BEEP_FIELD_NUMBER: _ClassVar[int]
    I2C_TRANSACTION_FIELD_NUMBER: _ClassVar[int]
    I2C_RESULT_FIELD_NUMBER: _ClassVar[int]
    I2C_SCAN_FIELD_NUMBER: _ClassVar[int]
    I2C_SCAN_RESULT_FIELD_NUMBER: _ClassVar[int]
    FILE_TRANSFER_FIELD_NUMBER: _ClassVar[int]
    DIRECTORY_LISTING_FIELD_NUMBER: _ClassVar[int]
    GET_SD_INFO_FIELD_NUMBER: _ClassVar[int]
    SD_INFO_FIELD_NUMBER: _ClassVar[int]
    PING_FIELD_NUMBER: _ClassVar[int]
    PONG_FIELD_NUMBER: _ClassVar[int]
    NACK_FIELD_NUMBER: _ClassVar[int]
    SD_COMMAND_FIELD_NUMBER: _ClassVar[int]
    id: int
    nmea: str
    beep: int
    i2c_transaction: I2CTransaction
    i2c_result: I2CResult
    i2c_scan: bool
    i2c_scan_result: bytes
    file_transfer: FileTransfer
    directory_listing: DirectoryListing
    get_sd_info: bool
    sd_info: SdCardInfo
    ping: InterdeviceVersion
    pong: InterdeviceVersion
    nack: bool
    sd_command: SdCommand
    def __init__(self, id: _Optional[int] = ..., nmea: _Optional[str] = ..., beep: _Optional[int] = ..., i2c_transaction: _Optional[_Union[I2CTransaction, _Mapping]] = ..., i2c_result: _Optional[_Union[I2CResult, _Mapping]] = ..., i2c_scan: bool = ..., i2c_scan_result: _Optional[bytes] = ..., file_transfer: _Optional[_Union[FileTransfer, _Mapping]] = ..., directory_listing: _Optional[_Union[DirectoryListing, _Mapping]] = ..., get_sd_info: bool = ..., sd_info: _Optional[_Union[SdCardInfo, _Mapping]] = ..., ping: _Optional[_Union[InterdeviceVersion, str]] = ..., pong: _Optional[_Union[InterdeviceVersion, str]] = ..., nack: bool = ..., sd_command: _Optional[_Union[SdCommand, str]] = ...) -> None: ...
