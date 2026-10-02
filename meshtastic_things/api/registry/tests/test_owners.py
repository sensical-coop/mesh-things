from registry.auth import hash_api_key
from registry.models import Device

from .helpers import SIGNUP_TERMS, RegistryTestCase


class OwnerCrudTests(RegistryTestCase):
    def test_owner_creation_returns_api_key_once_and_hides_it_afterward(self):
        owner = self.create_owner(name="Alice", email="alice@example.com")
        self.assertIn("api_key", owner)
        self.assertGreater(len(owner["api_key"]), 20)

        get_resp = self.client.get(f"/owners/{owner['id']}")
        self.assertEqual(get_resp.status_code, 200)
        self.assertNotIn("api_key", get_resp.json())

        list_resp = self.client.get("/owners")
        self.assertNotIn("api_key", list_resp.json()[0])

    def test_create_owner_duplicate_email_conflict(self):
        self.create_owner(email="dup@example.com")
        resp = self.client.post("/owners", {**SIGNUP_TERMS, "name": "Bob", "email": "dup@example.com", "password": "Correct-Horse-Battery-42"}, format="json")
        self.assertEqual(resp.status_code, 409)

    def test_owner_crud(self):
        created = self.create_owner(name="Alice", email="alice2@example.com")
        self.assertEqual(created["name"], "Alice")

        list_resp = self.client.get("/owners")
        self.assertEqual(len(list_resp.json()), 1)

        get_resp = self.client.get(f"/owners/{created['id']}")
        self.assertEqual(get_resp.status_code, 200)

        missing_resp = self.client.get("/owners/00000000-0000-0000-0000-000000000000")
        self.assertEqual(missing_resp.status_code, 404)


class OwnerPublicDirectoryTests(RegistryTestCase):
    """GET /owners and GET /owners/{id} are a public"""

    def test_list_owners_omits_email(self):
        self.create_owner(name="Alice", email="alice-public@example.com")
        resp = self.client.get("/owners")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("email", resp.json()[0])
        self.assertEqual(resp.json()[0]["name"], "Alice")

    def test_get_owner_by_id_omits_email(self):
        owner = self.create_owner(name="Bob", email="bob-public@example.com")
        resp = self.client.get(f"/owners/{owner['id']}")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("email", resp.json())

    def test_own_profile_still_includes_email(self):
        owner = self.create_owner(name="Carol", email="carol-public@example.com")
        resp = self.client.get("/owners/me", **self.auth_headers(owner))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["email"], "carol-public@example.com")

    def test_public_routes_do_not_name_the_superusers(self):
        """Unauthenticated, so this would tell an attacker which account to target."""
        owner = self.create_owner(name="Dave", email="dave-public@example.com")
        self.promote_to_superuser(owner)

        self.assertNotIn("is_superuser", self.client.get("/owners").json()[0])
        self.assertNotIn("is_superuser", self.client.get(f"/owners/{owner['id']}").json())

    def test_own_profile_still_reports_superuser_status(self):
        owner = self.create_owner(name="Erin", email="erin-public@example.com")
        self.promote_to_superuser(owner)

        resp = self.client.get("/owners/me", **self.auth_headers(owner))

        self.assertTrue(resp.json()["is_superuser"])

    def test_a_plain_owner_reading_the_list_gets_the_public_shape(self):
        """The list stays one shape, so an owner's own row is not widened there."""
        owner = self.create_owner(name="Frank", email="frank-public@example.com")

        listed = self.client.get("/owners", **self.auth_headers(owner)).json()[0]

        self.assertNotIn("email", listed)
        self.assertNotIn("is_superuser", listed)

    def test_an_owner_reads_their_own_detail_in_full(self):
        owner = self.create_owner(name="Gail", email="gail-self@example.com")

        body = self.client.get(f"/owners/{owner['id']}", **self.auth_headers(owner)).json()

        self.assertEqual(body["email"], "gail-self@example.com")
        self.assertFalse(body["is_superuser"])
        self.assertTrue(body["is_active"])
        self.assertNotIn("api_key", body)

    def test_an_owner_reading_someone_elses_detail_gets_the_public_shape(self):
        owner = self.create_owner(name="Hugo", email="hugo-self@example.com")
        other = self.create_owner(name="Ivy", email="ivy-self@example.com")

        body = self.client.get(f"/owners/{other['id']}", **self.auth_headers(owner)).json()

        self.assertNotIn("email", body)
        self.assertNotIn("is_superuser", body)

    def test_anonymous_detail_is_unchanged_by_self_access(self):
        owner = self.create_owner(name="Jo", email="jo-self@example.com")

        body = self.client.get(f"/owners/{owner['id']}").json()

        self.assertEqual(sorted(body), ["created_at", "id", "name"])


