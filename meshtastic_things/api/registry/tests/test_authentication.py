from unittest.mock import patch

from rest_framework.test import APIClient

from registry.tests.helpers import SIGNUP_TERMS, RegistryTestCase


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

    def test_invalid_tokens_from_one_client_do_not_throttle_another_behind_the_proxy(self):
        owner = self.create_owner()
        with patch("registry.authentication.FAILED_AUTH_RATE_LIMIT", 1):
            self.client.get("/owners/me", HTTP_AUTHORIZATION="Bearer bad-token", HTTP_X_FORWARDED_FOR="203.0.113.1")
            resp = self.client.get("/owners/me", HTTP_X_FORWARDED_FOR="203.0.113.2", **self.auth_headers(owner))
        self.assertEqual(resp.status_code, 200)


class OwnerSessionAuthenticationTests(RegistryTestCase):
    def test_unverified_session_writes_still_need_the_csrf_token(self):
        client = APIClient(enforce_csrf_checks=True)
        client.post(
            "/owners",
            {**SIGNUP_TERMS, "name": "Uma", "email": "session-csrf@example.com", "password": self.DEFAULT_PASSWORD},
            format="json",
        )

        without_token = client.post("/owners/me/resend-verification")
        client.get("/owners/csrf-cookie")
        with_token = client.post(
            "/owners/me/resend-verification", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value
        )

        self.assertEqual(without_token.status_code, 403)
        self.assertEqual(with_token.status_code, 200)
