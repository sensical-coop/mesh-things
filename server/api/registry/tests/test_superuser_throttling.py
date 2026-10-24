"""Superusers are never throttled; everyone else still is."""
from unittest.mock import patch

from registry.throttling import OwnerRateThrottle

from .helpers import RegistryTestCase

TIGHT = {**OwnerRateThrottle.THROTTLE_RATES, "owner": "2/min"}


class SuperuserThrottlingTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.member = self.create_owner(name="Member", email="throttle-member@example.com")
        self.admin = self.create_owner(name="Admin", email="throttle-admin@example.com")
        self.promote_to_superuser(self.admin)

    def statuses(self, owner, count):
        return [self.client.get("/owners/me", **self.auth_headers(owner)).status_code for _ in range(count)]

    @patch.object(OwnerRateThrottle, "THROTTLE_RATES", TIGHT)
    def test_a_superuser_is_not_rate_limited(self):
        self.assertEqual(self.statuses(self.admin, 5), [200] * 5)

    @patch.object(OwnerRateThrottle, "THROTTLE_RATES", TIGHT)
    def test_a_member_still_is(self):
        self.assertEqual(self.statuses(self.member, 3), [200, 200, 429])

    def test_a_superuser_key_passes_an_address_blocked_for_bad_keys(self):
        with patch("registry.authentication.FAILED_AUTH_RATE_LIMIT", 1):
            self.client.get("/owners/me", HTTP_AUTHORIZATION="Bearer bad-token")

            self.assertEqual(self.statuses(self.admin, 1), [200])
            self.assertEqual(self.statuses(self.member, 1), [429])
