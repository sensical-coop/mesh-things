from .helpers import RegistryTestCase


class MetricsViewTests(RegistryTestCase):
    def test_metrics_counts_things_that_exist(self):
        owner = self.create_owner(name="Alice", email="alice-metrics@example.com")
        mesh = self.create_mesh(owner, channel_id="MetricsMesh")
        self.create_gateway(owner, mesh, device_id=1001)
        self.create_node(owner, mesh, device_id=1002)

        resp = self.client.get("/metrics")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertGreaterEqual(body["owners"], 1)
        self.assertGreaterEqual(body["meshes"], 1)
        self.assertGreaterEqual(body["devices"], 2)
        self.assertGreaterEqual(body["active_gateways"], 1)

    def test_metrics_excludes_rejected_gateways_from_active_count(self):
        owner = self.create_owner(name="Bob", email="bob-metrics@example.com")
        mesh = self.create_mesh(owner, channel_id="MetricsMesh2")
        gateway = self.create_gateway(owner, mesh, device_id=2001)

        before = self.client.get("/metrics").json()["active_gateways"]

        self.client.put(
            f"/devices/{gateway['uuid']}",
            {"is_allowed": False},
            format="json",
            **self.auth_headers(owner),
        )
        after = self.client.get("/metrics").json()["active_gateways"]

        self.assertEqual(after, before - 1)

    def test_metrics_is_public(self):
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
