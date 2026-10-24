#!/usr/bin/env python3
"""Export a mesh's readings over a range of days as one zip, wait for it, and download it.

CSV covers every device, a file per measurement and day plus channels.csv with units.
Parquet holds the archive's hourly files and needs the operator role. Days are UTC.
Pass --dataframe to load a CSV export with pandas (needs mesh-things[pandas]).
See docs/api-reference.md#exports.
"""
import argparse
import os
import sys

from mesh_things.client import ExportFailed, ExportInProgress, MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"))
    parser.add_argument("--mesh-id", default=os.environ.get("MESH_ID"))
    parser.add_argument("--format", choices=["csv", "parquet"], default="csv")
    parser.add_argument("--start", required=True, help="First day, YYYY-MM-DD.")
    parser.add_argument("--stop", required=True, help="Last day, included, YYYY-MM-DD.")
    parser.add_argument("--node-id", type=int, action="append", dest="node_ids", help="CSV only. Repeat for several.")
    parser.add_argument("--out", help="Output file. Defaults to the export's own name.")
    parser.add_argument("--dataframe", action="store_true", help="print each measurement's frame after downloading")
    args = parser.parse_args()
    if not args.api_key:
        sys.exit("No API key - pass --api-key or set MESH_THINGS_API_KEY")
    if not args.mesh_id:
        sys.exit("No mesh - pass --mesh-id or set MESH_ID")
    api = MeshThings(API_URL, args.api_key)

    body = {"format": args.format, "start": args.start, "stop": args.stop}
    if args.node_ids:
        body["node_ids"] = args.node_ids
    try:
        export = api.readings.meshes_exports_create(args.mesh_id, body=body)
    except ExportInProgress:
        sys.exit("Another export of yours is queued or running; list them with api.readings.exports_list()")
    print(f"Export {export['id']} {export['status']}, waiting for it")

    try:
        export = api.wait_for_export(args.mesh_id, export["id"], interval=2)
    except ExportFailed as e:
        sys.exit(str(e))

    # The link is signed on its own; it needs no API key and works until expires_at.
    out = api.download(export["url"], args.out or export["filename"])
    print(f"Wrote {export['size']} bytes to {out}; the link works until {export['expires_at']}")

    if args.dataframe:
        from mesh_things.pandas import read_export

        for measurement, frame in read_export(out).items():
            print(f"\n== {measurement}: {len(frame)} rows, units {frame.attrs.get('units', {})}")
            print(frame.head())


if __name__ == "__main__":
    main()
