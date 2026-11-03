"""Tests for alarms
"""
from registry.models import (
    DeviceTelemetryVariant,
    Measurement,
    MeasurementType,
    TelemetryVariant,
    TelemetryVariantMeasurement,
)

from .helpers import RegistryTestCase


class AlarmOptInTestCase(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_owner()
        self.mesh = self.create_mesh(self.owner)
        self.device = self.create_node(self.owner, self.mesh, device_id=7)
        self.variant = TelemetryVariant.objects.create(payload_kind="telemetry:environment_metrics")
        self.measurement_type = MeasurementType.objects.create(
            payload_kind="telemetry:environment_metrics", field_name="barometric_pressure"
        )
        self.link = TelemetryVariantMeasurement.objects.create(
            telemetry_variant=self.variant, measurement_type=self.measurement_type
        )
        dtv = DeviceTelemetryVariant.objects.create(
            device_id=self.device["uuid"], telemetry_variant=self.variant
        )
        self.measurement = Measurement.objects.create(
            device_telemetry_variant=dtv, measurement_type=self.measurement_type
        )
        self.url = f"/devices/{self.device['uuid']}/measurements/{self.measurement.id}"

    def measurements(self):
        return self.client.get(
            f"/devices/{self.device['uuid']}/measurements", **self.auth_headers(self.owner)
        ).json()


class DefaultsTests(AlarmOptInTestCase):
    def test_a_freshly_discovered_channel_alarms_on_nothing(self):
        self.assertEqual(self.measurements()[0]["effective_detectors"], [])
        self.assertIsNone(self.measurements()[0]["enabled_detectors"])

    def test_a_device_with_no_flag_does_not_run_absence(self):
        device = self.client.get(
            f"/devices/{self.device['uuid']}", **self.auth_headers(self.owner)
        ).json()

        self.assertFalse(device["absence_detection_enabled"])


class ResolutionTests(AlarmOptInTestCase):
    def test_the_catalog_default_applies_when_the_device_says_nothing(self):
        self.link.default_enabled_detectors = ["range"]
        self.link.save()

        self.assertEqual(self.measurements()[0]["effective_detectors"], ["range"])

    def test_the_device_override_replaces_the_default(self):
        self.link.default_enabled_detectors = ["flat_value"]
        self.link.save()

        self.client.put(self.url, {"enabled_detectors": ["range"]}, format="json",
                        **self.auth_headers(self.owner))

        self.assertEqual(self.measurements()[0]["effective_detectors"], ["range"])

    def test_an_empty_list_silences_a_channel_the_catalog_enables(self):
        self.link.default_enabled_detectors = ["flat_value", "range"]
        self.link.save()

        self.client.put(self.url, {"enabled_detectors": []}, format="json",
                        **self.auth_headers(self.owner))

        self.assertEqual(self.measurements()[0]["effective_detectors"], [])

    def test_null_hands_the_channel_back_to_the_catalog(self):
        self.link.default_enabled_detectors = ["range"]
        self.link.save()
        self.client.put(self.url, {"enabled_detectors": []}, format="json",
                        **self.auth_headers(self.owner))

        self.client.put(self.url, {"enabled_detectors": None}, format="json",
                        **self.auth_headers(self.owner))

        self.assertEqual(self.measurements()[0]["effective_detectors"], ["range"])


class ValidationTests(AlarmOptInTestCase):
    def test_an_unknown_detector_is_rejected(self):
        resp = self.client.put(self.url, {"enabled_detectors": ["typo_value"]}, format="json",
                               **self.auth_headers(self.owner))

        self.assertEqual(resp.status_code, 400)

    def test_absence_is_not_settable_per_measurement(self):
        resp = self.client.put(self.url, {"enabled_detectors": ["absence"]}, format="json",
                               **self.auth_headers(self.owner))

        self.assertEqual(resp.status_code, 400)


class PermissionTests(AlarmOptInTestCase):
    def test_another_owner_cannot_see_or_set_it(self):
        intruder = self.create_owner(name="Mallory", email="mallory-alarms@example.com")

        resp = self.client.put(self.url, {"enabled_detectors": []}, format="json",
                               **self.auth_headers(intruder))

        self.assertIn(resp.status_code, (403, 404))

    def test_a_measurement_from_another_device_is_a_404(self):
        other = self.create_node(self.owner, self.mesh, device_id=8)

        resp = self.client.put(
            f"/devices/{other['uuid']}/measurements/{self.measurement.id}",
            {"enabled_detectors": []}, format="json", **self.auth_headers(self.owner),
        )

        self.assertEqual(resp.status_code, 404)

    def test_the_catalog_default_is_superuser_only(self):
        url = f"/telemetry-variants/{self.variant.id}/measurements/{self.link.id}"

        denied = self.client.put(url, {"default_enabled_detectors": ["range"]},
                                 format="json", **self.auth_headers(self.owner))
        self.promote_to_superuser(self.owner)
        allowed = self.client.put(url, {"default_enabled_detectors": ["range"]},
                                  format="json", **self.auth_headers(self.owner))

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json()["default_enabled_detectors"], ["range"])


class DetectorRegistryTests(AlarmOptInTestCase):
    """GET /detectors is what a UI builds its options from."""

    def detectors(self):
        return self.client.get("/detectors", **self.auth_headers(self.owner)).json()

    def test_it_lists_every_detector_with_its_scope(self):
        by_name = {d["name"]: d for d in self.detectors()}

        self.assertEqual(
            {n for n, d in by_name.items() if d["scope"] == "measurement"},
            {"flat_value", "range", "completeness"},
        )
        self.assertEqual(by_name["absence"]["scope"], "device")

    def test_the_measurement_scoped_names_are_exactly_what_the_api_accepts(self):
        """A dropdown built from this must not offer a value that 400s."""
        offered = [d["name"] for d in self.detectors() if d["scope"] == "measurement"]

        resp = self.client.put(self.url, {"enabled_detectors": offered}, format="json",
                               **self.auth_headers(self.owner))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(sorted(resp.json()["effective_detectors"]), sorted(offered))

    def test_each_entry_says_what_else_it_needs(self):
        by_name = {d["name"]: d for d in self.detectors()}

        self.assertEqual(by_name["range"]["requires"], ["valid_min", "valid_max"])
        self.assertEqual(by_name["completeness"]["requires"], ["reading_interval_seconds"])
        self.assertEqual(by_name["flat_value"]["requires"], [])

    def test_it_needs_a_verified_owner(self):
        self.assertEqual(self.client.get("/detectors").status_code, 401)


class PublishTests(AlarmOptInTestCase):
    """The stream job only learns about a change through the compacted topic."""

    def test_setting_the_override_publishes_it(self):
        self.client.put(self.url, {"enabled_detectors": ["range"]}, format="json",
                        **self.auth_headers(self.owner))

        self.fake_publisher.publish_measurement_alarms.assert_called_once()

    def test_the_absence_switch_republishes_the_device_entry(self):
        self.client.put(f"/devices/{self.device['uuid']}", {"absence_detection_enabled": True},
                        format="json", **self.auth_headers(self.owner))

        self.fake_publisher.publish_device_intervals.assert_called_once()
