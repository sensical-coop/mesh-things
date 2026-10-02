from unittest.mock import patch

from registry.throttling import AnonReadThrottle, OwnerRateThrottle, SignupThrottle
from registry.tests.helpers import RegistryTestCase
from .helpers import SIGNUP_TERMS


class SignupThrottleTests(RegistryTestCase):
    def test_signup_throttled_after_limit(self):
        with patch.object(SignupThrottle, "rate", "2/min", create=True):
            for i in range(2):
                resp = self.client.post(
                    "/owners",
                    {**SIGNUP_TERMS, "name": f"O{i}", "email": f"o{i}@example.com", "password": self.DEFAULT_PASSWORD},
                    format="json",
                )
                self.assertEqual(resp.status_code, 201, resp.content)
            resp = self.client.post(
                "/owners",
                {**SIGNUP_TERMS, "name": "Too Many", "email": "toomany@example.com", "password": self.DEFAULT_PASSWORD},
                format="json",
            )
            self.assertEqual(resp.status_code, 429)

    def test_get_owners_not_counted_against_signup_throttle(self):
        with patch.object(SignupThrottle, "rate", "1/min", create=True):
            self.create_owner()
            resp = self.client.get("/owners")
            self.assertEqual(resp.status_code, 200)


class AnonReadThrottleTests(RegistryTestCase):
    def test_get_owners_throttled_after_limit(self):
        with patch.object(AnonReadThrottle, "rate", "2/min", create=True):
            for _ in range(2):
                resp = self.client.get("/owners")
                self.assertEqual(resp.status_code, 200)
            resp = self.client.get("/owners")
            self.assertEqual(resp.status_code, 429)

    def test_authenticated_requests_not_counted_against_anon_throttle(self):
        owner = self.create_owner()
        with patch.object(AnonReadThrottle, "rate", "1/min", create=True):
            resp = self.client.get("/owners")
            self.assertEqual(resp.status_code, 200)
            resp = self.client.get("/owners/me", **self.auth_headers(owner))
            self.assertEqual(resp.status_code, 200)


class OwnerRateThrottleTests(RegistryTestCase):
    def test_owner_throttled_after_limit(self):
        owner = self.create_owner()
        with patch.object(OwnerRateThrottle, "rate", "2/min", create=True):
            for _ in range(2):
                resp = self.client.get("/owners/me", **self.auth_headers(owner))
                self.assertEqual(resp.status_code, 200)
            resp = self.client.get("/owners/me", **self.auth_headers(owner))
            self.assertEqual(resp.status_code, 429)

    def test_different_owners_have_independent_budgets(self):
        owner_a = self.create_owner(email="a@example.com")
        owner_b = self.create_owner(email="b@example.com")
        with patch.object(OwnerRateThrottle, "rate", "1/min", create=True):
            resp_a = self.client.get("/owners/me", **self.auth_headers(owner_a))
            self.assertEqual(resp_a.status_code, 200)
            resp_b = self.client.get("/owners/me", **self.auth_headers(owner_b))
            self.assertEqual(resp_b.status_code, 200)


class HealthViewThrottleTests(RegistryTestCase):
    def test_health_never_throttled(self):
        with patch.object(AnonReadThrottle, "rate", "1/min", create=True):
            for _ in range(5):
                resp = self.client.get("/health")
                self.assertEqual(resp.status_code, 200)
