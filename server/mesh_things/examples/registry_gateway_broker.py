#!/usr/bin/env python3
"""Show the MQTT settings to enter in the Meshtastic app for a gateway.

Every gateway shares one login. Its packets are stored once it is registered on a mesh,
by you or by gateway discovery. The password stays hidden unless you pass --show-password.
"""
import argparse
import os
import sys

from mesh_things.client import MeshThings, NotFound

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"))
    parser.add_argument("--show-password", action="store_true", help="print the password instead of hiding it")
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY (see registry_create_owner.py).")
    try:
        broker = MeshThings(API_URL, args.api_key).owners.me_gateway_broker_get()
    except NotFound:
        sys.exit("This instance has no broker for gateways; ask its administrator for one.")

    print(f"Server address:  {broker['host']}:{broker['port']}")
    print(f"TLS:             {'on' if broker['tls'] else 'off'}")
    print(f"Username:        {broker['username']}")
    print(f"Password:        {broker['password'] if args.show_password else '(hidden, pass --show-password)'}")
    print("Then turn on uplink for the mesh's channel, and leave the root topic at its default.")


if __name__ == "__main__":
    main()
