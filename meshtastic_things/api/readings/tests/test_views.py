"""The readings views"""

from unittest.mock import MagicMock

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from readings import influx_client
from registry.auth import hash_api_key
from registry.models import Device, MeasurementType, Mesh, Owner


@override_settings(ROOT_URLCONF="api_project.urls_readings")
class ReadingsTestCase(APITestCase):
    """Registers one owner and one device"""

    VALID_TOKEN = "valid-test-token"
    NODE_ID = 123
    # A second mesh, so tests can prove a node number alone does not grant
    # access
    OTHER_CHANNEL = "OtherMesh"

    def setUp(self):
        super().setUp()
        cache.clear()

        self.owner = Owner.objects.create_user(
            email="owner@example.com", name="Owner", api_key_hash=hash_api_key(self.VALID_TOKEN)
        )
        self.mesh = Mesh.objects.create(owner=self.owner, channel_id="LongFast", psk_b64="AQ==")
        self.device = Device.objects.create(mesh=self.mesh, device_id=self.NODE_ID, is_gateway=False)
        self.mesh_id = str(self.mesh.id)
        self.device_uuid = str(self.device.id)

        self.fake_client = MagicMock()
        self.fake_client.ping.return_value = True
        self.fake_client.timeseries.return_value = [
            {"field": "battery_level", "points": [{"time": "2026-01-01T00:00:00+00:00", "value": 87.0}]}
        ]
        self.fake_client.latest.return_value = self.fake_client.timeseries.return_value
        self.fake_client.latest_all.return_value = [
            {
                "measurement": "device_metrics",
                "field": "battery_level",
                "value": 87.0,
                "time": "2026-01-01T00:00:00+00:00",
            }
        ]
        self.fake_client.device_metrics.return_value = {
            "points_ingested": 190.0,
            "plausibility_ratio": 0.98,
            "alarms_by_detector": {"plausibility": 2},
            "channels": [
                {
                    "channel": "device_metrics.battery_level",
                    "completeness_ratio": 0.95,
                    "observed": 190.0,
                    "expected": 200.0,
                    "largest_gap_seconds": 300.0,
                }
            ],
        }
        self._original_client = influx_client._client
        influx_client._client = self.fake_client

    def tearDown(self):
        influx_client._client = self._original_client
        cache.clear()
        super().tearDown()

    def auth_headers(self, token=None):
        return {"HTTP_AUTHORIZATION": f"Bearer {token or self.VALID_TOKEN}"}

    def node_url(self, suffix="", mesh_id=None, node_id=None):
        base = f"/readings/meshes/{mesh_id or self.mesh_id}/nodes/{node_id or self.NODE_ID}"
        return f"{base}/{suffix}" if suffix else base

    def uuid_url(self, suffix="", device_uuid=None):
        base = f"/readings/devices/{device_uuid or self.device_uuid}"
        return f"{base}/{suffix}" if suffix else base


class HealthTests(ReadingsTestCase):
    def test_health_ok_without_auth(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_health_reports_503_when_influx_unreachable(self):
        self.fake_client.ping.side_effect = RuntimeError("connection refused")
        self.assertEqual(self.client.get("/health").status_code, 503)


class AuthenticationTests(ReadingsTestCase):
    """The bearer key is checked against the owners table directly"""

    def test_missing_token_is_401(self):
        self.assertEqual(self.client.get(self.node_url("latest")).status_code, 401)

    def test_valid_token_is_accepted(self):
        self.assertEqual(self.client.get(self.node_url("latest"), **self.auth_headers()).status_code, 200)

    def test_unknown_token_is_401(self):
        resp = self.client.get(self.node_url("latest"), **self.auth_headers("nonsense"))
        self.assertEqual(resp.status_code, 401)

    def test_access_token_query_param_fallback(self):
        resp = self.client.get(f"{self.node_url('latest')}?access_token={self.VALID_TOKEN}")
        self.assertEqual(resp.status_code, 200)

    def test_a_device_registered_now_is_queryable_now(self):
        fresh = Device.objects.create(mesh=self.mesh, device_id=999, is_gateway=False)

        resp = self.client.get(self.node_url("latest", node_id=999), **self.auth_headers())

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(str(fresh.mesh_id), self.mesh_id)

    def test_an_unverified_owner_can_still_read(self):
        """Reading data needs an authenticated owner"""
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])

        self.assertEqual(self.client.get(self.node_url("latest"), **self.auth_headers()).status_code, 200)


