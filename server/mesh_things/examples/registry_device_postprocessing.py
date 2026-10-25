#!/usr/bin/env python3
"""Attach a blueprint to a device, calibrate it, switch it on and compute past values.

  attach     connect the blueprint's inputs to the device's channels and add the
             channels it produces
  calibrate  record the calibration of one step, in force from --valid-from onwards
  enable     start computing values from live readings
  backfill   compute values for past readings too (these never raise alarms)
  show       list the device's postprocessings, anything blocking them, and their backfills

A typical sequence, for the NO2 example of registry_manage_blueprint.py:

  python3 registry_device_postprocessing.py attach --device-uuid <uuid> --blueprint-id <id>
  python3 registry_device_postprocessing.py calibrate --device-uuid <uuid> --postprocessing-id <id> \\
      --step ppb --params '{"sensitivity": 0.42, "working_zero": 220.0}'
  python3 registry_device_postprocessing.py enable --device-uuid <uuid> --postprocessing-id <id>
  python3 registry_device_postprocessing.py backfill --device-uuid <uuid> --postprocessing-id <id> \\
      --start 2026-09-01
"""
import argparse
import json
import os
import sys

from mesh_things.client import ApiError, MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def print_postprocessing(pp: dict) -> None:
    state = "enabled" if pp["is_enabled"] else "disabled"
    print(f"{pp['id']}  {pp['blueprint_name']} v{pp['blueprint_version']}  [{state}]")
    print(f"  tolerance: {pp['effective_tolerance_seconds']}s")
    for slot, measurement_id in pp["input_bindings"].items():
        print(f"  slot {slot} <- measurement {measurement_id}")
    for output in pp["outputs"]:
        print(f"  output {output['channel']} ({output['unit'] or 'no unit'})")
    for problem in pp["problems"]:
        print(f"  ! {problem}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["attach", "calibrate", "enable", "backfill", "show"])
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"))
    parser.add_argument("--device-uuid", required=True)
    parser.add_argument("--postprocessing-id", help="required by calibrate, enable and backfill")
    parser.add_argument("--blueprint-id", help="attach: the blueprint, yours or a public one")
    parser.add_argument("--version", type=int, help="attach: version number, defaults to the latest")
    parser.add_argument("--bindings", default="{}", help='attach: JSON {slot: measurement id} for slots to bind by hand')
    parser.add_argument("--output-prefix", default="", help="attach: prepended to every derived field name")
    parser.add_argument("--step", help="calibrate: step key")
    parser.add_argument("--params", default="{}", help="calibrate: JSON of the step's calibration parameters")
    parser.add_argument("--valid-from", help="calibrate: when it takes effect, defaults to now")
    parser.add_argument("--start", help="backfill: start of the range, e.g. 2026-09-01")
    parser.add_argument("--stop", help="backfill: end of the range, defaults to now")
    parser.add_argument("--include-dependants", action="store_true", help="backfill: also recompute what reads it")
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY.")
    try:
        run(MeshThings(API_URL, args.api_key).devices, args)
    except ApiError as e:
        if e.status >= 500:
            raise
        sys.exit(f"{e.status}:\n{json.dumps(e.body, indent=2)}")


def run(devices, args) -> None:
    device = args.device_uuid
    if args.action == "show":
        for pp in devices.postprocessings_list(device):
            print_postprocessing(pp)
            for backfill in devices.postprocessings_backfills_list(device, pp["id"]):
                print(f"  backfill {backfill['start']} .. {backfill['stop']}: {backfill['status']}, "
                      f"{backfill['points_published']} value(s){' - ' + backfill['error'] if backfill['error'] else ''}")
        return

    if args.action == "attach":
        body = {"blueprint_id": args.blueprint_id, "input_bindings": json.loads(args.bindings),
                "output_prefix": args.output_prefix}
        if args.version:
            body["blueprint_version"] = args.version
        print_postprocessing(devices.postprocessings_create(device, body=body))
        return

    if not args.postprocessing_id:
        sys.exit(f"{args.action} needs --postprocessing-id")
    pp = args.postprocessing_id

    if args.action == "calibrate":
        body = {"step_key": args.step, "params": json.loads(args.params)}
        if args.valid_from:
            body["valid_from"] = args.valid_from
        calibration = devices.postprocessings_calibrations_create(device, pp, body=body)
        print(f"Calibrated step {calibration['step_key']} from {calibration['valid_from']}: {calibration['params']}")
    elif args.action == "enable":
        print_postprocessing(devices.postprocessings_update(device, pp, body={"is_enabled": True}))
    elif args.action == "backfill":
        body = {"start": args.start, "include_dependants": args.include_dependants}
        if args.stop:
            body["stop"] = args.stop
        backfill = devices.postprocessings_backfills_create(device, pp, body=body)
        print(f"Backfill {backfill['id']} queued ({backfill['start']} .. {backfill['stop']}); check it with `show`")


if __name__ == "__main__":
    main()
