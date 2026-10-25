#!/usr/bin/env python3
"""Change a mesh's label, channel name or key.

Only the values you pass are changed. A new channel name or key is sent to every
gateway on the mesh straight away.
"""
import argparse
import os
import sys

from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"))
    parser.add_argument("mesh_id", help="the mesh's 'id' field, from registry_create_mesh.py's output")
    parser.add_argument("--label", default=None)
    parser.add_argument("--channel-id", default=None)
    parser.add_argument("--psk-b64", default=None)
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY.")
    changes = {
        key: value
        for key, value in (("label", args.label), ("channel_id", args.channel_id), ("psk_b64", args.psk_b64))
        if value is not None
    }
    if not changes:
        sys.exit("There is nothing to update. Please pass --label, --channel-id or --psk-b64.")

    mesh = MeshThings(API_URL, args.api_key).meshes.update(args.mesh_id, body=changes)
    print(f"Updated mesh {mesh['id']}: label={mesh['label']!r} channel_id={mesh['channel_id']!r}")


if __name__ == "__main__":
    main()