class DeviceScopingTests(ReadingsTestCase):
    """A key reaches the meshes it owns, and nothing else."""

    def test_an_unregistered_node_on_your_own_mesh_is_readable(self):
        # Nodes are auto-discovered, so telemetry can arrive before the Device
        # row exists. The owner of the mesh it arrived on may still read it.
        resp = self.client.get(self.node_url("latest", node_id=4242), **self.auth_headers())

        self.assertEqual(resp.status_code, 200)

    def test_an_unregistered_node_on_someone_elses_mesh_is_404(self):
        other = Owner.objects.create_user(email="other-unreg@example.com", name="Other")
        other_mesh = Mesh.objects.create(owner=other, channel_id=self.OTHER_CHANNEL, psk_b64="AQ==")

        resp = self.client.get(
            self.node_url("latest", mesh_id=str(other_mesh.id), node_id=4242), **self.auth_headers()
        )

        self.assertEqual(resp.status_code, 404)

    def test_a_mesh_that_does_not_exist_is_404(self):
        resp = self.client.get(
            self.node_url("latest", mesh_id="00000000-0000-0000-0000-000000000000", node_id=1),
            **self.auth_headers(),
        )

        self.assertEqual(resp.status_code, 404)

    def test_own_device_is_allowed(self):
        self.assertEqual(self.client.get(self.node_url("latest"), **self.auth_headers()).status_code, 200)

    def test_another_owners_device_is_404(self):
        other = Owner.objects.create_user(email="other@example.com", name="Other")
        other_mesh = Mesh.objects.create(owner=other, channel_id=self.OTHER_CHANNEL, psk_b64="AQ==")
        Device.objects.create(mesh=other_mesh, device_id=777, is_gateway=False)

        resp = self.client.get(self.node_url("latest", mesh_id=str(other_mesh.id), node_id=777), **self.auth_headers())

        self.assertEqual(resp.status_code, 404)

    def test_same_node_number_in_a_mesh_you_do_not_own_is_404(self):
        """Node numbers are only unique among allowed registrations"""

        other = Owner.objects.create_user(email="other2@example.com", name="Other")
        other_mesh = Mesh.objects.create(owner=other, channel_id=self.OTHER_CHANNEL, psk_b64="AQ==")

        resp = self.client.get(
            self.node_url("latest", mesh_id=str(other_mesh.id), node_id=self.NODE_ID), **self.auth_headers()
        )

        self.assertEqual(resp.status_code, 404)

    def test_superuser_sees_devices_that_are_not_theirs(self):
        self.owner.is_superuser = True
        self.owner.save(update_fields=["is_superuser"])
        other = Owner.objects.create_user(email="other3@example.com", name="Other")
        other_mesh = Mesh.objects.create(owner=other, channel_id=self.OTHER_CHANNEL, psk_b64="AQ==")
        Device.objects.create(mesh=other_mesh, device_id=555, is_gateway=False)

        resp = self.client.get(self.node_url("latest", mesh_id=str(other_mesh.id), node_id=555), **self.auth_headers())

        self.assertEqual(resp.status_code, 200)


class ReadingsViewTests(ReadingsTestCase):
    def test_readings_shape(self):
        resp = self.client.get(self.node_url(), {"payload_kind": "telemetry:device_metrics"}, **self.auth_headers())

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["mesh_id"], self.mesh_id)
        self.assertEqual(body["node_id"], self.NODE_ID)
        self.assertEqual(body["series"][0]["channel"], "device_metrics.battery_level")

    def test_measurement_is_required(self):
        self.assertEqual(self.client.get(self.node_url(), **self.auth_headers()).status_code, 400)

    def test_value_error_from_the_client_is_a_400(self):
        self.fake_client.timeseries.side_effect = ValueError("Invalid measurement")

        resp = self.client.get(self.node_url(), {"measurement": "whatever"}, **self.auth_headers())

        self.assertEqual(resp.status_code, 400)


class QualityViewTests(ReadingsTestCase):
    def test_quality_shape(self):
        resp = self.client.get(self.node_url("quality"), **self.auth_headers())

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["points_ingested"], 190.0)
        self.assertEqual(body["alarms_by_detector"], {"plausibility": 2})
        self.assertEqual(body["channels"][0]["channel"], "device_metrics.battery_level")

    def test_default_window_is_the_last_hour(self):
        self.client.get(self.node_url("quality"), **self.auth_headers())

        args = self.fake_client.device_metrics.call_args.args
        self.assertEqual((str(args[0]), args[1], args[2], args[3]), (self.mesh_id, self.NODE_ID, "-1h", "now()"))


