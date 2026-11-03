#!/usr/bin/env python3
"""Make a mesh public, then read it without a key and as another owner.

The script publishes the mesh and reads it, its devices and their latest readings
without any key. With --reader-api-key, it also reads the mesh as another owner and
shows that this owner cannot change it. Finally, it makes the mesh private again,
unless you pass --keep.
"""
import argparse
import os
import sys

from mesh_things.client import ApiError, MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def read_anonymously(mesh_id: str) -> None:
    """Read the public mesh, its devices and their latest readings with no API key."""
    anonymous = MeshThings(API_URL, api_key="")
    mesh = anonymous.meshes.get(mesh_id)
    print(f"\nWithout credentials: read the mesh, fields={sorted(mesh)}")

    for device in anonymous.meshes.devices_list(mesh_id):
        latest = anonymous.readings.devices_latest_get(device["uuid"])
        try:
            anonymous.readings.devices_get(device["uuid"], channel="device_metrics.battery_level")
            refused = "not refused"
        except ApiError as e:
            refused = f"refused with {e.status}"
        print(f"  node {device['node_id']}: {len(latest['readings'])} latest reading(s), timeseries {refused}")


def read_as_another_owner(mesh_id: str, reader_api_key: str) -> None:
    """Read the mesh as an owner who does not own it, and fail to rename it."""
    reader = MeshThings(API_URL, reader_api_key)
    body = reader.meshes.get(mesh_id)
    print(f"\nAs another owner: read the mesh, channel_id={body['channel_id']!r}")
    # The pre-shared key is stripped for everyone but the owner, so its
    # absence here is the point of the exercise rather than a missing field.
    print(f"  psk_b64 present: {'psk_b64' in body}")
    try:
        reader.meshes.update(mesh_id, body={"label": "not mine to rename"})
        print("  write accepted - publishing should widen reads only")
    except ApiError as e:
        print(f"  write refused with {e.status} (publishing widens reads only)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"), help="the mesh owner's key")
    parser.add_argument("--mesh-id", default=os.environ.get("MESH_ID"))
    parser.add_argument("--reader-api-key", help="another owner's key; without it the read-back is skipped")
    parser.add_argument("--keep", action="store_true", help="leave the mesh public instead of reverting")
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY (see registry_create_owner.py).")
    if not args.mesh_id:
        sys.exit("Please pass --mesh-id or set MESH_ID (see registry_create_mesh.py).")

    owner = MeshThings(API_URL, args.api_key)
    owner.meshes.update(args.mesh_id, body={"is_public": True})
    print(f"Mesh {args.mesh_id} is now public, also to callers without an API key")
    # Made private again even when a step below fails, unless --keep asks otherwise.
    try:
        read_anonymously(args.mesh_id)
        if args.reader_api_key:
            read_as_another_owner(args.mesh_id, args.reader_api_key)
    finally:
        if args.keep:
            print("\nLeaving the mesh public (--keep)")
        else:
            owner.meshes.update(args.mesh_id, body={"is_public": False})
            print(f"\nMesh {args.mesh_id} is private again")


if __name__ == "__main__":
    main()
