from registry.models import Mesh
from registry.serializers import MeshSerializer

from .helpers import MESH_TERMS, RegistryTestCase


class MeshCrudTests(RegistryTestCase):
    def test_create_mesh_accepts_blank_psk_for_plaintext_only_channel(self):
        # "" is a legitimate psk_b64 value (no real encryption on that channel) -
        # needs an explicit allow_blank=True on the serializer field.
        owner = self.create_owner()
        resp = self.client.post(
            "/meshes", {**MESH_TERMS, "channel_id": "Plaintext", "psk_b64": ""}, format="json", **self.auth_headers(owner)
        )
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_create_list_get_update_delete_mesh_round_trip(self):
        owner = self.create_owner()
        create_resp = self.client.post(
            "/meshes",
            {**MESH_TERMS, "channel_id": "TestChan", "psk_b64": "AAAA", "label": "initial"},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(create_resp.status_code, 201)
        body = create_resp.json()
        mesh_id = body["id"]
        self.assertEqual(body["channel_id"], "TestChan")
        self.assertEqual(body["owner_id"], owner["id"])
        # creating a mesh alone publishes nothing - only a gateway device does
        self.fake_publisher.publish_gateway_upsert.assert_not_called()

        list_resp = self.client.get("/meshes", **self.auth_headers(owner))
        self.assertEqual(len(list_resp.json()), 1)

        get_resp = self.client.get(f"/meshes/{mesh_id}", **self.auth_headers(owner))
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["label"], "initial")

        update_resp = self.client.put(
            f"/meshes/{mesh_id}", {"label": "updated"}, format="json", **self.auth_headers(owner)
        )
        self.assertEqual(update_resp.status_code, 200)
        self.assertEqual(update_resp.json()["label"], "updated")

        delete_resp = self.client.delete(f"/meshes/{mesh_id}", **self.auth_headers(owner))
        self.assertEqual(delete_resp.status_code, 204)

        self.assertEqual(self.client.get("/meshes", **self.auth_headers(owner)).json(), [])

    def test_get_missing_mesh_returns_404(self):
        owner = self.create_owner()
        resp = self.client.get("/meshes/00000000-0000-0000-0000-000000000000", **self.auth_headers(owner))
        self.assertEqual(resp.status_code, 404)

    def test_create_mesh_requires_auth(self):
        resp = self.client.post("/meshes", {**MESH_TERMS, "channel_id": "X", "psk_b64": "AAAA"}, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_mesh_owner_id_body_field_is_ignored_owner_comes_from_auth(self):
        owner_a = self.create_owner(name="A", email="a@example.com")
        owner_b = self.create_owner(name="B", email="b@example.com")

        # Even if a client tried to smuggle an owner_id into the body, MeshSerializer
        # marks it read_only - owner_id can only come from the auth token.
        resp = self.client.post(
            "/meshes",
            {**MESH_TERMS, "channel_id": "X", "psk_b64": "AAAA", "owner_id": owner_b["id"]},
            format="json",
            **self.auth_headers(owner_a),
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["owner_id"], owner_a["id"])

    def test_mesh_update_and_delete_require_matching_owner(self):
        owner_a = self.create_owner(name="A", email="owner-a@example.com")
        owner_b = self.create_owner(name="B", email="owner-b@example.com")

        mesh = self.create_mesh(owner_a)
        mesh_id = mesh["id"]

        update_resp = self.client.put(
            f"/meshes/{mesh_id}", {"label": "hijacked"}, format="json", **self.auth_headers(owner_b)
        )
        self.assertEqual(update_resp.status_code, 403)

        delete_resp = self.client.delete(f"/meshes/{mesh_id}", **self.auth_headers(owner_b))
        self.assertEqual(delete_resp.status_code, 403)

        own_update = self.client.put(
            f"/meshes/{mesh_id}", {"label": "mine"}, format="json", **self.auth_headers(owner_a)
        )
        self.assertEqual(own_update.status_code, 200)

    def test_get_mesh_is_owner_scoped(self):
        owner_a = self.create_owner(name="A", email="owner-a2@example.com")
        owner_b = self.create_owner(name="B", email="owner-b2@example.com")
        mesh = self.create_mesh(owner_a)

        self.assertEqual(self.client.get(f"/meshes/{mesh['id']}").status_code, 404)
        # A read the caller may not perform is a 404: a 403 would confirm the mesh exists.
        self.assertEqual(self.client.get(f"/meshes/{mesh['id']}", **self.auth_headers(owner_b)).status_code, 404)
        self.assertEqual(self.client.get(f"/meshes/{mesh['id']}", **self.auth_headers(owner_a)).status_code, 200)

    def test_list_meshes_is_owner_scoped(self):
        owner_a = self.create_owner(name="A", email="owner-a3@example.com")
        owner_b = self.create_owner(name="B", email="owner-b3@example.com")
        self.create_mesh(owner_a, channel_id="A")
        self.create_mesh(owner_b, channel_id="B")

        resp_a = self.client.get("/meshes", **self.auth_headers(owner_a))
        self.assertEqual(len(resp_a.json()), 1)
        self.assertEqual(resp_a.json()[0]["channel_id"], "A")

        resp_b = self.client.get("/meshes", **self.auth_headers(owner_b))
        self.assertEqual(len(resp_b.json()), 1)
        self.assertEqual(resp_b.json()[0]["channel_id"], "B")

    def test_anonymous_list_omits_private_meshes(self):
        self.create_mesh(self.create_owner(), channel_id="A")

        resp = self.client.get("/meshes")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    def test_delete_mesh_cascades_gateways(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_gateway(owner, mesh, device_id=1)
        self.create_gateway(owner, mesh, device_id=2)

        resp = self.client.delete(f"/meshes/{mesh['id']}", **self.auth_headers(owner))
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.fake_publisher.publish_gateway_delete.call_count, 2)
        self.assertEqual(self.client.get("/devices", **self.auth_headers(owner)).json(), [])

    def test_delete_mesh_only_publishes_delete_for_allowed_gateways(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_gateway(owner, mesh, device_id=1)
        rejected_gateway = self.create_gateway(owner, mesh, device_id=2)
        self.client.put(
            f"/devices/{rejected_gateway['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner)
        )
        self.fake_publisher.publish_gateway_delete.reset_mock()

        resp = self.client.delete(f"/meshes/{mesh['id']}", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.fake_publisher.publish_gateway_delete.call_count, 1)
        self.assertEqual(self.client.get("/devices", **self.auth_headers(owner)).json(), [])

    def test_delete_mesh_unrejects_rejected_nodes(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)
        self.client.put(
            f"/devices/{node['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner)
        )
        self.fake_publisher.publish_node_unreject.reset_mock()

        resp = self.client.delete(f"/meshes/{mesh['id']}", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.fake_publisher.publish_node_unreject.call_count, 1)

    def test_update_mesh_psk_republishes_all_its_gateways(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner, psk_b64="AAAA")
        self.create_gateway(owner, mesh, device_id=1)
        self.create_gateway(owner, mesh, device_id=2)
        self.fake_publisher.publish_gateway_upsert.reset_mock()

        resp = self.client.put(
            f"/meshes/{mesh['id']}", {"psk_b64": "BBBB"}, format="json", **self.auth_headers(owner)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["psk_b64"], "BBBB")  # echoed back - the caller is this mesh's owner
        self.assertEqual(self.fake_publisher.publish_gateway_upsert.call_count, 2)
        published_meshes = [call.args[1] for call in self.fake_publisher.publish_gateway_upsert.call_args_list]
        self.assertTrue(all(m.psk_b64 == "BBBB" for m in published_meshes))

    def test_update_mesh_label_only_does_not_republish_gateways(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_gateway(owner, mesh, device_id=1)
        self.fake_publisher.publish_gateway_upsert.reset_mock()

        resp = self.client.put(
            f"/meshes/{mesh['id']}", {"label": "renamed"}, format="json", **self.auth_headers(owner)
        )
        self.assertEqual(resp.status_code, 200)
        self.fake_publisher.publish_gateway_upsert.assert_not_called()


class MeshPasswordFieldTests(RegistryTestCase):
    def test_mesh_get_and_list_include_psk_for_the_owner(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner, psk_b64="SECRET")

        self.assertEqual(
            self.client.get(f"/meshes/{mesh['id']}", **self.auth_headers(owner)).json()["psk_b64"], "SECRET"
        )
        self.assertEqual(self.client.get("/meshes", **self.auth_headers(owner)).json()[0]["psk_b64"], "SECRET")

    def test_mesh_serializer_hides_psk_from_a_non_owner_viewer(self):
        # No HTTP route lets a non-superuser view a mesh they don't own at all
        # (MeshDetailView 403s first) - the superuser bypass case is covered in
        # test_superuser.py. This exercises MeshSerializer's own visibility rule
        # directly, the thing that check ultimately depends on.
        owner = self.create_owner()
        other = self.create_owner(name="Other", email="mesh-psk-other@example.com")
        mesh_obj = Mesh.objects.get(pk=self.create_mesh(owner, psk_b64="SECRET")["id"])

        data = MeshSerializer(mesh_obj, context={"viewer_id": other["id"]}).data
        self.assertNotIn("psk_b64", data)
