import uuid
from io import StringIO

from django.core.management import call_command

from registry.models import (
    Device,
    DeviceTelemetryVariant,
    Measurement,
    PostprocessingStep,
    TelemetryVariant,
    TelemetryVariantMeasurement,
)

from .helpers import RegistryTestCase

def _blueprint_payload(name="air-quality-v1"):
    """A real two-step chain: step 1 consumes the derived channel step 0
    produces (no2_ppb), which is the whole point of ordered steps."""
    return {
        "name": name,
        "description": "NO2 from an EC sensor",
        "steps": [
            {
                "order": 0,
                "function_name": "ec_sensor_ppb",
                "inputs": {
                    "working": "ads1115.channel_0",
                    "auxiliary": "ads1115.channel_1",
                    "temperature": "environment_metrics.temperature",
                },
                "params": {"sensitivity": 0.42, "working_zero": 220.0},
                "outputs": {"concentration_ppb": "no2_ppb"},
            },
            {
                "order": 1,
                "function_name": "ppb_to_ugm3",
                "inputs": {
                    "concentration_ppb": "no2_ppb",
                    "temperature": "environment_metrics.temperature",
                },
                "params": {"molecular_weight": 46.01},
                "outputs": {"concentration_ugm3": "no2_ugm3"},
            },
        ],
    }


class AlgorithmListTests(RegistryTestCase):
    def test_lists_the_registry_for_any_verified_owner(self):
        owner = self.create_owner()

        resp = self.client.get("/algorithms", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 200)
        by_name = {a["name"]: a for a in resp.json()}
        self.assertIn("ec_sensor_ppb", by_name)
        # The multi-sensor case the blueprint design exists for.
        self.assertEqual(by_name["ec_sensor_ppb"]["inputs"], ["working", "auxiliary", "temperature"])
        self.assertEqual(by_name["ec_sensor_ppb"]["params"], ["sensitivity"])
        self.assertEqual(by_name["ec_sensor_ppb"]["mode"], "pointwise")

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/algorithms").status_code, 401)


class PostprocessingBlueprintCrudTests(RegistryTestCase):
    def test_create_with_nested_steps(self):
        owner = self.create_owner()

        resp = self.client.post(
            "/postprocessing-blueprints", _blueprint_payload(), format="json", **self.auth_headers(owner)
        )

        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertEqual(body["owner_id"], owner["id"])
        self.assertEqual([s["order"] for s in body["steps"]], [0, 1])
        self.assertEqual(body["steps"][1]["inputs"]["concentration_ppb"], "no2_ppb")
        self.assertEqual(PostprocessingStep.objects.count(), 2)

    def test_list_and_get_are_owner_scoped(self):
        owner_a = self.create_owner(name="A", email="bp-a@example.com")
        owner_b = self.create_owner(name="B", email="bp-b@example.com")
        created = self.client.post(
            "/postprocessing-blueprints", _blueprint_payload(), format="json", **self.auth_headers(owner_a)
        ).json()

        self.assertEqual(len(self.client.get("/postprocessing-blueprints", **self.auth_headers(owner_a)).json()), 1)
        self.assertEqual(len(self.client.get("/postprocessing-blueprints", **self.auth_headers(owner_b)).json()), 0)
        self.assertEqual(
            self.client.get(
                f"/postprocessing-blueprints/{created['id']}", **self.auth_headers(owner_b)
            ).status_code,
            403,
        )

    def test_superuser_sees_every_owners_blueprints(self):
        owner = self.create_owner()
        self.client.post(
            "/postprocessing-blueprints", _blueprint_payload(), format="json", **self.auth_headers(owner)
        )
        admin = self.create_owner(name="Admin", email="bp-admin@example.com")
        self.promote_to_superuser(admin)

        self.assertEqual(len(self.client.get("/postprocessing-blueprints", **self.auth_headers(admin)).json()), 1)

    def test_put_replaces_the_whole_step_list(self):
        owner = self.create_owner()
        created = self.client.post(
            "/postprocessing-blueprints", _blueprint_payload(), format="json", **self.auth_headers(owner)
        ).json()

        resp = self.client.put(
            f"/postprocessing-blueprints/{created['id']}",
            {
                "steps": [
                    {
                        "order": 0,
                        "function_name": "dew_point",
                        "inputs": {
                            "temperature": "environment_metrics.temperature",
                            "relative_humidity": "environment_metrics.relative_humidity",
                        },
                        "params": {},
                        "outputs": {"dew_point": "dew_point"},
                    }
                ]
            },
            format="json",
            **self.auth_headers(owner),
        )

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(resp.json()["steps"]), 1)
        self.assertEqual(PostprocessingStep.objects.count(), 1)

    def test_put_without_steps_leaves_them_alone(self):
        owner = self.create_owner()
        created = self.client.post(
            "/postprocessing-blueprints", _blueprint_payload(), format="json", **self.auth_headers(owner)
        ).json()

        resp = self.client.put(
            f"/postprocessing-blueprints/{created['id']}",
            {"description": "renamed only"},
            format="json",
            **self.auth_headers(owner),
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["steps"]), 2)

    def test_duplicate_name_for_same_owner_conflicts(self):
        owner = self.create_owner()
        self.client.post(
            "/postprocessing-blueprints", _blueprint_payload(), format="json", **self.auth_headers(owner)
        )

        resp = self.client.post(
            "/postprocessing-blueprints", _blueprint_payload(), format="json", **self.auth_headers(owner)
        )

        self.assertEqual(resp.status_code, 409)

    def test_same_name_for_a_different_owner_is_fine(self):
        owner_a = self.create_owner(name="A", email="bp-dup-a@example.com")
        owner_b = self.create_owner(name="B", email="bp-dup-b@example.com")
        self.client.post(
            "/postprocessing-blueprints", _blueprint_payload(), format="json", **self.auth_headers(owner_a)
        )

        resp = self.client.post(
            "/postprocessing-blueprints", _blueprint_payload(), format="json", **self.auth_headers(owner_b)
        )

        self.assertEqual(resp.status_code, 201, resp.content)

    def test_delete_nulls_the_device_fk_rather_than_cascading(self):
        # Deleting a recipe must never delete the devices using it.
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)
        created = self.client.post(
            "/postprocessing-blueprints", _blueprint_payload(), format="json", **self.auth_headers(owner)
        ).json()
        self.client.put(
            f"/devices/{node['uuid']}",
            {"postprocessing_blueprint_id": created["id"]},
            format="json",
            **self.auth_headers(owner),
        )

        resp = self.client.delete(f"/postprocessing-blueprints/{created['id']}", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 204)
        device = Device.objects.get(pk=uuid.UUID(node["uuid"]))
        self.assertIsNone(device.postprocessing_blueprint_id)

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/postprocessing-blueprints").status_code, 401)


