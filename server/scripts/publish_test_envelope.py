#!/usr/bin/env python3
"""Publish a Meshtastic raw envelope onto a Kafka topic"""
import argparse
import base64
import os

from kafka import KafkaProducer

from mesh_things import protocols
from mesh_things.codec import encrypt_packet


def build_telemetry_data(proto, battery_level=None, voltage=None, temperature=None, solar_irradiance=None) -> bytes:
    tel = proto.telemetry_pb2.Telemetry()
    if solar_irradiance is not None:
        tel.soil_water_metrics.solar_irradiance = solar_irradiance
    elif temperature is not None:
        tel.environment_metrics.temperature = temperature
    else:
        if battery_level is not None:
            tel.device_metrics.battery_level = battery_level
        if voltage is not None:
            tel.device_metrics.voltage = voltage

    data = proto.mesh_pb2.Data()
    data.portnum = 67  # TELEMETRY_APP
    data.payload = tel.SerializeToString()
    return data.SerializeToString()


def build_position_data(proto, latitude: float, longitude: float, altitude: float | None) -> bytes:
    pos = proto.mesh_pb2.Position()
    pos.latitude_i = int(latitude * 1e7)
    pos.longitude_i = int(longitude * 1e7)
    if altitude is not None:
        pos.altitude = int(altitude)

    data = proto.mesh_pb2.Data()
    data.portnum = 3  # POSITION_APP
    data.payload = pos.SerializeToString()
    return data.SerializeToString()


def build_nodeinfo_data(proto, long_name: str, short_name: str) -> bytes:
    user = proto.mesh_pb2.User()
    user.long_name = long_name
    user.short_name = short_name

    data = proto.mesh_pb2.Data()
    data.portnum = 4  # NODEINFO_APP
    data.payload = user.SerializeToString()
    return data.SerializeToString()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bootstrap", default=os.environ.get("KAFKA_BOOTSTRAP_LOCAL", "localhost:9092"))
    parser.add_argument("--topic", default=os.environ.get("MQTT_BRIDGE__KAFKA_TOPIC", "mesh.telemetry.raw.v1"))
    parser.add_argument("--kind", choices=["telemetry", "position", "nodeinfo"], default="telemetry")
    parser.add_argument(
        "--protocol", choices=sorted(protocols.VERSIONS), default=protocols.CANONICAL,
        help="Meshtastic protocol version to build the packet with",
    )
    parser.add_argument("--node-id", type=int, required=True)
    parser.add_argument("--packet-id", type=int, default=1)
    parser.add_argument("--channel-id", default="LongFast")
    parser.add_argument("--gateway-id", default="!testgw")
    parser.add_argument("--rx-time", type=int, default=0)
    parser.add_argument(
        "--encrypt-with-key",
        dest="key_b64",
        default=None,
        help="base64 AES key; if set, the packet is sent AES-CTR encrypted instead of plaintext-decoded",
    )
    parser.add_argument("--battery-level", type=int, default=87)
    parser.add_argument("--voltage", type=float, default=None)
    parser.add_argument("--temperature", type=float, default=None, help="sets environment_metrics instead of device_metrics")
    parser.add_argument(
        "--solar-irradiance", type=float, default=None, help="W/m2; sets soil_water_metrics, which needs --protocol 2.8"
    )
    parser.add_argument("--latitude", type=float, default=41.3851)
    parser.add_argument("--longitude", type=float, default=2.1734)
    parser.add_argument("--altitude", type=float, default=50)
    parser.add_argument("--long-name", default="Test Node")
    parser.add_argument("--short-name", default="TST")
    args = parser.parse_args()

    proto = protocols.get(args.protocol)
    if args.solar_irradiance is not None and not hasattr(proto.telemetry_pb2, "SoilWaterMetrics"):
        parser.error(f"protocol {args.protocol} has no soil_water_metrics")
    if args.kind == "telemetry":
        data_bytes = build_telemetry_data(
            proto, args.battery_level, args.voltage, args.temperature, args.solar_irradiance
        )
    elif args.kind == "position":
        data_bytes = build_position_data(proto, args.latitude, args.longitude, args.altitude)
    else:
        data_bytes = build_nodeinfo_data(proto, args.long_name, args.short_name)

    mp = proto.mesh_pb2.MeshPacket()
    mp.id = args.packet_id
    setattr(mp, "from", args.node_id)
    mp.rx_time = args.rx_time
    mp.hop_start = 1

    if args.key_b64:
        mp.encrypted = encrypt_packet(data_bytes, args.packet_id, args.node_id, base64.b64decode(args.key_b64))
    else:
        data = proto.mesh_pb2.Data()
        data.ParseFromString(data_bytes)
        mp.decoded.CopyFrom(data)

    se = proto.mqtt_pb2.ServiceEnvelope()
    se.packet.CopyFrom(mp)
    se.channel_id = args.channel_id
    se.gateway_id = args.gateway_id
    raw = se.SerializeToString()

    producer = KafkaProducer(bootstrap_servers=args.bootstrap)
    producer.send(args.topic, value=raw)
    producer.flush()

    print(
        f"Published {args.kind} envelope: node_id={args.node_id} packet_id={args.packet_id} "
        f"channel_id={args.channel_id} protocol={args.protocol} encrypted={bool(args.key_b64)} -> {args.topic} "
        f"({len(raw)} bytes) @ {args.bootstrap}"
    )


if __name__ == "__main__":
    main()
