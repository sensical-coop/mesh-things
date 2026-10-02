import uuid
from io import StringIO

from django.core.management import call_command

from registry.models import (
    BlueprintVersion,
    Device,
    DevicePostprocessing,
    DeviceTelemetryVariant,
    Measurement,
    MeasurementType,
    PostprocessingBlueprint,
    TelemetryVariant,
)

from .helpers import RegistryTestCase

WORKING = "ads1115.channel_0"
AUXILIARY = "ads1115.channel_1"
TEMPERATURE = "environment_metrics.temperature"


def _no2_blueprint(name="air-quality", **extra):
    """Two electrodes and a temperature to ppb, then ppb to ug/m3."""
    return {
        "name": name,
        "description": "NO2 from an EC sensor",
        "inputs": [
            {"slot": "working", "default_channel": WORKING},
            {"slot": "auxiliary", "default_channel": AUXILIARY},
            {"slot": "temperature", "default_channel": TEMPERATURE},
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
        **extra,
    }


def _offset_blueprint(name="offset", default_channel=TEMPERATURE):
    return {
        "name": name,
        "inputs": [{"slot": "value", "default_channel": default_channel}],
        "steps": [
            {
                "key": "cal",
                "order": 0,
                "function_name": "offset_scale",
                "inputs": {"value": "slot:value"},
                "outputs": {"calibrated": "calibrated"},
            }
        ],
    }


class PostprocessingTestCase(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_owner()
        self.mesh = self.create_mesh(self.owner)
        self.node = self.create_node(self.owner, self.mesh, device_id=7)
        self.device = Device.objects.get(pk=self.node["uuid"])
        self.channels = self.give_channels(self.device)

    @staticmethod
    def give_channels(device, units=None) -> dict[str, Measurement]:
        """The sensor channels the blueprints read, as discovery would register them."""
        units = units or {WORKING: "mV", AUXILIARY: "mV", TEMPERATURE: "degC"}
        created = {}
        for channel, unit in units.items():
            variant_name, field = channel.split(".")
            variant, _ = TelemetryVariant.objects.get_or_create(payload_kind=f"telemetry:{variant_name}")
            dtv, _ = DeviceTelemetryVariant.objects.get_or_create(device=device, telemetry_variant=variant)
            measurement_type, _ = MeasurementType.objects.get_or_create(
                payload_kind=f"telemetry:{variant_name}", field_name=field, defaults={"native_unit": unit}
            )
            created[channel] = Measurement.objects.create(device_telemetry_variant=dtv, measurement_type=measurement_type)
        return created

    def create_blueprint(self, payload=None, owner=None) -> dict:
        resp = self.client.post(
            "/postprocessing-blueprints", payload or _no2_blueprint(), format="json", **self.auth_headers(owner or self.owner)
        )
        assert resp.status_code == 201, resp.content
        return resp.json()

    def attach(self, blueprint, node=None, owner=None, expect=201, **fields):
        node = node or self.node
        resp = self.client.post(
            f"/devices/{node['uuid']}/postprocessings",
            {"blueprint_id": blueprint["id"], **fields},
            format="json",
            **self.auth_headers(owner or self.owner),
        )
        self.assertEqual(resp.status_code, expect, resp.content)
        return resp.json()

    def calibrate(self, attached, step_key="ppb", params=None, expect=201, **fields):
        resp = self.client.post(
            f"/devices/{attached['device_uuid']}/postprocessings/{attached['id']}/calibrations",
            {"step_key": step_key, "params": params if params is not None else {"sensitivity": 2.0}, **fields},
            format="json",
            **self.auth_headers(self.owner),
        )
        self.assertEqual(resp.status_code, expect, resp.content)
        return resp.json()

    def update(self, attached, expect=200, **fields):
        resp = self.client.put(
            f"/devices/{attached['device_uuid']}/postprocessings/{attached['id']}",
            fields,
            format="json",
            **self.auth_headers(self.owner),
        )
        self.assertEqual(resp.status_code, expect, resp.content)
        return resp.json()

    def last_published_plans(self) -> list[dict]:
        self.fake_publisher.publish_postprocessing_plans.assert_called()
        return self.fake_publisher.publish_postprocessing_plans.call_args[0][1]


class AlgorithmListTests(RegistryTestCase):
    def test_lists_param_metadata(self):
        owner = self.create_owner()

        resp = self.client.get("/algorithms", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 200)
        by_name = {a["name"]: a for a in resp.json()}
        self.assertEqual(by_name["ec_sensor_ppb"]["inputs"], ["working", "auxiliary", "temperature"])
        params = {p["name"]: p for p in by_name["ec_sensor_ppb"]["params"]}
        self.assertTrue(params["sensitivity"]["calibration"])
        self.assertTrue(params["sensitivity"]["required"])
        self.assertFalse(params["reference_temperature"]["calibration"])
        self.assertEqual(params["reference_temperature"]["default"], 20.0)

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/algorithms").status_code, 401)


class BlueprintTests(PostprocessingTestCase):
    def test_create_makes_the_first_version(self):
        body = self.create_blueprint()

        self.assertEqual(body["owner_id"], self.owner["id"])
        self.assertFalse(body["is_public"])
        version = body["latest_version"]
        self.assertEqual(version["number"], 1)
        self.assertEqual([s["key"] for s in version["steps"]], ["ppb", "ugm3"])
        self.assertEqual(version["inputs"][0], {"slot": "working", "default_channel": WORKING})

    def test_other_owners_see_public_blueprints_but_not_private_ones(self):
        other = self.create_owner(name="B", email="bp-other@example.com")
        private = self.create_blueprint()
        public = self.create_blueprint(_no2_blueprint(name="shared", is_public=True))

        listed = {b["id"] for b in self.client.get("/postprocessing-blueprints", **self.auth_headers(other)).json()}

        self.assertEqual(listed, {public["id"]})
        resp = self.client.get(f"/postprocessing-blueprints/{private['id']}", **self.auth_headers(other))
        self.assertEqual(resp.status_code, 404)

    def test_owned_filter_excludes_public_blueprints(self):
        other = self.create_owner(name="B", email="bp-owned@example.com")
        self.create_blueprint(_no2_blueprint(name="shared", is_public=True), owner=other)
        mine = self.create_blueprint()

        resp = self.client.get("/postprocessing-blueprints?owned=true", **self.auth_headers(self.owner))

        self.assertEqual([b["id"] for b in resp.json()], [mine["id"]])

    def test_only_the_owner_edits_a_public_blueprint(self):
        other = self.create_owner(name="B", email="bp-edit@example.com")
        public = self.create_blueprint(_no2_blueprint(name="shared", is_public=True))

        resp = self.client.put(
            f"/postprocessing-blueprints/{public['id']}", {"name": "mine"}, format="json", **self.auth_headers(other)
        )

        self.assertEqual(resp.status_code, 403)

    def test_put_changes_metadata_and_never_steps(self):
        blueprint = self.create_blueprint()

        resp = self.client.put(
            f"/postprocessing-blueprints/{blueprint['id']}",
            {"description": "updated", "is_public": True, "steps": []},
            format="json",
            **self.auth_headers(self.owner),
        )

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["description"], "updated")
        self.assertTrue(resp.json()["is_public"])
        self.assertEqual(len(resp.json()["latest_version"]["steps"]), 2)

    def test_duplicate_name_for_same_owner_conflicts(self):
        self.create_blueprint()

        resp = self.client.post(
            "/postprocessing-blueprints", _no2_blueprint(), format="json", **self.auth_headers(self.owner)
        )

        self.assertEqual(resp.status_code, 409)

    def test_new_version_leaves_the_old_one_untouched(self):
        blueprint = self.create_blueprint()
        v2 = _offset_blueprint()
        v2.pop("name")

        resp = self.client.post(
            f"/postprocessing-blueprints/{blueprint['id']}/versions", v2, format="json", **self.auth_headers(self.owner)
        )

        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["number"], 2)
        v1 = self.client.get(
            f"/postprocessing-blueprints/{blueprint['id']}/versions/1", **self.auth_headers(self.owner)
        ).json()
        self.assertEqual([s["key"] for s in v1["steps"]], ["ppb", "ugm3"])
        versions = self.client.get(
            f"/postprocessing-blueprints/{blueprint['id']}/versions", **self.auth_headers(self.owner)
        ).json()
        self.assertEqual([v["number"] for v in versions], [1, 2])

    def test_only_the_owner_adds_versions(self):
        other = self.create_owner(name="B", email="bp-version@example.com")
        public = self.create_blueprint(_no2_blueprint(name="shared", is_public=True))
        v2 = _no2_blueprint()
        v2.pop("name")

        resp = self.client.post(
            f"/postprocessing-blueprints/{public['id']}/versions", v2, format="json", **self.auth_headers(other)
        )

        self.assertEqual(resp.status_code, 403)

    def test_delete_is_refused_while_a_device_uses_it(self):
        blueprint = self.create_blueprint()
        attached = self.attach(blueprint)

        resp = self.client.delete(f"/postprocessing-blueprints/{blueprint['id']}", **self.auth_headers(self.owner))
        self.assertEqual(resp.status_code, 409)

        self.client.delete(
            f"/devices/{self.node['uuid']}/postprocessings/{attached['id']}", **self.auth_headers(self.owner)
        )
        resp = self.client.delete(f"/postprocessing-blueprints/{blueprint['id']}", **self.auth_headers(self.owner))
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(BlueprintVersion.objects.exists())

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/postprocessing-blueprints").status_code, 401)


