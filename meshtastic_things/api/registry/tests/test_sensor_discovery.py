import uuid
from io import StringIO

from django.core.management import call_command

from registry.management.commands.consume_sensor_discovery import Command as DiscoveryCommand
from registry.models import DeviceTelemetryVariant, Measurement, MeasurementType, TelemetryVariant, TelemetryVariantMeasurement

from .helpers import RegistryTestCase, SeededCatalogTestCase

def _seed_discovery(
    mesh: dict,
    device_id: int,
    payload_kind: str,
    fields: list[str],
    field_units: dict[str, str | None] | None = None,
) -> None:
    event = {
        "mesh_id": mesh["id"],
        "device_id": device_id,
        "payload_kind": payload_kind,
        "fields": fields,
        "op": "upsert",
    }
    if field_units:
        event["field_units"] = field_units
    DiscoveryCommand._upsert(event)


class SensorDiscoveryConsumerTests(SeededCatalogTestCase):
    def test_discovery_creates_variant_measurement_type_and_measurement(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_node(owner, mesh, device_id=1)

        _seed_discovery(mesh, 1, "telemetry:environment_metrics", ["temperature", "relative_humidity"])

        telemetry_variant = TelemetryVariant.objects.get(payload_kind="telemetry:environment_metrics")
        device_telemetry_variant = DeviceTelemetryVariant.objects.get(device__device_id=1, telemetry_variant=telemetry_variant)
        self.assertIsNotNone(device_telemetry_variant.last_seen)
        # environment_metrics has ~23 pre-seeded MeasurementTypes - only the two
        # discovered fields should have a Measurement row for this pairing.
        discovered_fields = set(
            Measurement.objects.filter(device_telemetry_variant=device_telemetry_variant).values_list("measurement_type__field_name", flat=True)
        )
        self.assertEqual(discovered_fields, {"temperature", "relative_humidity"})

    def test_seeded_measurement_type_native_unit_is_reused_not_overwritten(self):
        # temperature is pre-seeded by seed_measurement_catalog with native_unit="degC" -
        # get_or_create must find that row, not create a second one without a unit.
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_node(owner, mesh, device_id=1)

        _seed_discovery(mesh, 1, "telemetry:environment_metrics", ["temperature"])

        measurement_type = MeasurementType.objects.get(
            payload_kind="telemetry:environment_metrics", field_name="temperature"
        )
        self.assertEqual(measurement_type.native_unit, "degC")
        self.assertEqual(measurement_type.quantity_kind, "physical_property")
        self.assertEqual(
            MeasurementType.objects.filter(
                payload_kind="telemetry:environment_metrics", field_name="temperature"
            ).count(),
            1,
        )

    def test_published_units_fill_in_a_computed_channels_empty_catalog_row(self):
        """A derived channel has no protobuf field to inherit a unit from, so its producer
        sends one - otherwise the row is created bare and nothing downstream can label the
        series."""

        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_node(owner, mesh, device_id=1)

        _seed_discovery(mesh, 1, "derived", ["dew_point"], {"dew_point": "degC"})

        measurement_type = MeasurementType.objects.get(payload_kind="derived", field_name="dew_point")
        self.assertEqual(measurement_type.native_unit, "degC")
        # Derived from the unit rather than sent separately - the two aren't
        # independent facts. See common/units.py.
        self.assertEqual(measurement_type.quantity_kind, "physical_property")

    def test_units_backfill_a_row_discovered_before_units_were_published(self):
        # The state this shipped into: rows already existed with native_unit
        # NULL. The next discovery run fills them rather than needing a migration.
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_node(owner, mesh, device_id=1)

        _seed_discovery(mesh, 1, "derived", ["dew_point"])
        self.assertIsNone(MeasurementType.objects.get(payload_kind="derived", field_name="dew_point").native_unit)

        _seed_discovery(mesh, 1, "derived", ["dew_point"], {"dew_point": "degC"})

        self.assertEqual(
            MeasurementType.objects.get(payload_kind="derived", field_name="dew_point").native_unit, "degC"
        )

    def test_published_units_never_overwrite_a_curated_one(self):
        """Discovery is a default, not an authority: a superuser correcting the catalog through
        the API outranks it, and a producer republishing every run must not undo that."""

        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_node(owner, mesh, device_id=1)
        MeasurementType.objects.create(
            payload_kind="derived", field_name="dew_point", native_unit="degF", quantity_kind="physical_property"
        )

        _seed_discovery(mesh, 1, "derived", ["dew_point"], {"dew_point": "degC"})

        self.assertEqual(
            MeasurementType.objects.get(payload_kind="derived", field_name="dew_point").native_unit, "degF"
        )

    def test_an_unresolvable_unit_is_left_absent_rather_than_guessed(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_node(owner, mesh, device_id=1)

        _seed_discovery(mesh, 1, "derived", ["mystery"], {"mystery": None})

        measurement_type = MeasurementType.objects.get(payload_kind="derived", field_name="mystery")
        self.assertIsNone(measurement_type.native_unit)
        self.assertIsNone(measurement_type.quantity_kind)

    def test_events_without_field_units_still_work(self):
        # Decoded telemetry (flink/decode_job.py) publishes discovery without
        # units and must be unaffected - the field is additive.
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_node(owner, mesh, device_id=1)

        _seed_discovery(mesh, 1, "telemetry:device_metrics", ["battery_level"])

        self.assertTrue(
            Measurement.objects.filter(measurement_type__field_name="battery_level").exists()
        )

    def test_rediscovery_is_idempotent(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_node(owner, mesh, device_id=1)

        _seed_discovery(mesh, 1, "telemetry:device_metrics", ["voltage", "battery_level"])
        first_id = DeviceTelemetryVariant.objects.get(device__device_id=1).id
        _seed_discovery(mesh, 1, "telemetry:device_metrics", ["voltage", "battery_level"])

        self.assertEqual(DeviceTelemetryVariant.objects.filter(device__device_id=1).count(), 1)
        self.assertEqual(DeviceTelemetryVariant.objects.get(device__device_id=1).id, first_id)
        self.assertEqual(Measurement.objects.filter(device_telemetry_variant_id=first_id).count(), 2)

    def test_discovery_for_unknown_device_is_a_noop(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        # No Device row created for device_id=999 - the sightings consumer would
        # normally create it first; discovery alone must not error or create one.
        _seed_discovery(mesh, 999, "telemetry:device_metrics", ["voltage"])

        self.assertFalse(DeviceTelemetryVariant.objects.filter(device__device_id=999).exists())

    def test_a_gateways_own_telemetry_is_discovered_too(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        gateway = self.create_gateway(owner, mesh, device_id=1)

        _seed_discovery(mesh, 1, "telemetry:device_metrics", ["voltage"])

        device_telemetry_variant = DeviceTelemetryVariant.objects.get(device__pk=uuid.UUID(gateway["uuid"]))
        self.assertEqual(device_telemetry_variant.telemetry_variant.payload_kind, "telemetry:device_metrics")


class DeviceTelemetryVariantsEndpointTests(RegistryTestCase):
    """GET /devices/{uuid}/telemetry-variants - which telemetry types this device reports."""

    def test_lists_variants_without_nesting_measurements(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)
        _seed_discovery(mesh, 1, "telemetry:environment_metrics", ["temperature", "relative_humidity"])

        resp = self.client.get(f"/devices/{node['uuid']}/telemetry-variants", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["telemetry_variant"]["payload_kind"], "telemetry:environment_metrics")
        # The whole point of the split - channels are their own resource now.
        self.assertNotIn("measurements", body[0])

    def test_one_row_per_discovered_variant(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)
        _seed_discovery(mesh, 1, "telemetry:environment_metrics", ["temperature"])
        _seed_discovery(mesh, 1, "telemetry:device_metrics", ["voltage"])

        body = self.client.get(f"/devices/{node['uuid']}/telemetry-variants", **self.auth_headers(owner)).json()

        self.assertEqual(
            {r["telemetry_variant"]["payload_kind"] for r in body},
            {"telemetry:environment_metrics", "telemetry:device_metrics"},
        )

    def test_requires_auth_and_is_mesh_owner_scoped(self):
        owner_a = self.create_owner(name="A", email="sensors-owner-a@example.com")
        owner_b = self.create_owner(name="B", email="sensors-owner-b@example.com")
        mesh = self.create_mesh(owner_a)
        node = self.create_node(owner_a, mesh, device_id=1)
        url = f"/devices/{node['uuid']}/telemetry-variants"

        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.get(url, **self.auth_headers(owner_b)).status_code, 403)
        self.assertEqual(self.client.get(url, **self.auth_headers(owner_a)).status_code, 200)

    def test_empty_when_none_discovered_yet(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)

        resp = self.client.get(f"/devices/{node['uuid']}/telemetry-variants", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])


class DeviceMeasurementsEndpointTests(SeededCatalogTestCase):
    """GET /devices/{uuid}/measurements - a flat list of the channels a device actually
    produces, across all its variants."""

    def test_flat_list_carries_channel_and_measurement_type(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)
        _seed_discovery(mesh, 1, "telemetry:environment_metrics", ["temperature"])

        resp = self.client.get(f"/devices/{node['uuid']}/measurements", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body), 1)
        row = body[0]
        # `channel` is precomputed so callers go straight to querying or
        # configuring it - no reassembling "<measurement>.<field>" by hand.
        self.assertEqual(row["measurement_type"]["channel"], "environment_metrics.temperature")
        self.assertEqual(row["measurement_type"]["payload_kind"], "telemetry:environment_metrics")
        self.assertEqual(row["measurement_type"]["field_name"], "temperature")
        self.assertEqual(row["measurement_type"]["native_unit"], "degC")

    def test_flattens_across_several_variants(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)
        _seed_discovery(mesh, 1, "telemetry:environment_metrics", ["temperature", "relative_humidity"])
        _seed_discovery(mesh, 1, "telemetry:device_metrics", ["voltage"])

        body = self.client.get(f"/devices/{node['uuid']}/measurements", **self.auth_headers(owner)).json()

        self.assertEqual(
            {r["measurement_type"]["channel"] for r in body},
            {
                "environment_metrics.temperature",
                "environment_metrics.relative_humidity",
                "device_metrics.voltage",
            },
        )

    def test_requires_auth_and_is_mesh_owner_scoped(self):
        owner_a = self.create_owner(name="A", email="meas-owner-a@example.com")
        owner_b = self.create_owner(name="B", email="meas-owner-b@example.com")
        mesh = self.create_mesh(owner_a)
        node = self.create_node(owner_a, mesh, device_id=1)
        url = f"/devices/{node['uuid']}/measurements"

        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.get(url, **self.auth_headers(owner_b)).status_code, 403)
        self.assertEqual(self.client.get(url, **self.auth_headers(owner_a)).status_code, 200)

    def test_empty_when_none_discovered_yet(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)

        resp = self.client.get(f"/devices/{node['uuid']}/measurements", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    def test_old_sensors_route_is_gone(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)

        self.assertEqual(self.client.get(f"/devices/{node['uuid']}/sensors", **self.auth_headers(owner)).status_code, 404)


class MeasurementTypeCrudTests(SeededCatalogTestCase):
    def test_get_is_open_to_any_verified_owner(self):
        owner = self.create_owner()
        resp = self.client.get("/measurements", **self.auth_headers(owner))
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(len(resp.json()), 0)  # seeded by seed_measurement_catalog

    def test_get_requires_auth(self):
        self.assertEqual(self.client.get("/measurements").status_code, 401)

    def test_non_superuser_cannot_create(self):
        owner = self.create_owner()
        resp = self.client.post(
            "/measurements",
            {"payload_kind": "telemetry:custom", "field_name": "x"},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(resp.status_code, 403)

    def test_superuser_can_create_update_and_delete(self):
        owner = self.create_owner()
        self.promote_to_superuser(owner)

        create_resp = self.client.post(
            "/measurements",
            {"payload_kind": "telemetry:custom", "field_name": "widget_count", "native_unit": "count"},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(create_resp.status_code, 201, create_resp.content)
        measurement_type_id = create_resp.json()["id"]

        update_resp = self.client.put(
            f"/measurements/{measurement_type_id}",
            {"vocabulary_uri": "https://example.org/qudt/widget-count"},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(update_resp.status_code, 200)
        self.assertEqual(update_resp.json()["vocabulary_uri"], "https://example.org/qudt/widget-count")

        delete_resp = self.client.delete(
            f"/measurements/{measurement_type_id}", **self.auth_headers(owner)
        )
        self.assertEqual(delete_resp.status_code, 204)
        self.assertFalse(MeasurementType.objects.filter(pk=uuid.UUID(measurement_type_id)).exists())

    def test_payload_kind_and_field_name_are_immutable_on_update(self):
        owner = self.create_owner()
        self.promote_to_superuser(owner)
        measurement_type = MeasurementType.objects.get(
            payload_kind="telemetry:environment_metrics", field_name="temperature"
        )

        resp = self.client.put(
            f"/measurements/{measurement_type.id}",
            {"payload_kind": "telemetry:hijacked", "field_name": "hijacked", "native_unit": "degF"},
            format="json",
            **self.auth_headers(owner),
        )

        self.assertEqual(resp.status_code, 200)
        measurement_type.refresh_from_db()
        self.assertEqual(measurement_type.payload_kind, "telemetry:environment_metrics")
        self.assertEqual(measurement_type.field_name, "temperature")
        self.assertEqual(measurement_type.native_unit, "degF")

    def test_create_duplicate_payload_kind_and_field_name_conflicts(self):
        owner = self.create_owner()
        self.promote_to_superuser(owner)

        resp = self.client.post(
            "/measurements",
            {"payload_kind": "telemetry:environment_metrics", "field_name": "temperature"},
            format="json",
            **self.auth_headers(owner),
        )

        self.assertEqual(resp.status_code, 409)

    def test_non_superuser_cannot_update_or_delete(self):
        owner = self.create_owner()
        measurement_type = MeasurementType.objects.get(
            payload_kind="telemetry:environment_metrics", field_name="temperature"
        )

        self.assertEqual(
            self.client.put(
                f"/measurements/{measurement_type.id}",
                {"native_unit": "degF"},
                format="json",
                **self.auth_headers(owner),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(f"/measurements/{measurement_type.id}", **self.auth_headers(owner)).status_code,
            403,
        )


class TelemetryVariantCrudTests(RegistryTestCase):
    def test_get_is_open_to_any_verified_owner(self):
        owner = self.create_owner()
        resp = self.client.get("/telemetry-variants", **self.auth_headers(owner))
        self.assertEqual(resp.status_code, 200)

    def test_non_superuser_cannot_update(self):
        owner = self.create_owner()
        telemetry_variant = TelemetryVariant.objects.create(payload_kind="telemetry:environment_metrics")
        resp = self.client.put(
            f"/telemetry-variants/{telemetry_variant.id}",
            {"name": "EnvironmentMetrics"},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(resp.status_code, 403)

    def test_superuser_can_update_and_delete(self):
        owner = self.create_owner()
        self.promote_to_superuser(owner)
        telemetry_variant = TelemetryVariant.objects.create(
            payload_kind="telemetry:environment_metrics", model="BME280 (assumed)"
        )

        update_resp = self.client.put(
            f"/telemetry-variants/{telemetry_variant.id}",
            {"datasheet_url": "https://example.org/bme280.pdf"},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(update_resp.status_code, 200)

        delete_resp = self.client.delete(f"/telemetry-variants/{telemetry_variant.id}", **self.auth_headers(owner))
        self.assertEqual(delete_resp.status_code, 204)
        self.assertFalse(TelemetryVariant.objects.filter(pk=telemetry_variant.id).exists())

    def test_payload_kind_is_immutable_on_update(self):
        owner = self.create_owner()
        self.promote_to_superuser(owner)
        telemetry_variant = TelemetryVariant.objects.create(payload_kind="telemetry:environment_metrics")

        resp = self.client.put(
            f"/telemetry-variants/{telemetry_variant.id}",
            {"payload_kind": "telemetry:hijacked", "name": "EnvironmentMetrics"},
            format="json",
            **self.auth_headers(owner),
        )

        self.assertEqual(resp.status_code, 200)
        telemetry_variant.refresh_from_db()
        self.assertEqual(telemetry_variant.payload_kind, "telemetry:environment_metrics")
        self.assertEqual(telemetry_variant.name, "EnvironmentMetrics")

    def test_superuser_can_set_default_reading_interval_seconds(self):
        owner = self.create_owner()
        self.promote_to_superuser(owner)
        telemetry_variant = TelemetryVariant.objects.create(payload_kind="telemetry:environment_metrics")

        resp = self.client.put(
            f"/telemetry-variants/{telemetry_variant.id}",
            {"default_reading_interval_seconds": 900},
            format="json",
            **self.auth_headers(owner),
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["default_reading_interval_seconds"], 900)
        telemetry_variant.refresh_from_db()
        self.assertEqual(telemetry_variant.default_reading_interval_seconds, 900)


class TelemetryVariantMeasurementApiTests(SeededCatalogTestCase):
    def setUp(self):
        super().setUp()
        self.telemetry_variant = TelemetryVariant.objects.get(payload_kind="telemetry:environment_metrics")
        self.link = TelemetryVariantMeasurement.objects.get(
            telemetry_variant=self.telemetry_variant, measurement_type__field_name="temperature"
        )

    def test_get_measurement_types_is_open_to_any_verified_owner(self):
        owner = self.create_owner()

        resp = self.client.get(
            f"/telemetry-variants/{self.telemetry_variant.id}/measurements", **self.auth_headers(owner)
        )

        self.assertEqual(resp.status_code, 200)
        fields = {link["measurement_type"]["field_name"] for link in resp.json()}
        self.assertIn("temperature", fields)

    def test_get_measurement_types_requires_auth(self):
        resp = self.client.get(f"/telemetry-variants/{self.telemetry_variant.id}/measurements")
        self.assertEqual(resp.status_code, 401)

    def test_non_superuser_cannot_set_bounds(self):
        owner = self.create_owner()

        resp = self.client.put(
            f"/telemetry-variants/{self.link.telemetry_variant_id}/measurements/{self.link.id}",
            {"valid_min": -40, "valid_max": 85},
            format="json",
            **self.auth_headers(owner),
        )

        self.assertEqual(resp.status_code, 403)

    def test_superuser_can_set_bounds(self):
        owner = self.create_owner()
        self.promote_to_superuser(owner)

        resp = self.client.put(
            f"/telemetry-variants/{self.link.telemetry_variant_id}/measurements/{self.link.id}",
            {"valid_min": -40, "valid_max": 85},
            format="json",
            **self.auth_headers(owner),
        )

        self.assertEqual(resp.status_code, 200)
        self.link.refresh_from_db()
        self.assertEqual((self.link.valid_min, self.link.valid_max), (-40, 85))

    def test_bounds_survive_re_running_the_seed_command(self):
        self.link.valid_min, self.link.valid_max = -40, 85
        self.link.save(update_fields=["valid_min", "valid_max"])

        call_command("seed_measurement_catalog", stdout=StringIO())

        self.link.refresh_from_db()
        self.assertEqual((self.link.valid_min, self.link.valid_max), (-40, 85))


class MeasurementTypeFilterTests(SeededCatalogTestCase):
    """The catalog mixes namespaces - telemetry:<variant> for real sensor fields,
    computed:<measurement> for what this pipeline works out - so filtering matters."""

    def setUp(self):
        super().setUp()
        self.owner = self.create_owner()
        MeasurementType.objects.create(payload_kind="computed:derived", field_name="no2_ppb")
        MeasurementType.objects.create(payload_kind="computed:derived", field_name="no2_ugm3")

    def _kinds(self, query=""):
        resp = self.client.get(f"/measurements{query}", **self.auth_headers(self.owner))
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def test_unfiltered_returns_every_namespace(self):
        kinds = {r["payload_kind"].split(":", 1)[0] for r in self._kinds()}
        self.assertEqual(kinds, {"telemetry", "computed"})

    def test_kind_computed_excludes_sensor_fields(self):
        rows = self._kinds("?kind=computed")
        self.assertTrue(all(r["payload_kind"].startswith("computed:") for r in rows))
        self.assertLessEqual({"no2_ppb", "no2_ugm3"}, {r["field_name"] for r in rows})

    def test_kind_telemetry_excludes_derived(self):
        rows = self._kinds("?kind=telemetry")
        self.assertTrue(rows)
        self.assertTrue(all(r["payload_kind"].startswith("telemetry:") for r in rows))

    def test_kind_matches_the_namespace_not_a_bare_prefix(self):
        # "derive" must not match "derived:" - the filter appends the colon.
        self.assertEqual(self._kinds("?kind=derive"), [])

    def test_payload_kind_is_exact_match(self):
        rows = self._kinds("?payload_kind=telemetry:environment_metrics")
        self.assertTrue(rows)
        self.assertTrue(all(r["payload_kind"] == "telemetry:environment_metrics" for r in rows))

    def test_field_name_filter(self):
        rows = self._kinds("?field_name=temperature")
        self.assertTrue(rows)
        self.assertTrue(all(r["field_name"] == "temperature" for r in rows))

    def test_filters_combine(self):
        rows = self._kinds("?payload_kind=telemetry:environment_metrics&field_name=temperature")
        self.assertEqual(len(rows), 1)

    def test_unknown_kind_returns_empty_not_an_error(self):
        self.assertEqual(self._kinds("?kind=nonsense"), [])


class QualityAndDerivedCatalogTests(SeededCatalogTestCase):
    """Computed channels (blueprint outputs, quality metrics) are catalogued and per-device-
    linked the same way measured ones are - see docs/data-quality.md#where-everything-lives."""

    def setUp(self):
        super().setUp()
        self.owner = self.create_owner()
        self.mesh = self.create_mesh(self.owner)
        self.node = self.create_node(self.owner, self.mesh, device_id=1)

    def test_quality_namespace_is_seeded_with_units(self):
        rows = {
            r["field_name"]: r
            for r in self.client.get(
                "/measurements?payload_kind=computed:quality", **self.auth_headers(self.owner)
            ).json()
        }
        self.assertEqual(
            set(rows), {"completeness_ratio", "observed", "expected", "largest_gap_seconds"}
        )
        self.assertEqual(rows["completeness_ratio"]["native_unit"], "ratio")
        self.assertEqual(rows["largest_gap_seconds"]["native_unit"], "s")

    def test_quality_channel_names_match_the_influx_series(self):
        # quality.completeness_ratio, not "<something>.completeness_ratio" -
        # a mismatch here means a curated bound could never match real data.
        rows = self.client.get(
            "/measurements?payload_kind=computed:quality", **self.auth_headers(self.owner)
        ).json()
        self.assertIn("quality.completeness_ratio", {r["channel"] for r in rows})

    def test_alarms_are_deliberately_not_catalogued(self):
        # `value` has no stable unit and `message` is free text - it's an
        # event log, not a measurement series.
        self.assertEqual(
            self.client.get(
                "/measurements?payload_kind=computed:alarms", **self.auth_headers(self.owner)
            ).json(),
            [],
        )

    def test_origin_distinguishes_measured_from_computed(self):
        rows = self.client.get("/measurements", **self.auth_headers(self.owner)).json()
        by_origin = {}
        for r in rows:
            by_origin.setdefault(r["origin"], set()).add(r["payload_kind"])
        self.assertEqual(by_origin["computed"], {"computed:quality"})
        self.assertTrue(all(p.startswith("telemetry:") for p in by_origin["measured"]))

    def test_derived_and_quality_appear_per_device_once_discovered(self):
        # The worker publishes sensor-discovery events for its computed
        # channels, so they link to the device like measured ones do.
        _seed_discovery(self.mesh, 1, "telemetry:environment_metrics", ["temperature"])
        _seed_discovery(self.mesh, 1, "computed:derived", ["dew_point"])
        _seed_discovery(self.mesh, 1, "computed:quality", ["completeness_ratio"])

        rows = self.client.get(f"/devices/{self.node['uuid']}/measurements", **self.auth_headers(self.owner)).json()

        by_channel = {r["measurement_type"]["channel"]: r["measurement_type"]["origin"] for r in rows}
        self.assertEqual(by_channel["environment_metrics.temperature"], "measured")
        self.assertEqual(by_channel["derived.dew_point"], "computed")
        self.assertEqual(by_channel["quality.completeness_ratio"], "computed")

    def test_the_kind_filter_reaches_the_computed_namespace(self):
        rows = self.client.get("/measurements?kind=computed", **self.auth_headers(self.owner)).json()
        self.assertTrue(rows)
        self.assertTrue(all(r["payload_kind"].startswith("computed:") for r in rows))
