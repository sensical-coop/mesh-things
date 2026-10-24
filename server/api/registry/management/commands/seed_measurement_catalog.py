"""Populate the TelemetryVariant/MeasurementType/TelemetryVariantMeasurement
catalog from the Meshtastic Telemetry protobuf schema"""
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from mesh_things.catalog import telemetry_variants
from mesh_things.channels import QUALITY_KIND
from mesh_things.units import QUALITY_CHANNELS, quantity_kind_for

from registry.measurement_catalog_seed import defaults_for
from registry.models import MeasurementType, TelemetryVariant, TelemetryVariantMeasurement

# The data-quality metrics quality_worker writes to InfluxDB's `quality` measurement.
_QUALITY_SEED = [
    (field_name, {"native_unit": unit, "quantity_kind": quantity_kind_for(unit), "description": description})
    for field_name, (unit, description) in QUALITY_CHANNELS.items()
]


def _fill_blanks(instance, **curated) -> bool:
    """Fill empty columns, never overwriting one already set. True if anything changed."""
    blanks = [name for name, value in curated.items() if value and not getattr(instance, name)]
    if not blanks:
        return False
    for name in blanks:
        setattr(instance, name, curated[name])
    instance.save(update_fields=blanks)
    return True


class Command(BaseCommand):
    help = "Seed TelemetryVariant/MeasurementType/TelemetryVariantMeasurement from the Telemetry protobuf schema."

    @transaction.atomic
    def handle(self, *args, **options):
        variants = list(telemetry_variants())
        created, backfilled = Counter(), Counter()

        for payload_kind, name, field_names in variants:
            telemetry_variant, was_created = TelemetryVariant.objects.get_or_create(
                payload_kind=payload_kind, defaults={"name": name}
            )
            created["variants"] += was_created
            # Sensor discovery creates variants bare, so an existing row may have no name.
            if not was_created:
                backfilled["variants"] += _fill_blanks(telemetry_variant, name=name)

            for field_name in field_names:
                curated = defaults_for(payload_kind, field_name)
                measurement_type, was_created = MeasurementType.objects.get_or_create(
                    payload_kind=payload_kind, field_name=field_name, defaults=curated
                )
                created["measurement_types"] += was_created
                if not was_created:
                    backfilled["measurement_types"] += _fill_blanks(measurement_type, **curated)
                _, was_created = TelemetryVariantMeasurement.objects.get_or_create(
                    telemetry_variant=telemetry_variant, measurement_type=measurement_type
                )
                created["links"] += was_created

        quality_variant, was_created = TelemetryVariant.objects.get_or_create(
            payload_kind=QUALITY_KIND, defaults={"name": "Data quality metrics"}
        )
        created["variants"] += was_created
        if not was_created:
            backfilled["variants"] += _fill_blanks(quality_variant, name="Data quality metrics")

        for field_name, curated in _QUALITY_SEED:
            measurement_type, was_created = MeasurementType.objects.get_or_create(
                payload_kind=QUALITY_KIND, field_name=field_name, defaults=curated
            )
            created["measurement_types"] += was_created
            if not was_created:
                backfilled["measurement_types"] += _fill_blanks(measurement_type, **curated)
            _, was_created = TelemetryVariantMeasurement.objects.get_or_create(
                telemetry_variant=quality_variant, measurement_type=measurement_type
            )
            created["links"] += was_created

        self.stdout.write(
            f"TelemetryVariant: {created['variants']} created, {backfilled['variants']} backfilled. "
            f"MeasurementType: {created['measurement_types']} created, "
            f"{backfilled['measurement_types']} backfilled. "
            f"TelemetryVariantMeasurement: {created['links']} created "
            f"({len(variants)} telemetry variants + the quality namespace)."
        )
