#!/usr/bin/env python3
"""Switch the Parquet archive on or off for one device.

Devices can only be archived on meshes owned by an operator, and only on instances
that run the archive. From then on, the device's decoded and derived readings are
stored. Switching it off keeps what was already stored. You can read the archive with
archive_duckdb.py, archive_pandas.py or archive_download.py.
"""
import argparse
import os
import sys

from mesh_things.client import MeshThings, ValidationFailed

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"), help="the mesh owner's key")
    parser.add_argument("--device-uuid", required=True, help="the device's registration uuid, from GET /devices")
    parser.add_argument("--off", action="store_true", help="stop archiving instead")
    args = parser.parse_args()
    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY.")

    try:
        device = MeshThings(API_URL, args.api_key).devices.update(
            args.device_uuid, body={"archive_enabled": not args.off},
        )
    except ValidationFailed as e:
        sys.exit(f"Refused: {e.errors.get('archive_enabled', e.errors)}")
    state = "on" if device["archive_enabled"] else "off"
    print(f"Archive {state} for node {device['node_id']} on mesh {device['mesh_id']}")


if __name__ == "__main__":
    main()
