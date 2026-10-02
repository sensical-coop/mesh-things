import re
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.utils import timezone

from registry.models import Owner
from registry.views import LOGIN_FAILED_RATE_LIMIT

from .helpers import SIGNUP_TERMS, RegistryTestCase

def _extract_token(email) -> str:
    match = re.search(r"token=(\S+)", email.body)
    assert match, email.body
    return match.group(1)


class SignupPasswordTests(RegistryTestCase):
    def test_signup_without_password_is_400(self):
        resp = self.client.post("/owners", {**SIGNUP_TERMS, "name": "Alice", "email": "login-nopass@example.com"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_signup_with_password_creates_usable_password(self):
        self.create_owner(name="Alice", email="login-signup@example.com")
        owner = Owner.objects.get(email="login-signup@example.com")
        self.assertTrue(owner.has_usable_password())

    def test_signup_rejects_a_password_too_similar_to_the_email(self):
        resp = self.client.post(
            "/owners",
            {**SIGNUP_TERMS, "name": "Alice", "email": "similar@example.com", "password": "similar@example.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("password", resp.json())

    def test_signup_rejects_a_too_short_password(self):
        resp = self.client.post(
            "/owners", {**SIGNUP_TERMS, "name": "Alice", "email": "short-pw@example.com", "password": "abc123"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)


class LoginTests(RegistryTestCase):
    def test_login_with_correct_credentials_returns_profile_and_sets_session(self):
        owner = self.create_owner(name="Alice", email="login-a@example.com")

        resp = self.client.post(
            "/owners/login",
            {"email": "login-a@example.com", "password": self.DEFAULT_PASSWORD},
            format="json",
        )

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["id"], owner["id"])
        self.assertIn("devices", resp.json())
        self.assertIn("sessionid", resp.cookies)

    def test_login_with_wrong_password_is_401(self):
        self.create_owner(name="Alice", email="login-b@example.com")

        resp = self.client.post(
            "/owners/login", {"email": "login-b@example.com", "password": "wrong-password"}, format="json"
        )

        self.assertEqual(resp.status_code, 401)

    def test_login_with_unknown_email_is_401(self):
        resp = self.client.post(
            "/owners/login", {"email": "nobody@example.com", "password": "whatever"}, format="json"
        )
        self.assertEqual(resp.status_code, 401)

    def test_login_before_verification_is_403(self):
        resp = self.client.post(
            "/owners",
            {**SIGNUP_TERMS, "name": "Bob", "email": "login-unverified@example.com", "password": self.DEFAULT_PASSWORD},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)

        login = self.client.post(
            "/owners/login",
            {"email": "login-unverified@example.com", "password": self.DEFAULT_PASSWORD},
            format="json",
        )

        self.assertEqual(login.status_code, 403)

    def test_failed_login_attempts_are_throttled_per_ip(self):
        self.create_owner(name="Alice", email="login-throttle@example.com")

        for _ in range(LOGIN_FAILED_RATE_LIMIT):
            resp = self.client.post(
                "/owners/login", {"email": "login-throttle@example.com", "password": "wrong"}, format="json"
            )
            self.assertEqual(resp.status_code, 401)

        throttled = self.client.post(
            "/owners/login", {"email": "login-throttle@example.com", "password": "wrong"}, format="json"
        )
        self.assertEqual(throttled.status_code, 429)

    def test_session_authenticates_a_gated_route_with_no_bearer_header(self):
        owner = self.create_owner(name="Alice", email="login-session@example.com")
        self.client.post(
            "/owners/login",
            {"email": "login-session@example.com", "password": self.DEFAULT_PASSWORD},
            format="json",
        )

        resp = self.client.get("/owners/me")  # no Authorization header - cookie keeps the session

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], owner["id"])

    def test_logout_clears_the_session(self):
        self.create_owner(name="Alice", email="login-logout@example.com")
        self.client.post(
            "/owners/login",
            {"email": "login-logout@example.com", "password": self.DEFAULT_PASSWORD},
            format="json",
        )

        logout = self.client.post("/owners/logout")
        self.assertEqual(logout.status_code, 200)

        resp = self.client.get("/owners/me")
        self.assertEqual(resp.status_code, 401)

    def test_logout_is_a_noop_without_a_session(self):
        resp = self.client.post("/owners/logout")
        self.assertEqual(resp.status_code, 200)

    def test_csrf_cookie_route_sets_a_cookie(self):
        resp = self.client.get("/owners/csrf-cookie")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("csrftoken", resp.cookies)


class PasswordResetTests(RegistryTestCase):
    def test_request_reset_for_unknown_email_is_generic_200_no_email_sent(self):
        resp = self.client.post(
            "/owners/request-password-reset", {"email": "nobody@example.com"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_request_reset_for_known_email_sends_one_email(self):
        self.create_owner(name="Alice", email="reset-a@example.com")
        mail.outbox.clear()  # drop the signup verification email

        resp = self.client.post(
            "/owners/request-password-reset", {"email": "reset-a@example.com"}, format="json"
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reset-password?token=", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ["reset-a@example.com"])

    def test_reset_with_valid_token_sets_a_working_password(self):
        self.create_owner(name="Alice", email="reset-b@example.com")
        mail.outbox.clear()
        self.client.post("/owners/request-password-reset", {"email": "reset-b@example.com"}, format="json")
        token = _extract_token(mail.outbox[0])

        resp = self.client.post(
            "/owners/reset-password",
            {"new_password": "N3w-Str0ng-Password!"},
            format="json",
            **self.auth_headers(token),
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        login = self.client.post(
            "/owners/login", {"email": "reset-b@example.com", "password": "N3w-Str0ng-Password!"}, format="json"
        )
        self.assertEqual(login.status_code, 200)

    def test_reset_token_is_single_use(self):
        self.create_owner(name="Alice", email="reset-c@example.com")
        mail.outbox.clear()
        self.client.post("/owners/request-password-reset", {"email": "reset-c@example.com"}, format="json")
        token = _extract_token(mail.outbox[0])
        self.client.post(
            "/owners/reset-password",
            {"new_password": "N3w-Str0ng-Password!"},
            format="json",
            **self.auth_headers(token),
        )

        reused = self.client.post(
            "/owners/reset-password",
            {"new_password": "Another-Str0ng-1"},
            format="json",
            **self.auth_headers(token),
        )

        self.assertEqual(reused.status_code, 401)

    def test_reset_with_invalid_token_is_401(self):
        resp = self.client.post(
            "/owners/reset-password",
            {"new_password": "N3w-Str0ng-Password!"},
            format="json",
            **self.auth_headers("not-a-real-token"),
        )
        self.assertEqual(resp.status_code, 401)

    def test_reset_without_a_token_is_401(self):
        resp = self.client.post(
            "/owners/reset-password", {"new_password": "N3w-Str0ng-Password!"}, format="json"
        )
        self.assertEqual(resp.status_code, 401)

    def test_reset_with_expired_token_is_401(self):
        self.create_owner(name="Alice", email="reset-d@example.com")
        mail.outbox.clear()
        self.client.post("/owners/request-password-reset", {"email": "reset-d@example.com"}, format="json")
        token = _extract_token(mail.outbox[0])
        owner = Owner.objects.get(email="reset-d@example.com")
        owner.password_reset_sent_at = timezone.now() - timedelta(hours=2)
        owner.save(update_fields=["password_reset_sent_at"])

        resp = self.client.post(
            "/owners/reset-password",
            {"new_password": "N3w-Str0ng-Password!"},
            format="json",
            **self.auth_headers(token),
        )

        self.assertEqual(resp.status_code, 401)

    def test_reset_lets_an_owner_without_a_usable_password_set_one(self):
        owner_obj = Owner.objects.create_user(email="reset-legacy@example.com", name="Legacy", is_active=True)
        self.assertFalse(owner_obj.has_usable_password())

        self.client.post("/owners/request-password-reset", {"email": "reset-legacy@example.com"}, format="json")
        token = _extract_token(mail.outbox[0])
        resp = self.client.post(
            "/owners/reset-password",
            {"new_password": "N3w-Str0ng-Password!"},
            format="json",
            **self.auth_headers(token),
        )

        self.assertEqual(resp.status_code, 200)
        owner_obj.refresh_from_db()
        self.assertTrue(owner_obj.has_usable_password())

    def test_request_reset_throttled_per_ip(self):
        from registry.throttling import RequestPasswordResetThrottle

        self.create_owner(name="Alice", email="reset-throttle@example.com")
        with patch.object(RequestPasswordResetThrottle, "rate", "1/min", create=True):
            first = self.client.post(
                "/owners/request-password-reset", {"email": "reset-throttle@example.com"}, format="json"
            )
            self.assertEqual(first.status_code, 200)
            second = self.client.post(
                "/owners/request-password-reset", {"email": "reset-throttle@example.com"}, format="json"
            )
            self.assertEqual(second.status_code, 429)


class ChangePasswordTests(RegistryTestCase):
    def test_change_password_requires_current_password(self):
        owner = self.create_owner(name="Alice", email="change-a@example.com")

        resp = self.client.post(
            "/owners/me/change-password",
            {"current_password": "wrong", "new_password": "N3w-Str0ng-Password!"},
            format="json",
            **self.auth_headers(owner),
        )

        self.assertEqual(resp.status_code, 400)

    def test_change_password_succeeds_and_old_password_stops_working(self):
        owner = self.create_owner(name="Alice", email="change-b@example.com")

        resp = self.client.post(
            "/owners/me/change-password",
            {"current_password": self.DEFAULT_PASSWORD, "new_password": "N3w-Str0ng-Password!"},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(resp.status_code, 200)

        old_login = self.client.post(
            "/owners/login", {"email": "change-b@example.com", "password": self.DEFAULT_PASSWORD}, format="json"
        )
        self.assertEqual(old_login.status_code, 401)

        new_login = self.client.post(
            "/owners/login",
            {"email": "change-b@example.com", "password": "N3w-Str0ng-Password!"},
            format="json",
        )
        self.assertEqual(new_login.status_code, 200)

    def test_change_password_requires_auth(self):
        resp = self.client.post(
            "/owners/me/change-password",
            {"current_password": "x", "new_password": "N3w-Str0ng-Password!"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)
