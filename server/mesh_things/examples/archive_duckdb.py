#!/usr/bin/env python3
"""Query a mesh's Parquet archive with DuckDB, using temporary credentials from the API.

Only devices you have switched on for the archive are stored (see
registry_device_archive.py), and only superusers and the mesh's owner, while an operator, can read it. The
script asks the API for credentials limited to one mesh, then queries its files as one
partitioned dataset:

  {prefix}/mesh_id={mesh_id}/dt=YYYY-MM-DD/hour=HH/data.parquet

`mesh_id`, `dt` and `hour` come from the file paths, and `node_id` is a regular
column, so you can filter on any of them.
"""
import argparse
import os
import sys

import duckdb

from mesh_things.client import MeshThings, NotFound

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def connect(creds: dict) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    options = {
        "TYPE": "s3",
        "KEY_ID": creds["access_key_id"],
        "SECRET": creds["secret_access_key"],
        "SESSION_TOKEN": creds["session_token"],
        "REGION": creds["region"],
    }
    # A null endpoint means AWS, which DuckDB reaches on its own.
    if creds["endpoint"]:
        scheme, host = creds["endpoint"].split("://", 1)
        # Path-style, so a self-hosted endpoint needs no wildcard DNS.
        options.update({"ENDPOINT": host, "USE_SSL": str(scheme == "https").lower(), "URL_STYLE": "path"})
    con.execute("CREATE SECRET archive (" + ", ".join(f"{k} '{v}'" for k, v in options.items()) + ")")
    return con


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"))
    parser.add_argument("--mesh-id", default=os.environ.get("MESH_ID"))
    parser.add_argument("--node-id", type=int, help="Restrict to one device.")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY.")
    if not args.mesh_id:
        sys.exit("Please pass --mesh-id or set MESH_ID.")

    try:
        creds = MeshThings(API_URL, args.api_key).readings.archive_meshes_credentials_create(args.mesh_id)
    except NotFound:
        sys.exit("There is no archive for this mesh. Archives are kept only for meshes their operator owns, on instances that run the archive.")
    print(f"Credentials for {creds['s3_path']}, valid until {creds['expires_at']}")
    con = connect(creds)
    source = f"read_parquet('{creds['s3_path']}dt=*/hour=*/data.parquet', hive_partitioning=true)"
    where = f"WHERE node_id = {args.node_id}" if args.node_id else ""

    print("\n== rows per device and day ==")
    for row in con.execute(
        f"SELECT node_id, dt, count(*) AS rows FROM {source} {where} "
        f"GROUP BY 1, 2 ORDER BY dt DESC, rows DESC LIMIT {args.limit}"
    ).fetchall():
        print(f"  node={row[0]} dt={row[1]} rows={row[2]}")

    print("\n== latest readings, payload pulled out of the JSON column ==")
    for row in con.execute(
        f"""SELECT node_id, payload_kind, epoch_ms(rx_time * 1000) AS at_utc,
                   json_extract_string(payload_json, '$.environment_metrics.temperature') AS temperature
            FROM {source} {where}
            ORDER BY rx_time DESC LIMIT {args.limit}"""
    ).fetchall():
        print(f"  node={row[0]} {row[1]} at={row[2]}Z temperature={row[3]}")


if __name__ == "__main__":
    main()
