from collections import namedtuple
from unittest.mock import patch

from django.core import mail
from django.test import override_settings

from registry.disk_alert import check_disk
from registry.models import Owner

from .helpers import RegistryTestCase

Usage = namedtuple("Usage", "total used free")
GB = 10**9


def _usage(percent_used):
    return Usage(total=100 * GB, used=percent_used * GB, free=(100 - percent_used) * GB)


class DiskAlertTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        admin = self.create_owner(name="Admin", email="disk-admin@example.com")
        self.promote_to_superuser(admin)
        self.create_owner(name="Owner", email="disk-owner@example.com")
        mail.outbox.clear()

    def _check(self, percent_used):
        with patch("registry.disk_alert.shutil.disk_usage", return_value=_usage(percent_used)):
            return check_disk()

    def test_superusers_are_emailed_over_the_limit(self):
        self.assertTrue(self._check(85))

        self.assertEqual([m.to for m in mail.outbox], [["disk-admin@example.com"]])
        self.assertIn("85% full", mail.outbox[0].subject)
        self.assertIn("15.0 GB left", mail.outbox[0].body)

    def test_nothing_is_sent_under_the_limit(self):
        self.assertFalse(self._check(79))

        self.assertEqual(mail.outbox, [])

    def test_at_most_one_email_a_day(self):
        self._check(90)
        self._check(95)

        self.assertEqual(len(mail.outbox), 1)

    def test_a_failed_email_is_retried_on_the_next_pass(self):
        with patch("registry.disk_alert.send_disk_space_email", side_effect=RuntimeError("smtp down")):
            with self.assertRaises(RuntimeError):
                self._check(90)

        self.assertTrue(self._check(90))
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(DISK_ALERT_PERCENT=0)
    def test_zero_turns_the_check_off(self):
        self.assertFalse(self._check(99))

        self.assertEqual(mail.outbox, [])

    def test_inactive_superusers_are_not_emailed(self):
        Owner.objects.filter(email="disk-admin@example.com").update(is_active=False)

        self._check(90)

        self.assertEqual(mail.outbox, [])
