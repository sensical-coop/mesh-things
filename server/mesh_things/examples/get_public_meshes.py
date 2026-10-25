#!/usr/bin/env python3
"""What anyone can read, without an API key: public meshes, their devices and their latest readings.

An owner can make a mesh public (see registry_publish_mesh.py) to share it openly. Public
meshes never reveal their channel key, and only their latest readings are open; the full
history still needs the owner's key.

  python3 get_public_meshes.py
"""
import argparse
import os

from mesh_things import node_ids
from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args()

    # An empty key makes sure no key is sent, even when MESH_THINGS_API_KEY is set.
    api = MeshThings(API_URL, api_key="")
    meshes = api.meshes.list()
    if not meshes:
        print("There are no public meshes on this instance yet.")
        return

    for mesh in meshes:
        print(f"\nMesh {mesh['label'] or mesh['channel_id']!r}, id {mesh['id']}")
        for device in api.meshes.devices_list(mesh["id"]):
            name = device["label"] or device["name"] or node_ids.to_hex(device["node_id"])
            readings = api.readings.devices_latest_get(device["uuid"])["readings"]
            measured = [r for r in readings if r["origin"] == "measured"]
            summary = ", ".join(f"{r['channel']}={r['value']}{(' ' + r['unit']) if r.get('unit') else ''}" for r in measured[:3])
            print(f"  {name:<24} {summary or 'no sensor readings yet'}")


if __name__ == "__main__":
    main()
