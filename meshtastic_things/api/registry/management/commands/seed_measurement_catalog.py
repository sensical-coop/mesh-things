"""Populate the TelemetryVariant/MeasurementType/TelemetryVariantMeasurement
catalog from the Meshtastic Telemetry protobuf schema"""
from collections import Counter

from google.protobuf.descriptor import FieldDescriptor
from meshtastic.protobuf import telemetry_pb2

from django.core.management.base import BaseCommand
from django.db import transaction

from common.channels import QUALITY_KIND, TELEMETRY
from common.units import QUALITY_CHANNELS, quantity_kind_for

from registry.measurement_catalog_seed import defaults_for
from registry.models import MeasurementType, TelemetryVariant, TelemetryVariantMeasurement

_SKIP_CPP_TYPES = (FieldDescriptor.CPPTYPE_STRING, FieldDescriptor.CPPTYPE_MESSAGE)

# The data-quality metrics quality_worker writes to InfluxDB's `quality` measurement.
_QUALITY_SEED = [
    (field_name, {"native_unit": unit, "quantity_kind": quantity_kind_for(unit), "description": description})
    for field_name, (unit, description) in QUALITY_CHANNELS.items()
]


def _is_catalogued(field) -> bool:
    """Whether a protobuf field is one numeric channel.

    Repeated numerics arrive as a list, so nothing downstream can write them.
    """
    if field.cpp_type in _SKIP_CPP_TYPES:
        return False
    # protobuf >= 6 dropped FieldDescriptor.label in favour of is_repeated.
    is_repeated = getattr(field, "is_repeated", None)
    if is_repeated is None:
        is_repeated = field.label == FieldDescriptor.LABEL_REPEATED
    return not is_repeated


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
        variant_fields = telemetry_pb2.Telemetry.DESCRIPTOR.oneofs_by_name["variant"].fields
        created, backfilled = Counter(), Counter()

        for variant_field in variant_fields:
            payload_kind = f"{TELEMETRY}:{variant_field.name}"
            name = variant_field.message_type.name
            telemetry_variant, was_created = TelemetryVariant.objects.get_or_create(
                payload_kind=payload_kind, defaults={"name": name}
            )
            created["variants"] += was_created
            # Sensor discovery creates variants bare, so an existing row may have no name.
            if not was_created:
                backfilled["variants"] += _fill_blanks(telemetry_variant, name=name)

            for field in variant_field.message_type.fields:
                if not _is_catalogued(field):
                    continue
                curated = defaults_for(payload_kind, field.name)
                measurement_type, was_created = MeasurementType.objects.get_or_create(
                    payload_kind=payload_kind, field_name=field.name, defaults=curated
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
            f"({len(variant_fields)} telemetry variants + the quality namespace)."
        )
