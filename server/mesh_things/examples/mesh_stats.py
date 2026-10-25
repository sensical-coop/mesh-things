#!/usr/bin/env python3
"""A summary of a mesh's radio traffic: totals, packets by type, the busiest nodes, gateways and hops.

The statistics refer to devices by number, so the script adds their names from the
mesh's device list. A public mesh can be read without an API key.
"""
import argparse
import os

from mesh_things import node_ids
from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh-id", required=True)
    parser.add_argument("--range", default="24h", choices=["1h", "24h", "7d", "30d"])
    args = parser.parse_args()
    api = MeshThings(API_URL)

    stats = api.readings.meshes_stats_get(args.mesh_id, range=args.range)
    names = {d["uuid"]: d["label"] or d["name"] or d["short_name"] for d in api.meshes.devices_list(args.mesh_id)}

    def name(entry: dict) -> str:
        return names.get(entry["device_uuid"]) or node_ids.to_hex(entry["node_id"])

    summary = stats["summary"]
    print(f"Last {stats['range']} (buckets of {stats['window']}, hourly figures from {stats['hourly_start']}):")
    for key, value in summary.items():
        print(f"  {key}: {value}")

    print("\nPackets by portnum:")
    for entry in stats["traffic"]:
        print(f"  {entry['name']:<30} packets={entry['packets']} receptions={entry['receptions']}")

    print("\nBusiest nodes:")
    for entry in stats["nodes"]:
        print(f"  {name(entry):<30} packets={entry['packets']} receptions={entry['receptions']}")

    print("\nGateways:")
    for entry in stats["gateways"]:
        snr = "-" if entry["rx_snr_mean"] is None else f"{entry['rx_snr_mean']:.1f} dB"
        print(
            f"  {name(entry):<30} receptions={entry['receptions']} share={entry['share']:.0%} "
            f"direct={entry['direct_receptions']} snr={snr}"
        )

    print("\nGateways heard the same packets (a vs b):")
    for pair in stats["gateway_pairs"][:10]:
        a, b = name({"node_id": pair["gateway_a"], "device_uuid": pair["device_uuid_a"]}), name(
            {"node_id": pair["gateway_b"], "device_uuid": pair["device_uuid_b"]}
        )
        snr = "-" if pair["snr_diff_mean"] is None else f"{pair['snr_diff_mean']:+.1f} dB"
        print(f"  {a} <-> {b}: {pair['common_packets']} packets, snr {snr}")

    print("\nRelays into gateways (last byte -> could be):")
    for relay in stats["relays"][:10]:
        gateway = name({"node_id": relay["gateway_id"], "device_uuid": relay["device_uuid"]})
        could_be = ", ".join(name(c) for c in relay["candidates"]) or "no registered node"
        print(f"  {gateway} <- ..{relay['relay']:02x} x{relay['receptions']}: {could_be}")

    print("\nHops:")
    for entry in stats["hops"]:
        print(f"  {'unknown' if entry['hops'] is None else entry['hops']:<8} packets={entry['packets']}")


if __name__ == "__main__":
    main()
