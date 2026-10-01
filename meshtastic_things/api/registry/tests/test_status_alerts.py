from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.core import mail
from django.test import override_settings
from django.utils import timezone

from registry import status_alerts
from registry.models import Owner, Sink, Source

from .helpers import RegistryTestCase

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=dt_timezone.utc)


@override_settings(SOURCE_ALERT_HOURS=2, SINK_ALERT_HOURS=24)
class StatusAlertTestCase(RegistryTestCase):
    def setUp(self):
        super().setUp()
        env = patch.dict("os.environ", {"REGISTRY__EMQX_API_URL": "https://emqx.example.org/api/v5"})
        env.start()
        self.addCleanup(env.stop)
        self.operator = self.create_owner(name="Operator", email="alerts-op@example.com")
        self.promote_to_operator(self.operator)
        self.opt_in(True)
        mail.outbox.clear()

    def opt_in(self, enabled: bool) -> None:
        resp = self.client.put(
            "/owners/me", {"status_alerts_enabled": enabled}, format="json", **self.auth_headers(self.operator)
        )
        self.assertEqual(resp.status_code, 200, resp.content)


class OptInTests(StatusAlertTestCase):
    def test_alerts_are_off_by_default(self):
        other = self.create_owner(name="Other", email="alerts-other@example.com")

        self.assertFalse(self.client.get("/owners/me", **self.auth_headers(other)).json()["status_alerts_enabled"])
        self.assertTrue(Owner.objects.get(pk=self.operator["id"]).status_alerts_enabled)

    def test_an_operator_who_did_not_opt_in_is_not_emailed(self):
        self.opt_in(False)
        source = self.create_source(self.operator)
        self.create_sink(self.operator, mesh_ids=[self.create_mesh(self.operator)["id"]])
        self.fake_emqx.source_statuses.return_value = {source["id"]: "disconnected"}
        status_alerts.check_sources(NOW)
        status_alerts.check_sinks(NOW)

        self.assertEqual(status_alerts.check_sources(NOW + timedelta(hours=24)), 0)
        self.assertEqual(status_alerts.check_sinks(NOW + timedelta(hours=24)), 0)
        self.assertEqual(mail.outbox, [])


class SourceAlertTests(StatusAlertTestCase):
    def setUp(self):
        super().setUp()
        self.source = self.create_source(self.operator)
        self.fake_emqx.source_statuses.return_value = {self.source["id"]: "disconnected"}

    def test_a_source_down_for_the_alert_hours_emails_its_operator_once(self):
        self.assertEqual(status_alerts.check_sources(NOW), 0)
        self.assertEqual(status_alerts.check_sources(NOW + timedelta(hours=1)), 0)

        self.assertEqual(status_alerts.check_sources(NOW + timedelta(hours=2)), 1)
        self.assertEqual(status_alerts.check_sources(NOW + timedelta(hours=3)), 0)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["alerts-op@example.com"])
        self.assertIn("2026-10-01 12:00 UTC", mail.outbox[0].body)
        self.assertIn("disconnected", mail.outbox[0].body)

    def test_reconnecting_starts_a_new_outage(self):
        status_alerts.check_sources(NOW)
        status_alerts.check_sources(NOW + timedelta(hours=2))
        self.fake_emqx.source_statuses.return_value = {self.source["id"]: "connected"}
        status_alerts.check_sources(NOW + timedelta(hours=3))
        self.fake_emqx.source_statuses.return_value = {self.source["id"]: "disconnected"}

        self.assertEqual(status_alerts.check_sources(NOW + timedelta(hours=4)), 0)
        self.assertEqual(status_alerts.check_sources(NOW + timedelta(hours=6)), 1)
        self.assertEqual(len(mail.outbox), 2)

    def test_a_bridge_missing_from_the_broker_counts_as_down(self):
        self.fake_emqx.source_statuses.return_value = {}
        status_alerts.check_sources(NOW)

        self.assertEqual(status_alerts.check_sources(NOW + timedelta(hours=2)), 1)
        self.assertIn("missing", mail.outbox[0].body)

    def test_a_paused_source_is_not_reported(self):
        Source.objects.filter(pk=self.source["id"]).update(paused_at=timezone.now())
        status_alerts.check_sources(NOW)

        self.assertEqual(status_alerts.check_sources(NOW + timedelta(hours=2)), 0)

    def test_a_failed_email_is_retried_next_pass(self):
        status_alerts.check_sources(NOW)
        with patch.object(status_alerts, "send_source_disconnected_email", side_effect=RuntimeError("smtp down")):
            self.assertEqual(status_alerts.check_sources(NOW + timedelta(hours=2)), 0)

        self.assertEqual(status_alerts.check_sources(NOW + timedelta(hours=3)), 1)

    @override_settings(SOURCE_ALERT_HOURS=0)
    def test_zero_turns_it_off(self):
        self.assertEqual(status_alerts.check_sources(NOW), 0)
        self.fake_emqx.source_statuses.assert_not_called()

    def test_an_unreachable_broker_skips_the_check(self):
        self.fake_emqx.source_statuses.side_effect = RuntimeError("emqx down")

        self.assertEqual(status_alerts.check_sources(NOW), 0)


class SinkAlertTests(StatusAlertTestCase):
    def setUp(self):
        super().setUp()
        mesh = self.create_mesh(self.operator)
        self.sink = self.create_sink(self.operator, mesh_ids=[mesh["id"]])
        self.fake_emqx.sink_connections.return_value = {}

    def test_a_sink_in_use_with_nobody_connected_emails_its_operator_once(self):
        status_alerts.check_sinks(NOW)
        self.assertEqual(status_alerts.check_sinks(NOW + timedelta(hours=23)), 0)

        self.assertEqual(status_alerts.check_sinks(NOW + timedelta(hours=24)), 1)
        self.assertEqual(status_alerts.check_sinks(NOW + timedelta(hours=25)), 0)
        self.assertEqual(mail.outbox[0].to, ["alerts-op@example.com"])

    def test_a_connected_consumer_clears_it(self):
        status_alerts.check_sinks(NOW)
        self.fake_emqx.sink_connections.return_value = {self.sink["id"]: 1}
        status_alerts.check_sinks(NOW + timedelta(hours=12))
        self.fake_emqx.sink_connections.return_value = {}
        status_alerts.check_sinks(NOW + timedelta(hours=13))

        self.assertEqual(status_alerts.check_sinks(NOW + timedelta(hours=24)), 0)
        self.assertEqual(status_alerts.check_sinks(NOW + timedelta(hours=37)), 1)

    def test_a_sink_with_nothing_attached_is_not_reported(self):
        self.create_sink(self.operator)
        status_alerts.check_sinks(NOW)

        self.assertEqual(status_alerts.check_sinks(NOW + timedelta(hours=24)), 1)

    def test_a_paused_sink_is_not_reported(self):
        Sink.objects.filter(pk=self.sink["id"]).update(paused_at=timezone.now())
        status_alerts.check_sinks(NOW)

        self.assertEqual(status_alerts.check_sinks(NOW + timedelta(hours=24)), 0)

    @override_settings(SINK_ALERT_HOURS=0)
    def test_zero_turns_it_off(self):
        self.fake_emqx.sink_connections.reset_mock()

        self.assertEqual(status_alerts.check_sinks(NOW), 0)
        self.fake_emqx.sink_connections.assert_not_called()
