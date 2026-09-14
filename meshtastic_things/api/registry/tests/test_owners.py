from registry.auth import hash_api_key
from registry.models import Device

from .helpers import RegistryTestCase


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
        resp = self.client.post("/owners", {"name": "Bob", "email": "dup@example.com", "password": "Correct-Horse-Battery-42"}, format="json")
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
        self.assertEqual(devices[0]["device_id"], 7)
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
            f"/devices/{rejected_gateway['id']}", {"is_allowed": False}, format="json", **self.auth_headers(owner)
        )
        self.fake_publisher.publish_gateway_delete.reset_mock()

        resp = self.client.delete("/owners/me", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.fake_publisher.publish_gateway_delete.call_count, 1)
        self.assertFalse(
            Device.objects.filter(pk__in=[allowed_gateway["id"], rejected_gateway["id"]]).exists()
        )

    def test_delete_own_owner_unrejects_rejected_nodes(self):
        owner = self.create_owner(name="Alice", email="alice-node-cascade@example.com")
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=5)
        self.client.put(f"/devices/{node['id']}", {"is_allowed": False}, format="json", **self.auth_headers(owner))
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
