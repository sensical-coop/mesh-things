from unittest.mock import patch

from django.core.cache import cache
from rest_framework.test import APIClient

from registry.authentication import FAILED_AUTH_RATE_WINDOW_SECONDS, OwnerBearerAuthentication

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

    def test_counter_recreated_by_an_expiry_race_still_expires(self):
        key = "registry:failed-auth:race"

        def incr_after_expiry(cache_key):
            # What Redis INCR does to a key that expired after Django checked it exists.
            cache.set(cache_key, 1, None)
            return 1

        with patch.object(cache, "incr", side_effect=incr_after_expiry):
            OwnerBearerAuthentication()._record_failed_attempt(key)
        ttl = cache._cache.get_client(write=True).ttl(cache.make_and_validate_key(key))
        self.assertGreater(ttl, 0)
        self.assertLessEqual(ttl, FAILED_AUTH_RATE_WINDOW_SECONDS)


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
