#!/usr/bin/env python3
"""Curate quality config: a telemetry variant's default reading interval and
default detectors (catalog-wide, superuser-only), and one device's range
bounds (valid_min/valid_max, set by the mesh owner).

This is live config, not just documentation: every edit publishes to
mesh.quality_config.v1, which the Flink quality checks hold as broadcast
state. The interval sizes the flat-value window and feeds the completeness
check; the range bounds drive the range check. See ../../../docs/data-quality.md.

Range is deliberately per-device rather than catalog-wide - one device's
plausible range for a channel can differ from another's reporting the same
field - so --range-min/--range-max need --device-uuid, while the catalog
options apply to every device reporting that telemetry variant.

Catalog rows themselves are pre-seeded from the Meshtastic protobuf schema
when the registry_api container starts, not created here - this script only
edits the ones that already exist. TelemetryVariant is keyed by wire-format
message type (e.g. "telemetry:environment_metrics"), NOT verified hardware -
a variant can be produced by several different chips. Catalog writes are
superuser-only, see ../../../docs/architecture.md#sensor--measurement-catalog."""
import argparse
import os
import sys

from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def find_telemetry_variant(api: MeshThings, payload_kind: str) -> dict:
    telemetry_variant = next((v for v in api.telemetry_variants.list() if v["payload_kind"] == payload_kind), None)
    if telemetry_variant is None:
        sys.exit(
            f"No TelemetryVariant for payload_kind={payload_kind!r} - registry_api seeds these at "
            "start; run `manage.py seed_measurement_catalog` if it has not"
        )
    return telemetry_variant


def find_device_measurement(api: MeshThings, device_uuid: str, field_name: str) -> dict:
    measurements = api.devices.measurements_list(device_uuid)
    measurement = next((m for m in measurements if m["measurement_type"]["field_name"] == field_name), None)
    if measurement is None:
        sys.exit(
            f"Device {device_uuid} has no measurement for field {field_name!r} - channels appear "
            "on their own as telemetry arrives"
        )
    return measurement


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"), help="must be a superuser key for catalog writes")
    parser.add_argument("--payload-kind", required=True, help='e.g. "telemetry:environment_metrics"')
    parser.add_argument("--list", action="store_true", help="print every linked field and its catalog defaults, then exit")
    parser.add_argument(
        "--default-reading-interval-seconds",
        type=int,
        default=None,
        help="catalog default for how often devices sample this telemetry type, used "
        "when a device hasn't set its own reading_interval_seconds",
    )
    parser.add_argument("--device-uuid", default=None, help="required with --range-min/--range-max")
    parser.add_argument("--field-name", default=None, help='e.g. "temperature" - required with --range-min/--range-max')
    parser.add_argument("--range-min", type=float, default=None)
    parser.add_argument("--range-max", type=float, default=None)
    args = parser.parse_args()

    setting_range = args.range_min is not None or args.range_max is not None

    if not args.api_key:
        sys.exit("No API key - pass --api-key or set MESH_THINGS_API_KEY")
    if not args.list and args.default_reading_interval_seconds is None and not setting_range:
        sys.exit(
            "Nothing to do - pass --list, --default-reading-interval-seconds, and/or "
            "--device-uuid and --field-name with --range-min/--range-max"
        )
    if setting_range and (args.range_min is None or args.range_max is None):
        sys.exit("--range-min and --range-max must be given together")
    if setting_range and (args.device_uuid is None or args.field_name is None):
        sys.exit("--range-min/--range-max require --device-uuid and --field-name")

    api = MeshThings(API_URL, args.api_key)
    telemetry_variant = find_telemetry_variant(api, args.payload_kind)

    if args.list:
        print(
            f"{telemetry_variant['payload_kind']}  "
            f"default_reading_interval_seconds={telemetry_variant['default_reading_interval_seconds']}"
        )
        for link in api.telemetry_variants.measurements_list(telemetry_variant["id"]):
            mt = link["measurement_type"]
            print(
                f"  {mt['field_name']:<24} default_enabled_detectors={link['default_enabled_detectors']}  "
                f"unit={mt['native_unit']}"
            )
        return

    if args.default_reading_interval_seconds is not None:
        telemetry_variant = api.telemetry_variants.update(
            telemetry_variant["id"],
            body={"default_reading_interval_seconds": args.default_reading_interval_seconds},
        )
        print(
            f"{telemetry_variant['payload_kind']}: "
            f"default_reading_interval_seconds={telemetry_variant['default_reading_interval_seconds']}"
        )

    if setting_range:
        measurement = find_device_measurement(api, args.device_uuid, args.field_name)
        # valid_min/valid_max are always sent together - the API rejects one alone.
        measurement = api.devices.measurements_update(
            args.device_uuid, measurement["id"], body={"valid_min": args.range_min, "valid_max": args.range_max},
        )
        print(
            f"{args.device_uuid} {args.payload_kind}:{args.field_name}: "
            f"valid_min={measurement['valid_min']} valid_max={measurement['valid_max']}"
        )


if __name__ == "__main__":
    main()
