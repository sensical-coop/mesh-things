#!/usr/bin/env python3
"""Query a mesh's Parquet archive with pandas and pyarrow, using credentials from the API.

Same archive and credentials as archive_duckdb.py. Partition keys live only in
the path, so a plain Hive read works: `dt` and `hour` come back as columns, and
filters on them prune whole files, while `node_id` filters use row-group
statistics. Needs mesh-things[archive]. See docs/api-reference.md#parquet-archive.
"""
import argparse
import os
import sys

import pyarrow.dataset as ds

from mesh_things import archive
from mesh_things.client import MeshThings, NotFound
from mesh_things.pandas import archive_frame

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"))
    parser.add_argument("--mesh-id", default=os.environ.get("MESH_ID"))
    parser.add_argument("--node-id", type=int, help="Restrict to one device.")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if not args.api_key:
        sys.exit("No API key - pass --api-key or set MESH_THINGS_API_KEY")
    if not args.mesh_id:
        sys.exit("No mesh - pass --mesh-id or set MESH_ID")

    try:
        dataset = archive.open_dataset(MeshThings(API_URL, args.api_key), args.mesh_id)
    except NotFound:
        sys.exit("No archive for this mesh: not an operator's mesh you own, or the instance runs no archive.")
    expr = ds.field("node_id") == args.node_id if args.node_id else None
    # The summary below needs every row, so the whole (filtered) archive is loaded;
    # narrow it with --node-id, or filter on dt, for a large mesh.
    df = dataset.to_table(filter=expr).to_pandas()
    if df.empty:
        print("No rows. Check that a device on this mesh has archive_enabled, and that s3_writer has flushed.")
        return

    print(f"\n== {len(df)} rows ==")
    print(df.groupby(["node_id", "dt"]).size().tail(args.limit).to_string())

    # payload_json holds the decoded payload; archive_frame spreads it into the API's channels.
    channels = archive_frame(df)
    if "environment_metrics.temperature" in channels:
        temperature = channels["environment_metrics.temperature"].dropna()
        print("\n== environment_metrics.temperature, most recent first ==")
        print(temperature.sort_index(level="time", ascending=False).head(args.limit).to_string())


if __name__ == "__main__":
    main()
