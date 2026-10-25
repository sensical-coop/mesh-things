#!/usr/bin/env python3
"""What this instance knows about: telemetry types, measurements, alarm detectors and algorithms.

The catalog is shared by every owner. It explains what each channel measures and in which
unit, which alarms you can switch on, and which postprocessing algorithms you can use in a
blueprint. The instance's overall figures come first.

  python3 get_catalog.py
  python3 get_catalog.py --payload-kind telemetry:environment_metrics
"""
import argparse
import os
import sys

from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"))
    parser.add_argument("--payload-kind", help="only the measurements of this telemetry type")
    args = parser.parse_args()
    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY.")
    api = MeshThings(API_URL, args.api_key)

    figures = api.metrics.get()
    print(f"This instance has {figures['owners']} owner(s), {figures['meshes']} mesh(es), "
          f"{figures['devices']} device(s) and {figures['active_gateways']} active gateway(s).")

    print("\nTelemetry types:")
    for variant in api.telemetry_variants.list():
        print(f"  {variant['payload_kind']:<40} {variant['name'] or ''}")

    print("\nMeasurements:")
    for measurement in api.measurements.list(payload_kind=args.payload_kind):
        unit = measurement["native_unit"] or "no unit"
        print(f"  {measurement['channel']:<44} {unit:<10} {measurement['origin']}")

    print("\nAlarm detectors:")
    for detector in api.detectors.list():
        print(f"  {detector['name']:<14} switched on per {detector['scope']}")

    print("\nPostprocessing algorithms:")
    for algorithm in api.algorithms.list():
        print(f"  {algorithm['name']:<24} from {', '.join(algorithm['inputs'])} to {', '.join(algorithm['outputs'])}")


if __name__ == "__main__":
    main()
