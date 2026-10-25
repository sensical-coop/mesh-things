#!/usr/bin/env python3
"""Who hears whom on a mesh: its radio links, longest first, and its newest traceroutes.

Device names come from the mesh's device list. A public mesh can be read without an
API key.
"""
import argparse
import itertools
import os

from mesh_things import node_ids
from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh-id", required=True)
    parser.add_argument("--since", default="7d", choices=["24h", "7d", "30d"])
    parser.add_argument("--node-id", help="Only links and traceroutes of this node, as a number or !aabbccdd.")
    parser.add_argument("--traceroutes", type=int, default=10, help="How many traceroutes to show.")
    args = parser.parse_args()
    api = MeshThings(API_URL)

    devices = api.meshes.devices_list(args.mesh_id)
    names = {d["node_id"]: d["label"] or d["name"] or d["short_name"] for d in devices}

    def name(node: int) -> str:
        return names.get(node) or node_ids.to_hex(node)

    links = api.meshes.links_list(args.mesh_id, since=args.since, node_id=args.node_id)
    print(f"Links heard in the last {args.since} (transmitter -> receiver):")
    for link in links:
        distance = "-" if link["distance_km"] is None else f"{link['distance_km']:.1f} km"
        print(
            f"  {name(link['from_node']):>20} -> {name(link['to_node']):<20} {link['source']:<12} "
            f"snr={link['snr_mean']:.1f} dB samples={link['samples']} distance={distance}"
        )

    print("\nNewest traceroutes:")
    traceroutes = api.traceroutes(args.mesh_id, node_id=args.node_id, page_size=min(args.traceroutes, 500))
    for t in itertools.islice(traceroutes, args.traceroutes):
        towards = " -> ".join(name(n) for n in t["towards"])
        back = " -> ".join(name(n) for n in t["back"]) or "-"
        print(f"  {t['heard_at']}  {towards}")
        print(f"  {'':20}back: {back}  complete={t['complete']}")


if __name__ == "__main__":
    main()
