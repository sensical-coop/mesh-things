from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from common.units import quantity_kind_for
from registry.management.commands.seed_measurement_catalog import _is_catalogued
from registry.measurement_catalog_seed import MEASUREMENT_TYPE_SEED
from registry.models import MeasurementType, TelemetryVariant, TelemetryVariantMeasurement

_EXPECTED_VARIANTS = {
    "telemetry:device_metrics",
    "telemetry:environment_metrics",
    "telemetry:air_quality_metrics",
    "telemetry:power_metrics",
    "telemetry:local_stats",
    "telemetry:health_metrics",
    "telemetry:host_metrics",
    "telemetry:traffic_management_stats",
}


class SeedMeasurementCatalogTests(TestCase):
    def test_seeds_a_telemetry_variant_per_protobuf_variant(self):
        call_command("seed_measurement_catalog", stdout=StringIO())

        seeded = set(TelemetryVariant.objects.values_list("payload_kind", flat=True))

        self.assertEqual(seeded, _EXPECTED_VARIANTS | {"computed:quality"})

    def test_seeds_the_quality_namespace_with_units(self):
        call_command("seed_measurement_catalog", stdout=StringIO())

        rows = {
            m.field_name: m for m in MeasurementType.objects.filter(payload_kind="computed:quality")
        }
        self.assertEqual(
            set(rows), {"completeness_ratio", "observed", "expected", "largest_gap_seconds"}
        )
        self.assertEqual(rows["completeness_ratio"].native_unit, "ratio")
        self.assertEqual(rows["largest_gap_seconds"].quantity_kind, "physical_property")

    def test_alarms_are_not_seeded(self):
        call_command("seed_measurement_catalog", stdout=StringIO())

        self.assertFalse(MeasurementType.objects.filter(payload_kind__startswith="alarms").exists())

    def test_skips_non_numeric_fields(self):
        call_command("seed_measurement_catalog", stdout=StringIO())

        self.assertFalse(
            MeasurementType.objects.filter(payload_kind="telemetry:host_metrics", field_name="user_string").exists()
        )
        self.assertTrue(
            MeasurementType.objects.filter(payload_kind="telemetry:host_metrics", field_name="uptime_seconds").exists()
        )

    def test_links_every_measurement_type_to_its_telemetry_variant(self):
        call_command("seed_measurement_catalog", stdout=StringIO())

        telemetry_variant = TelemetryVariant.objects.get(payload_kind="telemetry:environment_metrics")
        linked_fields = set(
            TelemetryVariantMeasurement.objects.filter(telemetry_variant=telemetry_variant).values_list(
                "measurement_type__field_name", flat=True
            )
        )
        self.assertIn("temperature", linked_fields)
        self.assertIn("relative_humidity", linked_fields)
        self.assertEqual(
            MeasurementType.objects.filter(payload_kind="telemetry:environment_metrics").count(), len(linked_fields)
        )

    def test_telemetry_rows_get_their_curated_unit_and_description(self):
        call_command("seed_measurement_catalog", stdout=StringIO())

        row = MeasurementType.objects.get(payload_kind="telemetry:environment_metrics", field_name="temperature")
        self.assertEqual(row.native_unit, "degC")
        self.assertEqual(row.quantity_kind, "physical_property")
        self.assertEqual(row.description, "Temperature measured")

    def test_every_catalogued_protobuf_field_has_curated_data(self):
        call_command("seed_measurement_catalog", stdout=StringIO())

        uncurated = MeasurementType.objects.filter(
            payload_kind__startswith="telemetry:", native_unit__isnull=True, quantity_kind__isnull=True
        ).values_list("payload_kind", "field_name")
        self.assertEqual(list(uncurated), [])

    def test_skips_repeated_numeric_fields(self):
        call_command("seed_measurement_catalog", stdout=StringIO())

        self.assertFalse(
            MeasurementType.objects.filter(
                payload_kind="telemetry:environment_metrics", field_name="one_wire_temperature"
            ).exists()
        )

    def test_backfills_a_row_discovery_created_without_units(self):
        # consume_sensor_discovery creates empty rows from live traffic
        MeasurementType.objects.create(payload_kind="telemetry:environment_metrics", field_name="temperature")

        call_command("seed_measurement_catalog", stdout=StringIO())

        row = MeasurementType.objects.get(payload_kind="telemetry:environment_metrics", field_name="temperature")
        self.assertEqual((row.native_unit, row.quantity_kind), ("degC", "physical_property"))
        self.assertEqual(row.description, "Temperature measured")

    def test_never_overwrites_a_curated_unit(self):
        MeasurementType.objects.create(
            payload_kind="telemetry:environment_metrics",
            field_name="temperature",
            native_unit="degF",
            quantity_kind="physical_property",
            description="hand-corrected",
        )

        call_command("seed_measurement_catalog", stdout=StringIO())

        row = MeasurementType.objects.get(payload_kind="telemetry:environment_metrics", field_name="temperature")
        self.assertEqual((row.native_unit, row.description), ("degF", "hand-corrected"))

    def test_backfills_a_variant_name_discovery_left_null(self):
        # consume_sensor_discovery get_or_creates the variant with no defaults.
        TelemetryVariant.objects.create(payload_kind="telemetry:environment_metrics")

        call_command("seed_measurement_catalog", stdout=StringIO())

        self.assertEqual(
            TelemetryVariant.objects.get(payload_kind="telemetry:environment_metrics").name, "EnvironmentMetrics"
        )

    def test_never_overwrites_a_curated_variant_name(self):
        TelemetryVariant.objects.create(payload_kind="telemetry:environment_metrics", name="BME280 (curated)")

        call_command("seed_measurement_catalog", stdout=StringIO())

        self.assertEqual(
            TelemetryVariant.objects.get(payload_kind="telemetry:environment_metrics").name, "BME280 (curated)"
        )

    def test_is_idempotent_and_does_not_clobber_curated_detectors(self):
        call_command("seed_measurement_catalog", stdout=StringIO())
        link = TelemetryVariantMeasurement.objects.get(
            telemetry_variant__payload_kind="telemetry:environment_metrics",
            measurement_type__field_name="temperature",
        )
        link.default_enabled_detectors = ["range"]
        link.save(update_fields=["default_enabled_detectors"])
        telemetry_variant_count = TelemetryVariant.objects.count()
        measurement_type_count = MeasurementType.objects.count()
        link_count = TelemetryVariantMeasurement.objects.count()

        call_command("seed_measurement_catalog", stdout=StringIO())

        self.assertEqual(TelemetryVariant.objects.count(), telemetry_variant_count)
        self.assertEqual(MeasurementType.objects.count(), measurement_type_count)
        self.assertEqual(TelemetryVariantMeasurement.objects.count(), link_count)
        link.refresh_from_db()
        self.assertEqual(link.default_enabled_detectors, ["range"])


class CuratedSeedTableTests(SimpleTestCase):
    """The curated table against the protobuf it describes."""

    @staticmethod
    def _catalogued_protobuf_fields() -> set[tuple[str, str]]:
        from meshtastic.protobuf import telemetry_pb2

        return {
            (f"telemetry:{variant_field.name}", field.name)
            for variant_field in telemetry_pb2.Telemetry.DESCRIPTOR.oneofs_by_name["variant"].fields
            for field in variant_field.message_type.fields
            if _is_catalogued(field)
        }

    def test_covers_exactly_the_catalogued_protobuf_fields(self):
        self.assertEqual(self._catalogued_protobuf_fields(), set(MEASUREMENT_TYPE_SEED))

    def test_every_curated_unit_resolves_to_a_quantity_kind(self):
        # A typo unit would store quantity_kind as NULL.
        for (payload_kind, field_name), (unit, _) in MEASUREMENT_TYPE_SEED.items():
            if unit is not None:
                with self.subTest(channel=f"{payload_kind}.{field_name}"):
                    self.assertIsNotNone(quantity_kind_for(unit), f"unknown unit {unit!r}")
