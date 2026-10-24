"""Every email's outcome is recorded, and superusers can read whether sending works."""
from smtplib import SMTPServerDisconnected
from unittest.mock import patch

from django.core import mail

from registry import email_health
from registry.emailing import send_templated_email

from .helpers import RegistryTestCase


class EmailStatusTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.create_owner(name="Admin", email="email-status-admin@example.com")
        self.promote_to_superuser(self.admin)
        mail.outbox.clear()
        # Signing the admin up sent a verification email; start the record empty.
        email_health._client().delete(email_health.HEALTH_KEY, email_health.SENT_KEY, email_health.FAILED_KEY)

    def status(self, owner=None, expect=200):
        resp = self.client.get("/status/email", **self.auth_headers(owner or self.admin))
        self.assertEqual(resp.status_code, expect, resp.content)
        return resp.json()

    def send(self):
        send_templated_email("someone@example.com", "Subject", "password_reset", {"name": "A", "reset_link": "x", "ttl_hours": 1})

    def test_sent_emails_are_counted(self):
        self.send()

        body = self.status()

        self.assertTrue(body["ok"])
        self.assertEqual((body["sent_24h"], body["failed_24h"]), (1, 0))
        self.assertEqual(body["last_sent_template"], "password_reset")
        self.assertIsNone(body["last_failed_at"])

    def test_a_failing_mail_server_is_reported_until_a_send_succeeds(self):
        self.send()
        with patch("registry.emailing.EmailMultiAlternatives.send", side_effect=SMTPServerDisconnected("Connection unexpectedly closed")):
            with self.assertRaises(SMTPServerDisconnected):
                self.send()

        failing = self.status()
        self.send()
        recovered = self.status()

        self.assertFalse(failing["ok"])
        self.assertEqual(failing["last_error"], "SMTPServerDisconnected: Connection unexpectedly closed")
        self.assertEqual(failing["failed_24h"], 1)
        self.assertTrue(recovered["ok"])

    def test_counts_cover_one_day(self):
        email_health.record_sent("quality_alarm", now=1_000.0)
        email_health.record_sent("quality_alarm", now=1_000.0 + email_health.WINDOW_S + 10)

        self.assertEqual(email_health.summary(now=1_000.0 + email_health.WINDOW_S + 20)["sent_24h"], 1)

    def test_only_superusers_read_it(self):
        member = self.create_owner(name="Member", email="email-status-member@example.com")

        self.status(owner=member, expect=403)