class LatestAllTests(ReadingsTestCase):
    """Omitting ?payload_kind= returns every channel"""

    def setUp(self):
        super().setUp()
        # 0001_initial seeds the catalog, so this channel already exists.
        MeasurementType.objects.update_or_create(
            payload_kind="telemetry:device_metrics",
            field_name="battery_level",
            defaults={"native_unit": "%", "quantity_kind": "ratio"},
        )

    def test_readings_are_annotated_from_the_catalog(self):
        resp = self.client.get(self.node_url("latest"), **self.auth_headers())

        self.assertEqual(resp.status_code, 200)
        reading = resp.json()["readings"][0]
        self.assertEqual(reading["value"], 87.0)
        self.assertEqual(reading["unit"], "%")
        self.assertEqual(reading["quantity_kind"], "ratio")
        self.assertEqual(reading["origin"], "measured")

    def test_an_uncatalogued_field_still_comes_back(self):
        MeasurementType.objects.all().delete()

        reading = self.client.get(self.node_url("latest"), **self.auth_headers()).json()["readings"][0]

        self.assertEqual(reading["value"], 87.0)
        self.assertIsNone(reading["unit"])

    def test_measurement_given_uses_the_series_shape(self):
        resp = self.client.get(self.node_url("latest"), {"payload_kind": "telemetry:device_metrics"}, **self.auth_headers())

        self.assertEqual(resp.json()["payload_kind"], "telemetry:device_metrics")
        self.assertNotIn("readings", resp.json())
        self.fake_client.latest_all.assert_not_called()

    def test_a_reading_speaks_the_same_vocabulary_as_the_catalog(self):
        """Storage flattens `telemetry:device_metrics` to `device_metrics`; the API must not
        hand that back as the payload_kind."""
        reading = self.client.get(self.node_url("latest"), **self.auth_headers()).json()["readings"][0]

        self.assertEqual(reading["payload_kind"], "telemetry:device_metrics")
        self.assertEqual(reading["field_name"], "battery_level")
        self.assertEqual(reading["channel"], "device_metrics.battery_level")

    def test_an_uncatalogued_channel_still_gets_its_namespace_back(self):
        MeasurementType.objects.all().delete()

        reading = self.client.get(self.node_url("latest"), **self.auth_headers()).json()["readings"][0]

        self.assertEqual(reading["payload_kind"], "telemetry:device_metrics")
        self.assertEqual(reading["field_name"], "battery_level")

    def test_channel_is_always_payload_kind_and_field_name(self):
        """The three fields have to agree, or a consumer cannot join a reading to its catalog
        row."""
        for reading in self.client.get(self.node_url("latest"), **self.auth_headers()).json()["readings"]:
            with self.subTest(channel=reading["channel"]):
                measurement = reading["payload_kind"].split(":", 1)[-1]
                self.assertEqual(reading["channel"], f"{measurement}.{reading['field_name']}")

    def test_asking_by_channel_reports_the_namespaced_payload_kind(self):
        resp = self.client.get(
            self.node_url(), {"channel": "device_metrics.battery_level"}, **self.auth_headers()
        )

        self.assertEqual(resp.json()["payload_kind"], "telemetry:device_metrics")


class DeviceUuidAddressingTests(ReadingsTestCase):
    """Getting a device by uuid or nodeID should be the same"""

    def test_uuid_and_node_addresses_agree(self):
        by_uuid = self.client.get(self.uuid_url("latest"), **self.auth_headers())
        by_node = self.client.get(self.node_url("latest"), **self.auth_headers())

        self.assertEqual(by_uuid.status_code, 200)
        self.assertEqual(by_uuid.json(), by_node.json())

    def test_unknown_uuid_is_404(self):
        resp = self.client.get(
            self.uuid_url("latest", device_uuid="99999999-9999-9999-9999-999999999999"), **self.auth_headers()
        )
        self.assertEqual(resp.status_code, 404)

    def test_another_owners_uuid_is_404(self):
        other = Owner.objects.create_user(email="other4@example.com", name="Other")
        other_mesh = Mesh.objects.create(owner=other, channel_id=self.OTHER_CHANNEL, psk_b64="AQ==")
        theirs = Device.objects.create(mesh=other_mesh, device_id=888, is_gateway=False)

        resp = self.client.get(self.uuid_url("latest", device_uuid=str(theirs.id)), **self.auth_headers())

        self.assertEqual(resp.status_code, 404)

    def test_a_node_number_on_the_uuid_route_is_404(self):
        self.assertEqual(self.client.get("/readings/devices/123/latest", **self.auth_headers()).status_code, 404)


class RoleTrimmingTests(ReadingsTestCase):
    """The readings role can't get anything from registry"""

    def test_registry_routes_are_absent(self):
        for path in ("/owners", "/meshes", "/devices", "/metrics", "/admin", "/schema", "/docs"):
            self.assertEqual(self.client.get(path, **self.auth_headers()).status_code, 404, path)

    def test_unmatched_paths_answer_json_not_html(self):
        resp = self.client.get("/nope", **self.auth_headers())

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp["Content-Type"], "application/json")
        self.assertIn("detail", resp.json())

    def test_the_old_prefixed_paths_are_gone(self):
        for path in (f"/data/meshes/{self.mesh_id}/nodes/{self.NODE_ID}/latest", self.node_url("timeseries")):
            self.assertEqual(self.client.get(path, **self.auth_headers()).status_code, 404, path)
