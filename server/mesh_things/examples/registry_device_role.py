#!/usr/bin/env python3
"""Turn a registered node into a gateway, or a gateway back into a node.

A gateway is the device that publishes the mesh's traffic to the broker, and the
instance finds the mesh's key by the gateway's node number. For that reason, a node
number can only belong to one gateway on the instance at a time.
"""
import argparse
import os
import sys

from mesh_things.client import Conflict, MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"), help="the mesh owner's key")
    parser.add_argument("--device-uuid", required=True, help="the device's registration uuid, from GET /devices")
    parser.add_argument("--node", action="store_true", help="make it a plain node instead of a gateway")
    args = parser.parse_args()
    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY.")

    try:
        device = MeshThings(API_URL, args.api_key).devices.update(
            args.device_uuid, body={"is_gateway": not args.node},
        )
    except Conflict as e:
        sys.exit(f"Refused: {e}")
    role = "gateway" if device["is_gateway"] else "node"
    print(f"Node {device['node_id']} on mesh {device['mesh_id']} is now a {role}")


if __name__ == "__main__":
    main()