class BlueprintValidationTests(PostprocessingTestCase):
    """Bad steps fail when the version is written, not later in the stream."""

    def assert_rejected(self, payload, fragment):
        resp = self.client.post("/postprocessing-blueprints", payload, format="json", **self.auth_headers(self.owner))
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn(fragment, str(resp.json()))

    def test_unknown_function_name(self):
        payload = _offset_blueprint()
        payload["steps"][0]["function_name"] = "not_a_real_algorithm"
        self.assert_rejected(payload, "Unknown algorithm")

    def test_calibration_param_on_a_step(self):
        payload = _no2_blueprint()
        payload["steps"][0]["params"] = {"sensitivity": 1.0}
        self.assert_rejected(payload, "calibration parameters, set per device")

    def test_missing_required_configuration(self):
        payload = _no2_blueprint()
        payload["steps"][1]["params"] = {}
        self.assert_rejected(payload, "requires param(s)")

    def test_unknown_output(self):
        payload = _offset_blueprint()
        payload["steps"][0]["outputs"] = {"calibratd": "x"}
        self.assert_rejected(payload, "has no output(s)")

    def test_input_from_an_undeclared_slot(self):
        payload = _offset_blueprint()
        payload["steps"][0]["inputs"] = {"value": "slot:nope"}
        self.assert_rejected(payload, "slot:<declared slot>")

    def test_input_from_a_later_step(self):
        payload = _no2_blueprint()
        payload["steps"][0]["order"], payload["steps"][1]["order"] = 1, 0
        self.assert_rejected(payload, "earlier step key")

    def test_raw_channel_names_are_not_step_inputs(self):
        payload = _offset_blueprint()
        payload["steps"][0]["inputs"] = {"value": TEMPERATURE}
        self.assert_rejected(payload, "slot:<declared slot>")

    def test_output_field_produced_twice(self):
        payload = _no2_blueprint()
        payload["steps"][1]["outputs"] = {"concentration_ugm3": "no2_ppb"}
        self.assert_rejected(payload, "produced twice")

    def test_unused_slot(self):
        payload = _offset_blueprint()
        payload["inputs"].append({"slot": "spare"})
        self.assert_rejected(payload, "not used by any step")

    def test_step_keys_must_be_unique(self):
        payload = _no2_blueprint()
        payload["steps"][1]["key"] = "ppb"
        self.assert_rejected(payload, "used twice")

    def test_no_steps(self):
        payload = _offset_blueprint()
        payload["steps"] = []
        self.assert_rejected(payload, "at least one step")

    def test_duplicate_order(self):
        payload = _no2_blueprint()
        payload["steps"][1]["order"] = 0
        self.assert_rejected(payload, "unique")


