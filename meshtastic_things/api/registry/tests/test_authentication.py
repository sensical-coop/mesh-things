from unittest.mock import patch

from registry.tests.helpers import RegistryTestCase


class FailedAuthGuardTests(RegistryTestCase):
    def test_invalid_tokens_capped_per_source_ip(self):
        with patch("registry.authentication.FAILED_AUTH_RATE_LIMIT", 2):
            for i in range(2):
                resp = self.client.get("/owners/me", HTTP_AUTHORIZATION=f"Bearer bad-token-{i}")
                self.assertEqual(resp.status_code, 401)
            resp = self.client.get("/owners/me", HTTP_AUTHORIZATION="Bearer one-too-many")
            self.assertEqual(resp.status_code, 429)

    def test_valid_requests_not_counted_against_failed_auth_guard(self):
        owner = self.create_owner()
        with patch("registry.authentication.FAILED_AUTH_RATE_LIMIT", 1):
            for _ in range(5):
                resp = self.client.get("/owners/me", **self.auth_headers(owner))
                self.assertEqual(resp.status_code, 200)

    def test_missing_token_not_counted_against_failed_auth_guard(self):
        with patch("registry.authentication.FAILED_AUTH_RATE_LIMIT", 1):
            for _ in range(5):
                resp = self.client.get("/owners/me")
                self.assertEqual(resp.status_code, 401)
