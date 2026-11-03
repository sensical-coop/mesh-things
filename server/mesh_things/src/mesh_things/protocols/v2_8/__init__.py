"""Meshtastic protocol 2.8, generated from the protobufs tag in `_source`."""
from mesh_things.protocols.v2_8 import (
    admin_pb2,
    mesh_pb2,
    mqtt_pb2,
    paxcount_pb2,
    portnums_pb2,
    powermon_pb2,
    remote_hardware_pb2,
    storeforward_pb2,
    telemetry_pb2,
)
from mesh_things.protocols.v2_8._source import COMMIT, REF

PortNum = portnums_pb2.PortNum

# The portnums whose payload is a protobuf message. Text payloads have none.
PAYLOAD_MESSAGES = {
    PortNum.POSITION_APP: mesh_pb2.Position,
    PortNum.NODEINFO_APP: mesh_pb2.User,
    PortNum.ADMIN_APP: admin_pb2.AdminMessage,
    PortNum.ROUTING_APP: mesh_pb2.Routing,
    PortNum.TELEMETRY_APP: telemetry_pb2.Telemetry,
    PortNum.REMOTE_HARDWARE_APP: remote_hardware_pb2.HardwareMessage,
    PortNum.SIMULATOR_APP: mesh_pb2.Compressed,
    PortNum.TRACEROUTE_APP: mesh_pb2.RouteDiscovery,
    PortNum.POWERSTRESS_APP: powermon_pb2.PowerStressMessage,
    PortNum.WAYPOINT_APP: mesh_pb2.Waypoint,
    PortNum.PAXCOUNTER_APP: paxcount_pb2.Paxcount,
    PortNum.STORE_FORWARD_APP: storeforward_pb2.StoreAndForward,
    PortNum.NEIGHBORINFO_APP: mesh_pb2.NeighborInfo,
    PortNum.MAP_REPORT_APP: mqtt_pb2.MapReport,
}

__all__ = [
    "COMMIT",
    "PAYLOAD_MESSAGES",
    "REF",
    "PortNum",
    "admin_pb2",
    "mesh_pb2",
    "mqtt_pb2",
    "paxcount_pb2",
    "portnums_pb2",
    "powermon_pb2",
    "remote_hardware_pb2",
    "storeforward_pb2",
    "telemetry_pb2",
]
