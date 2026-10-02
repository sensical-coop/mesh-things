from io import StringIO

from django.core.management import call_command

from registry.models import DeviceTelemetryVariant, Measurement, TelemetryVariant, TelemetryVariantMeasurement

from .helpers import RegistryTestCase


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

    def test_intervals_default_to_null(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)

        body = self.client.get(f"/devices/{node['uuid']}", **self.auth_headers(owner)).json()

        self.assertIsNone(body["reading_interval_seconds"])
        self.assertIsNone(body["publish_interval_seconds"])

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