class PostprocessingStepValidationTests(RegistryTestCase):
    """Bad step config must fail at write time, not hours later in a worker."""

    def _post(self, owner, step):
        return self.client.post(
            "/postprocessing-blueprints",
            {"name": "bp", "steps": [step]},
            format="json",
            **self.auth_headers(owner),
        )

    def test_unknown_function_name_is_rejected(self):
        resp = self._post(
            self.create_owner(),
            {"order": 0, "function_name": "not_a_real_algorithm", "inputs": {}, "params": {}, "outputs": {}},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Unknown algorithm", str(resp.json()))

    def test_missing_required_input_is_rejected(self):
        resp = self._post(
            self.create_owner(),
            {
                "order": 0,
                "function_name": "ec_sensor_ppb",
                "inputs": {"working": "a"},
                "params": {"sensitivity": 1.0},
                "outputs": {"concentration_ppb": "x"},
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("requires input(s)", str(resp.json()))

    def test_unexpected_input_is_rejected(self):
        resp = self._post(
            self.create_owner(),
            {
                "order": 0,
                "function_name": "dew_point",
                "inputs": {"temperature": "a", "relative_humidity": "b", "pressure": "c"},
                "params": {},
                "outputs": {"dew_point": "x"},
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("does not accept input(s)", str(resp.json()))

    def test_missing_required_param_is_rejected(self):
        resp = self._post(
            self.create_owner(),
            {
                "order": 0,
                "function_name": "ec_sensor_ppb",
                "inputs": {"working": "a", "auxiliary": "b", "temperature": "c"},
                "params": {},
                "outputs": {"concentration_ppb": "x"},
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("requires param(s)", str(resp.json()))

    def test_unknown_param_is_rejected(self):
        resp = self._post(
            self.create_owner(),
            {
                "order": 0,
                "function_name": "dew_point",
                "inputs": {"temperature": "a", "relative_humidity": "b"},
                "params": {"bogus": 1},
                "outputs": {"dew_point": "x"},
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("does not accept param(s)", str(resp.json()))

    def test_optional_params_are_accepted(self):
        resp = self._post(
            self.create_owner(),
            {
                "order": 0,
                "function_name": "ec_sensor_ppb",
                "inputs": {"working": "a", "auxiliary": "b", "temperature": "c"},
                "params": {"sensitivity": 1.0, "working_zero": 220.0, "temperature_coefficient": 0.01},
                "outputs": {"concentration_ppb": "x"},
            },
        )
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_blueprint_with_no_steps_is_rejected(self):
        owner = self.create_owner()
        resp = self.client.post(
            "/postprocessing-blueprints", {"name": "empty", "steps": []}, format="json", **self.auth_headers(owner)
        )
        self.assertEqual(resp.status_code, 400)

    def test_duplicate_step_order_is_rejected(self):
        owner = self.create_owner()
        step = {
            "order": 0,
            "function_name": "dew_point",
            "inputs": {"temperature": "a", "relative_humidity": "b"},
            "params": {},
            "outputs": {"dew_point": "x"},
        }
        resp = self.client.post(
            "/postprocessing-blueprints",
            {"name": "dupe-order", "steps": [step, dict(step)]},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("unique", str(resp.json()).lower())


class DevicePostprocessingFieldsTests(RegistryTestCase):
    def test_attach_blueprint_and_set_intervals(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)
        blueprint = self.client.post(
            "/postprocessing-blueprints", _blueprint_payload(), format="json", **self.auth_headers(owner)
        ).json()

        resp = self.client.put(
            f"/devices/{node['uuid']}",
            {
                "postprocessing_blueprint_id": blueprint["id"],
                "reading_interval_seconds": 300,
                "publish_interval_seconds": 3600,
            },
            format="json",
            **self.auth_headers(owner),
        )

        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["postprocessing_blueprint_id"], blueprint["id"])
        # Deliberately different - "not publishing" and "not reading" are
        # separate faults, see docs/architecture.md#device-fault-detection.
        self.assertEqual(body["reading_interval_seconds"], 300)
        self.assertEqual(body["publish_interval_seconds"], 3600)

    def test_cannot_attach_another_owners_blueprint(self):
        owner_a = self.create_owner(name="A", email="bp-attach-a@example.com")
        owner_b = self.create_owner(name="B", email="bp-attach-b@example.com")
        blueprint = self.client.post(
            "/postprocessing-blueprints", _blueprint_payload(), format="json", **self.auth_headers(owner_a)
        ).json()
        mesh_b = self.create_mesh(owner_b, channel_id="ChanB")
        node_b = self.create_node(owner_b, mesh_b, device_id=2)

        resp = self.client.put(
            f"/devices/{node_b['uuid']}",
            {"postprocessing_blueprint_id": blueprint["id"]},
            format="json",
            **self.auth_headers(owner_b),
        )

        self.assertEqual(resp.status_code, 403)

    def test_detaching_a_blueprint_with_null(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)
        blueprint = self.client.post(
            "/postprocessing-blueprints", _blueprint_payload(), format="json", **self.auth_headers(owner)
        ).json()
        self.client.put(
            f"/devices/{node['uuid']}",
            {"postprocessing_blueprint_id": blueprint["id"]},
            format="json",
            **self.auth_headers(owner),
        )

        resp = self.client.put(
            f"/devices/{node['uuid']}",
            {"postprocessing_blueprint_id": None},
            format="json",
            **self.auth_headers(owner),
        )

        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["postprocessing_blueprint_id"])

    def test_has_postprocessing_filter(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        with_bp = self.create_node(owner, mesh, device_id=1)
        self.create_node(owner, mesh, device_id=2)
        blueprint = self.client.post(
            "/postprocessing-blueprints", _blueprint_payload(), format="json", **self.auth_headers(owner)
        ).json()
        self.client.put(
            f"/devices/{with_bp['uuid']}",
            {"postprocessing_blueprint_id": blueprint["id"]},
            format="json",
            **self.auth_headers(owner),
        )

        enabled = self.client.get("/devices?has_postprocessing=true", **self.auth_headers(owner)).json()
        disabled = self.client.get("/devices?has_postprocessing=false", **self.auth_headers(owner)).json()

        self.assertEqual([d["node_id"] for d in enabled], [1])
        self.assertEqual([d["node_id"] for d in disabled], [2])

    def test_intervals_default_to_null(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)

        body = self.client.get(f"/devices/{node['uuid']}", **self.auth_headers(owner)).json()

        self.assertIsNone(body["reading_interval_seconds"])
        self.assertIsNone(body["publish_interval_seconds"])
        self.assertIsNone(body["postprocessing_blueprint_id"])


class QualityConfigPublishTests(RegistryTestCase):
    """Catalog edits must reach Flink's broadcast state - that's what makes
    the registry catalog the single source of truth for quality thresholds."""

    def setUp(self):
        super().setUp()
        call_command("seed_measurement_catalog", stdout=StringIO())
        self.variant = TelemetryVariant.objects.get(payload_kind="telemetry:environment_metrics")
        self.link = TelemetryVariantMeasurement.objects.get(
            telemetry_variant=self.variant, measurement_type__field_name="temperature"
        )

    def test_setting_the_catalog_default_publishes_the_channel_config(self):
        owner = self.create_owner()
        self.promote_to_superuser(owner)

        self.client.put(
            f"/telemetry-variants/{self.link.telemetry_variant_id}/measurements/{self.link.id}",
            {"default_enabled_detectors": ["range"]},
            format="json",
            **self.auth_headers(owner),
        )

        self.fake_publisher.publish_variant_measurement_config.assert_called_once()
        published = self.fake_publisher.publish_variant_measurement_config.call_args[0][0]
        self.assertEqual(published.id, self.link.id)
        self.assertEqual(published.default_enabled_detectors, ["range"])

    def _device_measurement(self, owner):
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)
        dtv = DeviceTelemetryVariant.objects.create(device_id=node["uuid"], telemetry_variant=self.variant)
        measurement = Measurement.objects.create(
            device_telemetry_variant=dtv, measurement_type=self.link.measurement_type
        )
        return node, measurement

    def test_setting_a_devices_range_publishes_the_measurement_alarms_event(self):
        """Range has no catalog equivalent - only the per-device event carries it."""
        owner = self.create_owner()
        node, measurement = self._device_measurement(owner)

        self.client.put(
            f"/devices/{node['uuid']}/measurements/{measurement.id}",
            {"valid_min": -40, "valid_max": 85},
            format="json",
            **self.auth_headers(owner),
        )

        self.fake_publisher.publish_measurement_alarms.assert_called_once()
        _, published = self.fake_publisher.publish_measurement_alarms.call_args[0]
        self.assertEqual((published.valid_min, published.valid_max), (-40, 85))

    def test_setting_the_variant_interval_republishes_every_field_under_it(self):
        # default_reading_interval_seconds lives on the variant but is consumed
        # per-channel, so one edit has to fan out.
        owner = self.create_owner()
        self.promote_to_superuser(owner)
        field_count = self.variant.measurement_links.count()
        self.assertGreater(field_count, 1)

        self.client.put(
            f"/telemetry-variants/{self.variant.id}",
            {"default_reading_interval_seconds": 900},
            format="json",
            **self.auth_headers(owner),
        )

        self.assertEqual(self.fake_publisher.publish_variant_measurement_config.call_count, field_count)

    def test_setting_device_intervals_publishes_them(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)

        self.client.put(
            f"/devices/{node['uuid']}",
            {"reading_interval_seconds": 300, "publish_interval_seconds": 3600},
            format="json",
            **self.auth_headers(owner),
        )

        self.fake_publisher.publish_device_intervals.assert_called_once()
        published = self.fake_publisher.publish_device_intervals.call_args[0][0]
        self.assertEqual(published.reading_interval_seconds, 300)
        self.assertEqual(published.publish_interval_seconds, 3600)

    def test_unrelated_device_edit_does_not_publish_intervals(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)

        self.client.put(
            f"/devices/{node['uuid']}", {"label": "renamed"}, format="json", **self.auth_headers(owner)
        )

        self.fake_publisher.publish_device_intervals.assert_not_called()

    def test_range_publish_failure_does_not_fail_the_api_write(self):
        # Deliberately unlike the gateway/node publishes, which roll back -
        # a stale threshold delays a detection, it doesn't leak anything.
        owner = self.create_owner()
        node, measurement = self._device_measurement(owner)
        self.fake_publisher.publish_measurement_alarms.side_effect = RuntimeError("kafka down")

        resp = self.client.put(
            f"/devices/{node['uuid']}/measurements/{measurement.id}",
            {"valid_min": -40, "valid_max": 85},
            format="json",
            **self.auth_headers(owner),
        )

        self.assertEqual(resp.status_code, 200)
        measurement.refresh_from_db()
        self.assertEqual((measurement.valid_min, measurement.valid_max), (-40, 85))
