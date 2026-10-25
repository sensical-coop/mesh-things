#!/usr/bin/env python3
"""Download one hour of a mesh's Parquet archive, with no S3 client at all.

readings answers with a redirect to a temporary link, which the client follows
without forwarding the API key. Useful where SigV4 is not available, or to fetch
a single known hour. Hours are UTC, and the list of what exists comes from the
manifest route. See docs/api-reference.md#parquet-archive.
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
        sys.exit("No API key - pass --api-key or set MESH_THINGS_API_KEY")
    if not args.mesh_id:
        sys.exit("No mesh - pass --mesh-id or set MESH_ID")
    if (args.day is None) != (args.hour is None):
        parser.error("--day and --hour go together")
    api = MeshThings(API_URL, args.api_key)

    partitions = api.readings.archive_meshes_get(args.mesh_id)["partitions"]
    print(f"{len(partitions)} hour(s) archived")
    if args.day is None:
        if not partitions:
            sys.exit("Nothing archived yet")
        args.day, args.hour = partitions[-1]["dt"], partitions[-1]["hour"]

    out = api.download_partition(args.mesh_id, args.day, args.hour, args.out or f"{args.day}-{args.hour:02d}.parquet")
    print(f"Wrote {out.stat().st_size} bytes to {out}")


if __name__ == "__main__":
    main()
