#!/usr/bin/env python3
"""How well one device is reporting: data quality and radio traffic.

Quality tells you, for each channel, how many readings arrived compared with how many
were expected, and the longest gap. Traffic tells you how many packets the device sent,
and of which kinds. Both help you spot a device that is struggling before its data goes
missing.

  python3 get_device_health.py --device-uuid <uuid>
  python3 get_device_health.py --device-uuid <uuid> --start=-7d --range 7d
"""
import argparse
import os
import sys

from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"))
    parser.add_argument("--device-uuid", required=True, help="the device's uuid, from get_started.py")
    parser.add_argument("--start", default="-24h", help="start of the quality window, for example -7d")
    parser.add_argument("--range", default="24h", choices=["1h", "24h", "7d", "30d"], help="traffic window")
    args = parser.parse_args()
    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY.")
    api = MeshThings(API_URL, args.api_key)

    quality = api.readings.devices_quality_get(args.device_uuid, start=args.start)
    print(f"Quality from {quality['start']} to {quality['stop']}: {quality['points_ingested']:.0f} point(s) received")
    if quality["range_ratio"] is not None:
        print(f"  {quality['range_ratio']:.0%} of the values were within their expected range")
    for channel in quality["channels"]:
        ratio = "-" if channel["completeness_ratio"] is None else f"{channel['completeness_ratio']:.0%}"
        gap = "-" if channel["largest_gap_seconds"] is None else f"{channel['largest_gap_seconds'] / 60:.0f} min"
        print(f"  {channel['channel']:<40} complete {ratio:>5}, largest gap {gap}")
    alarms = {name: count for name, count in quality["alarms_by_detector"].items() if count}
    print(f"  alarms: {alarms or 'none'}")

    traffic = api.readings.devices_traffic_get(args.device_uuid, range=args.range)
    print(f"\nTraffic over the last {traffic['range']}: {traffic['packets']} packet(s), heard {traffic['receptions']} time(s)")
    for port in traffic["ports"]:
        print(f"  {port['name']:<28} {port['packets']} packet(s)")


if __name__ == "__main__":
    main()
