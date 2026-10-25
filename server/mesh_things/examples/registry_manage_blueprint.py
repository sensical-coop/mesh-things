#!/usr/bin/env python3
"""List the postprocessing algorithms, create a blueprint, or add a version to one.

A blueprint is a reusable recipe. It lists the inputs it reads and the steps it runs,
each step using one of the instance's algorithms (see them with --list-algorithms). A
step takes its inputs from the blueprint's inputs ("slot:<name>") or from an earlier
step ("step:<key>.<output>"), so turning a voltage into ppb and then into ug/m3 takes
two steps. Calibration is not part of the recipe: each device brings its own when the
blueprint is attached (see registry_device_postprocessing.py).

A version cannot be changed once created. To change the steps, add a new version;
devices keep using theirs until you move them.
"""
import argparse
import json
import os
import sys

from mesh_things.client import ApiError, MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")

# NO2 from a four-electrode electrochemical sensor, converted to a mass
# concentration. Its sensitivity and zero offsets are calibration: set per device.
EXAMPLE_BLUEPRINT = {
    "name": "no2-electrochemical",
    "description": "NO2 from an EC sensor, in ppb and ug/m3",
    "is_public": False,
    "inputs": [
        {"slot": "working", "default_channel": "ads1115.channel_0"},
        {"slot": "auxiliary", "default_channel": "ads1115.channel_1"},
        {"slot": "temperature", "default_channel": "environment_metrics.temperature"},
    ],
    "steps": [
        {
            "key": "ppb",
            "order": 0,
            "function_name": "ec_sensor_ppb",
            "inputs": {"working": "slot:working", "auxiliary": "slot:auxiliary", "temperature": "slot:temperature"},
            "params": {"temperature_coefficient": 0.01},
            "outputs": {"concentration_ppb": "no2_ppb"},
        },
        {
            "key": "ugm3",
            "order": 1,
            "function_name": "ppb_to_ugm3",
            "inputs": {"concentration_ppb": "step:ppb.concentration_ppb", "temperature": "slot:temperature"},
            "params": {"molecular_weight": 46.01},
            "outputs": {"concentration_ugm3": "no2_ugm3"},
        },
    ],
    "notes": "First version",
}


def print_algorithms(api: MeshThings) -> None:
    for spec in api.algorithms.list():
        print(f"{spec['name']}  [{spec['mode']}]")
        print(f"  inputs:  {', '.join(spec['inputs'])}")
        # "@<input>" means unit-preserving: the output carries the unit of
        # whichever channel is bound to that input.
        units = spec.get("output_units") or {}
        print(f"  outputs: {', '.join(f'{o} ({units[o]})' if units.get(o) else o for o in spec['outputs'])}")
        for param in spec["params"]:
            kind = "calibration, per device" if param["calibration"] else "blueprint step"
            default = "required" if param["required"] else f"default {param['default']}"
            unit = f", {param['unit']}" if param["unit"] else ""
            print(f"  param:   {param['name']} ({kind}, {default}{unit})")


def print_version(version: dict) -> None:
    print(f"  version {version['number']}, used by {version['device_count']} device(s)")
    for slot in version["inputs"]:
        default = f" (default {slot['default_channel']})" if slot.get("default_channel") else ""
        print(f"    slot {slot['slot']}{default}")
    for step in version["steps"]:
        print(f"    {step['order']}. {step['key']}: {step['function_name']} -> {', '.join(step['outputs'].values())}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"))
    parser.add_argument("--list-algorithms", action="store_true", help="print the available algorithms and exit")
    parser.add_argument("--blueprint-file", help="JSON file to create; defaults to the built-in example")
    parser.add_argument(
        "--new-version-of", metavar="BLUEPRINT_ID", help="add the file's inputs/steps as a new version of this blueprint"
    )
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY.")
    api = MeshThings(API_URL, args.api_key)

    if args.list_algorithms:
        print_algorithms(api)
        return

    payload = EXAMPLE_BLUEPRINT
    if args.blueprint_file:
        with open(args.blueprint_file) as f:
            payload = json.load(f)

    blueprints = api.postprocessing_blueprints
    try:
        if args.new_version_of:
            body = {k: payload[k] for k in ("inputs", "steps", "notes") if k in payload}
            version = blueprints.versions_create(args.new_version_of, body=body)
            print(f"Added version {version['number']} to blueprint {args.new_version_of}")
            print_version(version)
            return
        blueprint = blueprints.create(body=payload)
    except ApiError as e:
        if e.status >= 500:
            raise
        # Steps are validated against the algorithm registry when written, so
        # a mis-bound input fails here rather than later in the stream.
        sys.exit(f"{e.status}:\n{json.dumps(e.body, indent=2)}")
    print(f"Created blueprint {blueprint['id']} ({blueprint['name']})")
    print_version(blueprint["latest_version"])
    print("\nAttach it to a device with registry_device_postprocessing.py attach")


if __name__ == "__main__":
    main()
