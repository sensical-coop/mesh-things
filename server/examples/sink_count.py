#!/usr/bin/env python3
"""Subscribe to an MQTT sink and count the readings and alarms it delivers.

For testing a sink end to end, e.g. alongside source_publish_fake.py: prints a running
total every --report seconds and a summary per stream, node and payload kind when it
stops. Stops on Ctrl-C, after --duration seconds, or once --expect messages arrived;
exits 1 if --expect was not reached. Takes the credentials registry_create_sink.py
printed. See docs/api-reference.md#consuming-a-sink.
"""
import argparse
import json
import os
import sys
import threading
import time
from collections import Counter

import paho.mqtt.client as mqtt
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--broker", default=os.environ.get("SINK_BROKER"), help="host:port, from the sink")
    parser.add_argument("--username", default=os.environ.get("SINK_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("SINK_PASSWORD"))
    parser.add_argument("--topic", default=os.environ.get("SINK_TOPIC_FILTER"), help="the sink's topic_filter, or narrower")
    parser.add_argument("--no-ssl", action="store_true", help="connect without TLS")
    parser.add_argument(
        "--client-id", default="sink-counter",
        help="the broker disconnects any other client already using this id",
    )
    parser.add_argument("--session-expiry", type=int, default=0, help="seconds the broker keeps the session offline")
    parser.add_argument("--duration", type=float, default=0, help="stop after this many seconds; 0 runs until Ctrl-C")
    parser.add_argument("--expect", type=int, default=0, help="stop once this many messages arrived")
    parser.add_argument("--report", type=float, default=10, help="seconds between running totals")
    parser.add_argument("--verbose", action="store_true", help="also print each message")
    args = parser.parse_args()
    if not all((args.broker, args.username, args.password, args.topic)):
        sys.exit("--broker, --username, --password and --topic are required (or SINK_* env vars)")
    host, _, port = args.broker.rpartition(":")

    totals = Counter()
    by_stream, by_node, by_kind = Counter(), Counter(), Counter()
    lock = threading.Lock()
    done = threading.Event()
    started = time.monotonic()
    first_at = None

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"Connection refused: {reason_code}", file=sys.stderr)
            done.set()
            return
        client.subscribe(args.topic, qos=1)

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        # "Not authorized" means the filter is outside this sink's topics.
        print(f"subscribed to {args.topic}: {reason_codes[0]}")
        if reason_codes[0].is_failure:
            done.set()

    def on_disconnect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"disconnected: {reason_code}", file=sys.stderr)

    def on_message(client, userdata, msg):
        nonlocal first_at
        # Topic: {root}/{sink_id}/{stream}/{mesh_id}/{node_id}
        parts = msg.topic.split("/")
        stream, node = (parts[-3], parts[-1]) if len(parts) >= 3 else ("?", "?")
        try:
            body = json.loads(msg.payload)
            kind = body.get("payload_kind") or body.get("detector") or "?"
        except ValueError:
            body, kind = None, "not json"
            totals["not json"] += 1
        with lock:
            first_at = first_at or time.monotonic()
            totals["messages"] += 1
            by_stream[stream] += 1
            by_node[node] += 1
            by_kind[kind] += 1
            count = totals["messages"]
        if args.verbose:
            print(f"{count:>6} {stream:8} {node:>12} {kind}")
        if args.expect and count >= args.expect:
            done.set()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=args.client_id, protocol=mqtt.MQTTv5)
    client.username_pw_set(args.username, args.password)
    if not args.no_ssl:
        client.tls_set()
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    properties = Properties(PacketTypes.CONNECT)
    properties.SessionExpiryInterval = args.session_expiry
    client.connect(host, int(port), clean_start=args.session_expiry == 0, properties=properties)
    client.loop_start()

    last_report = started
    try:
        while not done.wait(0.5):
            now = time.monotonic()
            if args.duration and now - started >= args.duration:
                break
            if args.report and now - last_report >= args.report:
                last_report = now
                with lock:
                    streams = ", ".join(f"{s}={n}" for s, n in sorted(by_stream.items())) or "none yet"
                    print(f"[{now - started:6.0f}s] {totals['messages']} messages ({streams})")
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()

    elapsed = time.monotonic() - started
    count = totals["messages"]
    print(f"\n{count} messages in {elapsed:.0f}s ({count / elapsed * 60:.1f}/min)" if elapsed else "")
    if first_at is not None:
        print(f"first after {first_at - started:.1f}s")
    for title, counter in (("stream", by_stream), ("node", by_node), ("payload kind", by_kind)):
        if counter:
            print(f"by {title}:")
            for key, n in counter.most_common():
                print(f"  {key:<40} {n}")
    if totals["not json"]:
        print(f"{totals['not json']} messages were not JSON")
    if args.expect and count < args.expect:
        sys.exit(f"expected {args.expect}, got {count}")


if __name__ == "__main__":
    main()