class AttachTests(PostprocessingTestCase):
    def test_default_channels_are_bound_and_outputs_registered(self):
        attached = self.attach(self.create_blueprint())

        self.assertEqual(
            attached["input_bindings"],
            {
                "working": str(self.channels[WORKING].id),
                "auxiliary": str(self.channels[AUXILIARY].id),
                "temperature": str(self.channels[TEMPERATURE].id),
            },
        )
        outputs = {o["channel"]: o["unit"] for o in attached["outputs"]}
        self.assertEqual(outputs, {"derived.no2_ppb": "ppb", "derived.no2_ugm3": "ug/m3"})
        self.assertEqual(Measurement.objects.filter(produced_by_id=attached["id"]).count(), 2)

    def test_starts_disabled_and_reports_the_missing_calibration(self):
        attached = self.attach(self.create_blueprint())

        self.assertFalse(attached["is_enabled"])
        self.assertEqual(len(attached["problems"]), 1)
        self.assertIn("'ppb' needs a calibration", attached["problems"][0])
        self.assertEqual(self.last_published_plans(), [])

    def test_enabling_without_calibration_is_refused(self):
        self.attach(self.create_blueprint(), is_enabled=True, expect=400)
        self.assertFalse(DevicePostprocessing.objects.exists())

    def test_derived_channels_appear_among_the_device_measurements(self):
        attached = self.attach(self.create_blueprint())

        rows = self.client.get(f"/devices/{self.node['uuid']}/measurements", **self.auth_headers(self.owner)).json()

        produced = {r["measurement_type"]["channel"]: r["produced_by"] for r in rows}
        self.assertEqual(produced["derived.no2_ppb"], attached["id"])
        self.assertIsNone(produced[TEMPERATURE])

    def test_explicit_binding_overrides_the_default_channel(self):
        [other] = self.give_channels(self.device, {"environment_metrics.relative_humidity": "%"}).values()

        attached = self.attach(self.create_blueprint(_offset_blueprint()), input_bindings={"value": str(other.id)})

        self.assertEqual(attached["input_bindings"], {"value": str(other.id)})
        self.assertEqual(attached["outputs"][0]["unit"], "%")

    def test_binding_another_devices_channel_is_refused(self):
        node = self.create_node(self.owner, self.mesh, device_id=8)
        [foreign] = self.give_channels(Device.objects.get(pk=node["uuid"]), {TEMPERATURE: "degC"}).values()

        self.attach(self.create_blueprint(_offset_blueprint()), input_bindings={"value": str(foreign.id)}, expect=400)

    def test_unknown_slot_is_refused(self):
        self.attach(
            self.create_blueprint(_offset_blueprint()),
            input_bindings={"nope": str(self.channels[TEMPERATURE].id)},
            expect=400,
        )

    def test_private_blueprint_of_another_owner_is_not_found(self):
        other = self.create_owner(name="B", email="attach-private@example.com")
        blueprint = self.create_blueprint(owner=other)

        self.attach(blueprint, expect=404)

    def test_public_blueprint_of_another_owner_can_be_attached(self):
        other = self.create_owner(name="B", email="attach-public@example.com")
        blueprint = self.create_blueprint(_no2_blueprint(is_public=True), owner=other)

        self.attach(blueprint)

    def test_viewer_of_a_public_mesh_cannot_attach(self):
        other = self.create_owner(name="B", email="attach-viewer@example.com")
        self.client.put(f"/meshes/{self.mesh['id']}", {"is_public": True}, format="json", **self.auth_headers(self.owner))
        blueprint = self.create_blueprint(owner=other)

        self.attach(blueprint, owner=other, expect=403)

    def test_same_outputs_twice_need_a_prefix(self):
        blueprint = self.create_blueprint()
        self.attach(blueprint)

        self.attach(blueprint, expect=400)
        second = self.attach(blueprint, output_prefix="second_")

        self.assertEqual(
            {o["channel"] for o in second["outputs"]}, {"derived.second_no2_ppb", "derived.second_no2_ugm3"}
        )

    def test_unit_that_conflicts_with_the_catalog_is_refused(self):
        MeasurementType.objects.create(payload_kind="computed:derived", field_name="no2_ppb", native_unit="ug/m3")

        self.attach(self.create_blueprint(), expect=400)

    def test_failed_publish_rolls_the_attachment_back(self):
        self.fake_publisher.publish_postprocessing_plans.side_effect = RuntimeError("kafka down")

        self.attach(self.create_blueprint(), expect=502)

        self.assertFalse(DevicePostprocessing.objects.exists())
        self.assertFalse(Measurement.objects.filter(measurement_type__payload_kind="computed:derived").exists())

    def test_has_postprocessing_filter(self):
        self.create_node(self.owner, self.mesh, device_id=8)
        self.attach(self.create_blueprint())

        with_any = self.client.get("/devices?has_postprocessing=true", **self.auth_headers(self.owner)).json()
        without = self.client.get("/devices?has_postprocessing=false", **self.auth_headers(self.owner)).json()

        self.assertEqual([d["node_id"] for d in with_any], [7])
        self.assertEqual([d["node_id"] for d in without], [8])


