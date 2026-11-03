from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Team(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    Unspecifed_Color: _ClassVar[Team]
    White: _ClassVar[Team]
    Yellow: _ClassVar[Team]
    Orange: _ClassVar[Team]
    Magenta: _ClassVar[Team]
    Red: _ClassVar[Team]
    Maroon: _ClassVar[Team]
    Purple: _ClassVar[Team]
    Dark_Blue: _ClassVar[Team]
    Blue: _ClassVar[Team]
    Cyan: _ClassVar[Team]
    Teal: _ClassVar[Team]
    Green: _ClassVar[Team]
    Dark_Green: _ClassVar[Team]
    Brown: _ClassVar[Team]

class MemberRole(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    Unspecifed: _ClassVar[MemberRole]
    TeamMember: _ClassVar[MemberRole]
    TeamLead: _ClassVar[MemberRole]
    HQ: _ClassVar[MemberRole]
    Sniper: _ClassVar[MemberRole]
    Medic: _ClassVar[MemberRole]
    ForwardObserver: _ClassVar[MemberRole]
    RTO: _ClassVar[MemberRole]
    K9: _ClassVar[MemberRole]

class CotHow(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CotHow_Unspecified: _ClassVar[CotHow]
    CotHow_h_e: _ClassVar[CotHow]
    CotHow_m_g: _ClassVar[CotHow]
    CotHow_h_g_i_g_o: _ClassVar[CotHow]
    CotHow_m_r: _ClassVar[CotHow]
    CotHow_m_f: _ClassVar[CotHow]
    CotHow_m_p: _ClassVar[CotHow]
    CotHow_m_s: _ClassVar[CotHow]

class CotType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CotType_Other: _ClassVar[CotType]
    CotType_a_f_G_U_C: _ClassVar[CotType]
    CotType_a_f_G_U_C_I: _ClassVar[CotType]
    CotType_a_n_A_C_F: _ClassVar[CotType]
    CotType_a_n_A_C_H: _ClassVar[CotType]
    CotType_a_n_A_C: _ClassVar[CotType]
    CotType_a_f_A_M_H: _ClassVar[CotType]
    CotType_a_f_A_M: _ClassVar[CotType]
    CotType_a_f_A_M_F_F: _ClassVar[CotType]
    CotType_a_f_A_M_H_A: _ClassVar[CotType]
    CotType_a_f_A_M_H_U_M: _ClassVar[CotType]
    CotType_a_h_A_M_F_F: _ClassVar[CotType]
    CotType_a_h_A_M_H_A: _ClassVar[CotType]
    CotType_a_u_A_C: _ClassVar[CotType]
    CotType_t_x_d_d: _ClassVar[CotType]
    CotType_a_f_G_E_S_E: _ClassVar[CotType]
    CotType_a_f_G_E_V_C: _ClassVar[CotType]
    CotType_a_f_S: _ClassVar[CotType]
    CotType_a_f_A_M_F: _ClassVar[CotType]
    CotType_a_f_A_M_F_C_H: _ClassVar[CotType]
    CotType_a_f_A_M_F_U_L: _ClassVar[CotType]
    CotType_a_f_A_M_F_L: _ClassVar[CotType]
    CotType_a_f_A_M_F_P: _ClassVar[CotType]
    CotType_a_f_A_C_H: _ClassVar[CotType]
    CotType_a_n_A_M_F_Q: _ClassVar[CotType]
    CotType_b_t_f: _ClassVar[CotType]
    CotType_b_r_f_h_c: _ClassVar[CotType]
    CotType_b_a_o_pan: _ClassVar[CotType]
    CotType_b_a_o_opn: _ClassVar[CotType]
    CotType_b_a_o_can: _ClassVar[CotType]
    CotType_b_a_o_tbl: _ClassVar[CotType]
    CotType_b_a_g: _ClassVar[CotType]
    CotType_a_f_G: _ClassVar[CotType]
    CotType_a_f_G_U: _ClassVar[CotType]
    CotType_a_h_G: _ClassVar[CotType]
    CotType_a_u_G: _ClassVar[CotType]
    CotType_a_n_G: _ClassVar[CotType]
    CotType_b_m_r: _ClassVar[CotType]
    CotType_b_m_p_w: _ClassVar[CotType]
    CotType_b_m_p_s_p_i: _ClassVar[CotType]
    CotType_u_d_f: _ClassVar[CotType]
    CotType_u_d_r: _ClassVar[CotType]
    CotType_u_d_c_c: _ClassVar[CotType]
    CotType_u_rb_a: _ClassVar[CotType]
    CotType_a_h_A: _ClassVar[CotType]
    CotType_a_u_A: _ClassVar[CotType]
    CotType_a_f_A_M_H_Q: _ClassVar[CotType]
    CotType_a_f_A_C_F: _ClassVar[CotType]
    CotType_a_f_A_C: _ClassVar[CotType]
    CotType_a_f_A_C_L: _ClassVar[CotType]
    CotType_a_f_A: _ClassVar[CotType]
    CotType_a_f_A_M_H_C: _ClassVar[CotType]
    CotType_a_n_A_M_F_F: _ClassVar[CotType]
    CotType_a_u_A_C_F: _ClassVar[CotType]
    CotType_a_f_G_U_C_F_T_A: _ClassVar[CotType]
    CotType_a_f_G_U_C_V_S: _ClassVar[CotType]
    CotType_a_f_G_U_C_R_X: _ClassVar[CotType]
    CotType_a_f_G_U_C_I_Z: _ClassVar[CotType]
    CotType_a_f_G_U_C_E_C_W: _ClassVar[CotType]
    CotType_a_f_G_U_C_I_L: _ClassVar[CotType]
    CotType_a_f_G_U_C_R_O: _ClassVar[CotType]
    CotType_a_f_G_U_C_R_V: _ClassVar[CotType]
    CotType_a_f_G_U_H: _ClassVar[CotType]
    CotType_a_f_G_U_U_M_S_E: _ClassVar[CotType]
    CotType_a_f_G_U_S_M_C: _ClassVar[CotType]
    CotType_a_f_G_E_S: _ClassVar[CotType]
    CotType_a_f_G_E: _ClassVar[CotType]
    CotType_a_f_G_E_V_C_U: _ClassVar[CotType]
    CotType_a_f_G_E_V_C_ps: _ClassVar[CotType]
    CotType_a_u_G_E_V: _ClassVar[CotType]
    CotType_a_f_S_N_N_R: _ClassVar[CotType]
    CotType_a_f_F_B: _ClassVar[CotType]
    CotType_b_m_p_s_p_loc: _ClassVar[CotType]
    CotType_b_i_v: _ClassVar[CotType]
    CotType_b_f_t_r: _ClassVar[CotType]
    CotType_b_f_t_a: _ClassVar[CotType]
    CotType_u_d_f_m: _ClassVar[CotType]
    CotType_u_d_p: _ClassVar[CotType]
    CotType_b_m_p_s_m: _ClassVar[CotType]
    CotType_b_m_p_c: _ClassVar[CotType]
    CotType_u_r_b_c_c: _ClassVar[CotType]
    CotType_u_r_b_bullseye: _ClassVar[CotType]
    CotType_a_f_G_E_V_A: _ClassVar[CotType]
    CotType_a_n_A: _ClassVar[CotType]
    CotType_a_u_G_U_C_F: _ClassVar[CotType]
    CotType_a_n_G_U_C_F: _ClassVar[CotType]
    CotType_a_h_G_U_C_F: _ClassVar[CotType]
    CotType_a_f_G_U_C_F: _ClassVar[CotType]
    CotType_a_u_G_I: _ClassVar[CotType]
    CotType_a_n_G_I: _ClassVar[CotType]
    CotType_a_h_G_I: _ClassVar[CotType]
    CotType_a_f_G_I: _ClassVar[CotType]
    CotType_a_u_G_E_X_M: _ClassVar[CotType]
    CotType_a_n_G_E_X_M: _ClassVar[CotType]
    CotType_a_h_G_E_X_M: _ClassVar[CotType]
    CotType_a_f_G_E_X_M: _ClassVar[CotType]
    CotType_a_u_S: _ClassVar[CotType]
    CotType_a_n_S: _ClassVar[CotType]
    CotType_a_h_S: _ClassVar[CotType]
    CotType_a_u_G_U_C_I_d: _ClassVar[CotType]
    CotType_a_n_G_U_C_I_d: _ClassVar[CotType]
    CotType_a_h_G_U_C_I_d: _ClassVar[CotType]
    CotType_a_f_G_U_C_I_d: _ClassVar[CotType]
    CotType_a_u_G_E_V_A_T: _ClassVar[CotType]
    CotType_a_n_G_E_V_A_T: _ClassVar[CotType]
    CotType_a_h_G_E_V_A_T: _ClassVar[CotType]
    CotType_a_f_G_E_V_A_T: _ClassVar[CotType]
    CotType_a_u_G_U_C_I: _ClassVar[CotType]
    CotType_a_n_G_U_C_I: _ClassVar[CotType]
    CotType_a_h_G_U_C_I: _ClassVar[CotType]
    CotType_a_n_G_E_V: _ClassVar[CotType]
    CotType_a_h_G_E_V: _ClassVar[CotType]
    CotType_a_f_G_E_V: _ClassVar[CotType]
    CotType_b_m_p_w_GOTO: _ClassVar[CotType]
    CotType_b_m_p_c_ip: _ClassVar[CotType]
    CotType_b_m_p_c_cp: _ClassVar[CotType]
    CotType_b_m_p_s_p_op: _ClassVar[CotType]
    CotType_u_d_v: _ClassVar[CotType]
    CotType_u_d_v_m: _ClassVar[CotType]
    CotType_u_d_c_e: _ClassVar[CotType]
    CotType_b_i_x_i: _ClassVar[CotType]
    CotType_b_t_f_d: _ClassVar[CotType]
    CotType_b_t_f_r: _ClassVar[CotType]
    CotType_b_a_o_c: _ClassVar[CotType]
    CotType_t_s: _ClassVar[CotType]
    CotType_m_t_t: _ClassVar[CotType]
    CotType_y: _ClassVar[CotType]

class GeoPointSource(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    GeoPointSource_Unspecified: _ClassVar[GeoPointSource]
    GeoPointSource_GPS: _ClassVar[GeoPointSource]
    GeoPointSource_USER: _ClassVar[GeoPointSource]
    GeoPointSource_NETWORK: _ClassVar[GeoPointSource]
Unspecifed_Color: Team
White: Team
Yellow: Team
Orange: Team
Magenta: Team
Red: Team
Maroon: Team
Purple: Team
Dark_Blue: Team
Blue: Team
Cyan: Team
Teal: Team
Green: Team
Dark_Green: Team
Brown: Team
Unspecifed: MemberRole
TeamMember: MemberRole
TeamLead: MemberRole
HQ: MemberRole
Sniper: MemberRole
Medic: MemberRole
ForwardObserver: MemberRole
RTO: MemberRole
K9: MemberRole
CotHow_Unspecified: CotHow
CotHow_h_e: CotHow
CotHow_m_g: CotHow
CotHow_h_g_i_g_o: CotHow
CotHow_m_r: CotHow
CotHow_m_f: CotHow
CotHow_m_p: CotHow
CotHow_m_s: CotHow
CotType_Other: CotType
CotType_a_f_G_U_C: CotType
CotType_a_f_G_U_C_I: CotType
CotType_a_n_A_C_F: CotType
CotType_a_n_A_C_H: CotType
CotType_a_n_A_C: CotType
CotType_a_f_A_M_H: CotType
CotType_a_f_A_M: CotType
CotType_a_f_A_M_F_F: CotType
CotType_a_f_A_M_H_A: CotType
CotType_a_f_A_M_H_U_M: CotType
CotType_a_h_A_M_F_F: CotType
CotType_a_h_A_M_H_A: CotType
CotType_a_u_A_C: CotType
CotType_t_x_d_d: CotType
CotType_a_f_G_E_S_E: CotType
CotType_a_f_G_E_V_C: CotType
CotType_a_f_S: CotType
CotType_a_f_A_M_F: CotType
CotType_a_f_A_M_F_C_H: CotType
CotType_a_f_A_M_F_U_L: CotType
CotType_a_f_A_M_F_L: CotType
CotType_a_f_A_M_F_P: CotType
CotType_a_f_A_C_H: CotType
CotType_a_n_A_M_F_Q: CotType
CotType_b_t_f: CotType
CotType_b_r_f_h_c: CotType
CotType_b_a_o_pan: CotType
CotType_b_a_o_opn: CotType
CotType_b_a_o_can: CotType
CotType_b_a_o_tbl: CotType
CotType_b_a_g: CotType
CotType_a_f_G: CotType
CotType_a_f_G_U: CotType
CotType_a_h_G: CotType
CotType_a_u_G: CotType
CotType_a_n_G: CotType
CotType_b_m_r: CotType
CotType_b_m_p_w: CotType
CotType_b_m_p_s_p_i: CotType
CotType_u_d_f: CotType
CotType_u_d_r: CotType
CotType_u_d_c_c: CotType
CotType_u_rb_a: CotType
CotType_a_h_A: CotType
CotType_a_u_A: CotType
CotType_a_f_A_M_H_Q: CotType
CotType_a_f_A_C_F: CotType
CotType_a_f_A_C: CotType
CotType_a_f_A_C_L: CotType
CotType_a_f_A: CotType
CotType_a_f_A_M_H_C: CotType
CotType_a_n_A_M_F_F: CotType
CotType_a_u_A_C_F: CotType
CotType_a_f_G_U_C_F_T_A: CotType
CotType_a_f_G_U_C_V_S: CotType
CotType_a_f_G_U_C_R_X: CotType
CotType_a_f_G_U_C_I_Z: CotType
CotType_a_f_G_U_C_E_C_W: CotType
CotType_a_f_G_U_C_I_L: CotType
CotType_a_f_G_U_C_R_O: CotType
CotType_a_f_G_U_C_R_V: CotType
CotType_a_f_G_U_H: CotType
CotType_a_f_G_U_U_M_S_E: CotType
CotType_a_f_G_U_S_M_C: CotType
CotType_a_f_G_E_S: CotType
CotType_a_f_G_E: CotType
CotType_a_f_G_E_V_C_U: CotType
CotType_a_f_G_E_V_C_ps: CotType
CotType_a_u_G_E_V: CotType
CotType_a_f_S_N_N_R: CotType
CotType_a_f_F_B: CotType
CotType_b_m_p_s_p_loc: CotType
CotType_b_i_v: CotType
CotType_b_f_t_r: CotType
CotType_b_f_t_a: CotType
CotType_u_d_f_m: CotType
CotType_u_d_p: CotType
CotType_b_m_p_s_m: CotType
CotType_b_m_p_c: CotType
CotType_u_r_b_c_c: CotType
CotType_u_r_b_bullseye: CotType
CotType_a_f_G_E_V_A: CotType
CotType_a_n_A: CotType
CotType_a_u_G_U_C_F: CotType
CotType_a_n_G_U_C_F: CotType
CotType_a_h_G_U_C_F: CotType
CotType_a_f_G_U_C_F: CotType
CotType_a_u_G_I: CotType
CotType_a_n_G_I: CotType
CotType_a_h_G_I: CotType
CotType_a_f_G_I: CotType
CotType_a_u_G_E_X_M: CotType
CotType_a_n_G_E_X_M: CotType
CotType_a_h_G_E_X_M: CotType
CotType_a_f_G_E_X_M: CotType
CotType_a_u_S: CotType
CotType_a_n_S: CotType
CotType_a_h_S: CotType
CotType_a_u_G_U_C_I_d: CotType
CotType_a_n_G_U_C_I_d: CotType
CotType_a_h_G_U_C_I_d: CotType
CotType_a_f_G_U_C_I_d: CotType
CotType_a_u_G_E_V_A_T: CotType
CotType_a_n_G_E_V_A_T: CotType
CotType_a_h_G_E_V_A_T: CotType
CotType_a_f_G_E_V_A_T: CotType
CotType_a_u_G_U_C_I: CotType
CotType_a_n_G_U_C_I: CotType
CotType_a_h_G_U_C_I: CotType
CotType_a_n_G_E_V: CotType
CotType_a_h_G_E_V: CotType
CotType_a_f_G_E_V: CotType
CotType_b_m_p_w_GOTO: CotType
CotType_b_m_p_c_ip: CotType
CotType_b_m_p_c_cp: CotType
CotType_b_m_p_s_p_op: CotType
CotType_u_d_v: CotType
CotType_u_d_v_m: CotType
CotType_u_d_c_e: CotType
CotType_b_i_x_i: CotType
CotType_b_t_f_d: CotType
CotType_b_t_f_r: CotType
CotType_b_a_o_c: CotType
CotType_t_s: CotType
CotType_m_t_t: CotType
CotType_y: CotType
GeoPointSource_Unspecified: GeoPointSource
GeoPointSource_GPS: GeoPointSource
GeoPointSource_USER: GeoPointSource
GeoPointSource_NETWORK: GeoPointSource

class TAKPacket(_message.Message):
    __slots__ = ("is_compressed", "contact", "group", "status", "pli", "chat", "detail")
    IS_COMPRESSED_FIELD_NUMBER: _ClassVar[int]
    CONTACT_FIELD_NUMBER: _ClassVar[int]
    GROUP_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    PLI_FIELD_NUMBER: _ClassVar[int]
    CHAT_FIELD_NUMBER: _ClassVar[int]
    DETAIL_FIELD_NUMBER: _ClassVar[int]
    is_compressed: bool
    contact: Contact
    group: Group
    status: Status
    pli: PLI
    chat: GeoChat
    detail: bytes
    def __init__(self, is_compressed: bool = ..., contact: _Optional[_Union[Contact, _Mapping]] = ..., group: _Optional[_Union[Group, _Mapping]] = ..., status: _Optional[_Union[Status, _Mapping]] = ..., pli: _Optional[_Union[PLI, _Mapping]] = ..., chat: _Optional[_Union[GeoChat, _Mapping]] = ..., detail: _Optional[bytes] = ...) -> None: ...

class GeoChat(_message.Message):
    __slots__ = ("message", "to", "to_callsign", "receipt_for_uid", "receipt_type", "lang", "room_id", "voice_profile_id")
    class ReceiptType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        ReceiptType_None: _ClassVar[GeoChat.ReceiptType]
        ReceiptType_Delivered: _ClassVar[GeoChat.ReceiptType]
        ReceiptType_Read: _ClassVar[GeoChat.ReceiptType]
    ReceiptType_None: GeoChat.ReceiptType
    ReceiptType_Delivered: GeoChat.ReceiptType
    ReceiptType_Read: GeoChat.ReceiptType
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    TO_FIELD_NUMBER: _ClassVar[int]
    TO_CALLSIGN_FIELD_NUMBER: _ClassVar[int]
    RECEIPT_FOR_UID_FIELD_NUMBER: _ClassVar[int]
    RECEIPT_TYPE_FIELD_NUMBER: _ClassVar[int]
    LANG_FIELD_NUMBER: _ClassVar[int]
    ROOM_ID_FIELD_NUMBER: _ClassVar[int]
    VOICE_PROFILE_ID_FIELD_NUMBER: _ClassVar[int]
    message: str
    to: str
    to_callsign: str
    receipt_for_uid: str
    receipt_type: GeoChat.ReceiptType
    lang: str
    room_id: str
    voice_profile_id: str
    def __init__(self, message: _Optional[str] = ..., to: _Optional[str] = ..., to_callsign: _Optional[str] = ..., receipt_for_uid: _Optional[str] = ..., receipt_type: _Optional[_Union[GeoChat.ReceiptType, str]] = ..., lang: _Optional[str] = ..., room_id: _Optional[str] = ..., voice_profile_id: _Optional[str] = ...) -> None: ...

class Group(_message.Message):
    __slots__ = ("role", "team")
    ROLE_FIELD_NUMBER: _ClassVar[int]
    TEAM_FIELD_NUMBER: _ClassVar[int]
    role: MemberRole
    team: Team
    def __init__(self, role: _Optional[_Union[MemberRole, str]] = ..., team: _Optional[_Union[Team, str]] = ...) -> None: ...

class Status(_message.Message):
    __slots__ = ("battery",)
    BATTERY_FIELD_NUMBER: _ClassVar[int]
    battery: int
    def __init__(self, battery: _Optional[int] = ...) -> None: ...

class Contact(_message.Message):
    __slots__ = ("callsign", "device_callsign")
    CALLSIGN_FIELD_NUMBER: _ClassVar[int]
    DEVICE_CALLSIGN_FIELD_NUMBER: _ClassVar[int]
    callsign: str
    device_callsign: str
    def __init__(self, callsign: _Optional[str] = ..., device_callsign: _Optional[str] = ...) -> None: ...

class PLI(_message.Message):
    __slots__ = ("latitude_i", "longitude_i", "altitude", "speed", "course")
    LATITUDE_I_FIELD_NUMBER: _ClassVar[int]
    LONGITUDE_I_FIELD_NUMBER: _ClassVar[int]
    ALTITUDE_FIELD_NUMBER: _ClassVar[int]
    SPEED_FIELD_NUMBER: _ClassVar[int]
    COURSE_FIELD_NUMBER: _ClassVar[int]
    latitude_i: int
    longitude_i: int
    altitude: int
    speed: int
    course: int
    def __init__(self, latitude_i: _Optional[int] = ..., longitude_i: _Optional[int] = ..., altitude: _Optional[int] = ..., speed: _Optional[int] = ..., course: _Optional[int] = ...) -> None: ...

class AircraftTrack(_message.Message):
    __slots__ = ("icao", "registration", "flight", "aircraft_type", "squawk", "category", "rssi_x10", "gps", "cot_host_id")
    ICAO_FIELD_NUMBER: _ClassVar[int]
    REGISTRATION_FIELD_NUMBER: _ClassVar[int]
    FLIGHT_FIELD_NUMBER: _ClassVar[int]
    AIRCRAFT_TYPE_FIELD_NUMBER: _ClassVar[int]
    SQUAWK_FIELD_NUMBER: _ClassVar[int]
    CATEGORY_FIELD_NUMBER: _ClassVar[int]
    RSSI_X10_FIELD_NUMBER: _ClassVar[int]
    GPS_FIELD_NUMBER: _ClassVar[int]
    COT_HOST_ID_FIELD_NUMBER: _ClassVar[int]
    icao: str
    registration: str
    flight: str
    aircraft_type: str
    squawk: int
    category: str
    rssi_x10: int
    gps: bool
    cot_host_id: str
    def __init__(self, icao: _Optional[str] = ..., registration: _Optional[str] = ..., flight: _Optional[str] = ..., aircraft_type: _Optional[str] = ..., squawk: _Optional[int] = ..., category: _Optional[str] = ..., rssi_x10: _Optional[int] = ..., gps: bool = ..., cot_host_id: _Optional[str] = ...) -> None: ...

class CotGeoPoint(_message.Message):
    __slots__ = ("lat_delta_i", "lon_delta_i")
    LAT_DELTA_I_FIELD_NUMBER: _ClassVar[int]
    LON_DELTA_I_FIELD_NUMBER: _ClassVar[int]
    lat_delta_i: int
    lon_delta_i: int
    def __init__(self, lat_delta_i: _Optional[int] = ..., lon_delta_i: _Optional[int] = ...) -> None: ...

class DrawnShape(_message.Message):
    __slots__ = ("kind", "style", "major_cm", "minor_cm", "angle_deg", "stroke_color", "stroke_argb", "stroke_weight_x10", "fill_color", "fill_argb", "labels_on", "vertex_lat_deltas", "vertex_lon_deltas", "truncated", "bullseye_distance_dm", "bullseye_bearing_ref", "bullseye_flags", "bullseye_uid_ref")
    class Kind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        Kind_Unspecified: _ClassVar[DrawnShape.Kind]
        Kind_Circle: _ClassVar[DrawnShape.Kind]
        Kind_Rectangle: _ClassVar[DrawnShape.Kind]
        Kind_Freeform: _ClassVar[DrawnShape.Kind]
        Kind_Telestration: _ClassVar[DrawnShape.Kind]
        Kind_Polygon: _ClassVar[DrawnShape.Kind]
        Kind_RangingCircle: _ClassVar[DrawnShape.Kind]
        Kind_Bullseye: _ClassVar[DrawnShape.Kind]
        Kind_Ellipse: _ClassVar[DrawnShape.Kind]
        Kind_Vehicle2D: _ClassVar[DrawnShape.Kind]
        Kind_Vehicle3D: _ClassVar[DrawnShape.Kind]
    Kind_Unspecified: DrawnShape.Kind
    Kind_Circle: DrawnShape.Kind
    Kind_Rectangle: DrawnShape.Kind
    Kind_Freeform: DrawnShape.Kind
    Kind_Telestration: DrawnShape.Kind
    Kind_Polygon: DrawnShape.Kind
    Kind_RangingCircle: DrawnShape.Kind
    Kind_Bullseye: DrawnShape.Kind
    Kind_Ellipse: DrawnShape.Kind
    Kind_Vehicle2D: DrawnShape.Kind
    Kind_Vehicle3D: DrawnShape.Kind
    class StyleMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        StyleMode_Unspecified: _ClassVar[DrawnShape.StyleMode]
        StyleMode_StrokeOnly: _ClassVar[DrawnShape.StyleMode]
        StyleMode_FillOnly: _ClassVar[DrawnShape.StyleMode]
        StyleMode_StrokeAndFill: _ClassVar[DrawnShape.StyleMode]
    StyleMode_Unspecified: DrawnShape.StyleMode
    StyleMode_StrokeOnly: DrawnShape.StyleMode
    StyleMode_FillOnly: DrawnShape.StyleMode
    StyleMode_StrokeAndFill: DrawnShape.StyleMode
    KIND_FIELD_NUMBER: _ClassVar[int]
    STYLE_FIELD_NUMBER: _ClassVar[int]
    MAJOR_CM_FIELD_NUMBER: _ClassVar[int]
    MINOR_CM_FIELD_NUMBER: _ClassVar[int]
    ANGLE_DEG_FIELD_NUMBER: _ClassVar[int]
    STROKE_COLOR_FIELD_NUMBER: _ClassVar[int]
    STROKE_ARGB_FIELD_NUMBER: _ClassVar[int]
    STROKE_WEIGHT_X10_FIELD_NUMBER: _ClassVar[int]
    FILL_COLOR_FIELD_NUMBER: _ClassVar[int]
    FILL_ARGB_FIELD_NUMBER: _ClassVar[int]
    LABELS_ON_FIELD_NUMBER: _ClassVar[int]
    VERTEX_LAT_DELTAS_FIELD_NUMBER: _ClassVar[int]
    VERTEX_LON_DELTAS_FIELD_NUMBER: _ClassVar[int]
    TRUNCATED_FIELD_NUMBER: _ClassVar[int]
    BULLSEYE_DISTANCE_DM_FIELD_NUMBER: _ClassVar[int]
    BULLSEYE_BEARING_REF_FIELD_NUMBER: _ClassVar[int]
    BULLSEYE_FLAGS_FIELD_NUMBER: _ClassVar[int]
    BULLSEYE_UID_REF_FIELD_NUMBER: _ClassVar[int]
    kind: DrawnShape.Kind
    style: DrawnShape.StyleMode
    major_cm: int
    minor_cm: int
    angle_deg: int
    stroke_color: Team
    stroke_argb: int
    stroke_weight_x10: int
    fill_color: Team
    fill_argb: int
    labels_on: bool
    vertex_lat_deltas: _containers.RepeatedScalarFieldContainer[int]
    vertex_lon_deltas: _containers.RepeatedScalarFieldContainer[int]
    truncated: bool
    bullseye_distance_dm: int
    bullseye_bearing_ref: int
    bullseye_flags: int
    bullseye_uid_ref: str
    def __init__(self, kind: _Optional[_Union[DrawnShape.Kind, str]] = ..., style: _Optional[_Union[DrawnShape.StyleMode, str]] = ..., major_cm: _Optional[int] = ..., minor_cm: _Optional[int] = ..., angle_deg: _Optional[int] = ..., stroke_color: _Optional[_Union[Team, str]] = ..., stroke_argb: _Optional[int] = ..., stroke_weight_x10: _Optional[int] = ..., fill_color: _Optional[_Union[Team, str]] = ..., fill_argb: _Optional[int] = ..., labels_on: bool = ..., vertex_lat_deltas: _Optional[_Iterable[int]] = ..., vertex_lon_deltas: _Optional[_Iterable[int]] = ..., truncated: bool = ..., bullseye_distance_dm: _Optional[int] = ..., bullseye_bearing_ref: _Optional[int] = ..., bullseye_flags: _Optional[int] = ..., bullseye_uid_ref: _Optional[str] = ...) -> None: ...

class Marker(_message.Message):
    __slots__ = ("kind", "color", "color_argb", "readiness", "parent_uid", "parent_type", "parent_callsign", "iconset")
    class Kind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        Kind_Unspecified: _ClassVar[Marker.Kind]
        Kind_Spot: _ClassVar[Marker.Kind]
        Kind_Waypoint: _ClassVar[Marker.Kind]
        Kind_Checkpoint: _ClassVar[Marker.Kind]
        Kind_SelfPosition: _ClassVar[Marker.Kind]
        Kind_Symbol2525: _ClassVar[Marker.Kind]
        Kind_SpotMap: _ClassVar[Marker.Kind]
        Kind_CustomIcon: _ClassVar[Marker.Kind]
        Kind_GoToPoint: _ClassVar[Marker.Kind]
        Kind_InitialPoint: _ClassVar[Marker.Kind]
        Kind_ContactPoint: _ClassVar[Marker.Kind]
        Kind_ObservationPost: _ClassVar[Marker.Kind]
        Kind_ImageMarker: _ClassVar[Marker.Kind]
    Kind_Unspecified: Marker.Kind
    Kind_Spot: Marker.Kind
    Kind_Waypoint: Marker.Kind
    Kind_Checkpoint: Marker.Kind
    Kind_SelfPosition: Marker.Kind
    Kind_Symbol2525: Marker.Kind
    Kind_SpotMap: Marker.Kind
    Kind_CustomIcon: Marker.Kind
    Kind_GoToPoint: Marker.Kind
    Kind_InitialPoint: Marker.Kind
    Kind_ContactPoint: Marker.Kind
    Kind_ObservationPost: Marker.Kind
    Kind_ImageMarker: Marker.Kind
    KIND_FIELD_NUMBER: _ClassVar[int]
    COLOR_FIELD_NUMBER: _ClassVar[int]
    COLOR_ARGB_FIELD_NUMBER: _ClassVar[int]
    READINESS_FIELD_NUMBER: _ClassVar[int]
    PARENT_UID_FIELD_NUMBER: _ClassVar[int]
    PARENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    PARENT_CALLSIGN_FIELD_NUMBER: _ClassVar[int]
    ICONSET_FIELD_NUMBER: _ClassVar[int]
    kind: Marker.Kind
    color: Team
    color_argb: int
    readiness: bool
    parent_uid: str
    parent_type: str
    parent_callsign: str
    iconset: str
    def __init__(self, kind: _Optional[_Union[Marker.Kind, str]] = ..., color: _Optional[_Union[Team, str]] = ..., color_argb: _Optional[int] = ..., readiness: bool = ..., parent_uid: _Optional[str] = ..., parent_type: _Optional[str] = ..., parent_callsign: _Optional[str] = ..., iconset: _Optional[str] = ...) -> None: ...

class RangeAndBearing(_message.Message):
    __slots__ = ("anchor", "anchor_uid", "range_cm", "bearing_cdeg", "stroke_color", "stroke_argb", "stroke_weight_x10")
    ANCHOR_FIELD_NUMBER: _ClassVar[int]
    ANCHOR_UID_FIELD_NUMBER: _ClassVar[int]
    RANGE_CM_FIELD_NUMBER: _ClassVar[int]
    BEARING_CDEG_FIELD_NUMBER: _ClassVar[int]
    STROKE_COLOR_FIELD_NUMBER: _ClassVar[int]
    STROKE_ARGB_FIELD_NUMBER: _ClassVar[int]
    STROKE_WEIGHT_X10_FIELD_NUMBER: _ClassVar[int]
    anchor: CotGeoPoint
    anchor_uid: str
    range_cm: int
    bearing_cdeg: int
    stroke_color: Team
    stroke_argb: int
    stroke_weight_x10: int
    def __init__(self, anchor: _Optional[_Union[CotGeoPoint, _Mapping]] = ..., anchor_uid: _Optional[str] = ..., range_cm: _Optional[int] = ..., bearing_cdeg: _Optional[int] = ..., stroke_color: _Optional[_Union[Team, str]] = ..., stroke_argb: _Optional[int] = ..., stroke_weight_x10: _Optional[int] = ...) -> None: ...

class Route(_message.Message):
    __slots__ = ("method", "direction", "prefix", "stroke_weight_x10", "links", "truncated")
    class Method(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        Method_Unspecified: _ClassVar[Route.Method]
        Method_Driving: _ClassVar[Route.Method]
        Method_Walking: _ClassVar[Route.Method]
        Method_Flying: _ClassVar[Route.Method]
        Method_Swimming: _ClassVar[Route.Method]
        Method_Watercraft: _ClassVar[Route.Method]
    Method_Unspecified: Route.Method
    Method_Driving: Route.Method
    Method_Walking: Route.Method
    Method_Flying: Route.Method
    Method_Swimming: Route.Method
    Method_Watercraft: Route.Method
    class Direction(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        Direction_Unspecified: _ClassVar[Route.Direction]
        Direction_Infil: _ClassVar[Route.Direction]
        Direction_Exfil: _ClassVar[Route.Direction]
    Direction_Unspecified: Route.Direction
    Direction_Infil: Route.Direction
    Direction_Exfil: Route.Direction
    class Link(_message.Message):
        __slots__ = ("point", "uid", "callsign", "link_type")
        POINT_FIELD_NUMBER: _ClassVar[int]
        UID_FIELD_NUMBER: _ClassVar[int]
        CALLSIGN_FIELD_NUMBER: _ClassVar[int]
        LINK_TYPE_FIELD_NUMBER: _ClassVar[int]
        point: CotGeoPoint
        uid: str
        callsign: str
        link_type: int
        def __init__(self, point: _Optional[_Union[CotGeoPoint, _Mapping]] = ..., uid: _Optional[str] = ..., callsign: _Optional[str] = ..., link_type: _Optional[int] = ...) -> None: ...
    METHOD_FIELD_NUMBER: _ClassVar[int]
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    PREFIX_FIELD_NUMBER: _ClassVar[int]
    STROKE_WEIGHT_X10_FIELD_NUMBER: _ClassVar[int]
    LINKS_FIELD_NUMBER: _ClassVar[int]
    TRUNCATED_FIELD_NUMBER: _ClassVar[int]
    method: Route.Method
    direction: Route.Direction
    prefix: str
    stroke_weight_x10: int
    links: _containers.RepeatedCompositeFieldContainer[Route.Link]
    truncated: bool
    def __init__(self, method: _Optional[_Union[Route.Method, str]] = ..., direction: _Optional[_Union[Route.Direction, str]] = ..., prefix: _Optional[str] = ..., stroke_weight_x10: _Optional[int] = ..., links: _Optional[_Iterable[_Union[Route.Link, _Mapping]]] = ..., truncated: bool = ...) -> None: ...

class CasevacReport(_message.Message):
    __slots__ = ("precedence", "equipment_flags", "litter_patients", "ambulatory_patients", "security", "hlz_marking", "zone_marker", "us_military", "us_civilian", "non_us_military", "non_us_civilian", "epw", "child", "terrain_flags", "frequency", "title", "medline_remarks", "urgent_count", "urgent_surgical_count", "priority_count", "routine_count", "convenience_count", "equipment_detail", "zone_protected_coord", "terrain_slope_dir", "terrain_other_detail", "marked_by", "obstacles", "winds_are_from", "friendlies", "enemy", "hlz_remarks", "zmist")
    class Precedence(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        Precedence_Unspecified: _ClassVar[CasevacReport.Precedence]
        Precedence_Urgent: _ClassVar[CasevacReport.Precedence]
        Precedence_UrgentSurgical: _ClassVar[CasevacReport.Precedence]
        Precedence_Priority: _ClassVar[CasevacReport.Precedence]
        Precedence_Routine: _ClassVar[CasevacReport.Precedence]
        Precedence_Convenience: _ClassVar[CasevacReport.Precedence]
    Precedence_Unspecified: CasevacReport.Precedence
    Precedence_Urgent: CasevacReport.Precedence
    Precedence_UrgentSurgical: CasevacReport.Precedence
    Precedence_Priority: CasevacReport.Precedence
    Precedence_Routine: CasevacReport.Precedence
    Precedence_Convenience: CasevacReport.Precedence
    class HlzMarking(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        HlzMarking_Unspecified: _ClassVar[CasevacReport.HlzMarking]
        HlzMarking_Panels: _ClassVar[CasevacReport.HlzMarking]
        HlzMarking_PyroSignal: _ClassVar[CasevacReport.HlzMarking]
        HlzMarking_Smoke: _ClassVar[CasevacReport.HlzMarking]
        HlzMarking_None: _ClassVar[CasevacReport.HlzMarking]
        HlzMarking_Other: _ClassVar[CasevacReport.HlzMarking]
    HlzMarking_Unspecified: CasevacReport.HlzMarking
    HlzMarking_Panels: CasevacReport.HlzMarking
    HlzMarking_PyroSignal: CasevacReport.HlzMarking
    HlzMarking_Smoke: CasevacReport.HlzMarking
    HlzMarking_None: CasevacReport.HlzMarking
    HlzMarking_Other: CasevacReport.HlzMarking
    class Security(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        Security_Unspecified: _ClassVar[CasevacReport.Security]
        Security_NoEnemy: _ClassVar[CasevacReport.Security]
        Security_PossibleEnemy: _ClassVar[CasevacReport.Security]
        Security_EnemyInArea: _ClassVar[CasevacReport.Security]
        Security_EnemyInArmedContact: _ClassVar[CasevacReport.Security]
    Security_Unspecified: CasevacReport.Security
    Security_NoEnemy: CasevacReport.Security
    Security_PossibleEnemy: CasevacReport.Security
    Security_EnemyInArea: CasevacReport.Security
    Security_EnemyInArmedContact: CasevacReport.Security
    PRECEDENCE_FIELD_NUMBER: _ClassVar[int]
    EQUIPMENT_FLAGS_FIELD_NUMBER: _ClassVar[int]
    LITTER_PATIENTS_FIELD_NUMBER: _ClassVar[int]
    AMBULATORY_PATIENTS_FIELD_NUMBER: _ClassVar[int]
    SECURITY_FIELD_NUMBER: _ClassVar[int]
    HLZ_MARKING_FIELD_NUMBER: _ClassVar[int]
    ZONE_MARKER_FIELD_NUMBER: _ClassVar[int]
    US_MILITARY_FIELD_NUMBER: _ClassVar[int]
    US_CIVILIAN_FIELD_NUMBER: _ClassVar[int]
    NON_US_MILITARY_FIELD_NUMBER: _ClassVar[int]
    NON_US_CIVILIAN_FIELD_NUMBER: _ClassVar[int]
    EPW_FIELD_NUMBER: _ClassVar[int]
    CHILD_FIELD_NUMBER: _ClassVar[int]
    TERRAIN_FLAGS_FIELD_NUMBER: _ClassVar[int]
    FREQUENCY_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    MEDLINE_REMARKS_FIELD_NUMBER: _ClassVar[int]
    URGENT_COUNT_FIELD_NUMBER: _ClassVar[int]
    URGENT_SURGICAL_COUNT_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_COUNT_FIELD_NUMBER: _ClassVar[int]
    ROUTINE_COUNT_FIELD_NUMBER: _ClassVar[int]
    CONVENIENCE_COUNT_FIELD_NUMBER: _ClassVar[int]
    EQUIPMENT_DETAIL_FIELD_NUMBER: _ClassVar[int]
    ZONE_PROTECTED_COORD_FIELD_NUMBER: _ClassVar[int]
    TERRAIN_SLOPE_DIR_FIELD_NUMBER: _ClassVar[int]
    TERRAIN_OTHER_DETAIL_FIELD_NUMBER: _ClassVar[int]
    MARKED_BY_FIELD_NUMBER: _ClassVar[int]
    OBSTACLES_FIELD_NUMBER: _ClassVar[int]
    WINDS_ARE_FROM_FIELD_NUMBER: _ClassVar[int]
    FRIENDLIES_FIELD_NUMBER: _ClassVar[int]
    ENEMY_FIELD_NUMBER: _ClassVar[int]
    HLZ_REMARKS_FIELD_NUMBER: _ClassVar[int]
    ZMIST_FIELD_NUMBER: _ClassVar[int]
    precedence: CasevacReport.Precedence
    equipment_flags: int
    litter_patients: int
    ambulatory_patients: int
    security: CasevacReport.Security
    hlz_marking: CasevacReport.HlzMarking
    zone_marker: str
    us_military: int
    us_civilian: int
    non_us_military: int
    non_us_civilian: int
    epw: int
    child: int
    terrain_flags: int
    frequency: str
    title: str
    medline_remarks: str
    urgent_count: int
    urgent_surgical_count: int
    priority_count: int
    routine_count: int
    convenience_count: int
    equipment_detail: str
    zone_protected_coord: str
    terrain_slope_dir: str
    terrain_other_detail: str
    marked_by: str
    obstacles: str
    winds_are_from: str
    friendlies: str
    enemy: str
    hlz_remarks: str
    zmist: _containers.RepeatedCompositeFieldContainer[ZMistEntry]
    def __init__(self, precedence: _Optional[_Union[CasevacReport.Precedence, str]] = ..., equipment_flags: _Optional[int] = ..., litter_patients: _Optional[int] = ..., ambulatory_patients: _Optional[int] = ..., security: _Optional[_Union[CasevacReport.Security, str]] = ..., hlz_marking: _Optional[_Union[CasevacReport.HlzMarking, str]] = ..., zone_marker: _Optional[str] = ..., us_military: _Optional[int] = ..., us_civilian: _Optional[int] = ..., non_us_military: _Optional[int] = ..., non_us_civilian: _Optional[int] = ..., epw: _Optional[int] = ..., child: _Optional[int] = ..., terrain_flags: _Optional[int] = ..., frequency: _Optional[str] = ..., title: _Optional[str] = ..., medline_remarks: _Optional[str] = ..., urgent_count: _Optional[int] = ..., urgent_surgical_count: _Optional[int] = ..., priority_count: _Optional[int] = ..., routine_count: _Optional[int] = ..., convenience_count: _Optional[int] = ..., equipment_detail: _Optional[str] = ..., zone_protected_coord: _Optional[str] = ..., terrain_slope_dir: _Optional[str] = ..., terrain_other_detail: _Optional[str] = ..., marked_by: _Optional[str] = ..., obstacles: _Optional[str] = ..., winds_are_from: _Optional[str] = ..., friendlies: _Optional[str] = ..., enemy: _Optional[str] = ..., hlz_remarks: _Optional[str] = ..., zmist: _Optional[_Iterable[_Union[ZMistEntry, _Mapping]]] = ...) -> None: ...

class ZMistEntry(_message.Message):
    __slots__ = ("title", "z", "m", "i", "s", "t")
    TITLE_FIELD_NUMBER: _ClassVar[int]
    Z_FIELD_NUMBER: _ClassVar[int]
    M_FIELD_NUMBER: _ClassVar[int]
    I_FIELD_NUMBER: _ClassVar[int]
    S_FIELD_NUMBER: _ClassVar[int]
    T_FIELD_NUMBER: _ClassVar[int]
    title: str
    z: str
    m: str
    i: str
    s: str
    t: str
    def __init__(self, title: _Optional[str] = ..., z: _Optional[str] = ..., m: _Optional[str] = ..., i: _Optional[str] = ..., s: _Optional[str] = ..., t: _Optional[str] = ...) -> None: ...

class EmergencyAlert(_message.Message):
    __slots__ = ("type", "authoring_uid", "cancel_reference_uid")
    class Type(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        Type_Unspecified: _ClassVar[EmergencyAlert.Type]
        Type_Alert911: _ClassVar[EmergencyAlert.Type]
        Type_RingTheBell: _ClassVar[EmergencyAlert.Type]
        Type_InContact: _ClassVar[EmergencyAlert.Type]
        Type_GeoFenceBreached: _ClassVar[EmergencyAlert.Type]
        Type_Custom: _ClassVar[EmergencyAlert.Type]
        Type_Cancel: _ClassVar[EmergencyAlert.Type]
    Type_Unspecified: EmergencyAlert.Type
    Type_Alert911: EmergencyAlert.Type
    Type_RingTheBell: EmergencyAlert.Type
    Type_InContact: EmergencyAlert.Type
    Type_GeoFenceBreached: EmergencyAlert.Type
    Type_Custom: EmergencyAlert.Type
    Type_Cancel: EmergencyAlert.Type
    TYPE_FIELD_NUMBER: _ClassVar[int]
    AUTHORING_UID_FIELD_NUMBER: _ClassVar[int]
    CANCEL_REFERENCE_UID_FIELD_NUMBER: _ClassVar[int]
    type: EmergencyAlert.Type
    authoring_uid: str
    cancel_reference_uid: str
    def __init__(self, type: _Optional[_Union[EmergencyAlert.Type, str]] = ..., authoring_uid: _Optional[str] = ..., cancel_reference_uid: _Optional[str] = ...) -> None: ...

class TaskRequest(_message.Message):
    __slots__ = ("task_type", "target_uid", "assignee_uid", "priority", "status", "note")
    class Priority(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        Priority_Unspecified: _ClassVar[TaskRequest.Priority]
        Priority_Low: _ClassVar[TaskRequest.Priority]
        Priority_Normal: _ClassVar[TaskRequest.Priority]
        Priority_High: _ClassVar[TaskRequest.Priority]
        Priority_Critical: _ClassVar[TaskRequest.Priority]
    Priority_Unspecified: TaskRequest.Priority
    Priority_Low: TaskRequest.Priority
    Priority_Normal: TaskRequest.Priority
    Priority_High: TaskRequest.Priority
    Priority_Critical: TaskRequest.Priority
    class Status(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        Status_Unspecified: _ClassVar[TaskRequest.Status]
        Status_Pending: _ClassVar[TaskRequest.Status]
        Status_Acknowledged: _ClassVar[TaskRequest.Status]
        Status_InProgress: _ClassVar[TaskRequest.Status]
        Status_Completed: _ClassVar[TaskRequest.Status]
        Status_Cancelled: _ClassVar[TaskRequest.Status]
    Status_Unspecified: TaskRequest.Status
    Status_Pending: TaskRequest.Status
    Status_Acknowledged: TaskRequest.Status
    Status_InProgress: TaskRequest.Status
    Status_Completed: TaskRequest.Status
    Status_Cancelled: TaskRequest.Status
    TASK_TYPE_FIELD_NUMBER: _ClassVar[int]
    TARGET_UID_FIELD_NUMBER: _ClassVar[int]
    ASSIGNEE_UID_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    NOTE_FIELD_NUMBER: _ClassVar[int]
    task_type: str
    target_uid: str
    assignee_uid: str
    priority: TaskRequest.Priority
    status: TaskRequest.Status
    note: str
    def __init__(self, task_type: _Optional[str] = ..., target_uid: _Optional[str] = ..., assignee_uid: _Optional[str] = ..., priority: _Optional[_Union[TaskRequest.Priority, str]] = ..., status: _Optional[_Union[TaskRequest.Status, str]] = ..., note: _Optional[str] = ...) -> None: ...

class TAKEnvironment(_message.Message):
    __slots__ = ("temperature_c_x10", "wind_direction_deg", "wind_speed_cm_s")
    TEMPERATURE_C_X10_FIELD_NUMBER: _ClassVar[int]
    WIND_DIRECTION_DEG_FIELD_NUMBER: _ClassVar[int]
    WIND_SPEED_CM_S_FIELD_NUMBER: _ClassVar[int]
    temperature_c_x10: int
    wind_direction_deg: int
    wind_speed_cm_s: int
    def __init__(self, temperature_c_x10: _Optional[int] = ..., wind_direction_deg: _Optional[int] = ..., wind_speed_cm_s: _Optional[int] = ...) -> None: ...

class SensorFov(_message.Message):
    __slots__ = ("type", "azimuth_deg", "range_m", "fov_horizontal_deg", "fov_vertical_deg", "elevation_deg", "roll_deg", "model")
    class SensorType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        SensorType_Unspecified: _ClassVar[SensorFov.SensorType]
        SensorType_Camera: _ClassVar[SensorFov.SensorType]
        SensorType_Thermal: _ClassVar[SensorFov.SensorType]
        SensorType_Laser: _ClassVar[SensorFov.SensorType]
        SensorType_Nvg: _ClassVar[SensorFov.SensorType]
        SensorType_Rf: _ClassVar[SensorFov.SensorType]
        SensorType_Other: _ClassVar[SensorFov.SensorType]
    SensorType_Unspecified: SensorFov.SensorType
    SensorType_Camera: SensorFov.SensorType
    SensorType_Thermal: SensorFov.SensorType
    SensorType_Laser: SensorFov.SensorType
    SensorType_Nvg: SensorFov.SensorType
    SensorType_Rf: SensorFov.SensorType
    SensorType_Other: SensorFov.SensorType
    TYPE_FIELD_NUMBER: _ClassVar[int]
    AZIMUTH_DEG_FIELD_NUMBER: _ClassVar[int]
    RANGE_M_FIELD_NUMBER: _ClassVar[int]
    FOV_HORIZONTAL_DEG_FIELD_NUMBER: _ClassVar[int]
    FOV_VERTICAL_DEG_FIELD_NUMBER: _ClassVar[int]
    ELEVATION_DEG_FIELD_NUMBER: _ClassVar[int]
    ROLL_DEG_FIELD_NUMBER: _ClassVar[int]
    MODEL_FIELD_NUMBER: _ClassVar[int]
    type: SensorFov.SensorType
    azimuth_deg: int
    range_m: int
    fov_horizontal_deg: int
    fov_vertical_deg: int
    elevation_deg: int
    roll_deg: int
    model: str
    def __init__(self, type: _Optional[_Union[SensorFov.SensorType, str]] = ..., azimuth_deg: _Optional[int] = ..., range_m: _Optional[int] = ..., fov_horizontal_deg: _Optional[int] = ..., fov_vertical_deg: _Optional[int] = ..., elevation_deg: _Optional[int] = ..., roll_deg: _Optional[int] = ..., model: _Optional[str] = ...) -> None: ...

class TakTalkMessage(_message.Message):
    __slots__ = ("text", "chatroom_id", "lang", "from_voice")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    CHATROOM_ID_FIELD_NUMBER: _ClassVar[int]
    LANG_FIELD_NUMBER: _ClassVar[int]
    FROM_VOICE_FIELD_NUMBER: _ClassVar[int]
    text: str
    chatroom_id: str
    lang: str
    from_voice: bool
    def __init__(self, text: _Optional[str] = ..., chatroom_id: _Optional[str] = ..., lang: _Optional[str] = ..., from_voice: bool = ...) -> None: ...

class TakTalkRoomData(_message.Message):
    __slots__ = ("sender_callsign", "room_id", "room_name", "participants")
    SENDER_CALLSIGN_FIELD_NUMBER: _ClassVar[int]
    ROOM_ID_FIELD_NUMBER: _ClassVar[int]
    ROOM_NAME_FIELD_NUMBER: _ClassVar[int]
    PARTICIPANTS_FIELD_NUMBER: _ClassVar[int]
    sender_callsign: str
    room_id: str
    room_name: str
    participants: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, sender_callsign: _Optional[str] = ..., room_id: _Optional[str] = ..., room_name: _Optional[str] = ..., participants: _Optional[_Iterable[str]] = ...) -> None: ...

class Marti(_message.Message):
    __slots__ = ("dest_callsign",)
    DEST_CALLSIGN_FIELD_NUMBER: _ClassVar[int]
    dest_callsign: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, dest_callsign: _Optional[_Iterable[str]] = ...) -> None: ...

class TAKPacketV2(_message.Message):
    __slots__ = ("cot_type_id", "how", "callsign", "team", "role", "latitude_i", "longitude_i", "altitude", "speed", "course", "battery", "geo_src", "alt_src", "uid", "device_callsign", "stale_seconds", "tak_version", "tak_device", "tak_platform", "tak_os", "endpoint", "phone", "cot_type_str", "remarks", "environment", "sensor_fov", "marti", "chat", "aircraft", "raw_detail", "shape", "marker", "rab", "route", "casevac", "emergency", "task", "taktalk", "taktalk_room")
    COT_TYPE_ID_FIELD_NUMBER: _ClassVar[int]
    HOW_FIELD_NUMBER: _ClassVar[int]
    CALLSIGN_FIELD_NUMBER: _ClassVar[int]
    TEAM_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    LATITUDE_I_FIELD_NUMBER: _ClassVar[int]
    LONGITUDE_I_FIELD_NUMBER: _ClassVar[int]
    ALTITUDE_FIELD_NUMBER: _ClassVar[int]
    SPEED_FIELD_NUMBER: _ClassVar[int]
    COURSE_FIELD_NUMBER: _ClassVar[int]
    BATTERY_FIELD_NUMBER: _ClassVar[int]
    GEO_SRC_FIELD_NUMBER: _ClassVar[int]
    ALT_SRC_FIELD_NUMBER: _ClassVar[int]
    UID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_CALLSIGN_FIELD_NUMBER: _ClassVar[int]
    STALE_SECONDS_FIELD_NUMBER: _ClassVar[int]
    TAK_VERSION_FIELD_NUMBER: _ClassVar[int]
    TAK_DEVICE_FIELD_NUMBER: _ClassVar[int]
    TAK_PLATFORM_FIELD_NUMBER: _ClassVar[int]
    TAK_OS_FIELD_NUMBER: _ClassVar[int]
    ENDPOINT_FIELD_NUMBER: _ClassVar[int]
    PHONE_FIELD_NUMBER: _ClassVar[int]
    COT_TYPE_STR_FIELD_NUMBER: _ClassVar[int]
    REMARKS_FIELD_NUMBER: _ClassVar[int]
    ENVIRONMENT_FIELD_NUMBER: _ClassVar[int]
    SENSOR_FOV_FIELD_NUMBER: _ClassVar[int]
    MARTI_FIELD_NUMBER: _ClassVar[int]
    CHAT_FIELD_NUMBER: _ClassVar[int]
    AIRCRAFT_FIELD_NUMBER: _ClassVar[int]
    RAW_DETAIL_FIELD_NUMBER: _ClassVar[int]
    SHAPE_FIELD_NUMBER: _ClassVar[int]
    MARKER_FIELD_NUMBER: _ClassVar[int]
    RAB_FIELD_NUMBER: _ClassVar[int]
    ROUTE_FIELD_NUMBER: _ClassVar[int]
    CASEVAC_FIELD_NUMBER: _ClassVar[int]
    EMERGENCY_FIELD_NUMBER: _ClassVar[int]
    TASK_FIELD_NUMBER: _ClassVar[int]
    TAKTALK_FIELD_NUMBER: _ClassVar[int]
    TAKTALK_ROOM_FIELD_NUMBER: _ClassVar[int]
    cot_type_id: CotType
    how: CotHow
    callsign: str
    team: Team
    role: MemberRole
    latitude_i: int
    longitude_i: int
    altitude: int
    speed: int
    course: int
    battery: int
    geo_src: GeoPointSource
    alt_src: GeoPointSource
    uid: str
    device_callsign: str
    stale_seconds: int
    tak_version: str
    tak_device: str
    tak_platform: str
    tak_os: str
    endpoint: str
    phone: str
    cot_type_str: str
    remarks: str
    environment: TAKEnvironment
    sensor_fov: SensorFov
    marti: Marti
    chat: GeoChat
    aircraft: AircraftTrack
    raw_detail: bytes
    shape: DrawnShape
    marker: Marker
    rab: RangeAndBearing
    route: Route
    casevac: CasevacReport
    emergency: EmergencyAlert
    task: TaskRequest
    taktalk: TakTalkMessage
    taktalk_room: TakTalkRoomData
    def __init__(self, cot_type_id: _Optional[_Union[CotType, str]] = ..., how: _Optional[_Union[CotHow, str]] = ..., callsign: _Optional[str] = ..., team: _Optional[_Union[Team, str]] = ..., role: _Optional[_Union[MemberRole, str]] = ..., latitude_i: _Optional[int] = ..., longitude_i: _Optional[int] = ..., altitude: _Optional[int] = ..., speed: _Optional[int] = ..., course: _Optional[int] = ..., battery: _Optional[int] = ..., geo_src: _Optional[_Union[GeoPointSource, str]] = ..., alt_src: _Optional[_Union[GeoPointSource, str]] = ..., uid: _Optional[str] = ..., device_callsign: _Optional[str] = ..., stale_seconds: _Optional[int] = ..., tak_version: _Optional[str] = ..., tak_device: _Optional[str] = ..., tak_platform: _Optional[str] = ..., tak_os: _Optional[str] = ..., endpoint: _Optional[str] = ..., phone: _Optional[str] = ..., cot_type_str: _Optional[str] = ..., remarks: _Optional[str] = ..., environment: _Optional[_Union[TAKEnvironment, _Mapping]] = ..., sensor_fov: _Optional[_Union[SensorFov, _Mapping]] = ..., marti: _Optional[_Union[Marti, _Mapping]] = ..., chat: _Optional[_Union[GeoChat, _Mapping]] = ..., aircraft: _Optional[_Union[AircraftTrack, _Mapping]] = ..., raw_detail: _Optional[bytes] = ..., shape: _Optional[_Union[DrawnShape, _Mapping]] = ..., marker: _Optional[_Union[Marker, _Mapping]] = ..., rab: _Optional[_Union[RangeAndBearing, _Mapping]] = ..., route: _Optional[_Union[Route, _Mapping]] = ..., casevac: _Optional[_Union[CasevacReport, _Mapping]] = ..., emergency: _Optional[_Union[EmergencyAlert, _Mapping]] = ..., task: _Optional[_Union[TaskRequest, _Mapping]] = ..., taktalk: _Optional[_Union[TakTalkMessage, _Mapping]] = ..., taktalk_room: _Optional[_Union[TakTalkRoomData, _Mapping]] = ...) -> None: ...
