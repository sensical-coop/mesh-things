#!/usr/bin/env python3
"""Register a gateway on a mesh, the node that relays the mesh's traffic to the broker.

Registering a gateway is what allows the instance to decode the mesh's traffic. The
mesh's other nodes appear on their own once their packets are decoded.
"""
import argparse
import os
import sys

from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"))
    parser.add_argument("--mesh-id", default=os.environ.get("MESH_ID"))
    parser.add_argument("--node-id", type=int, required=True, help="Meshtastic node number of the relaying node")
    parser.add_argument("--label", default=None)
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY (see registry_create_owner.py).")
    if not args.mesh_id:
        sys.exit("Please pass --mesh-id or set MESH_ID (see registry_create_mesh.py).")

    gateway = MeshThings(API_URL, args.api_key).devices.create(body={
        "node_id": args.node_id, "mesh_id": args.mesh_id, "is_gateway": True, "label": args.label,
    })
    print(f"Registered gateway {gateway['node_id']} on mesh {gateway['mesh_id']}")
    print(f"  uuid={gateway['uuid']}  is_allowed={gateway['is_allowed']}")


if __name__ == "__main__":
    main()
