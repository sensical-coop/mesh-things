#!/usr/bin/env python3
"""A walk through your readings: your devices, the channels they report, and their values.

The script first lists the devices you have registered and the channels each one
reports. It then shows the values of one kind of telemetry over a range of time, and
the latest value of every channel, with its unit.

A device can be addressed in two ways, and the script shows both:

  by its registration    the device's uuid, as listed by the API (the default here)
  by mesh and node       the mesh id and the node number, with --mesh-id and --node-id,
                         which also reaches devices that report but were never registered

It needs your API key in MESH_THINGS_API_KEY. Pass --dataframe to see the values as a
pandas DataFrame, which needs mesh-things[pandas].
"""
import argparse
import os

from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def first_device_with_channels(api: MeshThings, devices: list[dict]) -> tuple[str, list[dict]]:
    """Return the first device that has reported any channels.

    A device can be registered and never have reported, so the first one listed may have no data.
    """
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
    parser.add_argument("--device-uuid", default=None, help="the device to read; defaults to the first one that has reported")
    parser.add_argument("--payload-kind", default=None, help="if omitted, the family of the first channel the device reports")
    # A node number is only unique within a mesh, so it is always given together with the mesh.
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
        # Addressing by mesh and node also reaches devices that were never registered.
        address = (args.mesh_id, args.node_id)
        timeseries, latest = api.readings.meshes_nodes_get, api.readings.meshes_nodes_latest_get
        channels = []
        print(f"Querying by mesh+node: mesh={args.mesh_id} node={args.node_id}")
    else:
        # Registration rows, not an InfluxDB scan: a device is listed whether or not it has reported.
        devices = api.devices.list()
        print(f"{len(devices)} device(s) registered:")
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

    # Without a payload_kind, the API returns the latest value of every channel, with its unit and origin.
    print("\nLatest value of every channel:")
    for r in latest(*address)["readings"]:
        unit = f" {r['unit']}" if r.get("unit") else ""
        print(f"  {r['channel']:<42} = {r['value']}{unit}  ({r['origin']})")


if __name__ == "__main__":
    main()
