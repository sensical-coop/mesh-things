"""The response fields `quality_worker` reads out of this API."""

from registry.models import MeasurementType
from .helpers import SeededCatalogTestCase, RegistryTestCase

def _seed_quality_discovery(test, mesh, device_id):
    from .test_sensor_discovery import _seed_discovery

    _seed_discovery(mesh, device_id, "computed:quality", ["completeness_ratio"])


class QualityWorkerRouteContractTests(SeededCatalogTestCase):
    """registry_client.py calls exactly these paths."""

    def setUp(self):
        super().setUp()
        self.owner = self.create_owner()
        self.promote_to_superuser(self.owner)  # the worker holds a superuser key
        self.mesh = self.create_mesh(self.owner)
        self.device = self.create_node(self.owner, self.mesh, device_id=7)

    def test_every_route_the_worker_calls_exists(self):
        for path in (
            "/devices",
            "/telemetry-variants",
            "/measurements",
            f"/devices/{self.device['uuid']}/measurements",
            f"/devices/{self.device['uuid']}/postprocessings",
        ):
            with self.subTest(path=path):
                resp = self.client.get(path, **self.auth_headers(self.owner))
                self.assertEqual(resp.status_code, 200, f"{path} -> {resp.status_code}")


class QualityWorkerFieldContractTests(SeededCatalogTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_owner()
        self.promote_to_superuser(self.owner)
        self.mesh = self.create_mesh(self.owner)
        self.device = self.create_node(self.owner, self.mesh, device_id=7)

    def test_devices_carry_what_scan_devices_and_the_tasks_read(self):
        """The keys tasks.py reads off a device row."""
        device = self.client.get("/devices", **self.auth_headers(self.owner)).json()[0]

        for field in ("uuid", "mesh_id", "node_id", "reading_interval_seconds"):
            with self.subTest(field=field):
                self.assertIn(field, device)

    def test_the_device_key_is_the_one_the_readings_routes_take(self):
        """scan_devices passes it straight through as the device address."""
        device = self.client.get("/devices", **self.auth_headers(self.owner)).json()[0]

        resp = self.client.get(f"/devices/{device['uuid']}", **self.auth_headers(self.owner))

        self.assertEqual(resp.status_code, 200)

    def test_device_measurements_nest_the_catalog_entry(self):
        """tasks.py reads these under measurement_type, not at the row root."""
        _seed_quality_discovery(self, self.mesh, 7)

        rows = self.client.get(
            f"/devices/{self.device['uuid']}/measurements", **self.auth_headers(self.owner)
        ).json()

        self.assertTrue(rows)
        for row in rows:
            with self.subTest(row=row["id"]):
                self.assertIn("measurement_type", row)
                for field in ("channel", "origin", "payload_kind"):
                    self.assertIn(field, row["measurement_type"])
                # Completeness follows a derived channel's inputs through it.
                self.assertIn("produced_by", row)

    def test_postprocessings_carry_their_input_bindings(self):
        """derived_reading_interval walks these to find a derived channel's inputs."""
        from registry.models import Device, DeviceTelemetryVariant, Measurement, TelemetryVariant

        device = Device.objects.get(pk=self.device["uuid"])
        variant = TelemetryVariant.objects.get(payload_kind="telemetry:environment_metrics")
        dtv = DeviceTelemetryVariant.objects.create(device=device, telemetry_variant=variant)
        temperature = Measurement.objects.create(
            device_telemetry_variant=dtv, measurement_type=variant.measurement_links.get(
                measurement_type__field_name="temperature"
            ).measurement_type
        )
        blueprint = self.client.post(
            "/postprocessing-blueprints",
            {
                "name": "contract",
                "inputs": [{"slot": "value", "default_channel": "environment_metrics.temperature"}],
                "steps": [
                    {
                        "key": "cal",
                        "order": 0,
                        "function_name": "offset_scale",
                        "inputs": {"value": "slot:value"},
                        "outputs": {"calibrated": "contract_temperature"},
                    }
                ],
            },
            format="json",
            **self.auth_headers(self.owner),
        ).json()
        self.client.post(
            f"/devices/{self.device['uuid']}/postprocessings",
            {"blueprint_id": blueprint["id"]},
            format="json",
            **self.auth_headers(self.owner),
        )

        [attached] = self.client.get(
            f"/devices/{self.device['uuid']}/postprocessings", **self.auth_headers(self.owner)
        ).json()
        rows = self.client.get(
            f"/devices/{self.device['uuid']}/measurements", **self.auth_headers(self.owner)
        ).json()

        self.assertEqual(attached["input_bindings"], {"value": str(temperature.id)})
        derived = next(r for r in rows if r["produced_by"])
        self.assertEqual(derived["produced_by"], attached["id"])

    def test_the_catalog_is_flat_and_carries_channel_and_unit(self):
        """catalog_units reads these at the root: this response is not nested."""
        rows = self.client.get("/measurements", **self.auth_headers(self.owner)).json()

        self.assertTrue(rows)
        for row in rows[:5]:
            with self.subTest(row=row["id"]):
                self.assertIn("channel", row)
                self.assertIn("native_unit", row)

    def test_origin_still_marks_which_channels_to_check(self):
        """tasks.py skips anything not `measured`, so metrics are not self-checked."""
        _seed_quality_discovery(self, self.mesh, 7)

        rows = self.client.get(
            f"/devices/{self.device['uuid']}/measurements", **self.auth_headers(self.owner)
        ).json()
        origins = {r["measurement_type"]["origin"] for r in rows}

        self.assertIn("computed", origins)
        self.assertNotIn("quality", origins)  # the pre-namespace spelling

    def test_telemetry_variants_carry_the_interval_fallback(self):
        """The per-variant fallback when a device sets no interval."""
        variants = self.client.get("/telemetry-variants", **self.auth_headers(self.owner)).json()

        self.assertTrue(variants)
        for variant in variants[:3]:
            with self.subTest(variant=variant["payload_kind"]):
                self.assertIn("default_reading_interval_seconds", variant)
                self.assertIn("payload_kind", variant)


class QualityChannelCatalogTests(RegistryTestCase):
    def test_the_worker_writes_quality_under_the_namespaced_kind(self):
        """Disagreement here catalogues the channels under a kind nothing queries."""
        from common.channels import QUALITY_KIND

        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_node(owner, mesh, device_id=9)
        from .test_sensor_discovery import _seed_discovery

        _seed_discovery(mesh, 9, QUALITY_KIND, ["completeness_ratio"])

        row = MeasurementType.objects.get(field_name="completeness_ratio")

        self.assertEqual(row.payload_kind, QUALITY_KIND)
        self.assertEqual(row.payload_kind, "computed:quality")