class OwnerFullRecordFieldTests(RegistryTestCase):
    """The fields the full record carries beyond the public directory."""

    EXPECTED = [
        "alarm_email_cooldown_seconds",
        "created_at",
        "email",
        "email_verification_sent_at",
        "email_verified_at",
        "id",
        "is_active",
        "is_staff",
        "is_superuser",
        "last_login",
        "name",
        "role",
        "terms_accepted_version",
    ]

    def test_profile_carries_exactly_the_documented_fields(self):
        owner = self.create_owner(name="Kim", email="kim-fields@example.com")

        body = self.client.get("/owners/me", **self.auth_headers(owner)).json()

        self.assertEqual(sorted(k for k in body if k != "devices"), self.EXPECTED)

    def test_own_detail_carries_the_same_fields_as_the_profile(self):
        owner = self.create_owner(name="Lee", email="lee-fields@example.com")

        profile = self.client.get("/owners/me", **self.auth_headers(owner)).json()
        detail = self.client.get(f"/owners/{owner['id']}", **self.auth_headers(owner)).json()

        self.assertEqual(sorted(detail), sorted(k for k in profile if k != "devices"))

    def test_is_staff_is_reported_separately_from_is_superuser(self):
        """Django admin access is a distinct capability - promoting to superuser
        alone does not grant it."""
        owner = self.create_owner(name="Mo", email="mo-fields@example.com")
        self.promote_to_superuser(owner)

        body = self.client.get("/owners/me", **self.auth_headers(owner)).json()

        self.assertTrue(body["is_superuser"])
        self.assertFalse(body["is_staff"])

    def test_last_login_is_null_until_a_password_login(self):
        """A bearer-key request never updates it."""
        owner = self.create_owner(name="Nia", email="nia-fields@example.com")

        before = self.client.get("/owners/me", **self.auth_headers(owner)).json()
        self.assertIsNone(before["last_login"])

        self.client.post(
            "/owners/login",
            {"email": "nia-fields@example.com", "password": self.DEFAULT_PASSWORD},
            format="json",
        )

        after = self.client.get("/owners/me", **self.auth_headers(owner)).json()
        self.assertIsNotNone(after["last_login"])

    def test_email_verification_sent_at_is_set_at_signup(self):
        owner = self.create_owner(name="Ola", email="ola-fields@example.com")

        body = self.client.get("/owners/me", **self.auth_headers(owner)).json()

        self.assertIsNotNone(body["email_verification_sent_at"])

    def test_the_public_shape_carries_none_of_them(self):
        owner = self.create_owner(name="Pia", email="pia-fields@example.com")

        body = self.client.get(f"/owners/{owner['id']}").json()

        for field in ("email", "is_staff", "is_superuser", "last_login", "email_verification_sent_at"):
            self.assertNotIn(field, body)


class OwnerSuperuserDirectoryTests(RegistryTestCase):
    """A superuser reads the directory in full, on the same routes."""

    def setUp(self):
        super().setUp()
        self.admin = self.create_owner(name="Admin", email="admin-directory@example.com")
        self.promote_to_superuser(self.admin)

    def test_list_includes_email_and_superuser_status(self):
        self.create_owner(name="Gina", email="gina-directory@example.com")

        resp = self.client.get("/owners", **self.auth_headers(self.admin))

        self.assertEqual(resp.status_code, 200)
        by_email = {o["email"]: o for o in resp.json()}
        self.assertTrue(by_email["admin-directory@example.com"]["is_superuser"])
        self.assertFalse(by_email["gina-directory@example.com"]["is_superuser"])

    def test_detail_includes_email_and_verification_state(self):
        other = self.create_owner(name="Hank", email="hank-directory@example.com")

        resp = self.client.get(f"/owners/{other['id']}", **self.auth_headers(self.admin))

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["email"], "hank-directory@example.com")
        self.assertFalse(body["is_superuser"])
        self.assertTrue(body["is_active"])
        self.assertIsNotNone(body["email_verified_at"])

    def test_detail_of_an_unverified_owner_reports_it(self):
        resp = self.client.post(
            "/owners",
            {**SIGNUP_TERMS, "name": "Iris", "email": "iris-directory@example.com", "password": self.DEFAULT_PASSWORD},
            format="json",
        )
        unverified_id = resp.json()["id"]

        body = self.client.get(f"/owners/{unverified_id}", **self.auth_headers(self.admin)).json()

        self.assertFalse(body["is_active"])
        self.assertIsNone(body["email_verified_at"])

    def test_the_api_key_is_never_included(self):
        self.create_owner(name="Jane", email="jane-directory@example.com")

        listed = self.client.get("/owners", **self.auth_headers(self.admin)).json()

        for body in listed:
            self.assertNotIn("api_key", body)