class CalibrationTests(PostprocessingTestCase):
    def setUp(self):
        super().setUp()
        self.attached = self.attach(self.create_blueprint())

    def test_calibrating_then_enabling_publishes_the_resolved_plan(self):
        self.calibrate(self.attached, params={"sensitivity": 2.0, "working_zero": 220.0})

        enabled = self.update(self.attached, is_enabled=True)

        self.assertTrue(enabled["is_enabled"])
        self.assertEqual(enabled["problems"], [])
        [plan] = self.last_published_plans()
        self.assertEqual(plan["id"], self.attached["id"])
        self.assertEqual(plan["blueprint_version"], 1)
        ppb, ugm3 = plan["steps"]
        self.assertEqual(ppb["inputs"], {"working": WORKING, "auxiliary": AUXILIARY, "temperature": TEMPERATURE})
        self.assertEqual(ppb["outputs"], {"concentration_ppb": "derived.no2_ppb"})
        self.assertEqual(ppb["params"], {"temperature_coefficient": 0.01})
        self.assertEqual(ppb["calibrations"][0]["params"], {"sensitivity": 2.0, "working_zero": 220.0})
        self.assertEqual(ugm3["inputs"]["concentration_ppb"], "derived.no2_ppb")

    def test_tolerance_follows_the_device_reading_interval(self):
        self.calibrate(self.attached)
        self.update(self.attached, is_enabled=True)

        self.client.put(
            f"/devices/{self.node['uuid']}", {"reading_interval_seconds": 120}, format="json", **self.auth_headers(self.owner)
        )

        self.assertEqual(self.last_published_plans()[0]["tolerance_seconds"], 60.0)

    def test_history_is_kept_in_order(self):
        self.calibrate(self.attached, params={"sensitivity": 2.0}, valid_from="2026-01-01T00:00:00Z")
        self.calibrate(self.attached, params={"sensitivity": 3.0}, valid_from="2026-06-01T00:00:00Z")

        rows = self.client.get(
            f"/devices/{self.node['uuid']}/postprocessings/{self.attached['id']}/calibrations",
            **self.auth_headers(self.owner),
        ).json()

        self.assertEqual([r["params"]["sensitivity"] for r in rows], [2.0, 3.0])
        self.assertEqual(rows[0]["function_name"], "ec_sensor_ppb")

    def test_configuration_params_are_refused(self):
        self.calibrate(self.attached, params={"sensitivity": 1.0, "reference_temperature": 25}, expect=400)

    def test_incomplete_calibration_is_refused(self):
        self.calibrate(self.attached, params={"working_zero": 220.0}, expect=400)

    def test_unknown_step_is_refused(self):
        self.calibrate(self.attached, step_key="nope", expect=400)

    def test_deleting_the_only_calibration_of_an_enabled_postprocessing_is_refused(self):
        calibration = self.calibrate(self.attached)
        self.update(self.attached, is_enabled=True)
        url = f"/devices/{self.node['uuid']}/postprocessings/{self.attached['id']}/calibrations/{calibration['id']}"

        self.assertEqual(self.client.delete(url, **self.auth_headers(self.owner)).status_code, 409)
        self.update(self.attached, is_enabled=False)
        self.assertEqual(self.client.delete(url, **self.auth_headers(self.owner)).status_code, 204)

    def test_viewer_cannot_calibrate(self):
        other = self.create_owner(name="B", email="calibrate-viewer@example.com")
        self.client.put(f"/meshes/{self.mesh['id']}", {"is_public": True}, format="json", **self.auth_headers(self.owner))

        resp = self.client.post(
            f"/devices/{self.node['uuid']}/postprocessings/{self.attached['id']}/calibrations",
            {"step_key": "ppb", "params": {"sensitivity": 1.0}},
            format="json",
            **self.auth_headers(other),
        )

        self.assertEqual(resp.status_code, 403)


