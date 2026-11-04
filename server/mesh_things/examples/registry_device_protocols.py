#!/usr/bin/env python3
"""Show which Meshtastic protocol version each device on a mesh follows.

Every device is decoded with its mesh's protocol version. A device on newer firmware
sends readings that version does not know, and those are not stored until the mesh
declares the newer version. A gateway that sends map reports also shows its firmware.
This lists the devices that need a newer version, and with --fix sets the mesh's
protocol to the newest one they need.
"""
import argparse
import os
import sys

from mesh_things import node_ids, protocols
from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"), help="the mesh owner's key")
    parser.add_argument("mesh_id", help="the mesh's 'id' field, from registry_create_mesh.py's output")
    parser.add_argument("--fix", action="store_true", help="declare the version the devices need on the mesh")
    args = parser.parse_args()
    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY.")

    api = MeshThings(API_URL, args.api_key)
    mesh = api.meshes.get(args.mesh_id)
    print(f"Mesh {mesh['label'] or mesh['channel_id']!r} is declared on protocol {mesh['protocol']}")
    mismatched = []
    for device in api.meshes.devices_list(args.mesh_id):
        name = device["label"] or device["name"] or node_ids.to_hex(device["node_id"])
        observed = device["observed_protocol"] or "-"
        firmware = device["firmware_version"] or "-"
        flag = "  readings lost or misread" if device["protocol_mismatch"] else ""
        print(f"  {name:<24} decoded with {device['protocol']}  needs {observed}  firmware {firmware}{flag}")
        if device["protocol_mismatch"]:
            mismatched += [
                version
                for version in (device["observed_protocol"], device["firmware_protocol"])
                if protocols.is_newer(version, mesh["protocol"])
            ]

    if not mismatched:
        print("No device needs a newer protocol than the mesh's.")
        return
    needed = protocols.newest(mismatched)
    if needed == protocols.UNSUPPORTED:
        print("Some devices run a version this instance does not support yet.")
        return
    if not args.fix:
        print(f"Run again with --fix to declare protocol {needed} on the mesh.")
        return
    mesh = api.meshes.update(args.mesh_id, body={"protocol": needed})
    print(f"The mesh is now declared on protocol {mesh['protocol']}.")


if __name__ == "__main__":
    main()
