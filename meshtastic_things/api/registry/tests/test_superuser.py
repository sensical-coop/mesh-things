from .helpers import RegistryTestCase


class SuperuserBypassTests(RegistryTestCase):
    def test_superuser_bypasses_mesh_and_device_ownership(self):
        owner = self.create_owner(name="Owner", email="su-owner@example.com")
        admin = self.create_owner(name="Admin", email="su-admin@example.com")
        self.promote_to_superuser(admin)

        mesh = self.create_mesh(owner)
        gateway = self.create_gateway(owner, mesh, device_id=1)
        node = self.create_node(owner, mesh, device_id=2)

        self.assertEqual(self.client.get(f"/meshes/{mesh['id']}", **self.auth_headers(admin)).status_code, 200)
        self.assertEqual(
            self.client.put(
                f"/meshes/{mesh['id']}", {"label": "renamed by admin"}, format="json", **self.auth_headers(admin)
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(f"/devices/{gateway['uuid']}", **self.auth_headers(admin)).status_code, 200
        )
        self.assertEqual(
            self.client.put(
                f"/devices/{gateway['uuid']}",
                {"label": "renamed by admin"},
                format="json",
                **self.auth_headers(admin),
            ).status_code,
            200,
        )
        self.assertEqual(self.client.get(f"/devices/{node['uuid']}", **self.auth_headers(admin)).status_code, 200)
        self.assertEqual(self.client.delete(f"/devices/{node['uuid']}", **self.auth_headers(admin)).status_code, 204)

    def test_superuser_list_routes_return_every_owner(self):
        owner_a = self.create_owner(name="A", email="su-list-a@example.com")
        owner_b = self.create_owner(name="B", email="su-list-b@example.com")
        admin = self.create_owner(name="Admin", email="su-list-admin@example.com")
        self.promote_to_superuser(admin)

        mesh_a = self.create_mesh(owner_a, channel_id="A")
        mesh_b = self.create_mesh(owner_b, channel_id="B")
        self.create_gateway(owner_a, mesh_a, device_id=1)
        self.create_gateway(owner_b, mesh_b, device_id=2)
        self.create_node(owner_a, mesh_a, device_id=10)
        self.create_node(owner_b, mesh_b, device_id=20)

        self.assertEqual(len(self.client.get("/meshes", **self.auth_headers(admin)).json()), 2)
        self.assertEqual(len(self.client.get("/devices", **self.auth_headers(admin)).json()), 4)
        # a non-superuser still only sees their own
        self.assertEqual(len(self.client.get("/meshes", **self.auth_headers(owner_a)).json()), 1)
        self.assertEqual(len(self.client.get("/devices", **self.auth_headers(owner_a)).json()), 2)

    def test_superuser_create_gateway_on_someone_elses_mesh(self):
        owner = self.create_owner(name="Owner", email="su-create-owner@example.com")
        admin = self.create_owner(name="Admin", email="su-create-admin@example.com")
        self.promote_to_superuser(admin)
        mesh = self.create_mesh(owner)

        resp = self.client.post(
            "/devices",
            {"node_id": 99, "mesh_id": mesh["id"], "is_gateway": True},
            format="json",
            **self.auth_headers(admin),
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["mesh_id"], mesh["id"])

    def test_superuser_gets_no_special_access_to_psk_or_admin_keys(self):
        owner = self.create_owner(name="Owner", email="su-secret-owner@example.com")
        admin = self.create_owner(name="Admin", email="su-secret-admin@example.com")
        self.promote_to_superuser(admin)
        mesh = self.create_mesh(owner, psk_b64="SECRET")
        node = self.create_node(owner, mesh, device_id=3, admin_keys_b64=["SECRET"])

        self.assertNotIn("psk_b64", self.client.get(f"/meshes/{mesh['id']}", **self.auth_headers(admin)).json())
        self.assertNotIn(
            "admin_keys_b64", self.client.get(f"/devices/{node['uuid']}", **self.auth_headers(admin)).json()
        )

    def test_non_superuser_still_scoped_to_own_resources(self):
        owner_a = self.create_owner(name="A", email="su-scope-a@example.com")
        owner_b = self.create_owner(name="B", email="su-scope-b@example.com")
        mesh = self.create_mesh(owner_a)

        self.assertEqual(self.client.get(f"/meshes/{mesh['id']}", **self.auth_headers(owner_b)).status_code, 403)
