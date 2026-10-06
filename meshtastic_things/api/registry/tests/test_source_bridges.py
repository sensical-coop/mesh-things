"""Each source's bridge follows the channels, discovery flags and gateways of its meshes."""
from registry.models import Device, Mesh, Source

from .helpers import MESH_TERMS, RegistryTestCase


class _SourceBridgeCase(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.operator = self.create_owner(name="Operator", email="bridge-op@example.com")
        self.promote_to_operator(self.operator)
        self.source = self.create_source(self.operator)
        self.headers = self.auth_headers(self.operator)
        self.fake_emqx.apply_source.reset_mock()

    def _mesh(self, channel_id="LongFast", **fields) -> dict:
        resp = self.client.post(
            "/meshes",
            {**MESH_TERMS, "channel_id": channel_id, "psk_b64": "AQ==", "source_id": self.source["id"], **fields},
            format="json",
            **self.headers,
        )
        assert resp.status_code == 201, resp.content
        return resp.json()

    def _applied(self) -> dict:
        """The channels of the last bridge applied."""
        return self.fake_emqx.apply_source.call_args.args[1]



class SourceBridgeTests(_SourceBridgeCase):
    def test_a_channel_without_gateways_or_discovery_is_not_subscribed(self):
        self._mesh()

        self.assertEqual(self._applied(), {})

    def test_a_registered_gateway_subscribes_its_channel_and_passes_only_it(self):
        mesh = self._mesh()

        self.create_gateway(self.operator, mesh, device_id=0xAABBCCDD)

        self.assertEqual(self._applied(), {"LongFast": ["!aabbccdd"]})

    def test_discovery_passes_every_gateway_on_its_channel(self):
        mesh = self._mesh(discover_gateways=True)
        self.create_gateway(self.operator, mesh, device_id=1)

        self.assertEqual(self._applied(), {"LongFast": None})

    def test_rejected_gateways_and_meshes_on_other_sources_are_left_out(self):
        mesh = self._mesh()
        gateway = self.create_gateway(self.operator, mesh, device_id=1)
        self.create_gateway(self.operator, self.create_mesh(self.operator, channel_id="LongFast"), device_id=2)

        self.client.put(f"/devices/{gateway['uuid']}", {"is_allowed": False}, format="json", **self.headers)

        self.assertEqual(self._applied(), {})

    def test_switching_discovery_resyncs_the_bridge(self):
        mesh = self._mesh()

        self.client.put(f"/meshes/{mesh['id']}", {"discover_gateways": True}, format="json", **self.headers)

        self.assertEqual(self._applied(), {"LongFast": None})

    def test_changing_the_channel_moves_the_subscription(self):
        mesh = self._mesh()
        self.create_gateway(self.operator, mesh, device_id=1)

        self.client.put(f"/meshes/{mesh['id']}", {"channel_id": "Private"}, format="json", **self.headers)

        self.assertEqual(self._applied(), {"Private": ["!00000001"]})

    def test_deleting_a_mesh_drops_its_channel(self):
        mesh = self._mesh()
        self.create_gateway(self.operator, mesh, device_id=1)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.delete(f"/meshes/{mesh['id']}", **self.headers)

        self.assertEqual(self._applied(), {})

    def test_deleting_a_gateway_drops_it_from_the_rule(self):
        mesh = self._mesh()
        self.create_gateway(self.operator, mesh, device_id=1)
        second = self.create_gateway(self.operator, mesh, device_id=2)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.delete(f"/devices/{second['uuid']}", **self.headers)

        self.assertEqual(self._applied(), {"LongFast": ["!00000001"]})

    def test_a_removal_is_kept_when_the_bridge_cannot_be_updated(self):
        mesh = self._mesh()
        gateway = self.create_gateway(self.operator, mesh, device_id=1)
        self.fake_emqx.apply_source.side_effect = RuntimeError("emqx down")

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.delete(f"/devices/{gateway['uuid']}", **self.headers)

        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Device.objects.filter(pk=gateway["uuid"]).exists())

    def test_a_default_broker_mesh_never_touches_emqx(self):
        mesh = self.create_mesh(self.operator)

        self.create_gateway(self.operator, mesh, device_id=1)

        self.fake_emqx.apply_source.assert_not_called()

    def test_a_paused_source_gets_no_bridge(self):
        mesh = self._mesh()
        Source.objects.filter(pk=self.source["id"]).update(paused_at="2026-01-01T00:00:00Z")
        self.fake_emqx.apply_source.reset_mock()

        self.create_gateway(self.operator, mesh, device_id=1)

        self.fake_emqx.apply_source.assert_not_called()


class SourceBridgeFailureTests(_SourceBridgeCase):
    """A change that would add traffic is rolled back when EMQX refuses it."""

    def test_a_gateway_is_not_registered_when_the_bridge_fails(self):
        mesh = self._mesh()
        self.fake_emqx.apply_source.side_effect = RuntimeError("emqx down")

        resp = self.client.post(
            "/devices", {"node_id": 1, "mesh_id": mesh["id"], "is_gateway": True}, format="json", **self.headers
        )

        self.assertEqual(resp.status_code, 502)
        self.assertFalse(Device.objects.exists())
        self.fake_publisher.publish_gateway_upsert.assert_not_called()

    def test_a_mesh_is_not_created_when_the_bridge_fails(self):
        self.fake_emqx.apply_source.side_effect = RuntimeError("emqx down")

        resp = self.client.post(
            "/meshes",
            {**MESH_TERMS, "channel_id": "LongFast", "psk_b64": "AQ==", "source_id": self.source["id"]},
            format="json",
            **self.headers,
        )

        self.assertEqual(resp.status_code, 502)
        self.assertFalse(Mesh.objects.exists())

    def test_a_mesh_update_is_rolled_back_when_the_bridge_fails(self):
        mesh = self._mesh()
        self.fake_emqx.apply_source.side_effect = RuntimeError("emqx down")

        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.put(f"/meshes/{mesh['id']}", {"channel_id": "Other"}, format="json", **self.headers)

        self.assertEqual(resp.status_code, 502)
        self.assertEqual(Mesh.objects.get(pk=mesh["id"]).channel_id, "LongFast")


class ChannelNameTests(RegistryTestCase):
    def test_a_channel_cannot_hold_topic_separators_or_wildcards(self):
        owner = self.create_owner(email="channel-name@example.com")
        for channel in ("a/b", "a+", "#"):
            resp = self.client.post(
                "/meshes",
                {**MESH_TERMS, "channel_id": channel, "psk_b64": "AQ=="},
                format="json",
                **self.auth_headers(owner),
            )
            self.assertEqual(resp.status_code, 400, channel)
