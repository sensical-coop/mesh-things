"""The protocol versions on offer, their sunset, and moving meshes off a retired one."""
from datetime import date, datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest.mock import patch

from django.apps import apps as django_apps
from django.core import mail
from django.core.management import call_command

from mesh_things import protocols
from registry.data_lifecycle import send_protocol_notices
from registry.models import Device, Mesh
from registry.protocol_moves import move_meshes_off, refuse_while_used

from .helpers import MESH_TERMS, RegistryTestCase

TODAY = date(2026, 11, 3)
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=dt_timezone.utc)


def _retiring(status: str, sunset: date | None) -> dict:
    """PROTOCOLS with 2.7 given a status and sunset date."""
    return {
        **protocols.PROTOCOLS,
        "2.7": protocols.PROTOCOLS["2.7"]._replace(status=status, sunset=sunset),
    }


class ProtocolListTests(RegistryTestCase):
    def test_every_version_is_listed_oldest_first_without_credentials(self):
        resp = self.client.get("/protocols")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual([p["version"] for p in resp.json()], list(protocols.VERSIONS))
        latest = resp.json()[-1]
        self.assertEqual(latest, {
            "version": "2.8", "status": "current", "sunset": None, "source_ref": "v2.8.2", "is_default": True,
        })

    def test_a_version_past_its_sunset_date_is_listed_as_sunset(self):
        with patch.object(protocols, "PROTOCOLS", _retiring(protocols.DEPRECATED, date(2020, 1, 1))):
            resp = self.client.get("/protocols")

        self.assertEqual(resp.json()[0]["status"], "sunset")
        self.assertEqual(resp.json()[0]["sunset"], "2020-01-01")


class SunsetTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_owner()
        sunset = patch.object(protocols, "PROTOCOLS", _retiring(protocols.DEPRECATED, date(2020, 1, 1)))
        sunset.start()
        self.addCleanup(sunset.stop)

    def test_a_new_mesh_cannot_choose_a_version_past_its_sunset(self):
        resp = self.client.post(
            "/meshes",
            {**MESH_TERMS, "channel_id": "Old", "psk_b64": "AQ==", "protocol": "2.7"},
            format="json",
            **self.auth_headers(self.owner),
        )

        self.assertEqual(resp.status_code, 400)
        self.assertIn("sunset", str(resp.json()["protocol"]))

    def test_a_mesh_cannot_move_onto_it(self):
        mesh = self.create_mesh(self.owner)

        resp = self.client.put(
            f"/meshes/{mesh['id']}", {"protocol": "2.7"}, format="json", **self.auth_headers(self.owner)
        )

        self.assertEqual(resp.status_code, 400)

    def test_a_mesh_already_on_it_keeps_it_and_shows_its_status(self):
        mesh = self.create_mesh(self.owner)
        Mesh.objects.filter(pk=mesh["id"]).update(protocol="2.7")

        resp = self.client.put(
            f"/meshes/{mesh['id']}", {"protocol": "2.7", "label": "kept"}, format="json", **self.auth_headers(self.owner)
        )

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["protocol_status"], "sunset")
        self.assertEqual(resp.json()["protocol_sunset"], "2020-01-01")


class ProtocolNoticeTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_owner(email="notice-owner@example.com")
        self.mesh = self.create_mesh(self.owner, label="Old field")
        Mesh.objects.filter(pk=self.mesh["id"]).update(protocol="2.7")
        mail.outbox.clear()

    def notices(self, status, sunset, now=NOW) -> int:
        with patch.object(protocols, "PROTOCOLS", _retiring(status, sunset)):
            return send_protocol_notices(now)

    def test_supported_versions_send_nothing(self):
        self.assertEqual(send_protocol_notices(NOW), 0)
        self.assertEqual(mail.outbox, [])

    def test_a_deprecated_version_is_announced_once_within_the_notice_window(self):
        sunset = TODAY + timedelta(days=20)

        self.assertEqual(self.notices(protocols.DEPRECATED, sunset), 1)
        self.assertEqual(self.notices(protocols.DEPRECATED, sunset, NOW + timedelta(days=1)), 0)
        self.assertEqual(mail.outbox[0].to, ["notice-owner@example.com"])
        self.assertIn("is deprecated", mail.outbox[0].subject)
        self.assertIn("set the mesh's protocol to\n2.8", mail.outbox[0].body)

    def test_a_sunset_far_away_waits_for_the_notice_window(self):
        self.assertEqual(self.notices(protocols.DEPRECATED, TODAY + timedelta(days=90)), 0)

    def test_a_deprecated_version_without_a_date_is_announced_straight_away(self):
        self.assertEqual(self.notices(protocols.DEPRECATED, None), 1)

    def test_the_sunset_sends_one_more(self):
        sunset = TODAY + timedelta(days=10)
        self.notices(protocols.DEPRECATED, sunset)

        self.assertEqual(self.notices(protocols.DEPRECATED, sunset, NOW + timedelta(days=10)), 1)
        self.assertEqual(self.notices(protocols.DEPRECATED, sunset, NOW + timedelta(days=11)), 0)
        self.assertIn("past its sunset", mail.outbox[1].subject)

    def test_a_mesh_that_moved_is_left_alone(self):
        Mesh.objects.filter(pk=self.mesh["id"]).update(protocol="2.8")

        self.assertEqual(self.notices(protocols.DEPRECATED, None), 0)


class RetirementTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_owner()
        self.mesh = self.create_mesh(self.owner)
        Mesh.objects.filter(pk=self.mesh["id"]).update(protocol="2.7")

    def test_meshes_move_up_when_the_next_version_only_adds(self):
        move_meshes_off("2.7")(django_apps, None)

        self.assertEqual(Mesh.objects.get(pk=self.mesh["id"]).protocol, "2.8")

    def test_meshes_are_not_moved_across_a_version_that_changes_meaning(self):
        changes = {**protocols.PROTOCOLS, "2.8": protocols.PROTOCOLS["2.8"]._replace(adds_only=False)}
        with patch.object(protocols, "PROTOCOLS", changes), self.assertRaisesRegex(RuntimeError, "adds_only"):
            move_meshes_off("2.7")(django_apps, None)

        self.assertEqual(Mesh.objects.get(pk=self.mesh["id"]).protocol, "2.7")

    def test_a_version_in_use_cannot_be_removed(self):
        with self.assertRaisesRegex(RuntimeError, "still on protocol 2.7"):
            refuse_while_used("2.7")(django_apps, None)

        Mesh.objects.filter(pk=self.mesh["id"]).update(protocol="2.8")
        refuse_while_used("2.7")(django_apps, None)

    def test_publish_gateways_republishes_every_allowed_gateway(self):
        self.create_gateway(self.owner, self.mesh, device_id=1)
        Device.objects.create(mesh_id=self.mesh["id"], device_id=2, is_gateway=True, is_allowed=False)
        self.fake_publisher.publish_gateway_upsert.reset_mock()

        out = StringIO()
        call_command("publish_gateways", stdout=out)

        self.assertEqual(self.fake_publisher.publish_gateway_upsert.call_count, 1)
        self.assertEqual(self.fake_publisher.publish_gateway_upsert.call_args.args[1].protocol, "2.7")
        self.assertIn("Published 1 gateway", out.getvalue())
