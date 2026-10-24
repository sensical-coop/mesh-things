#!/usr/bin/env python3
"""Attach a mesh to a source, so its traffic is ingested from the remote broker.

The caller must own the mesh and be the operator who created the source (or a
superuser). Once attached, the mesh's gateways are accepted only through that source. Pass
--detach to return the mesh to this instance's own broker topic. See
docs/api-reference.md#sources.
"""
import argparse
import os
import sys

from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"), help="the mesh owner's key, who also created the source")
    parser.add_argument("--mesh-id", default=os.environ.get("MESH_ID"))
    parser.add_argument("--source-id", default=os.environ.get("SOURCE_ID"))
    parser.add_argument("--detach", action="store_true", help="back to this instance's own topic")
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("No API key - pass --api-key or set MESH_THINGS_API_KEY (see registry_create_owner.py)")
    if not args.mesh_id:
        sys.exit("No mesh - pass --mesh-id or set MESH_ID (see registry_create_mesh.py)")
    if not args.detach and not args.source_id:
        sys.exit("No source - pass --source-id or set SOURCE_ID (see registry_create_source.py)")

    mesh = MeshThings(API_URL, args.api_key).meshes.update(
        args.mesh_id, body={"source_id": None if args.detach else args.source_id},
    )
    where = f"source {mesh['source_id']}" if mesh["source_id"] else "this instance's own topic"
    print(f"Mesh {mesh['id']} ({mesh['channel_id']}) now reads from {where}")
    print("  every allowed gateway on it was republished with the change")


if __name__ == "__main__":
    main()
