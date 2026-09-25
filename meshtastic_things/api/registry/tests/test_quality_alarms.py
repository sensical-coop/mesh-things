import uuid
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache

from registry.management.commands.consume_quality_alarms import Command as AlarmCommand
from registry.models import Device, Mesh, Owner

from .helpers import RegistryTestCase

def _alarm(mesh_id, device_id=1, detector="absence", channel=None, **overrides):
    event = {
        "mesh_id": str(mesh_id),
        "device_id": device_id,
        "channel": channel,
        "detector": detector,
        "source": "stream",
        "value": 900,
        "message": "No telemetry received for 900s",
        "triggered_at": "2026-09-06T12:00:00+00:00",
    }
    event.update(overrides)
    return event


class QualityAlarmRoutingTests(RegistryTestCase):

    def _device(self, owner_name="Alice", email="alarm-owner@example.com", **mesh_kwargs):
        """Owner + mesh + node, with the outbox cleared"""
        owner = self.create_owner(name=owner_name, email=email)
        mesh = self.create_mesh(owner, **mesh_kwargs)
        self.create_node(owner, mesh, device_id=1, label="greenhouse")
        mail.outbox.clear()
        return owner, mesh

    def test_alarm_emails_the_device_owner(self):
        _, mesh = self._device(label="Garden mesh")

        AlarmCommand._handle(_alarm(mesh["id"], 1))

        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["alarm-owner@example.com"])
        self.assertIn("stopped publishing", sent.subject)
        self.assertIn("greenhouse", sent.subject)
        self.assertIn("Garden mesh", sent.body)
        self.assertIn("No telemetry received for 900s", sent.body)

    def test_alarm_links_to_the_device_and_mesh_in_the_console(self):
        _, mesh = self._device()
        device = Device.objects.get(mesh_id=mesh["id"], device_id=1)

        with self.settings(PUBLIC_FRONTEND_URL="https://app.example.org", FRONTEND_CONSOLE_PATH="/console"):
            AlarmCommand._handle(_alarm(mesh["id"], 1))

        body = mail.outbox[0].body
        self.assertIn(f"https://app.example.org/console/devices/{device.id}", body)
        self.assertIn(f"https://app.example.org/console/meshes/{mesh['id']}", body)

    def test_absence_email_explains_the_publish_vs_read_distinction(self):
        _, mesh = self._device()

        AlarmCommand._handle(_alarm(mesh["id"], 1, detector="absence"))

        self.assertIn("may still deliver this period later", mail.outbox[0].body)

    def test_completeness_email_names_the_channel(self):
        _, mesh = self._device()

        AlarmCommand._handle(
            _alarm(mesh["id"], 1, detector="completeness", channel="environment_metrics.temperature")
        )

        self.assertIn("environment_metrics.temperature", mail.outbox[0].body)
        self.assertIn("gaps", mail.outbox[0].subject)

    def test_repeat_alarm_is_suppressed_by_the_cooldown(self):
        # The owner shouldn't get an
        # email every time.
        _, mesh = self._device()

        AlarmCommand._handle(_alarm(mesh["id"], 1))
        AlarmCommand._handle(_alarm(mesh["id"], 1))

        self.assertEqual(len(mail.outbox), 1)

    def test_owner_can_disable_the_cooldown(self):
        # alarm_email_cooldown_seconds=0 means "email on every alarm".
        owner, mesh = self._device()
        Owner.objects.filter(pk=owner["id"]).update(alarm_email_cooldown_seconds=0)

        AlarmCommand._handle(_alarm(mesh["id"], 1))
        AlarmCommand._handle(_alarm(mesh["id"], 1))

        self.assertEqual(len(mail.outbox), 2)

    def test_owner_cooldown_overrides_the_server_default(self):
        owner, mesh = self._device()
        Owner.objects.filter(pk=owner["id"]).update(alarm_email_cooldown_seconds=30)

        with patch(
            "registry.management.commands.consume_quality_alarms.cache.add", wraps=cache.add
        ) as add:
            AlarmCommand._handle(_alarm(mesh["id"], 1))

        add.assert_called_once()
        self.assertEqual(add.call_args.args[2], 30)

    def test_owner_without_a_cooldown_set_uses_the_server_default(self):
        owner, mesh = self._device()
        self.assertIsNone(Owner.objects.get(pk=owner["id"]).alarm_email_cooldown_seconds)

        with patch(
            "registry.management.commands.consume_quality_alarms.cache.add", wraps=cache.add
        ) as add:
            AlarmCommand._handle(_alarm(mesh["id"], 1))

        from registry.management.commands.consume_quality_alarms import ALARM_EMAIL_COOLDOWN_SECONDS

        add.assert_called_once()
        self.assertEqual(add.call_args.args[2], ALARM_EMAIL_COOLDOWN_SECONDS)

    def test_a_different_detector_is_not_suppressed(self):
        _, mesh = self._device()

        AlarmCommand._handle(_alarm(mesh["id"], 1, detector="absence"))
        AlarmCommand._handle(_alarm(mesh["id"], 1, detector="range", channel="env.temperature"))

        self.assertEqual(len(mail.outbox), 2)

    def test_each_channel_gets_its_own_cooldown(self):
        _, mesh = self._device()

        AlarmCommand._handle(_alarm(mesh["id"], 1, detector="flat_value", channel="env.temperature"))
        AlarmCommand._handle(_alarm(mesh["id"], 1, detector="flat_value", channel="env.humidity"))

        self.assertEqual(len(mail.outbox), 2)

    def test_alarm_for_an_unknown_device_is_skipped(self):
        _, mesh = self._device()

        AlarmCommand._handle(_alarm(mesh["id"], 999))

        self.assertEqual(len(mail.outbox), 0)

    def test_legacy_alarm_without_mesh_id_is_skipped(self):
        AlarmCommand._handle({"node_id": 1, "field": "x", "detector": "stuck_value"})

        self.assertEqual(len(mail.outbox), 0)

    def test_unverified_owner_is_not_emailed(self):
        _, mesh = self._device()
        unverified = self.client.post(
            "/owners",
            {"name": "Unverified", "email": "unverified@example.com", "password": self.DEFAULT_PASSWORD},
            format="json",
        ).json()
        mesh_row = Mesh.objects.get(pk=uuid.UUID(mesh["id"]))
        mesh_row.owner = Owner.objects.get(pk=uuid.UUID(unverified["id"]))
        mesh_row.save()
        mail.outbox.clear()

        AlarmCommand._handle(_alarm(mesh["id"], 1))

        self.assertEqual(len(mail.outbox), 0)

    def test_send_failure_propagates_for_the_poll_loop_to_catch(self):
        # A broken SMTP server must not kill the consumer
        _, mesh = self._device()

        with patch(
            "registry.management.commands.consume_quality_alarms.send_templated_email",
            side_effect=RuntimeError("smtp down"),
        ):
            with self.assertRaises(RuntimeError):
                AlarmCommand._handle(_alarm(mesh["id"], 1))
