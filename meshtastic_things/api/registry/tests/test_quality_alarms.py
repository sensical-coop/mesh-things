import uuid
from unittest.mock import patch

from django.core import mail

from registry.management.commands.consume_quality_alarms import (
    ALARM_EMAIL_COOLDOWN_SECONDS,
    WINDOWS_KEY,
    Command as AlarmCommand,
    redis_client,
)
from registry.models import Device, Mesh, Owner

from .helpers import SIGNUP_TERMS, RegistryTestCase

NOW = 1_800_000_000.0


def _window(mesh, device_id=1):
    return f"{mesh['id']}:{device_id}"


def _alarm(mesh_id, device_id=1, detector="flat_value", channel="env.temperature", **overrides):
    event = {
        "mesh_id": str(mesh_id),
        "device_id": device_id,
        "channel": channel,
        "detector": detector,
        "source": "stream",
        "value": 21.0,
        "message": "Value flat at 21.0 for 12.0h (145 readings)",
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

        AlarmCommand._handle(
            _alarm(mesh["id"], 1, detector="absence", channel=None, message="No telemetry received for 900s")
        )

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

        AlarmCommand._handle(_alarm(mesh["id"], 1, detector="absence", channel=None))

        self.assertIn("may still deliver this period later", mail.outbox[0].body)

    def test_condition_email_says_it_will_not_repeat(self):
        _, mesh = self._device()

        AlarmCommand._handle(_alarm(mesh["id"], 1, detector="range"))

        self.assertIn("not get another email about this condition", mail.outbox[0].body)

    def test_completeness_email_names_the_channel(self):
        _, mesh = self._device()

        AlarmCommand._handle(
            _alarm(mesh["id"], 1, detector="completeness", channel="environment_metrics.temperature")
        )

        self.assertIn("environment_metrics.temperature", mail.outbox[0].body)
        self.assertIn("gaps", mail.outbox[0].subject)

    def test_second_alarm_is_held_for_the_summary(self):
        _, mesh = self._device()

        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW)
        AlarmCommand._handle(_alarm(mesh["id"], 1, channel="env.humidity"), now=NOW + 10)

        self.assertEqual(len(mail.outbox), 1)

    def test_replayed_alarm_is_neither_emailed_nor_held(self):
        _, mesh = self._device()

        AlarmCommand._handle(_alarm(mesh["id"], 1, detector="range", replay=True), now=NOW)

        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(redis_client().zscore(WINDOWS_KEY, _window(mesh)))

    def test_a_repeat_never_opens_a_window_or_emails(self):
        _, mesh = self._device()

        AlarmCommand._handle(_alarm(mesh["id"], 1, repeat=True), now=NOW)

        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(redis_client().zscore(WINDOWS_KEY, _window(mesh)))

    def test_a_repeat_is_counted_in_an_open_window(self):
        _, mesh = self._device()
        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW)
        AlarmCommand._handle(_alarm(mesh["id"], 1, repeat=True, message="still flat"), now=NOW + 10)

        AlarmCommand.flush_due_windows(now=NOW + ALARM_EMAIL_COOLDOWN_SECONDS)

        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Latest: still flat", mail.outbox[1].body)

    def test_a_repeat_is_not_emailed_even_without_a_cooldown(self):
        owner, mesh = self._device()
        Owner.objects.filter(pk=owner["id"]).update(alarm_email_cooldown_seconds=0)

        AlarmCommand._handle(_alarm(mesh["id"], 1, repeat=True), now=NOW)

        self.assertEqual(len(mail.outbox), 0)

    def test_hourly_repeats_of_one_condition_email_once(self):
        _, mesh = self._device()
        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW)
        for hour in range(1, 25):
            now = NOW + hour * ALARM_EMAIL_COOLDOWN_SECONDS + 1
            AlarmCommand.flush_due_windows(now=now)
            AlarmCommand._handle(_alarm(mesh["id"], 1, repeat=True), now=now)

        self.assertEqual(len(mail.outbox), 1)

    def test_absence_is_emailed_at_most_once_a_day_per_device(self):
        _, mesh = self._device()
        absence = _alarm(mesh["id"], 1, detector="absence", channel=None)

        AlarmCommand._handle(absence, now=NOW)
        AlarmCommand.flush_due_windows(now=NOW + ALARM_EMAIL_COOLDOWN_SECONDS)
        AlarmCommand._handle(absence, now=NOW + 3 * 3600)
        AlarmCommand.flush_due_windows(now=NOW + 5 * 3600)
        AlarmCommand._handle(absence, now=NOW + 25 * 3600)

        self.assertEqual(len(mail.outbox), 2)
        self.assertNotIn("Alarm summary", mail.outbox[1].subject)

    def test_a_second_absence_the_same_day_is_counted_in_an_open_window(self):
        _, mesh = self._device()
        AlarmCommand._handle(_alarm(mesh["id"], 1, detector="absence", channel=None), now=NOW)
        AlarmCommand._handle(_alarm(mesh["id"], 1, detector="absence", channel=None), now=NOW + 60)

        AlarmCommand.flush_due_windows(now=NOW + ALARM_EMAIL_COOLDOWN_SECONDS)

        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Alarm summary", mail.outbox[1].subject)

    def test_absence_is_emailed_straight_away_during_an_open_window(self):
        _, mesh = self._device()
        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW)

        AlarmCommand._handle(_alarm(mesh["id"], 1, detector="absence", channel=None), now=NOW + 10)

        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("stopped publishing", mail.outbox[1].subject)
        self.assertEqual(redis_client().zscore(WINDOWS_KEY, _window(mesh)), NOW + ALARM_EMAIL_COOLDOWN_SECONDS)

    def test_owner_can_disable_the_cooldown(self):
        # alarm_email_cooldown_seconds=0 means "email on every alarm".
        owner, mesh = self._device()
        Owner.objects.filter(pk=owner["id"]).update(alarm_email_cooldown_seconds=0)

        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW)
        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW + 10)
        AlarmCommand.flush_due_windows(now=NOW + 10**6)

        self.assertEqual(len(mail.outbox), 2)
        self.assertIsNone(redis_client().zscore(WINDOWS_KEY, _window(mesh)))

    def test_owner_cooldown_overrides_the_server_default(self):
        owner, mesh = self._device()
        Owner.objects.filter(pk=owner["id"]).update(alarm_email_cooldown_seconds=30)

        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW)

        self.assertEqual(redis_client().zscore(WINDOWS_KEY, _window(mesh)), NOW + 30)

    def test_owner_without_a_cooldown_set_uses_the_server_default(self):
        owner, mesh = self._device()
        self.assertIsNone(Owner.objects.get(pk=owner["id"]).alarm_email_cooldown_seconds)

        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW)

        self.assertEqual(
            redis_client().zscore(WINDOWS_KEY, _window(mesh)), NOW + ALARM_EMAIL_COOLDOWN_SECONDS
        )

    def test_other_detectors_and_channels_are_held_in_the_same_window(self):
        _, mesh = self._device()

        AlarmCommand._handle(_alarm(mesh["id"], 1, detector="flat_value", channel="env.temperature"), now=NOW)
        AlarmCommand._handle(_alarm(mesh["id"], 1, detector="flat_value", channel="env.humidity"), now=NOW + 1)
        AlarmCommand._handle(_alarm(mesh["id"], 1, detector="range"), now=NOW + 2)

        self.assertEqual(len(mail.outbox), 1)

    def test_each_device_gets_its_own_window(self):
        owner, mesh = self._device()
        self.create_node(owner, mesh, device_id=2, label="shed")
        mail.outbox.clear()

        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW)
        AlarmCommand._handle(_alarm(mesh["id"], 2), now=NOW + 1)

        self.assertEqual(len(mail.outbox), 2)

    def test_summary_is_sent_when_the_window_closes(self):
        _, mesh = self._device()
        AlarmCommand._handle(_alarm(mesh["id"], 1, detector="flat_value", channel="env.temperature"), now=NOW)
        for i in range(3):
            AlarmCommand._handle(
                _alarm(
                    mesh["id"], 1, detector="flat_value", channel="env.temperature",
                    triggered_at=f"2026-09-06T12:0{i + 1}:00+00:00", message=f"flat #{i}",
                ),
                now=NOW + 60 * (i + 1),
            )
        AlarmCommand._handle(
            _alarm(mesh["id"], 1, detector="range", triggered_at="2026-09-06T12:30:00+00:00"),
            now=NOW + 1800,
        )

        AlarmCommand.flush_due_windows(now=NOW + ALARM_EMAIL_COOLDOWN_SECONDS - 1)
        self.assertEqual(len(mail.outbox), 1)

        AlarmCommand.flush_due_windows(now=NOW + ALARM_EMAIL_COOLDOWN_SECONDS)

        self.assertEqual(len(mail.outbox), 2)
        summary = mail.outbox[1]
        self.assertIn("Alarm summary", summary.subject)
        self.assertIn("greenhouse", summary.subject)
        self.assertIn("4 more time(s)", summary.body)
        self.assertIn("flat_value), env.temperature", summary.body)
        self.assertIn("3 time(s), first 2026-09-06T12:01:00+00:00, last 2026-09-06T12:03:00+00:00", summary.body)
        self.assertIn("Latest: flat #2", summary.body)
        self.assertIn("(range)", summary.body)
        self.assertIn("1 time(s)", summary.body)

    def test_no_summary_when_nothing_was_held(self):
        _, mesh = self._device()
        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW)

        AlarmCommand.flush_due_windows(now=NOW + ALARM_EMAIL_COOLDOWN_SECONDS)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIsNone(redis_client().zscore(WINDOWS_KEY, _window(mesh)))

    def test_alarm_after_the_summary_opens_a_new_window(self):
        _, mesh = self._device()
        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW)
        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW + 10)
        AlarmCommand.flush_due_windows(now=NOW + ALARM_EMAIL_COOLDOWN_SECONDS)

        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW + ALARM_EMAIL_COOLDOWN_SECONDS + 5)
        AlarmCommand.flush_due_windows(now=NOW + 2 * ALARM_EMAIL_COOLDOWN_SECONDS + 5)

        self.assertEqual(len(mail.outbox), 3)
        self.assertNotIn("Alarm summary", mail.outbox[2].subject)

    def test_alarm_after_an_unflushed_window_sends_its_summary_first(self):
        # The tick runs every few seconds, so an alarm can land on an ended window.
        _, mesh = self._device()
        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW)
        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW + 10)

        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW + ALARM_EMAIL_COOLDOWN_SECONDS + 1)

        self.assertEqual(len(mail.outbox), 3)
        self.assertIn("Alarm summary", mail.outbox[1].subject)
        self.assertIn("1 more time(s)", mail.outbox[1].body)
        self.assertNotIn("Alarm summary", mail.outbox[2].subject)

    def test_summary_for_a_deleted_device_is_dropped(self):
        _, mesh = self._device()
        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW)
        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW + 10)
        Device.objects.filter(mesh_id=mesh["id"], device_id=1).delete()

        AlarmCommand.flush_due_windows(now=NOW + ALARM_EMAIL_COOLDOWN_SECONDS)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIsNone(redis_client().zscore(WINDOWS_KEY, _window(mesh)))

    def test_failed_summary_is_retried_on_the_next_tick(self):
        _, mesh = self._device()
        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW)
        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW + 10)

        with patch(
            "registry.management.commands.consume_quality_alarms.send_templated_email",
            side_effect=RuntimeError("smtp down"),
        ):
            AlarmCommand.flush_due_windows(now=NOW + ALARM_EMAIL_COOLDOWN_SECONDS)
        AlarmCommand.flush_due_windows(now=NOW + ALARM_EMAIL_COOLDOWN_SECONDS + 10)

        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Alarm summary", mail.outbox[1].subject)

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
            {**SIGNUP_TERMS, "name": "Unverified", "email": "unverified@example.com", "password": self.DEFAULT_PASSWORD},
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

    def test_failed_first_email_does_not_open_a_window(self):
        # Otherwise the next alarms would be held with no email ever sent.
        _, mesh = self._device()

        with patch(
            "registry.management.commands.consume_quality_alarms.send_templated_email",
            side_effect=RuntimeError("smtp down"),
        ):
            with self.assertRaises(RuntimeError):
                AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW)
        AlarmCommand._handle(_alarm(mesh["id"], 1), now=NOW + 10)

        self.assertEqual(len(mail.outbox), 1)
