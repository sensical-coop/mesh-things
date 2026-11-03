#!/usr/bin/env python3
"""Download one hour of a mesh's Parquet archive, without any S3 client.

The API answers with a temporary link to the file, which the client follows without
sending your API key. This is useful where you cannot use S3 credentials, or when you
only need one known hour. Hours are in UTC, and the script lists the hours that exist
before downloading. Leave out --day and --hour to get the latest one.
"""
import argparse
import os
import sys

from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"))
    parser.add_argument("--mesh-id", default=os.environ.get("MESH_ID"))
    parser.add_argument("--day", help="YYYY-MM-DD. Defaults to the latest archived hour.")
    parser.add_argument("--hour", type=int, help="0-23, with --day.")
    parser.add_argument("--out", help="Output file. Defaults to <day>-<hour>.parquet.")
    args = parser.parse_args()
    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY.")
    if not args.mesh_id:
        sys.exit("Please pass --mesh-id or set MESH_ID.")
    if (args.day is None) != (args.hour is None):
        parser.error("--day and --hour go together")
    api = MeshThings(API_URL, args.api_key)

    partitions = api.readings.archive_meshes_get(args.mesh_id)["partitions"]
    print(f"{len(partitions)} hour(s) archived")
    if args.day is None:
        if not partitions:
            sys.exit("Nothing has been archived for this mesh yet.")
        args.day, args.hour = partitions[-1]["dt"], partitions[-1]["hour"]

    out = api.download_partition(args.mesh_id, args.day, args.hour, args.out or f"{args.day}-{args.hour:02d}.parquet")
    print(f"Wrote {out.stat().st_size} bytes to {out}")


if __name__ == "__main__":
    main()
