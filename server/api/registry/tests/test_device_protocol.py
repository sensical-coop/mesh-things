"""Which protocol version a device follows, and the alert when it does not match its mesh's."""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.core import mail
from mesh_things import protocols

from registry import status_alerts
from registry.management.commands.consume_device_sightings import Command as SightingsCommand
from registry.models import Device, Mesh

from .helpers import RegistryTestCase

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=dt_timezone.utc)
MAP_REPORT = {"firmware_version": "2.7.26.54e0d8d", "region": "EU_868", "modem_preset": "LONG_FAST"}


def rescaling_2_8():
    """Pretend 2.8 changed how some values are encoded, as 3.0 will."""
    return mock.patch.dict(protocols.PROTOCOLS, {"2.8": protocols.PROTOCOLS["2.8"]._replace(adds_only=False)})


class DeviceProtocolTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_owner()
        self.mesh = self.create_mesh(self.owner)
        Mesh.objects.filter(pk=self.mesh["id"]).update(protocol="2.7")

    def sighting(self, device_id: int = 7, **fields) -> Device:
        SightingsCommand._upsert({"mesh_id": self.mesh["id"], "device_id": device_id, "op": "upsert", **fields})
        return Device.objects.get(mesh_id=self.mesh["id"], device_id=device_id)

    def device_json(self, device: Device, **headers) -> dict:
        resp = self.client.get(f"/devices/{device.id}", **(headers or self.auth_headers(self.owner)))
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()

    def test_a_device_follows_its_mesh_protocol_until_it_sends_more(self):
        body = self.device_json(self.sighting())

        self.assertEqual(body["protocol"], "2.7")
        self.assertIsNone(body["observed_protocol"])
        self.assertIsNone(body["observed_protocol_at"])
        self.assertFalse(body["protocol_mismatch"])

    def test_a_newer_protocol_on_a_sighting_is_a_mismatch(self):
        body = self.device_json(self.sighting(needs_protocol="2.8"))

        self.assertEqual(body["observed_protocol"], "2.8")
        self.assertIsNotNone(body["observed_protocol_at"])
        self.assertTrue(body["protocol_mismatch"])

    def test_the_observed_protocol_only_moves_forward(self):
        self.sighting(needs_protocol="unsupported")
        device = self.sighting(needs_protocol="2.8")

        self.assertEqual(device.observed_protocol, "unsupported")

    def test_a_sighting_without_evidence_keeps_the_observed_protocol(self):
        self.sighting(needs_protocol="2.8")

        self.assertEqual(self.sighting().observed_protocol, "2.8")

    def test_the_mismatch_clears_once_the_mesh_declares_the_version(self):
        device = self.sighting(needs_protocol="2.8")
        resp = self.client.put(
            f"/meshes/{self.mesh['id']}", {"protocol": "2.8"}, format="json", **self.auth_headers(self.owner)
        )
        self.assertEqual(resp.status_code, 200)

        body = self.device_json(device)
        self.assertEqual(body["protocol"], "2.8")
        self.assertFalse(body["protocol_mismatch"])

    def test_viewers_of_a_public_mesh_see_the_protocol_fields(self):
        Mesh.objects.filter(pk=self.mesh["id"]).update(is_public=True)
        device = self.sighting(needs_protocol="2.8")
        viewer = self.create_owner(name="Viewer", email="protocol-viewer@example.com")

        resp = self.client.get(f"/devices/{device.id}", **self.auth_headers(viewer))

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()["protocol_mismatch"])


    def test_a_map_report_fills_the_firmware_fields(self):
        body = self.device_json(self.sighting(**MAP_REPORT))

        self.assertEqual(body["firmware_version"], "2.7.26.54e0d8d")
        self.assertEqual(body["firmware_protocol"], "2.7")
        self.assertEqual(body["region"], "EU_868")
        self.assertEqual(body["modem_preset"], "LONG_FAST")
        self.assertIsNotNone(body["firmware_seen_at"])
        self.assertFalse(body["protocol_mismatch"])

    def test_a_sighting_without_a_report_keeps_the_firmware(self):
        self.sighting(**MAP_REPORT)

        self.assertEqual(self.sighting().firmware_version, "2.7.26.54e0d8d")

    def test_firmware_that_only_adds_fields_is_not_a_mismatch(self):
        Mesh.objects.filter(pk=self.mesh["id"]).update(protocol="2.8")

        self.assertFalse(self.sighting(**MAP_REPORT).protocol_mismatch)

    def test_older_firmware_is_a_mismatch_once_a_version_rescales(self):
        Mesh.objects.filter(pk=self.mesh["id"]).update(protocol="2.8")
        device = self.sighting(**MAP_REPORT)

        with rescaling_2_8():
            self.assertTrue(device.protocol_behind)
            self.assertTrue(device.protocol_mismatch)

    def test_newer_firmware_is_a_mismatch_once_a_version_rescales(self):
        device = self.sighting(**{**MAP_REPORT, "firmware_version": "2.8.2.a1b2c3d"})

        with rescaling_2_8():
            self.assertTrue(device.protocol_ahead)

    def test_firmware_newer_than_every_version_is_a_mismatch(self):
        body = self.device_json(self.sighting(**{**MAP_REPORT, "firmware_version": "3.0.0.a1b2c3d"}))

        self.assertEqual(body["firmware_protocol"], "unsupported")
        self.assertTrue(body["protocol_mismatch"])


class ProtocolMismatchAlertTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_owner(email="mismatch-owner@example.com")
        self.mesh = self.create_mesh(self.owner, label="Garden")
        Mesh.objects.filter(pk=self.mesh["id"]).update(protocol="2.7")
        resp = self.client.put(
            "/owners/me", {"status_alerts_enabled": True}, format="json", **self.auth_headers(self.owner)
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        mail.outbox.clear()

    def sighting(self, device_id: int = 7, **fields) -> None:
        SightingsCommand._upsert({"mesh_id": self.mesh["id"], "device_id": device_id, "op": "upsert", **fields})

    def test_a_mismatch_emails_the_owner_once(self):
        self.sighting(needs_protocol="2.8")

        self.assertEqual(status_alerts.check_protocol_mismatches(NOW), 1)
        self.assertEqual(status_alerts.check_protocol_mismatches(NOW + timedelta(hours=1)), 0)
        self.assertEqual(mail.outbox[0].to, ["mismatch-owner@example.com"])
        self.assertIn("Set the mesh's protocol to 2.8", mail.outbox[0].body)

    def test_a_version_this_instance_lacks_says_so(self):
        self.sighting(needs_protocol="unsupported")

        status_alerts.check_protocol_mismatches(NOW)

        self.assertIn("does not support the version", mail.outbox[0].body)

    def test_declaring_the_version_clears_it_and_a_new_mismatch_alerts_again(self):
        self.sighting(needs_protocol="2.8")
        status_alerts.check_protocol_mismatches(NOW)
        Mesh.objects.filter(pk=self.mesh["id"]).update(protocol="2.8")
        self.assertEqual(status_alerts.check_protocol_mismatches(NOW + timedelta(hours=1)), 0)

        self.sighting(device_id=8, needs_protocol="unsupported")

        self.assertEqual(status_alerts.check_protocol_mismatches(NOW + timedelta(hours=2)), 1)

    def test_an_owner_who_did_not_opt_in_is_not_emailed(self):
        self.client.put("/owners/me", {"status_alerts_enabled": False}, format="json", **self.auth_headers(self.owner))
        self.sighting(needs_protocol="2.8")

        self.assertEqual(status_alerts.check_protocol_mismatches(NOW), 0)
        self.assertEqual(mail.outbox, [])

    def test_a_rejected_device_does_not_count(self):
        self.sighting(needs_protocol="2.8")
        Device.objects.filter(mesh_id=self.mesh["id"]).update(is_allowed=False)

        self.assertEqual(status_alerts.check_protocol_mismatches(NOW), 0)

    def test_older_firmware_asks_for_a_firmware_update(self):
        Mesh.objects.filter(pk=self.mesh["id"]).update(protocol="2.8")
        self.sighting(**MAP_REPORT)

        with rescaling_2_8():
            self.assertEqual(status_alerts.check_protocol_mismatches(NOW), 1)

        body = mail.outbox[0].body
        self.assertIn("firmware 2.7.26.54e0d8d", body)
        self.assertIn("update the devices' firmware", body)
        self.assertNotIn("Set the mesh's protocol", body)

    def test_firmware_this_instance_lacks_says_so(self):
        self.sighting(**{**MAP_REPORT, "firmware_version": "3.0.0.a1b2c3d"})

        self.assertEqual(status_alerts.check_protocol_mismatches(NOW), 1)
        self.assertIn("does not support the version", mail.outbox[0].body)