class VersionMoveTests(PostprocessingTestCase):
    def test_calibration_carries_over_for_a_kept_step(self):
        blueprint = self.create_blueprint()
        attached = self.attach(blueprint)
        self.calibrate(attached)
        self.update(attached, is_enabled=True)
        v2 = _no2_blueprint()
        v2.pop("name")
        v2["steps"] = v2["steps"][:1]
        self.client.post(
            f"/postprocessing-blueprints/{blueprint['id']}/versions", v2, format="json", **self.auth_headers(self.owner)
        )

        moved = self.update(attached, blueprint_version=2)

        self.assertEqual(moved["blueprint_version"], 2)
        self.assertTrue(moved["is_enabled"])
        self.assertEqual([o["channel"] for o in moved["outputs"]], ["derived.no2_ppb"])
        self.assertFalse(Measurement.objects.filter(measurement_type__field_name="no2_ugm3").exists())
        [plan] = self.last_published_plans()
        self.assertEqual(plan["blueprint_version"], 2)
        self.assertEqual(plan["steps"][0]["calibrations"][0]["params"], {"sensitivity": 2.0})

    def test_move_that_needs_a_new_calibration_is_refused_while_enabled(self):
        blueprint = self.create_blueprint(_offset_blueprint())
        attached = self.attach(blueprint, is_enabled=True)
        v2 = _no2_blueprint()
        v2.pop("name")
        self.client.post(
            f"/postprocessing-blueprints/{blueprint['id']}/versions", v2, format="json", **self.auth_headers(self.owner)
        )

        self.update(attached, blueprint_version=2, expect=400)

        self.assertEqual(DevicePostprocessing.objects.get().blueprint_version.number, 1)

    def test_unknown_version_is_refused(self):
        attached = self.attach(self.create_blueprint())
        self.update(attached, blueprint_version=9, expect=400)