class OwnerMeTests(RegistryTestCase):
    def test_get_own_owner_profile(self):
        owner = self.create_owner(name="Alice", email="alice3@example.com")
        resp = self.client.get("/owners/me", **self.auth_headers(owner))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], owner["id"])
        self.assertNotIn("api_key", resp.json())

    def test_get_own_owner_profile_includes_devices(self):
        """mesh_id is included alongside device_id since device_id alone isn't
        globally unique"""
        owner = self.create_owner(name="Alice", email="alice-device-ids@example.com")
        mesh = self.create_mesh(owner)
        self.create_gateway(owner, mesh, device_id=7, label="office gateway")

        resp = self.client.get("/owners/me", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 200)
        devices = resp.json()["devices"]
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["mesh_id"], mesh["id"])
        self.assertEqual(devices[0]["node_id"], 7)
        self.assertEqual(devices[0]["label"], "office gateway")
        self.assertEqual(devices[0]["is_gateway"], True)
        self.assertEqual(devices[0]["admin_keys_b64"], [])  # the caller owns this device

    def test_get_own_owner_requires_auth(self):
        resp = self.client.get("/owners/me")
        self.assertEqual(resp.status_code, 401)

    def test_update_own_owner(self):
        owner = self.create_owner(name="Alice", email="alice4@example.com")
        resp = self.client.put(
            "/owners/me", {"name": "Alice Renamed"}, format="json", **self.auth_headers(owner)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "Alice Renamed")
        self.assertEqual(resp.json()["email"], "alice4@example.com")  # unchanged

    def test_update_own_owner_duplicate_email_conflict(self):
        self.create_owner(name="Bob", email="bob@example.com")
        owner_a = self.create_owner(name="Alice", email="alice5@example.com")
        resp = self.client.put(
            "/owners/me", {"email": "bob@example.com"}, format="json", **self.auth_headers(owner_a)
        )
        self.assertEqual(resp.status_code, 409)

    def test_update_own_owner_requires_auth(self):
        resp = self.client.put("/owners/me", {"name": "X"}, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_alarm_email_cooldown_seconds_defaults_to_null(self):
        owner = self.create_owner(name="Alice", email="alice-cooldown-default@example.com")
        resp = self.client.get("/owners/me", **self.auth_headers(owner))
        self.assertIsNone(resp.json()["alarm_email_cooldown_seconds"])

    def test_owner_can_set_their_own_alarm_email_cooldown(self):
        owner = self.create_owner(name="Alice", email="alice-cooldown-set@example.com")
        resp = self.client.put(
            "/owners/me",
            {"alarm_email_cooldown_seconds": 7200},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["alarm_email_cooldown_seconds"], 7200)

    def test_owner_can_clear_their_alarm_email_cooldown_back_to_the_default(self):
        owner = self.create_owner(name="Alice", email="alice-cooldown-clear@example.com")
        self.client.put(
            "/owners/me",
            {"alarm_email_cooldown_seconds": 7200},
            format="json",
            **self.auth_headers(owner),
        )
        resp = self.client.put(
            "/owners/me",
            {"alarm_email_cooldown_seconds": None},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["alarm_email_cooldown_seconds"])

    def test_alarm_email_cooldown_seconds_rejects_a_negative_value(self):
        owner = self.create_owner(name="Alice", email="alice-cooldown-negative@example.com")
        resp = self.client.put(
            "/owners/me",
            {"alarm_email_cooldown_seconds": -1},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(resp.status_code, 400)

    def test_alarm_email_cooldown_seconds_rejects_more_than_thirty_days(self):
        owner = self.create_owner(name="Alice", email="alice-cooldown-toolong@example.com")
        resp = self.client.put(
            "/owners/me",
            {"alarm_email_cooldown_seconds": 30 * 24 * 3600 + 1},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(resp.status_code, 400)

    def test_alarm_email_cooldown_seconds_accepts_zero(self):
        owner = self.create_owner(name="Alice", email="alice-cooldown-zero@example.com")
        resp = self.client.put(
            "/owners/me",
            {"alarm_email_cooldown_seconds": 0},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["alarm_email_cooldown_seconds"], 0)


class ApiKeyRotationTests(RegistryTestCase):
    def test_rotate_api_key_invalidates_old_key(self):
        owner = self.create_owner(name="Alice", email="alice6@example.com")
        old_key = owner["api_key"]

        rotate_resp = self.client.post("/owners/me/rotate-key", **self.auth_headers(owner))
        self.assertEqual(rotate_resp.status_code, 200)
        new_key = rotate_resp.json()["api_key"]
        self.assertNotEqual(new_key, old_key)
        self.assertEqual(rotate_resp.json()["id"], owner["id"])

        old_key_resp = self.client.get("/owners/me", **self.auth_headers(old_key))
        self.assertEqual(old_key_resp.status_code, 401)

        new_key_resp = self.client.get("/owners/me", **self.auth_headers(new_key))
        self.assertEqual(new_key_resp.status_code, 200)
        self.assertEqual(new_key_resp.json()["id"], owner["id"])

    def test_rotate_api_key_requires_auth(self):
        resp = self.client.post("/owners/me/rotate-key")
        self.assertEqual(resp.status_code, 401)

    def test_rotating_invalidates_the_old_key_immediately(self):
        """A rotated key stops working right away"""
        owner = self.create_owner(name="Alice", email="alice-rotate-revoke@example.com")

        resp = self.client.post("/owners/me/rotate-key", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.client.get("/owners/me", **self.auth_headers(owner)).status_code, 401)
        new_key = resp.json()["api_key"]
        self.assertEqual(self.client.get("/owners/me", **self.auth_headers(new_key)).status_code, 200)


class OwnerDeletionCascadeTests(RegistryTestCase):
    def test_delete_own_owner_cascades_gateways(self):
        owner = self.create_owner(name="Alice", email="alice7@example.com")
        mesh = self.create_mesh(owner)
        self.create_gateway(owner, mesh, device_id=1)
        self.create_gateway(owner, mesh, device_id=2)

        resp = self.client.delete("/owners/me", **self.auth_headers(owner))
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.fake_publisher.publish_gateway_delete.call_count, 2)

        self.assertEqual(self.client.get(f"/owners/{owner['id']}").status_code, 404)
        self.assertEqual(self.client.get("/owners/me", **self.auth_headers(owner)).status_code, 401)

    def test_delete_own_owner_with_no_gateways(self):
        owner = self.create_owner(name="Alice", email="alice8@example.com")
        resp = self.client.delete("/owners/me", **self.auth_headers(owner))
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.fake_publisher.publish_gateway_delete.call_count, 0)

    def test_delete_own_owner_aborts_on_publish_failure(self):
        owner = self.create_owner(name="Alice", email="alice9@example.com")
        mesh = self.create_mesh(owner)
        self.create_gateway(owner, mesh, device_id=1)
        self.fake_publisher.publish_gateway_delete.side_effect = RuntimeError("kafka down")

        resp = self.client.delete("/owners/me", **self.auth_headers(owner))
        self.assertEqual(resp.status_code, 502)

        self.assertEqual(self.client.get(f"/owners/{owner['id']}").status_code, 200)
        self.fake_publisher.publish_gateway_delete.side_effect = None
        self.assertEqual(len(self.client.get("/devices", **self.auth_headers(owner)).json()), 1)

    def test_delete_own_owner_requires_auth(self):
        resp = self.client.delete("/owners/me")
        self.assertEqual(resp.status_code, 401)

    def test_delete_own_owner_only_publishes_delete_for_allowed_gateways(self):
        owner = self.create_owner(name="Alice", email="alice-active-cascade@example.com")
        mesh = self.create_mesh(owner)
        allowed_gateway = self.create_gateway(owner, mesh, device_id=1)
        rejected_gateway = self.create_gateway(owner, mesh, device_id=2)
        self.client.put(
            f"/devices/{rejected_gateway['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner)
        )
        self.fake_publisher.publish_gateway_delete.reset_mock()

        resp = self.client.delete("/owners/me", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.fake_publisher.publish_gateway_delete.call_count, 1)
        self.assertFalse(
            Device.objects.filter(pk__in=[allowed_gateway["uuid"], rejected_gateway["uuid"]]).exists()
        )

    def test_delete_own_owner_unrejects_rejected_nodes(self):
        owner = self.create_owner(name="Alice", email="alice-node-cascade@example.com")
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=5)
        self.client.put(f"/devices/{node['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner))
        self.fake_publisher.publish_node_unreject.reset_mock()

        resp = self.client.delete("/owners/me", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.fake_publisher.publish_node_unreject.call_count, 1)

    def test_delete_own_owner_cascades_nodes(self):
        owner = self.create_owner(name="Alice", email="alice-nodes@example.com")
        mesh = self.create_mesh(owner)
        self.create_node(owner, mesh, device_id=42, admin_keys_b64=["AAAA"])

        resp = self.client.delete("/owners/me", **self.auth_headers(owner))
        self.assertEqual(resp.status_code, 204)  # would 500 on an FK violation if devices weren't cascaded

        self.assertEqual(self.client.get(f"/owners/{owner['id']}").status_code, 404)

    def test_deleting_an_owner_invalidates_their_key_immediately(self):
        owner = self.create_owner(name="Alice", email="alice-delete-revoke@example.com")

        resp = self.client.delete("/owners/me", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.client.get("/owners/me", **self.auth_headers(owner)).status_code, 401)


class OwnerAdminDeletionTests(RegistryTestCase):
    def test_superuser_deletes_another_owner(self):
        admin = self.create_owner(name="Admin", email="admin-delete@example.com")
        self.promote_to_superuser(admin)
        target = self.create_owner(name="Alice", email="alice-admin-delete@example.com")
        mesh = self.create_mesh(target)
        self.create_gateway(target, mesh, device_id=1)

        resp = self.client.delete(f"/owners/{target['id']}", **self.auth_headers(admin))

        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.fake_publisher.publish_gateway_delete.call_count, 1)
        self.assertEqual(self.client.get(f"/owners/{target['id']}").status_code, 404)

    def test_non_superuser_cannot_delete_another_owner(self):
        caller = self.create_owner(name="Bob", email="bob-admin-delete@example.com")
        target = self.create_owner(name="Alice", email="alice-admin-delete-2@example.com")

        resp = self.client.delete(f"/owners/{target['id']}", **self.auth_headers(caller))

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.client.get(f"/owners/{target['id']}").status_code, 200)

    def test_admin_delete_requires_auth(self):
        target = self.create_owner(name="Alice", email="alice-admin-delete-3@example.com")

        resp = self.client.delete(f"/owners/{target['id']}")

        self.assertEqual(resp.status_code, 401)

    def test_admin_delete_unknown_owner_404s(self):
        admin = self.create_owner(name="Admin", email="admin-delete-2@example.com")
        self.promote_to_superuser(admin)

        resp = self.client.delete("/owners/00000000-0000-0000-0000-000000000000", **self.auth_headers(admin))

        self.assertEqual(resp.status_code, 404)

    def test_admin_delete_aborts_on_publish_failure(self):
        admin = self.create_owner(name="Admin", email="admin-delete-3@example.com")
        self.promote_to_superuser(admin)
        target = self.create_owner(name="Alice", email="alice-admin-delete-4@example.com")
        mesh = self.create_mesh(target)
        self.create_gateway(target, mesh, device_id=1)
        self.fake_publisher.publish_gateway_delete.side_effect = RuntimeError("kafka down")

        resp = self.client.delete(f"/owners/{target['id']}", **self.auth_headers(admin))

        self.assertEqual(resp.status_code, 502)
        self.assertEqual(self.client.get(f"/owners/{target['id']}").status_code, 200)
        self.fake_publisher.publish_gateway_delete.side_effect = None

    def test_superuser_deletes_self_via_admin_route(self):
        admin = self.create_owner(name="Admin", email="admin-delete-4@example.com")
        self.promote_to_superuser(admin)

        resp = self.client.delete(f"/owners/{admin['id']}", **self.auth_headers(admin))

        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.client.get(f"/owners/{admin['id']}").status_code, 404)
