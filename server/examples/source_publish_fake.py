#!/usr/bin/env python3
"""Publish fake environment readings to a source's broker, as a Meshtastic gateway would.

For development: point it at a test broker that a source reads (registry_create_source.py),
never at a public one. Each message is a real ServiceEnvelope protobuf carrying an
encrypted `environment_metrics` telemetry packet, published on
`{--topic-prefix}/{--channel}/!{gateway hex}`. The topic must fall under the source's
topic filter, and its last segment is the gateway the readings are decoded as.

For the readings to come out of the readings API:
  - the mesh is attached to the source (registry_attach_mesh_to_source.py) and its
    psk_b64 is the key used here (default AQ==, Meshtastic's default channel key), and
  - --gateway-id is registered as a gateway on that mesh (registry_create_gateway.py).
Without them the instance drops the packets silently, as it would a stranger's.
"""
import argparse
import os
import random
import secrets
import sys
import time

import paho.mqtt.client as mqtt
from meshtastic.protobuf import mesh_pb2, mqtt_pb2, portnums_pb2, telemetry_pb2

from mesh_things import node_ids
from mesh_things.codec import decode_psk, encrypt_packet


def environment_packet(node_id: int, key: bytes, temperature: float, humidity: float, pressure: float) -> mesh_pb2.MeshPacket:
    now = int(time.time())
    telemetry = telemetry_pb2.Telemetry(time=now)
    telemetry.environment_metrics.temperature = temperature
    telemetry.environment_metrics.relative_humidity = humidity
    telemetry.environment_metrics.barometric_pressure = pressure
    data = mesh_pb2.Data(portnum=portnums_pb2.TELEMETRY_APP, payload=telemetry.SerializeToString())

    packet = mesh_pb2.MeshPacket(id=secrets.randbits(32), rx_time=now, hop_start=3, hop_limit=3)
    setattr(packet, "from", node_id)
    packet.to = 0xFFFFFFFF
    packet.encrypted = encrypt_packet(data.SerializeToString(), packet.id, node_id, key)
    return packet


def parse_node(value: str) -> int:
    """A node number, as decimal or as Meshtastic's !aabbccdd."""
    number = node_ids.to_num(value) if value.startswith("!") else int(value)
    if number is None:
        raise argparse.ArgumentTypeError(f"not a node number: {value}")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--broker", default=os.environ.get("SOURCE_BROKER"), help="host:port of the source's broker")
    parser.add_argument("--username", default=os.environ.get("SOURCE_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("SOURCE_PASSWORD"))
    parser.add_argument("--no-ssl", action="store_true", help="connect without TLS")
    parser.add_argument("--topic-prefix", default="msh/EU_868/2/e", help="inside the source's topic filter")
    parser.add_argument("--channel", default="LongFast", help="channel name, the topic segment before the gateway")
    parser.add_argument("--psk-b64", default="AQ==", help="the mesh's psk_b64; AQ== is the Meshtastic default")
    parser.add_argument("--gateway-id", required=True, type=parse_node, help="registered gateway, decimal or !hex")
    parser.add_argument("--node-id", type=parse_node, help="sending node; defaults to the gateway itself")
    parser.add_argument("--count", type=int, default=1, help="readings to publish; 0 for no limit")
    parser.add_argument("--interval", type=float, default=10, help="seconds between readings")
    parser.add_argument("--temperature", type=float, default=21.0, help="degrees C, varied by up to 1 per reading")
    parser.add_argument("--humidity", type=float, default=55.0, help="percent, varied by up to 5 per reading")
    parser.add_argument("--pressure", type=float, default=1013.0, help="hPa, varied by up to 2 per reading")
    args = parser.parse_args()
    if not args.broker:
        sys.exit("--broker is required (or SOURCE_BROKER), as host:port")

    host, _, port = args.broker.rpartition(":")
    key = decode_psk(args.psk_b64)
    if key is None:
        sys.exit("A PSK of AA== means no encryption; pick another key")
    node_id = args.node_id if args.node_id is not None else args.gateway_id
    gateway = node_ids.to_hex(args.gateway_id)
    topic = f"{args.topic_prefix.rstrip('/')}/{args.channel}/{gateway}"

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"fake-gateway-{gateway[1:]}", protocol=mqtt.MQTTv5)
    if args.username:
        client.username_pw_set(args.username, args.password)
    if not args.no_ssl:
        client.tls_set()
    client.connect(host, int(port))
    client.loop_start()

    sent = 0
    try:
        while args.count == 0 or sent < args.count:
            readings = (
                round(args.temperature + random.uniform(-1, 1), 2),
                round(args.humidity + random.uniform(-5, 5), 1),
                round(args.pressure + random.uniform(-2, 2), 1),
            )
            envelope = mqtt_pb2.ServiceEnvelope(channel_id=args.channel, gateway_id=gateway)
            envelope.packet.CopyFrom(environment_packet(node_id, key, *readings))
            info = client.publish(topic, envelope.SerializeToString(), qos=1)
            info.wait_for_publish(timeout=10)
            sent += 1
            print(f"{topic}  node {node_id}  temperature={readings[0]} humidity={readings[1]} pressure={readings[2]}")
            if args.count == 0 or sent < args.count:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()
    print(f"Published {sent} reading(s)")


if __name__ == "__main__":
    main()