class ChainingTests(PostprocessingTestCase):
    """One postprocessing may read another's output, never its own, directly or not."""

    def setUp(self):
        super().setUp()
        self.first = self.attach(self.create_blueprint())
        self.calibrate(self.first)
        self.first = self.update(self.first, is_enabled=True)
        self.ppb_id = next(o for o in self.first["outputs"] if o["field_name"] == "no2_ppb")["measurement_id"]
        self.second = self.attach(
            self.create_blueprint(_offset_blueprint(default_channel="derived.no2_ppb")), is_enabled=True
        )

    def test_derived_channel_is_bound_by_default_channel(self):
        self.assertEqual(self.second["input_bindings"], {"value": self.ppb_id})
        self.assertEqual(self.second["outputs"][0]["unit"], "ppb")

    def test_plans_are_published_in_dependency_order(self):
        self.update(self.first, tolerance_seconds=10)

        self.assertEqual([p["id"] for p in self.last_published_plans()], [self.first["id"], self.second["id"]])

    def test_reading_a_disabled_postprocessing_is_a_problem(self):
        self.update(self.second, is_enabled=False)
        self.update(self.first, is_enabled=False)

        second = self.client.get(
            f"/devices/{self.node['uuid']}/postprocessings/{self.second['id']}", **self.auth_headers(self.owner)
        ).json()

        self.assertIn("comes from a disabled postprocessing", second["problems"][0])

    def test_detaching_a_producer_that_is_read_is_refused(self):
        resp = self.client.delete(
            f"/devices/{self.node['uuid']}/postprocessings/{self.first['id']}", **self.auth_headers(self.owner)
        )

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(DevicePostprocessing.objects.count(), 2)

    def test_cycle_is_refused(self):
        calibrated_id = self.second["outputs"][0]["measurement_id"]

        self.update(self.first, input_bindings={"temperature": calibrated_id}, expect=400)

    def test_reading_its_own_output_is_refused(self):
        self.update(self.second, input_bindings={"value": self.second["outputs"][0]["measurement_id"]}, expect=400)


