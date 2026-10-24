#!/usr/bin/env python3
"""Readings walkthrough, demonstrating the split between the two roles:

  registry  GET /devices                          -> which devices are registered
  registry  GET /devices/{uuid}/measurements      -> which channels they report
  readings  GET /readings/devices/{uuid}          -> the values over a range
            GET /readings/devices/{uuid}/latest   -> the most recent of each

The registry owns the catalog; the readings role answers only for the values.
It deliberately has no device or channel listing of its own - a second copy of
that catalog only ever drifts from the first.

Each readings query is reachable two ways, and this script exercises both:

  /readings/devices/{uuid}            the registration address, the same UUID
                                      the registry uses - the default here
  /readings/meshes/{m}/nodes/{n}      the store-native address; InfluxDB is
                                      tagged by mesh_id/node_id, so it reaches
                                      devices with telemetry but no
                                      registration row (--mesh-id/--node-id)

Requires MESH_THINGS_API_KEY. Pass --dataframe to print the readings as a pandas
DataFrame (needs mesh-things[pandas]). See ../../../docs/api-reference.md.
"""
import argparse
import os

from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def first_device_with_channels(api: MeshThings, devices: list[dict]) -> tuple[str, list[dict]]:
    """A registration row doesn't imply telemetry - a device can be registered and
    never have reported - so walk to the first one that has channels."""
    for d in devices:
        channels = api.devices.measurements_list(d["uuid"])
        if channels:
            return d["uuid"], channels
    return devices[0]["uuid"], []


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--lookback",
        default="-30d",
        help="start of the range: a duration (-24h), a date (2026-09-01) or a timestamp",
    )
    parser.add_argument(
        "--stop", default=None, help="end of the range, same forms as --lookback; defaults to now()"
    )
    parser.add_argument("--device-uuid", default=None, help="registry Device.id; if omitted, the first device found")
    parser.add_argument("--payload-kind", default=None, help="if omitted, the family of the first channel the device reports")
    # The store-native address. node_id alone is only unique among registry's
    # currently-allowed Device rows, not globally or over time - hence the
    # mesh_id nesting. See ../../../docs/architecture.md#readings-authentication.
    parser.add_argument("--node-id", default=None, help="query by mesh+node instead of by UUID, as a number or !aabbccdd")
    parser.add_argument("--mesh-id", default=None, help="required alongside --node-id")
    parser.add_argument("--window", default=None, help="e.g. 6h, for downsampled timeseries")
    parser.add_argument("--agg", default=None, choices=["mean", "max", "min", "last", "first", "sum", "count"])
    parser.add_argument("--dataframe", action="store_true", help="print the readings as a pandas DataFrame")
    args = parser.parse_args()
    if (args.node_id is None) != (args.mesh_id is None):
        parser.error("--mesh-id and --node-id go together")
    api = MeshThings(API_URL)

    if args.node_id is not None:
        # Explicit store-native address: no registry lookup at all, which is
        # the point - this path works for devices registry has never heard of.
        address = (args.mesh_id, args.node_id)
        timeseries, latest = api.readings.meshes_nodes_get, api.readings.meshes_nodes_latest_get
        channels = []
        print(f"Querying by mesh+node: mesh={args.mesh_id} node={args.node_id}")
    else:
        # Registration rows, not an InfluxDB scan: a device is listed whether or not it has reported.
        devices = api.devices.list()
        print(f"{len(devices)} device(s) registered in registry:")
        for d in devices:
            described = d.get("label") or d.get("name") or "(unnamed)"
            hardware = f"  hw={d['hardware_type']}" if d.get("hardware_type") else ""
            print(f"  {d['uuid']}  node_id={d['node_id']}  {described}{hardware}")
        if not devices:
            return

        if args.device_uuid:
            device_uuid, channels = args.device_uuid, api.devices.measurements_list(args.device_uuid)
        else:
            device_uuid, channels = first_device_with_channels(api, devices)
        address = (device_uuid,)
        timeseries, latest = api.readings.devices_get, api.readings.devices_latest_get

        # Each channel carries an `origin`, so a postprocessing output or a quality
        # diagnostic is told apart from a sensor reading without parsing names.
        print(f"\n{len(channels)} channel(s) for device {device_uuid}:")
        for c in channels:
            mt = c["measurement_type"]
            print(f"  {mt['channel']:<42} origin={mt['origin']:<9} unit={mt['native_unit']}")

    # payload_kind reads a whole family at once; channel reads one series.
    if args.payload_kind:
        payload_kind = args.payload_kind
    elif channels:
        payload_kind = channels[0]["measurement_type"]["payload_kind"]
    else:
        payload_kind = "telemetry:device_metrics"

    readings = timeseries(
        *address, payload_kind=payload_kind, start=args.lookback, stop=args.stop, window=args.window, agg=args.agg,
    )
    span = f"{args.lookback} to {args.stop}" if args.stop else f"since {args.lookback}"
    print(f"\nReadings, payload_kind={payload_kind!r}, {span}:")
    if args.dataframe:
        from mesh_things.pandas import channel_units, to_dataframe

        print(to_dataframe(readings, units=channel_units(api.measurements.list())))
    else:
        for s in readings["series"]:
            latest_point = s["points"][-1] if s["points"] else None
            print(f"  {s['channel']:<42} {len(s['points'])} point(s), latest={latest_point}")

    # No payload_kind: the latest value of every channel at once, decorated with
    # unit/quantity_kind/origin from the registry's catalog.
    print("\nLatest value of every channel:")
    for r in latest(*address)["readings"]:
        unit = f" {r['unit']}" if r.get("unit") else ""
        print(f"  {r['channel']:<42} = {r['value']}{unit}  ({r['origin']})")


if __name__ == "__main__":
    main()
