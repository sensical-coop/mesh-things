#!/usr/bin/env python3
"""The latest value of every channel, for every device on a mesh.

Each value comes with its unit and its origin, so you can tell a sensor reading
(measured) from something the pipeline computed. Pass --dataframe to collect everything
in one pandas DataFrame, which needs mesh-things[pandas].

  python3 get_latest_readings.py --mesh-id <id>
  python3 get_latest_readings.py --mesh-id <id> --dataframe
"""
import argparse
import os
import sys

from mesh_things import node_ids
from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"))
    parser.add_argument("--mesh-id", default=os.environ.get("MESH_ID"))
    parser.add_argument("--dataframe", action="store_true", help="show the readings as one pandas DataFrame")
    args = parser.parse_args()
    if not args.mesh_id:
        sys.exit("Please pass --mesh-id or set MESH_ID.")

    # A public mesh can be read without a key; a private one needs its owner's.
    api = MeshThings(API_URL, args.api_key or "")
    rows = []
    for device in api.meshes.devices_list(args.mesh_id):
        name = device["label"] or device["name"] or node_ids.to_hex(device["node_id"])
        for reading in api.readings.devices_latest_get(device["uuid"])["readings"]:
            rows.append({"device": name, **reading})

    if not rows:
        print("No readings yet for this mesh.")
        return
    if args.dataframe:
        import pandas as pd

        frame = pd.DataFrame(rows).set_index(["device", "channel"])[["value", "unit", "origin", "time"]]
        print(frame.to_string())
        return
    for row in rows:
        unit = f" {row['unit']}" if row.get("unit") else ""
        print(f"{row['device']:<20} {row['channel']:<40} {row['value']}{unit}  ({row['origin']}, {row['time']})")


if __name__ == "__main__":
    main()
