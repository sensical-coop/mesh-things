#!/usr/bin/env python3
"""Set the admin keys of a node, for remote administration in Meshtastic.

The keys you pass replace the node's whole list, so please include every key the node
should keep. Meshtastic accepts up to three. If the node has not been seen yet, pass
--mesh-id to register it in advance.
"""
import argparse
import os
import sys

from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def set_admin_keys(
    api: MeshThings, node_id: int, admin_keys_b64: list[str], label: str | None, mesh_id: str | None
) -> dict:
    node = next((n for n in api.devices.list(is_gateway=False) if n["node_id"] == node_id), None)
    if node is not None:
        return api.devices.update(node["uuid"], body={"admin_keys_b64": admin_keys_b64})
    if not mesh_id:
        sys.exit(f"No node with node_id {node_id} exists yet - pass --mesh-id to pre-register it")
    return api.devices.create(body={
        "node_id": node_id, "mesh_id": mesh_id, "is_gateway": False, "admin_keys_b64": admin_keys_b64, "label": label,
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"))
    parser.add_argument("--mesh-id", default=os.environ.get("MESH_ID"), help="required only to pre-register a new node")
    parser.add_argument("--node-id", type=int, required=True, help="Meshtastic node number")
    parser.add_argument(
        "--admin-key-b64",
        action="append",
        required=True,
        dest="admin_keys_b64",
        help="repeat for multiple keys (up to 3) - this is the node's full list after the call, not an addition",
    )
    parser.add_argument("--label", default=None)
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY.")

    api = MeshThings(API_URL, args.api_key)
    node = set_admin_keys(api, args.node_id, args.admin_keys_b64, args.label, args.mesh_id)
    print(f"Node {node['node_id']} updated (uuid={node['uuid']})")


if __name__ == "__main__":
    main()
