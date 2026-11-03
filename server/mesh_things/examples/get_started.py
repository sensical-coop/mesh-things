#!/usr/bin/env python3
"""A first look at your data: your account, your meshes, their devices and the latest reading of each one.

This is a good place to start. It only reads from the API, so you can run it as often as
you like. You need an API key (see registry_create_owner.py) in MESH_THINGS_API_KEY.

  python3 get_started.py
  python3 get_started.py --mesh-id <id>    # only one mesh
"""
import argparse
import os
import sys

from mesh_things import node_ids
from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"))
    parser.add_argument("--mesh-id", help="show only this mesh")
    args = parser.parse_args()
    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY (see registry_create_owner.py).")

    api = MeshThings(API_URL, args.api_key)
    me = api.owners.me_get()
    print(f"Signed in as {me['name']} ({me['email']}), role: {me['role']}")

    meshes = [api.meshes.get(args.mesh_id)] if args.mesh_id else api.meshes.list()
    if not meshes:
        print("You have no meshes yet. You can create one with registry_create_mesh.py.")
        return

    for mesh in meshes:
        visibility = "public" if mesh["is_public"] else "private"
        print(f"\nMesh {mesh['label'] or mesh['channel_id']!r} ({visibility}), id {mesh['id']}")
        devices = api.meshes.devices_list(mesh["id"])
        if not devices:
            print("  No devices have been seen on this mesh yet.")
        for device in devices:
            name = device["label"] or device["name"] or node_ids.to_hex(device["node_id"])
            kind = "gateway" if device["is_gateway"] else "node"
            readings = api.readings.devices_latest_get(device["uuid"])["readings"]
            latest = max((r["time"] for r in readings), default=None)
            print(f"  {name:<24} {kind:<8} last reading: {latest or 'none yet'}, {len(readings)} channel(s)")


if __name__ == "__main__":
    main()