class DetachTests(PostprocessingTestCase):
    def test_detach_removes_the_derived_channels_and_republishes(self):
        attached = self.attach(self.create_blueprint())
        output = Measurement.objects.get(produced_by_id=attached["id"], measurement_type__field_name="no2_ppb")
        self.client.put(
            f"/devices/{self.node['uuid']}/measurements/{output.id}",
            {"valid_min": 0, "valid_max": 500},
            format="json",
            **self.auth_headers(self.owner),
        )
        self.fake_publisher.reset_mock()

        resp = self.client.delete(
            f"/devices/{self.node['uuid']}/postprocessings/{attached['id']}", **self.auth_headers(self.owner)
        )

        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Measurement.objects.filter(pk=output.pk).exists())
        self.assertEqual(self.last_published_plans(), [])
        _, cleared = self.fake_publisher.publish_measurement_alarms.call_args[0]
        self.assertIsNone(cleared.valid_min)

    def test_deleting_the_device_withdraws_its_plans(self):
        self.attach(self.create_blueprint())
        self.fake_publisher.reset_mock()

        resp = self.client.delete(f"/devices/{self.node['uuid']}", **self.auth_headers(self.owner))

        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.last_published_plans(), [])
        self.assertFalse(DevicePostprocessing.objects.exists())

    def test_blueprint_in_use_elsewhere_outlives_its_deleted_owner(self):
        other = self.create_owner(name="B", email="owner-delete@example.com")
        used = self.create_blueprint(_no2_blueprint(is_public=True), owner=other)
        unused = self.create_blueprint(_no2_blueprint(name="unused"), owner=other)
        attached = self.attach(used)

        resp = self.client.delete("/owners/me", **self.auth_headers(other))

        self.assertEqual(resp.status_code, 204)
        self.assertIsNone(PostprocessingBlueprint.objects.get(pk=used["id"]).owner_id)
        self.assertFalse(PostprocessingBlueprint.objects.filter(pk=unused["id"]).exists())
        self.assertTrue(DevicePostprocessing.objects.filter(pk=attached["id"]).exists())

    def test_ownerless_blueprint_is_editable_by_superusers_only(self):
        other = self.create_owner(name="B", email="ownerless@example.com")
        blueprint = self.create_blueprint(_no2_blueprint(is_public=True), owner=other)
        self.attach(blueprint)
        self.client.delete("/owners/me", **self.auth_headers(other))
        admin = self.create_owner(name="Admin", email="ownerless-admin@example.com")
        self.promote_to_superuser(admin)
        url = f"/postprocessing-blueprints/{blueprint['id']}"

        refused = self.client.put(url, {"description": "x"}, format="json", **self.auth_headers(self.owner))
        allowed = self.client.put(url, {"description": "x"}, format="json", **self.auth_headers(admin))

        self.assertEqual(refused.status_code, 403)
        self.assertEqual(allowed.status_code, 200)
        self.assertIsNone(allowed.json()["owner_id"])

    def test_owner_using_their_own_blueprint_can_be_deleted(self):
        self.attach(self.create_blueprint())

        resp = self.client.delete("/owners/me", **self.auth_headers(self.owner))

        self.assertEqual(resp.status_code, 204)
        self.assertFalse(PostprocessingBlueprint.objects.exists())


class ResyncCommandTests(PostprocessingTestCase):
    def test_republishes_every_device_with_a_postprocessing(self):
        attached = self.attach(self.create_blueprint(_offset_blueprint()), is_enabled=True)
        self.fake_publisher.reset_mock()

        out = StringIO()
        call_command("publish_postprocessing_config", stdout=out)

        self.assertIn("1 device(s)", out.getvalue())
        self.assertEqual(self.last_published_plans()[0]["id"], attached["id"])
        self.assertEqual(self.fake_publisher.publish_postprocessing_plans.call_args[0][0].id, uuid.UUID(self.node["uuid"]))


