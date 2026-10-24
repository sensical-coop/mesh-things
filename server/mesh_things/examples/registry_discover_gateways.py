#!/usr/bin/env python3
"""Switch gateway discovery on or off for a mesh, and list the gateways it found.

With discovery on, any gateway whose packets decode with the mesh's channel and PSK is
registered without being added by hand. On a mesh with the default or a blank PSK only
an operator may switch it on (403 otherwise).

  python3 registry_discover_gateways.py <mesh id> --on --wait 120
  python3 registry_discover_gateways.py <mesh id>          # just list
  python3 registry_discover_gateways.py <mesh id> --off
"""
import argparse
import os
import sys
import time

from mesh_things import node_ids
from mesh_things.client import Forbidden, MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"))
    parser.add_argument("mesh_id", help="the mesh's 'id' field, from registry_create_mesh.py's output")
    toggle = parser.add_mutually_exclusive_group()
    toggle.add_argument("--on", action="store_true", help="switch discovery on")
    toggle.add_argument("--off", action="store_true", help="switch discovery off; found gateways stay")
    parser.add_argument("--wait", type=int, default=0, help="seconds to keep polling for new gateways")
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("No API key - pass --api-key or set MESH_THINGS_API_KEY")
    api = MeshThings(API_URL, args.api_key)

    if args.on or args.off:
        try:
            mesh = api.meshes.update(args.mesh_id, body={"discover_gateways": args.on})
        except Forbidden as e:
            sys.exit(f"Refused: {e.detail}")
        print(f"Mesh {mesh['id']}: discover_gateways={mesh['discover_gateways']}")

    seen = set()
    deadline = time.monotonic() + args.wait
    while True:
        for gateway in api.meshes.devices_list(args.mesh_id):
            if gateway["is_gateway"] and gateway.get("discovered_at") and gateway["uuid"] not in seen:
                seen.add(gateway["uuid"])
                print(f"{node_ids.to_hex(gateway['node_id'])} discovered {gateway['discovered_at']}, "
                      f"last seen {gateway['last_seen']}")
        if time.monotonic() >= deadline:
            break
        time.sleep(10)
    if not seen:
        print("No discovered gateways yet")


if __name__ == "__main__":
    main()
