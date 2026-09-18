import uuid

from registry.management.commands.consume_device_sightings import Command as SightingsCommand
from registry.models import Device
from registry.serializers import DeviceReadSerializer

from .helpers import RegistryTestCase

def _get_device_admin_keys(device_id: str) -> list[str]:
    """Read admin_keys_b64 straight from the DB"""
    return list(Device.objects.get(pk=uuid.UUID(device_id)).admin_keys_b64)

def _seed_device_sighting(mesh: dict, device_id: int, **telemetry) -> None:
    event = {"mesh_id": mesh["id"], "device_id": device_id, "op": "upsert", **telemetry}
    SightingsCommand._upsert(event)


class DeviceGatewayCrudTests(RegistryTestCase):
    def test_create_list_get_update_delete_gateway_round_trip(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner, channel_id="TestChan", psk_b64="AAAA")

        create_resp = self.client.post(
            "/devices",
            {"node_id": 123, "mesh_id": mesh["id"], "is_gateway": True, "label": "initial"},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(create_resp.status_code, 201)
        body = create_resp.json()
        device_uuid = body["uuid"]
        self.assertEqual(body["node_id"], 123)
        self.assertEqual(body["mesh_id"], mesh["id"])
        self.assertTrue(body["is_gateway"])
        self.assertTrue(body["is_allowed"])
        self.assertEqual(self.fake_publisher.publish_gateway_upsert.call_count, 1)

        list_resp = self.client.get("/devices", **self.auth_headers(owner))
        self.assertEqual(len(list_resp.json()), 1)

        get_resp = self.client.get(f"/devices/{device_uuid}", **self.auth_headers(owner))
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["label"], "initial")

        update_resp = self.client.put(
            f"/devices/{device_uuid}", {"label": "updated"}, format="json", **self.auth_headers(owner)
        )
        self.assertEqual(update_resp.status_code, 200)
        self.assertEqual(update_resp.json()["label"], "updated")
        # a label-only update doesn't touch Kafka - the broadcast state has no label
        self.assertEqual(self.fake_publisher.publish_gateway_upsert.call_count, 1)

        delete_resp = self.client.delete(f"/devices/{device_uuid}", **self.auth_headers(owner))
        self.assertEqual(delete_resp.status_code, 204)
        self.assertEqual(self.fake_publisher.publish_gateway_delete.call_count, 1)

        self.assertEqual(self.client.get("/devices", **self.auth_headers(owner)).json(), [])

    def test_get_missing_device_returns_404(self):
        owner = self.create_owner()
        resp = self.client.get("/devices/00000000-0000-0000-0000-000000000000", **self.auth_headers(owner))
        self.assertEqual(resp.status_code, 404)

    def test_create_gateway_rejects_unknown_mesh(self):
        owner = self.create_owner()
        resp = self.client.post(
            "/devices",
            {"node_id": 1, "mesh_id": "00000000-0000-0000-0000-000000000000", "is_gateway": True},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(resp.status_code, 404)
        self.fake_publisher.publish_gateway_upsert.assert_not_called()

    def test_create_gateway_rejects_mesh_owned_by_someone_else(self):
        owner_a = self.create_owner(name="A", email="gw-owner-a@example.com")
        owner_b = self.create_owner(name="B", email="gw-owner-b@example.com")
        mesh = self.create_mesh(owner_a)

        resp = self.client.post(
            "/devices",
            {"node_id": 1, "mesh_id": mesh["id"], "is_gateway": True},
            format="json",
            **self.auth_headers(owner_b),
        )
        self.assertEqual(resp.status_code, 403)
        self.fake_publisher.publish_gateway_upsert.assert_not_called()

    def test_create_rolls_back_on_publish_failure(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.fake_publisher.publish_gateway_upsert.side_effect = RuntimeError("kafka down")

        resp = self.client.post(
            "/devices",
            {"node_id": 1, "mesh_id": mesh["id"], "is_gateway": True},
            format="json",
            **self.auth_headers(owner),
        )

        self.assertEqual(resp.status_code, 502)
        self.fake_publisher.publish_gateway_upsert.side_effect = None
        self.assertEqual(self.client.get("/devices", **self.auth_headers(owner)).json(), [])

    def test_mesh_id_filter(self):
        owner = self.create_owner()
        mesh_a = self.create_mesh(owner, channel_id="A")
        mesh_b = self.create_mesh(owner, channel_id="B")
        self.create_gateway(owner, mesh_a, device_id=1)
        self.create_gateway(owner, mesh_b, device_id=2)

        resp = self.client.get("/devices", {"mesh_id": mesh_a["id"]}, **self.auth_headers(owner))

        self.assertEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]["mesh_id"], mesh_a["id"])

    def test_create_device_requires_auth(self):
        resp = self.client.post(
            "/devices",
            {"node_id": 1, "mesh_id": "00000000-0000-0000-0000-000000000000", "is_gateway": True},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)
        self.fake_publisher.publish_gateway_upsert.assert_not_called()

    def test_create_device_rejects_invalid_api_key(self):
        resp = self.client.post(
            "/devices",
            {"node_id": 1, "mesh_id": "00000000-0000-0000-0000-000000000000", "is_gateway": True},
            format="json",
            HTTP_AUTHORIZATION="Bearer not-a-real-key",
        )
        self.assertEqual(resp.status_code, 401)

    def test_create_gateway_rejects_duplicate_device_id(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_gateway(owner, mesh, device_id=1)

        resp = self.client.post(
            "/devices",
            {"node_id": 1, "mesh_id": mesh["id"], "is_gateway": True},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(resp.status_code, 409)

    def test_device_update_and_delete_require_mesh_ownership(self):
        owner_a = self.create_owner(name="A", email="gw-owner-a2@example.com")
        owner_b = self.create_owner(name="B", email="gw-owner-b2@example.com")

        mesh = self.create_mesh(owner_a)
        gateway = self.create_gateway(owner_a, mesh, device_id=1)
        device_uuid = gateway["uuid"]

        update_resp = self.client.put(
            f"/devices/{device_uuid}", {"label": "hijacked"}, format="json", **self.auth_headers(owner_b)
        )
        self.assertEqual(update_resp.status_code, 403)

        delete_resp = self.client.delete(f"/devices/{device_uuid}", **self.auth_headers(owner_b))
        self.assertEqual(delete_resp.status_code, 403)

        own_update = self.client.put(
            f"/devices/{device_uuid}", {"label": "mine"}, format="json", **self.auth_headers(owner_a)
        )
        self.assertEqual(own_update.status_code, 200)

    def test_get_device_requires_auth_and_is_mesh_owner_scoped(self):
        owner_a = self.create_owner(name="A", email="gw-owner-a3@example.com")
        owner_b = self.create_owner(name="B", email="gw-owner-b3@example.com")
        mesh = self.create_mesh(owner_a)
        gateway = self.create_gateway(owner_a, mesh, device_id=1)

        self.assertEqual(self.client.get(f"/devices/{gateway['uuid']}").status_code, 401)
        self.assertEqual(
            self.client.get(f"/devices/{gateway['uuid']}", **self.auth_headers(owner_b)).status_code, 403
        )
        self.assertEqual(
            self.client.get(f"/devices/{gateway['uuid']}", **self.auth_headers(owner_a)).status_code, 200
        )

    def test_list_devices_is_mesh_owner_scoped(self):
        owner_a = self.create_owner(name="A", email="gw-owner-a4@example.com")
        owner_b = self.create_owner(name="B", email="gw-owner-b4@example.com")
        mesh_a = self.create_mesh(owner_a)
        mesh_b = self.create_mesh(owner_b)
        self.create_gateway(owner_a, mesh_a, device_id=1)
        self.create_gateway(owner_b, mesh_b, device_id=2)

        resp_a = self.client.get("/devices", **self.auth_headers(owner_a))
        self.assertEqual(len(resp_a.json()), 1)
        self.assertEqual(resp_a.json()[0]["node_id"], 1)

        resp_b = self.client.get("/devices", **self.auth_headers(owner_b))
        self.assertEqual(len(resp_b.json()), 1)
        self.assertEqual(resp_b.json()[0]["node_id"], 2)

    def test_list_devices_requires_auth(self):
        resp = self.client.get("/devices")
        self.assertEqual(resp.status_code, 401)

    def test_multiple_gateways_on_one_mesh_stay_simultaneously_allowed(self):
        # Confirms the unique-while-allowed constraint is per device_id, and not per
        # mesh. A mesh can have any number of distinct gateways at once.
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_gateway(owner, mesh, device_id=1)
        self.create_gateway(owner, mesh, device_id=2)
        self.create_gateway(owner, mesh, device_id=3)

        resp = self.client.get("/devices", {"mesh_id": mesh["id"], "is_allowed": "true"}, **self.auth_headers(owner))

        self.assertEqual(len(resp.json()), 3)
        self.assertTrue(all(d["is_allowed"] for d in resp.json()))


class DeviceRoleValidationTests(RegistryTestCase):
    def test_create_device_rejects_neither_role_flag(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        resp = self.client.post(
            "/devices", {"node_id": 1, "mesh_id": mesh["id"]}, format="json", **self.auth_headers(owner)
        )
        self.assertEqual(resp.status_code, 400)


class DeviceGatewayTakeoverTests(RegistryTestCase):
    """Reject/re-allow workflow - device_id uniqueness is enforced only among
    allowed devices, so a rejected row doesn't block a new registration."""

    def test_reject_gateway_publishes_delete_and_keeps_row(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        gateway = self.create_gateway(owner, mesh, device_id=1)

        resp = self.client.put(
            f"/devices/{gateway['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner)
        )

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["is_allowed"])
        self.assertEqual(self.fake_publisher.publish_gateway_delete.call_count, 1)
        get_resp = self.client.get(f"/devices/{gateway['uuid']}", **self.auth_headers(owner))
        self.assertEqual(get_resp.status_code, 200)
        self.assertFalse(get_resp.json()["is_allowed"])
        self.assertEqual(len(self.client.get("/devices", **self.auth_headers(owner)).json()), 1)

    def test_reallow_gateway_publishes_upsert(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        gateway = self.create_gateway(owner, mesh, device_id=1)
        self.client.put(
            f"/devices/{gateway['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner)
        )

        resp = self.client.put(
            f"/devices/{gateway['uuid']}", {"is_allowed": True}, format="json", **self.auth_headers(owner)
        )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["is_allowed"])
        # once on create, once on this re-allow
        self.assertEqual(self.fake_publisher.publish_gateway_upsert.call_count, 2)

    def test_create_gateway_with_same_device_id_as_rejected_gateway_succeeds(self):
        owner = self.create_owner()
        mesh_a = self.create_mesh(owner, channel_id="A")
        mesh_b = self.create_mesh(owner, channel_id="B")
        old_gateway = self.create_gateway(owner, mesh_a, device_id=1)
        self.client.put(
            f"/devices/{old_gateway['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner)
        )

        resp = self.client.post(
            "/devices",
            {"node_id": 1, "mesh_id": mesh_b["id"], "is_gateway": True},
            format="json",
            **self.auth_headers(owner),
        )

        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["is_allowed"])
        rows = self.client.get("/devices", **self.auth_headers(owner)).json()
        allowed_rows = [r for r in rows if r["node_id"] == 1 and r["is_allowed"]]
        self.assertEqual(len(allowed_rows), 1)
        self.assertEqual(allowed_rows[0]["mesh_id"], mesh_b["id"])

    def test_reallow_gateway_conflicts_with_currently_allowed_duplicate(self):
        owner = self.create_owner()
        mesh_a = self.create_mesh(owner, channel_id="A")
        mesh_b = self.create_mesh(owner, channel_id="B")
        gateway_a = self.create_gateway(owner, mesh_a, device_id=1)
        self.client.put(
            f"/devices/{gateway_a['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner)
        )
        self.create_gateway(owner, mesh_b, device_id=1)
        self.fake_publisher.publish_gateway_upsert.reset_mock()

        resp = self.client.put(
            f"/devices/{gateway_a['uuid']}", {"is_allowed": True}, format="json", **self.auth_headers(owner)
        )

        self.assertEqual(resp.status_code, 409)
        self.fake_publisher.publish_gateway_upsert.assert_not_called()

    def test_reject_gateway_rolls_back_on_publish_failure(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        gateway = self.create_gateway(owner, mesh, device_id=1)
        self.fake_publisher.publish_gateway_delete.side_effect = RuntimeError("kafka down")

        resp = self.client.put(
            f"/devices/{gateway['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner)
        )

        self.assertEqual(resp.status_code, 502)
        self.fake_publisher.publish_gateway_delete.side_effect = None
        get_resp = self.client.get(f"/devices/{gateway['uuid']}", **self.auth_headers(owner))
        self.assertTrue(get_resp.json()["is_allowed"])

    def test_reallow_gateway_rolls_back_on_publish_failure(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        gateway = self.create_gateway(owner, mesh, device_id=1)
        self.client.put(
            f"/devices/{gateway['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner)
        )
        self.fake_publisher.publish_gateway_upsert.side_effect = RuntimeError("kafka down")

        resp = self.client.put(
            f"/devices/{gateway['uuid']}", {"is_allowed": True}, format="json", **self.auth_headers(owner)
        )

        self.assertEqual(resp.status_code, 502)
        self.fake_publisher.publish_gateway_upsert.side_effect = None
        get_resp = self.client.get(f"/devices/{gateway['uuid']}", **self.auth_headers(owner))
        self.assertFalse(get_resp.json()["is_allowed"])

    def test_is_allowed_filter_on_list_devices(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        allowed_gateway = self.create_gateway(owner, mesh, device_id=1)
        rejected_gateway = self.create_gateway(owner, mesh, device_id=2)
        self.client.put(
            f"/devices/{rejected_gateway['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner)
        )

        both = self.client.get("/devices", **self.auth_headers(owner)).json()
        only_allowed = self.client.get("/devices", {"is_allowed": "true"}, **self.auth_headers(owner)).json()
        only_rejected = self.client.get("/devices", {"is_allowed": "false"}, **self.auth_headers(owner)).json()

        self.assertEqual(len(both), 2)
        self.assertEqual([d["uuid"] for d in only_allowed], [allowed_gateway["uuid"]])
        self.assertEqual([d["uuid"] for d in only_rejected], [rejected_gateway["uuid"]])


class DeviceNodeCrudTests(RegistryTestCase):
    def test_create_list_get_update_delete_node_round_trip(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        create_resp = self.client.post(
            "/devices",
            {
                "node_id": 111,
                "mesh_id": mesh["id"],
                "is_gateway": False,
                "admin_keys_b64": ["AAAA", "BBBB"],
                "label": "gateway node",
            },
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(create_resp.status_code, 201)
        body = create_resp.json()
        device_uuid = body["uuid"]
        self.assertEqual(body["node_id"], 111)
        self.assertTrue(body["is_allowed"])
        self.assertEqual(body["admin_keys_b64"], ["AAAA", "BBBB"])  # echoed back - caller owns this device's mesh
        # a node never touches Kafka on creation - only a gateway upsert does
        self.fake_publisher.publish_gateway_upsert.assert_not_called()
        self.assertEqual(_get_device_admin_keys(device_uuid), ["AAAA", "BBBB"])

        list_resp = self.client.get("/devices?is_gateway=false", **self.auth_headers(owner))
        self.assertEqual(len(list_resp.json()), 1)

        get_resp = self.client.get(f"/devices/{device_uuid}", **self.auth_headers(owner))
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["label"], "gateway node")

        update_resp = self.client.put(
            f"/devices/{device_uuid}", {"admin_keys_b64": ["CCCC"]}, format="json", **self.auth_headers(owner)
        )
        self.assertEqual(update_resp.status_code, 200)
        self.assertEqual(update_resp.json()["admin_keys_b64"], ["CCCC"])
        self.assertEqual(_get_device_admin_keys(device_uuid), ["CCCC"])

        delete_resp = self.client.delete(f"/devices/{device_uuid}", **self.auth_headers(owner))
        self.assertEqual(delete_resp.status_code, 204)
        self.assertEqual(self.client.get("/devices", **self.auth_headers(owner)).json(), [])

    def test_create_node_rejects_more_than_three_admin_keys(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        resp = self.client.post(
            "/devices",
            {"node_id": 111, "mesh_id": mesh["id"], "is_gateway": False, "admin_keys_b64": ["A", "B", "C", "D"]},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(resp.status_code, 400)

    def test_create_node_duplicate_device_id_conflict(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_node(owner, mesh, device_id=222)
        resp = self.client.post(
            "/devices",
            {"node_id": 222, "mesh_id": mesh["id"], "is_gateway": False},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(resp.status_code, 409)

    def test_node_requires_auth(self):
        self.assertEqual(
            self.client.post(
                "/devices",
                {"node_id": 1, "mesh_id": "00000000-0000-0000-0000-000000000000", "is_gateway": False},
                format="json",
            ).status_code,
            401,
        )
        self.assertEqual(self.client.get("/devices?is_gateway=false").status_code, 401)

    def test_node_create_update_delete_require_mesh_ownership(self):
        owner_a = self.create_owner(name="A", email="node-owner-a@example.com")
        owner_b = self.create_owner(name="B", email="node-owner-b@example.com")
        mesh = self.create_mesh(owner_a)

        create_resp = self.client.post(
            "/devices",
            {"node_id": 333, "mesh_id": mesh["id"], "is_gateway": False},
            format="json",
            **self.auth_headers(owner_b),
        )
        self.assertEqual(create_resp.status_code, 403)

        node = self.create_node(owner_a, mesh, device_id=333)
        device_uuid = node["uuid"]

        self.assertEqual(self.client.get(f"/devices/{device_uuid}", **self.auth_headers(owner_b)).status_code, 403)
        self.assertEqual(
            self.client.put(
                f"/devices/{device_uuid}", {"label": "hijacked"}, format="json", **self.auth_headers(owner_b)
            ).status_code,
            403,
        )
        self.assertEqual(self.client.delete(f"/devices/{device_uuid}", **self.auth_headers(owner_b)).status_code, 403)

        self.assertEqual(self.client.get(f"/devices/{device_uuid}", **self.auth_headers(owner_a)).status_code, 200)

    def test_list_nodes_is_mesh_owner_scoped(self):
        owner_a = self.create_owner(name="A", email="node-owner-a2@example.com")
        owner_b = self.create_owner(name="B", email="node-owner-b2@example.com")
        mesh_a = self.create_mesh(owner_a)
        mesh_b = self.create_mesh(owner_b)
        self.create_node(owner_a, mesh_a, device_id=1)
        self.create_node(owner_b, mesh_b, device_id=2)

        resp_a = self.client.get("/devices?is_gateway=false", **self.auth_headers(owner_a))
        self.assertEqual(len(resp_a.json()), 1)
        self.assertEqual(resp_a.json()[0]["node_id"], 1)


class DeviceNodeRejectionTests(RegistryTestCase):
    """The mesh owner's reject/unreject lever for a node - distinct Kafka
    topic/publisher calls from a gateway's is_allowed transition."""

    def test_reject_node_publishes_node_reject_not_gateway_events(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)

        resp = self.client.put(
            f"/devices/{node['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner)
        )

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["is_allowed"])
        self.assertEqual(self.fake_publisher.publish_node_reject.call_count, 1)
        self.fake_publisher.publish_gateway_upsert.assert_not_called()
        self.fake_publisher.publish_gateway_delete.assert_not_called()

    def test_unreject_node_publishes_node_unreject(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)
        self.client.put(f"/devices/{node['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner))

        resp = self.client.put(
            f"/devices/{node['uuid']}", {"is_allowed": True}, format="json", **self.auth_headers(owner)
        )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["is_allowed"])
        self.assertEqual(self.fake_publisher.publish_node_unreject.call_count, 1)

    def test_reject_node_rolls_back_on_publish_failure(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)
        self.fake_publisher.publish_node_reject.side_effect = RuntimeError("kafka down")

        resp = self.client.put(
            f"/devices/{node['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner)
        )

        self.assertEqual(resp.status_code, 502)
        self.fake_publisher.publish_node_reject.side_effect = None
        get_resp = self.client.get(f"/devices/{node['uuid']}", **self.auth_headers(owner))
        self.assertTrue(get_resp.json()["is_allowed"])

    def test_delete_rejected_node_publishes_unreject_to_clear_state(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)
        self.client.put(f"/devices/{node['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner))
        self.fake_publisher.publish_node_unreject.reset_mock()

        resp = self.client.delete(f"/devices/{node['uuid']}", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.fake_publisher.publish_node_unreject.call_count, 1)

    def test_delete_allowed_node_publishes_nothing(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)

        resp = self.client.delete(f"/devices/{node['uuid']}", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 204)
        self.fake_publisher.publish_node_unreject.assert_not_called()
        self.fake_publisher.publish_node_reject.assert_not_called()


class DevicePasswordFieldTests(RegistryTestCase):
    def test_node_get_and_list_include_admin_keys_for_the_owner(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=42, admin_keys_b64=["SECRET"])

        self.assertEqual(
            self.client.get(f"/devices/{node['uuid']}", **self.auth_headers(owner)).json()["admin_keys_b64"],
            ["SECRET"],
        )
        self.assertEqual(
            self.client.get("/devices?is_gateway=false", **self.auth_headers(owner)).json()[0]["admin_keys_b64"],
            ["SECRET"],
        )

    def test_device_serializer_hides_admin_keys_from_a_non_owner_viewer(self):
        # No HTTP route lets a non-superuser view a device they don't own at all
        # (DeviceDetailView 403s first) - the superuser bypass case is covered in
        # test_superuser.py. This exercises DeviceReadSerializer's own visibility
        # rule directly, the thing that check ultimately depends on.
        owner = self.create_owner()
        other = self.create_owner(name="Other", email="device-admin-keys-other@example.com")
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=42, admin_keys_b64=["SECRET"])
        device_obj = Device.objects.select_related("mesh").get(pk=uuid.UUID(node["uuid"]))

        data = DeviceReadSerializer(device_obj, context={"viewer_id": other["id"]}).data
        self.assertNotIn("admin_keys_b64", data)


class DeviceCatalogTests(RegistryTestCase):
    def test_list_mesh_devices_includes_gateway_and_sighted_node(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_gateway(owner, mesh, device_id=111)
        _seed_device_sighting(mesh, device_id=222)
        _seed_device_sighting(mesh, device_id=111)  # gateway also reported its own telemetry

        resp = self.client.get(f"/meshes/{mesh['id']}/devices", **self.auth_headers(owner))
        self.assertEqual(resp.status_code, 200)
        by_device_id = {d["node_id"]: d for d in resp.json()}
        self.assertEqual(set(by_device_id), {111, 222})
        self.assertTrue(by_device_id[111]["is_gateway"])
        self.assertFalse(by_device_id[222]["is_gateway"])
        self.assertTrue(by_device_id[222]["is_allowed"])

    def test_sighting_of_new_device_id_creates_allowed_node(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)

        _seed_device_sighting(mesh, device_id=222)

        device = Device.objects.get(mesh_id=uuid.UUID(mesh["id"]), device_id=222)
        self.assertFalse(device.is_gateway)
        self.assertTrue(device.is_allowed)
        self.assertIsNotNone(device.last_seen)

    def test_list_mesh_devices_requires_auth_and_is_owner_scoped(self):
        owner_a = self.create_owner(name="A", email="dev-owner-a@example.com")
        owner_b = self.create_owner(name="B", email="dev-owner-b@example.com")
        mesh = self.create_mesh(owner_a)

        self.assertEqual(self.client.get(f"/meshes/{mesh['id']}/devices").status_code, 401)
        self.assertEqual(
            self.client.get(f"/meshes/{mesh['id']}/devices", **self.auth_headers(owner_b)).status_code, 403
        )
        self.assertEqual(
            self.client.get(f"/meshes/{mesh['id']}/devices", **self.auth_headers(owner_a)).status_code, 200
        )

    def test_delete_mesh_also_removes_its_devices(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_gateway(owner, mesh, device_id=111)
        _seed_device_sighting(mesh, device_id=222)

        resp = self.client.delete(f"/meshes/{mesh['id']}", **self.auth_headers(owner))
        self.assertEqual(resp.status_code, 204)  # would 500 on an FK violation if devices weren't cascaded

    def test_sighting_of_existing_device_bumps_last_seen_only(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)

        _seed_device_sighting(mesh, device_id=333)
        first = Device.objects.get(mesh_id=uuid.UUID(mesh["id"]), device_id=333)
        created_at = first.created_at

        _seed_device_sighting(mesh, device_id=333)
        again = Device.objects.get(mesh_id=uuid.UUID(mesh["id"]), device_id=333)

        self.assertEqual(again.id, first.id)
        self.assertEqual(again.created_at, created_at)
        self.assertGreaterEqual(again.last_seen, first.last_seen)

    def test_sighting_does_not_touch_pre_registered_nodes_role_or_allow_state(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=444, admin_keys_b64=["AAAA"])
        self.client.put(f"/devices/{node['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner))

        _seed_device_sighting(mesh, device_id=444)

        device = Device.objects.get(pk=uuid.UUID(node["uuid"]))
        self.assertFalse(device.is_gateway)
        self.assertFalse(device.is_allowed)  # sighting never re-allows a rejected device
        self.assertEqual(list(device.admin_keys_b64), ["AAAA"])


class DeviceTelemetryAutoFillTests(RegistryTestCase):
    """Location and nodeinfo fields auto-fill from telemetry, but a PUT/POST
    value sticks - see docs/architecture.md#device-registration-and-the-is-allowed-gate."""

    def test_position_sighting_sets_latitude_and_longitude(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)

        _seed_device_sighting(mesh, device_id=1, latitude=45.4642, longitude=9.19)

        device = Device.objects.get(mesh_id=uuid.UUID(mesh["id"]), device_id=1)
        self.assertEqual(device.latitude, 45.4642)
        self.assertEqual(device.longitude, 9.19)
        self.assertFalse(device.location_overridden)

    def test_nodeinfo_sighting_sets_identity_fields_together(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)

        _seed_device_sighting(
            mesh, device_id=1, name="Alice Node", short_name="ALCE", hardware_type="TBEAM", role="CLIENT"
        )

        device = Device.objects.get(mesh_id=uuid.UUID(mesh["id"]), device_id=1)
        self.assertEqual(device.name, "Alice Node")
        self.assertEqual(device.short_name, "ALCE")
        self.assertEqual(device.hardware_type, "TBEAM")
        self.assertEqual(device.role, "CLIENT")
        self.assertFalse(device.nodeinfo_overridden)

    def test_put_location_pins_it_against_future_sightings(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)

        put_resp = self.client.put(
            f"/devices/{node['uuid']}",
            {"latitude": 1.0, "longitude": 2.0},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(put_resp.status_code, 200)
        self.assertTrue(put_resp.json()["location_overridden"])

        _seed_device_sighting(mesh, device_id=1, latitude=99.0, longitude=99.0)

        device = Device.objects.get(pk=uuid.UUID(node["uuid"]))
        self.assertEqual(device.latitude, 1.0)
        self.assertEqual(device.longitude, 2.0)

    def test_put_single_nodeinfo_field_pins_the_whole_group(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)

        put_resp = self.client.put(
            f"/devices/{node['uuid']}", {"name": "Manual Name"}, format="json", **self.auth_headers(owner)
        )
        self.assertEqual(put_resp.status_code, 200)
        self.assertTrue(put_resp.json()["nodeinfo_overridden"])

        _seed_device_sighting(
            mesh, device_id=1, name="Telemetry Name", short_name="TELE", hardware_type="TBEAM", role="CLIENT"
        )

        device = Device.objects.get(pk=uuid.UUID(node["uuid"]))
        self.assertEqual(device.name, "Manual Name")
        self.assertIsNone(device.hardware_type)  # never touched by the sighting either

    def test_put_full_location_null_clears_and_reopens_auto_fill(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)
        self.client.put(
            f"/devices/{node['uuid']}", {"latitude": 1.0, "longitude": 2.0}, format="json", **self.auth_headers(owner)
        )

        clear_resp = self.client.put(
            f"/devices/{node['uuid']}",
            {"latitude": None, "longitude": None},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(clear_resp.status_code, 200)
        self.assertFalse(clear_resp.json()["location_overridden"])
        self.assertIsNone(clear_resp.json()["latitude"])

        _seed_device_sighting(mesh, device_id=1, latitude=5.0, longitude=6.0)

        device = Device.objects.get(pk=uuid.UUID(node["uuid"]))
        self.assertEqual(device.latitude, 5.0)
        self.assertEqual(device.longitude, 6.0)

    def test_put_full_nodeinfo_null_clears_and_reopens_auto_fill(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)
        self.client.put(
            f"/devices/{node['uuid']}", {"name": "Manual Name"}, format="json", **self.auth_headers(owner)
        )

        clear_resp = self.client.put(
            f"/devices/{node['uuid']}",
            {"name": None, "short_name": None, "hardware_type": None, "role": None},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(clear_resp.status_code, 200)
        self.assertFalse(clear_resp.json()["nodeinfo_overridden"])

        _seed_device_sighting(mesh, device_id=1, name="Telemetry Name", hardware_type="TBEAM")

        device = Device.objects.get(pk=uuid.UUID(node["uuid"]))
        self.assertEqual(device.name, "Telemetry Name")
        self.assertEqual(device.hardware_type, "TBEAM")

    def test_post_with_location_sets_override_immediately(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)

        resp = self.client.post(
            "/devices",
            {"node_id": 1, "mesh_id": mesh["id"], "is_gateway": False, "latitude": 1.0, "longitude": 2.0},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["location_overridden"])

        _seed_device_sighting(mesh, device_id=1, latitude=99.0, longitude=99.0)

        device = Device.objects.get(pk=uuid.UUID(resp.json()["uuid"]))
        self.assertEqual(device.latitude, 1.0)

    def test_post_with_hardware_type_sets_nodeinfo_override_immediately(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)

        resp = self.client.post(
            "/devices",
            {"node_id": 1, "mesh_id": mesh["id"], "is_gateway": False, "hardware_type": "TBEAM"},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["nodeinfo_overridden"])

    def test_read_serializer_includes_new_fields(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)

        resp = self.client.get(f"/devices/{node['uuid']}", **self.auth_headers(owner))

        body = resp.json()
        for field in (
            "latitude", "longitude", "location_overridden",
            "name", "short_name", "hardware_type", "role", "nodeinfo_overridden",
        ):
            self.assertIn(field, body)

    def test_put_latitude_without_longitude_returns_400(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        node = self.create_node(owner, mesh, device_id=1)

        resp = self.client.put(
            f"/devices/{node['uuid']}", {"latitude": 1.0}, format="json", **self.auth_headers(owner)
        )
        self.assertEqual(resp.status_code, 400)

    def test_post_latitude_without_longitude_returns_400(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)

        resp = self.client.post(
            "/devices",
            {"node_id": 1, "mesh_id": mesh["id"], "is_gateway": False, "latitude": 1.0},
            format="json",
            **self.auth_headers(owner),
        )
        self.assertEqual(resp.status_code, 400)


class OwnerDeviceIdsTests(RegistryTestCase):
    """GET /owners/me/devices - used by readings to scope telemetry access, see
    docs/architecture.md#readings-authentication."""

    def test_requires_auth(self):
        resp = self.client.get("/owners/me/devices")
        self.assertEqual(resp.status_code, 401)

    def test_includes_own_gateway_and_seen_devices_only(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_gateway(owner, mesh, device_id=111)
        _seed_device_sighting(mesh, device_id=222)

        other_owner = self.create_owner(name="Other", email="devids-other@example.com")
        other_mesh = self.create_mesh(other_owner, channel_id="OtherChan")
        self.create_gateway(other_owner, other_mesh, device_id=999)

        resp = self.client.get("/owners/me/devices", **self.auth_headers(owner))
        self.assertEqual(resp.status_code, 200)
        devices = resp.json()["devices"]
        self.assertEqual({d["node_id"] for d in devices}, {111, 222})
        self.assertTrue(all(d["mesh_id"] == mesh["id"] for d in devices))

    def test_superuser_sees_every_device_id(self):
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        self.create_gateway(owner, mesh, device_id=111)
        _seed_device_sighting(mesh, device_id=222)

        superuser = self.create_owner(name="Admin", email="devids-admin@example.com")
        self.promote_to_superuser(superuser)

        resp = self.client.get("/owners/me/devices", **self.auth_headers(superuser))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual({d["node_id"] for d in resp.json()["devices"]}, {111, 222})

    def test_owner_with_no_devices_gets_empty_list(self):
        owner = self.create_owner()
        resp = self.client.get("/owners/me/devices", **self.auth_headers(owner))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["devices"], [])

    def test_devices_includes_rejected_gateways_too(self):
        # A rejected device still counts - telemetry collected while allowed
        # stays visible after a later rejection.
        owner = self.create_owner()
        mesh = self.create_mesh(owner)
        allowed_gateway = self.create_gateway(owner, mesh, device_id=111)
        rejected_gateway = self.create_gateway(owner, mesh, device_id=222)
        self.client.put(
            f"/devices/{rejected_gateway['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner)
        )

        resp = self.client.get("/owners/me/devices", **self.auth_headers(owner))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            {d["node_id"] for d in resp.json()["devices"]},
            {allowed_gateway["node_id"], rejected_gateway["node_id"]},
        )

    def test_mesh_id_disambiguates_a_device_id_reused_across_meshes(self):
        # device_id is only unique among currently-*allowed* rows
        # (uq_devices_device_id_allowed) - once owner A's device is rejected,
        # owner B's independent device can reuse the same device_id. Without
        # mesh_id there'd be no way to tell the two apart - see
        # docs/architecture.md#readings-authentication.
        owner_a = self.create_owner(name="A", email="devids-dup-a@example.com")
        mesh_a = self.create_mesh(owner_a, channel_id="ChanA")
        gateway_a = self.create_gateway(owner_a, mesh_a, device_id=111)
        self.client.put(
            f"/devices/{gateway_a['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(owner_a)
        )

        owner_b = self.create_owner(name="B", email="devids-dup-b@example.com")
        mesh_b = self.create_mesh(owner_b, channel_id="ChanB")
        self.create_gateway(owner_b, mesh_b, device_id=111)

        superuser = self.create_owner(name="Admin", email="devids-dup-admin@example.com")
        self.promote_to_superuser(superuser)

        resp = self.client.get("/owners/me/devices", **self.auth_headers(superuser))

        self.assertEqual(resp.status_code, 200)
        pairs = {(d["mesh_id"], d["node_id"]) for d in resp.json()["devices"]}
        self.assertEqual(pairs, {(mesh_a["id"], 111), (mesh_b["id"], 111)})
