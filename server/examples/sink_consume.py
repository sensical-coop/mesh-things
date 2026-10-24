#!/usr/bin/env python3
"""Subscribe to an MQTT sink as its consumer and print each reading or alarm.

This is the third party's side: it needs only the credentials registry_create_sink.py
printed, not an API key. Each message is one JSON object on
`{topic_filter without #}{stream}/{mesh_id}/{node_id}`. A persistent session
(--session-expiry) lets the broker queue messages while this is offline, up to its
queue limit. See docs/api-reference.md#consuming-a-sink.
"""
import argparse
import json
import os
import sys

import paho.mqtt.client as mqtt
from paho.mqtt.properties import Properties
from paho.mqtt.packettypes import PacketTypes


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--broker", default=os.environ.get("SINK_BROKER"), help="host:port, from the sink")
    parser.add_argument("--username", default=os.environ.get("SINK_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("SINK_PASSWORD"))
    parser.add_argument("--topic", default=os.environ.get("SINK_TOPIC_FILTER"), help="the sink's topic_filter, or narrower")
    parser.add_argument("--client-id", default="sink-consumer")
    parser.add_argument("--session-expiry", type=int, default=0, help="seconds the broker keeps the session offline")
    args = parser.parse_args()
    if not all((args.broker, args.username, args.password, args.topic)):
        sys.exit("--broker, --username, --password and --topic are required (or SINK_* env vars)")
    host, _, port = args.broker.rpartition(":")

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            sys.exit(f"Connection refused: {reason_code}")
        client.subscribe(args.topic, qos=1)

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        # "Not authorized" means the filter is outside this sink's topics.
        print(f"subscribed to {args.topic}: {reason_codes[0]}")

    def on_message(client, userdata, msg):
        body = json.loads(msg.payload)
        stream = msg.topic.split("/")[-3]
        what = body.get("payload_kind") or body.get("detector")
        print(f"{stream:8} {msg.topic.split('/')[-1]:>12} {what}: {json.dumps(body.get('payload', body.get('message')))[:120]}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=args.client_id, protocol=mqtt.MQTTv5)
    client.username_pw_set(args.username, args.password)
    client.tls_set()
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    properties = Properties(PacketTypes.CONNECT)
    properties.SessionExpiryInterval = args.session_expiry
    client.connect(host, int(port), clean_start=args.session_expiry == 0, properties=properties)
    client.loop_forever()


if __name__ == "__main__":
    main()
