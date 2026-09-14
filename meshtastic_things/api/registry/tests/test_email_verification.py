import re
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.utils import timezone

from registry.models import Owner
from registry.throttling import ResendVerificationThrottle

from .helpers import RegistryTestCase


def _extract_token(email) -> str:
    match = re.search(r"token=(\S+)", email.body)
    assert match, email.body
    return match.group(1)


class SignupVerificationTests(RegistryTestCase):
    def test_signup_creates_unverified_owner_and_sends_one_email(self):
        resp = self.client.post("/owners", {"name": "Alice", "email": "verify-a@example.com", "password": "Correct-Horse-Battery-42"}, format="json")

        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertFalse(body["is_active"])
        self.assertIsNone(body["email_verified_at"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("verify-email?token=", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ["verify-a@example.com"])

    def test_signup_email_send_failure_does_not_roll_back_account_creation(self):
        with patch("registry.views.send_verification_email", side_effect=RuntimeError("smtp down")):
            resp = self.client.post("/owners", {"name": "Bob", "email": "verify-b@example.com", "password": "Correct-Horse-Battery-42"}, format="json")

        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(Owner.objects.filter(email="verify-b@example.com").exists())
        owner = Owner.objects.get(email="verify-b@example.com")
        self.assertFalse(owner.is_active)


class VerifyEmailTests(RegistryTestCase):
    def test_verify_with_valid_token_activates_owner(self):
        self.client.post("/owners", {"name": "Carol", "email": "verify-c@example.com", "password": "Correct-Horse-Battery-42"}, format="json")
        token = _extract_token(mail.outbox[0])

        resp = self.client.get(f"/owners/verify-email?token={token}")

        self.assertEqual(resp.status_code, 200)
        owner = Owner.objects.get(email="verify-c@example.com")
        self.assertTrue(owner.is_active)
        self.assertIsNotNone(owner.email_verified_at)

    def test_verified_owner_gains_access_to_gated_route(self):
        resp = self.client.post("/owners", {"name": "Dave", "email": "verify-d@example.com", "password": "Correct-Horse-Battery-42"}, format="json")
        owner = resp.json()
        token = _extract_token(mail.outbox[0])

        blocked = self.client.post(
            "/meshes", {"channel_id": "X", "psk_b64": "AAAA"}, format="json", **self.auth_headers(owner)
        )
        self.assertEqual(blocked.status_code, 403)

        self.client.get(f"/owners/verify-email?token={token}")

        allowed = self.client.post(
            "/meshes", {"channel_id": "X", "psk_b64": "AAAA"}, format="json", **self.auth_headers(owner)
        )
        self.assertEqual(allowed.status_code, 201, allowed.content)

    def test_unverified_owner_blocked_with_403_on_gated_routes(self):
        resp = self.client.post("/owners", {"name": "Eve", "email": "verify-e@example.com", "password": "Correct-Horse-Battery-42"}, format="json")
        owner = resp.json()

        self.assertEqual(
            self.client.post(
                "/devices",
                {"device_id": 1, "mesh_id": "00000000-0000-0000-0000-000000000000", "is_gateway": False},
                format="json",
                **self.auth_headers(owner),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/owners/me/devices", **self.auth_headers(owner)).status_code, 403
        )
        self.assertEqual(
            self.client.post("/owners/me/rotate-key", **self.auth_headers(owner)).status_code, 403
        )

    def test_exempted_routes_stay_reachable_while_unverified(self):
        resp = self.client.post("/owners", {"name": "Frank", "email": "verify-f@example.com", "password": "Correct-Horse-Battery-42"}, format="json")
        owner = resp.json()

        self.assertEqual(self.client.get("/owners/me", **self.auth_headers(owner)).status_code, 200)
        self.assertEqual(
            self.client.put("/owners/me", {"name": "Frank2"}, format="json", **self.auth_headers(owner)).status_code,
            200,
        )
        self.assertEqual(
            self.client.post("/owners/me/resend-verification", **self.auth_headers(owner)).status_code, 200
        )
        self.assertEqual(self.client.delete("/owners/me", **self.auth_headers(owner)).status_code, 204)

    def test_public_and_anon_routes_unaffected(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/owners").status_code, 200)
        resp = self.client.post("/owners", {"name": "Grace", "email": "verify-g@example.com", "password": "Correct-Horse-Battery-42"}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(self.client.get(f"/owners/{resp.json()['id']}").status_code, 200)

    def test_reverifying_already_verified_link_is_idempotent(self):
        self.client.post("/owners", {"name": "Hank", "email": "verify-h@example.com", "password": "Correct-Horse-Battery-42"}, format="json")
        token = _extract_token(mail.outbox[0])
        self.client.get(f"/owners/verify-email?token={token}")

        resp = self.client.get(f"/owners/verify-email?token={token}")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["detail"], "Email already verified")

    def test_invalid_token_returns_400_with_detail_shape(self):
        resp = self.client.get("/owners/verify-email?token=not-a-real-token")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.json())
        self.assertIsInstance(resp.json()["detail"], str)

    def test_missing_token_returns_400(self):
        resp = self.client.get("/owners/verify-email")
        self.assertEqual(resp.status_code, 400)

    def test_expired_token_returns_400(self):
        self.client.post("/owners", {"name": "Ivy", "email": "verify-i@example.com", "password": "Correct-Horse-Battery-42"}, format="json")
        token = _extract_token(mail.outbox[0])
        owner = Owner.objects.get(email="verify-i@example.com")
        owner.email_verification_sent_at = timezone.now() - timedelta(hours=25)
        owner.save(update_fields=["email_verification_sent_at"])

        resp = self.client.get(f"/owners/verify-email?token={token}")

        self.assertEqual(resp.status_code, 400)


class ResendVerificationTests(RegistryTestCase):
    def test_resend_issues_fresh_token_invalidating_old_one(self):
        resp = self.client.post("/owners", {"name": "Jack", "email": "verify-j@example.com", "password": "Correct-Horse-Battery-42"}, format="json")
        owner = resp.json()
        old_token = _extract_token(mail.outbox[0])

        resend = self.client.post("/owners/me/resend-verification", **self.auth_headers(owner))
        self.assertEqual(resend.status_code, 200)
        self.assertEqual(len(mail.outbox), 2)
        new_token = _extract_token(mail.outbox[1])

        self.assertEqual(self.client.get(f"/owners/verify-email?token={old_token}").status_code, 400)
        self.assertEqual(self.client.get(f"/owners/verify-email?token={new_token}").status_code, 200)

    def test_resend_is_noop_once_verified(self):
        resp = self.client.post("/owners", {"name": "Kim", "email": "verify-k@example.com", "password": "Correct-Horse-Battery-42"}, format="json")
        owner = resp.json()
        token = _extract_token(mail.outbox[0])
        self.client.get(f"/owners/verify-email?token={token}")

        resend = self.client.post("/owners/me/resend-verification", **self.auth_headers(owner))

        self.assertEqual(resend.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_requires_auth_but_not_verification(self):
        resp = self.client.post("/owners", {"name": "Liam", "email": "verify-l@example.com", "password": "Correct-Horse-Battery-42"}, format="json")
        owner = resp.json()

        self.assertEqual(self.client.post("/owners/me/resend-verification").status_code, 401)
        self.assertEqual(
            self.client.post("/owners/me/resend-verification", **self.auth_headers(owner)).status_code, 200
        )

    def test_resend_send_failure_returns_502(self):
        resp = self.client.post("/owners", {"name": "Mona", "email": "verify-m@example.com", "password": "Correct-Horse-Battery-42"}, format="json")
        owner = resp.json()

        with patch("registry.views.send_verification_email", side_effect=RuntimeError("smtp down")):
            resend = self.client.post("/owners/me/resend-verification", **self.auth_headers(owner))

        self.assertEqual(resend.status_code, 502)

    def test_resend_throttled_after_limit(self):
        resp = self.client.post("/owners", {"name": "Nina", "email": "verify-n@example.com", "password": "Correct-Horse-Battery-42"}, format="json")
        owner = resp.json()

        with patch.object(ResendVerificationThrottle, "rate", "2/hour", create=True):
            for _ in range(2):
                r = self.client.post("/owners/me/resend-verification", **self.auth_headers(owner))
                self.assertEqual(r.status_code, 200)
            throttled = self.client.post("/owners/me/resend-verification", **self.auth_headers(owner))
            self.assertEqual(throttled.status_code, 429)


class EmailChangeResetsVerificationTests(RegistryTestCase):
    def test_changing_email_resets_verification_and_sends_new_email(self):
        owner = self.create_owner(email="verify-o-old@example.com")
        mail.outbox.clear()  # create_owner() already sent the initial signup email

        resp = self.client.put(
            "/owners/me", {"email": "verify-o-new@example.com"}, format="json", **self.auth_headers(owner)
        )

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["is_active"])
        self.assertIsNone(resp.json()["email_verified_at"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("verify-o-new@example.com", mail.outbox[0].to)

        blocked = self.client.post(
            "/meshes", {"channel_id": "X", "psk_b64": "AAAA"}, format="json", **self.auth_headers(owner)
        )
        self.assertEqual(blocked.status_code, 403)

    def test_changing_only_name_does_not_reset_verification(self):
        owner = self.create_owner(email="verify-p@example.com")
        mail.outbox.clear()  # create_owner() already sent the initial signup email

        resp = self.client.put("/owners/me", {"name": "New Name"}, format="json", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["is_active"])
        self.assertEqual(len(mail.outbox), 0)


class SerializerShapeTests(RegistryTestCase):
    def test_owner_read_serializer_includes_verification_fields(self):
        owner = self.create_owner(email="verify-q@example.com")

        resp = self.client.get("/owners/me", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 200)
        self.assertIn("is_active", resp.json())
        self.assertIn("email_verified_at", resp.json())

    def test_public_serializers_do_not_leak_verification_status(self):
        owner = self.create_owner(email="verify-r@example.com")

        list_resp = self.client.get("/owners")
        detail_resp = self.client.get(f"/owners/{owner['id']}")

        for body in (list_resp.json()[0], detail_resp.json()):
            self.assertNotIn("is_active", body)
            self.assertNotIn("email_verified_at", body)


class CreateOwnerHelperTests(RegistryTestCase):
    def test_create_owner_helper_is_immediately_usable(self):
        owner = self.create_owner()

        resp = self.client.post(
            "/meshes", {"channel_id": "X", "psk_b64": "AAAA"}, format="json", **self.auth_headers(owner)
        )

        self.assertEqual(resp.status_code, 201, resp.content)