class BackfillTests(PostprocessingTestCase):
    def setUp(self):
        super().setUp()
        self.attached = self.attach(self.create_blueprint())
        self.calibrate(self.attached)
        self.url = f"/devices/{self.node['uuid']}/postprocessings/{self.attached['id']}/backfills"
        self.admin = self.create_owner(name="Worker", email="backfill-worker@example.com")
        self.promote_to_superuser(self.admin)

    def request_backfill(self, expect=202, **fields):
        resp = self.client.post(
            self.url, {"start": "2026-09-01T00:00:00Z", **fields}, format="json", **self.auth_headers(self.owner)
        )
        self.assertEqual(resp.status_code, expect, resp.content)
        return resp.json()

    def claim(self, backfill, expect=200):
        resp = self.client.post(f"/postprocessing-backfills/{backfill['id']}/claim", **self.auth_headers(self.admin))
        self.assertEqual(resp.status_code, expect, resp.content)
        return resp.json()

    def test_request_is_queued_and_listed(self):
        backfill = self.request_backfill(stop="2026-09-02T00:00:00Z")

        self.assertEqual(backfill["status"], "pending")
        listed = self.client.get(self.url, **self.auth_headers(self.owner)).json()
        self.assertEqual([b["id"] for b in listed], [backfill["id"]])
        pending = self.client.get("/postprocessing-backfills?status=pending", **self.auth_headers(self.admin)).json()
        self.assertEqual([b["id"] for b in pending], [backfill["id"]])

    def test_a_disabled_but_runnable_postprocessing_can_be_backfilled(self):
        self.assertFalse(self.attached["is_enabled"])
        self.request_backfill()

    def test_an_unrunnable_postprocessing_is_refused(self):
        attached = self.attach(self.create_blueprint(_no2_blueprint(name="uncalibrated")), output_prefix="u_")

        resp = self.client.post(
            f"/devices/{self.node['uuid']}/postprocessings/{attached['id']}/backfills",
            {"start": "2026-09-01T00:00:00Z"},
            format="json",
            **self.auth_headers(self.owner),
        )

        self.assertEqual(resp.status_code, 400)
        self.assertIn("needs a calibration", str(resp.json()))

    def test_range_must_be_ordered_and_bounded(self):
        self.request_backfill(stop="2026-08-01T00:00:00Z", expect=400)
        self.request_backfill(start="2025-01-01T00:00:00Z", stop="2026-01-01T00:00:00Z", expect=400)

    def test_claim_hands_over_the_resolved_plan_once(self):
        backfill = self.request_backfill(stop="2026-09-02T00:00:00Z")

        claimed = self.claim(backfill)

        self.assertEqual(claimed["status"], "running")
        self.assertEqual(claimed["node_id"], 7)
        self.assertEqual(claimed["mesh_id"], self.mesh["id"])
        [plan] = claimed["plans"]
        self.assertEqual(plan["id"], self.attached["id"])
        self.assertEqual(plan["steps"][0]["calibrations"][0]["params"], {"sensitivity": 2.0})
        self.claim(backfill, expect=409)

    def test_dependants_are_included_in_order_when_asked(self):
        self.update(self.attached, is_enabled=True)
        second = self.attach(self.create_blueprint(_offset_blueprint(default_channel="derived.no2_ppb")), is_enabled=True)
        self.attach(self.create_blueprint(_offset_blueprint(name="unrelated")), output_prefix="t_", is_enabled=True)

        alone = self.claim(self.request_backfill())
        chained = self.claim(self.request_backfill(include_dependants=True))

        self.assertEqual([p["id"] for p in alone["plans"]], [self.attached["id"]])
        self.assertEqual([p["id"] for p in chained["plans"]], [self.attached["id"], second["id"]])

    def test_result_is_recorded_once(self):
        backfill = self.request_backfill()
        self.claim(backfill)
        url = f"/postprocessing-backfills/{backfill['id']}"

        resp = self.client.put(url, {"status": "done", "points_published": 42}, format="json", **self.auth_headers(self.admin))

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["points_published"], 42)
        self.assertIsNotNone(resp.json()["finished_at"])
        again = self.client.put(url, {"status": "failed"}, format="json", **self.auth_headers(self.admin))
        self.assertEqual(again.status_code, 409)

    def test_abandoned_run_can_be_claimed_again(self):
        from django.utils import timezone

        from registry.models import PostprocessingBackfill
        from registry.postprocessing import BACKFILL_CLAIM_TIMEOUT

        backfill = self.request_backfill()
        self.claim(backfill)
        PostprocessingBackfill.objects.filter(pk=backfill["id"]).update(
            started_at=timezone.now() - BACKFILL_CLAIM_TIMEOUT * 2
        )

        self.claim(backfill)

    def test_worker_routes_are_superuser_only(self):
        backfill = self.request_backfill()

        self.assertEqual(self.client.get("/postprocessing-backfills", **self.auth_headers(self.owner)).status_code, 403)
        resp = self.client.post(f"/postprocessing-backfills/{backfill['id']}/claim", **self.auth_headers(self.owner))
        self.assertEqual(resp.status_code, 403)

    def test_viewer_cannot_request_a_backfill(self):
        other = self.create_owner(name="B", email="backfill-viewer@example.com")
        self.client.put(f"/meshes/{self.mesh['id']}", {"is_public": True}, format="json", **self.auth_headers(self.owner))

        resp = self.client.post(self.url, {"start": "2026-09-01T00:00:00Z"}, format="json", **self.auth_headers(other))

        self.assertEqual(resp.status_code, 403)
