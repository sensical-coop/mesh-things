#!/usr/bin/env python3
"""List the Meshtastic protocol versions a mesh can be declared on, without an API key.

Each version shows its status and, for one being retired, the date it stops being
offered. Declare the version your devices' firmware runs; the default is marked.

  python3 get_protocols.py
"""
import argparse
import os

from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args()

    for protocol in MeshThings(API_URL, api_key="").protocols.list():
        sunset = f", sunset {protocol['sunset']}" if protocol["sunset"] else ""
        default = "  (default)" if protocol["is_default"] else ""
        print(f"{protocol['version']}  {protocol['status']}{sunset}, from protobufs {protocol['source_ref']}{default}")


if __name__ == "__main__":
    main()
