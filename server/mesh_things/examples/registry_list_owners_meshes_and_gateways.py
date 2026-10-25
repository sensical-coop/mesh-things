#!/usr/bin/env python3
"""List the owners on the instance and, with an API key, your own meshes and gateways.

The list of owners is public. With a superuser key, it also includes each owner's
email address and whether it has been verified.
"""
import argparse
import os

from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--api-key",
        default=os.environ.get("MESH_THINGS_API_KEY"),
        help="optional - also lists that owner's meshes and gateways, and widens the owner list for a superuser",
    )
    args = parser.parse_args()
    api = MeshThings(API_URL, args.api_key)

    # Public without a key. A superuser key additionally returns each owner's email and verification state.
    owners = api.owners.list()
    print(f"{len(owners)} owner(s):")
    for o in owners:
        # Present only for a superuser; a public read stops at id/name/created_at.
        extra = f"  {o['email']}  verified={o['is_active']}  superuser={o['is_superuser']}" if "email" in o else ""
        print(f"  {o['id']}  {o['name']!r}{extra}")

    if not args.api_key:
        print("\n(pass --api-key or set MESH_THINGS_API_KEY to also list that owner's meshes and gateways)")
        return

    meshes = api.meshes.list()
    print(f"\n{len(meshes)} mesh(es) for the authenticated owner:")
    for m in meshes:
        print(f"  {m['id']}  channel={m['channel_id']!r}  label={m['label']!r}")

    gateways = api.devices.list(is_gateway=True)
    print(f"\n{len(gateways)} gateway(s) for the authenticated owner:")
    for g in gateways:
        print(f"  {g['uuid']}  node_id={g['node_id']}  mesh_id={g['mesh_id']}  label={g['label']!r}")


if __name__ == "__main__":
    main()
