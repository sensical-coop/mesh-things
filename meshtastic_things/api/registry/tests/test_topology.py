"""Traceroutes and RF links: what the topology consumer stores and the routes that read it."""
from datetime import datetime, timedelta, timezone

from registry import topology
from registry.data_lifecycle import run_pass
from registry.models import Device, Mesh, RfLink, Traceroute

from .helpers import RegistryTestCase

A, R1, B = 0x0A, 0x11, 0x0B
NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


def _reply(mesh_id, gateway_id=100, route_back=(), snr_back=()):
    return {
        "mesh_id": mesh_id,
        "node_id": B,
        "to": A,
        "packet_id": 555,
        "request_id": 444,
        "portnum": 70,
        "gateway_id": gateway_id,
        "payload": {"route": [R1], "snr_towards": [24, 16], "route_back": list(route_back), "snr_back": list(snr_back)},
    }


class TopologyTestCase(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_owner()
        self.mesh = self.create_mesh(self.owner)
        self.mesh_id = self.mesh["id"]

    def links(self):
        return {(l.from_node, l.to_node, l.source): l for l in RfLink.objects.all()}


class RecordTracerouteTests(TopologyTestCase):
    def test_a_reply_is_stored_with_its_hops_as_links(self):
        topology.record_decoded(_reply(self.mesh_id), now=NOW)

        stored = Traceroute.objects.get()
        self.assertEqual((stored.from_node, stored.to_node, stored.request_id), (B, A, 444))
        self.assertEqual(stored.snr_towards, [6.0, 4.0])
        links = self.links()
        self.assertEqual(set(links), {(A, R1, "traceroute"), (R1, B, "traceroute")})
        self.assertEqual(links[(A, R1, "traceroute")].last_snr, 6.0)

    def test_a_second_gateway_adds_itself_and_only_the_new_hops(self):
        topology.record_decoded(_reply(self.mesh_id, gateway_id=100), now=NOW)
        topology.record_decoded(
            _reply(self.mesh_id, gateway_id=200, route_back=[R1], snr_back=[8]), now=NOW + timedelta(seconds=5)
        )

        stored = Traceroute.objects.get()
        self.assertEqual(stored.gateway_ids, [100, 200])
        self.assertEqual(stored.route_back, [R1])
        links = self.links()
        self.assertEqual(links[(A, R1, "traceroute")].samples, 1)
        self.assertEqual(links[(B, R1, "traceroute")].last_snr, 2.0)

    def test_neighbor_info_becomes_links_into_the_reporter(self):
        topology.record_decoded(
            {"mesh_id": self.mesh_id, "node_id": 7, "portnum": 71, "payload": {"node_id": 7, "neighbors": [{"node_id": 9, "snr": 5.5}]}},
            now=NOW,
        )

        self.assertEqual(set(self.links()), {(9, 7, "neighborinfo")})

    def test_other_portnums_and_unknown_meshes_are_ignored(self):
        topology.record_decoded({**_reply(self.mesh_id), "portnum": 67}, now=NOW)
        topology.record_decoded(_reply("00000000-0000-0000-0000-000000000000"), now=NOW)

        self.assertFalse(Traceroute.objects.exists())


class RecordDirectLinkTests(TopologyTestCase):
    def _summary(self, hour: int, samples=2, snr_sum=10.0):
        start = int((NOW + timedelta(hours=hour)).timestamp() * 1000)
        return {
            "mesh_id": self.mesh_id, "from_node": 7, "to_node": 100, "source": "direct",
            "samples": samples, "snr_sum": snr_sum, "first_seen": start, "last_seen": start + 60_000,
        }

    def test_hourly_summaries_add_up(self):
        topology.record_link(self._summary(0, samples=2, snr_sum=10.0))
        topology.record_link(self._summary(1, samples=1, snr_sum=2.0))

        link = RfLink.objects.get()
        self.assertEqual((link.samples, link.snr_sum, link.last_snr), (3, 12.0, 2.0))
        self.assertEqual(link.first_seen, NOW)

    def test_a_late_summary_does_not_replace_the_last_snr(self):
        topology.record_link(self._summary(1, samples=1, snr_sum=2.0))
        topology.record_link(self._summary(0, samples=2, snr_sum=10.0))

        link = RfLink.objects.get()
        self.assertEqual(link.last_snr, 2.0)
        self.assertEqual(link.last_seen, NOW + timedelta(hours=1, minutes=1))


class LinksRouteTests(TopologyTestCase):
    def setUp(self):
        super().setUp()
        self.node_a = self.create_node(self.owner, self.mesh, device_id=A)
        Device.objects.filter(pk=self.node_a["uuid"]).update(latitude=41.3874, longitude=2.1686)
        self.node_r1 = self.create_node(self.owner, self.mesh, device_id=R1)
        Device.objects.filter(pk=self.node_r1["uuid"]).update(latitude=40.4168, longitude=-3.7038)
        now = datetime.now(timezone.utc)
        topology.add_link(self.mesh_id, A, R1, "traceroute", 2, 8.0, 5.0, now, now)
        topology.add_link(self.mesh_id, R1, B, "direct", 4, 4.0, 1.0, now, now)
        old = now - timedelta(days=10)
        topology.add_link(self.mesh_id, 99, A, "neighborinfo", 1, 1.0, 1.0, old, old)

    def url(self, mesh_id=None):
        return f"/meshes/{mesh_id or self.mesh_id}/links"

    def test_links_heard_within_the_window_longest_first(self):
        body = self.client.get(self.url(), **self.auth_headers(self.owner)).json()

        self.assertEqual([(l["from_node"], l["to_node"]) for l in body], [(A, R1), (R1, B)])
        self.assertEqual(body[0]["from_device_uuid"], self.node_a["uuid"])
        self.assertEqual(body[0]["snr_mean"], 4.0)
        self.assertAlmostEqual(body[0]["distance_km"], 505, delta=2)
        self.assertIsNone(body[1]["distance_km"])

        wider = self.client.get(self.url(), {"since": "30d"}, **self.auth_headers(self.owner)).json()
        self.assertEqual(len(wider), 3)

    def test_filter_by_node_in_either_form(self):
        for node in (str(B), f"!{B:08x}"):
            body = self.client.get(self.url(), {"node_id": node}, **self.auth_headers(self.owner)).json()
            self.assertEqual([(l["from_node"], l["to_node"]) for l in body], [(R1, B)])

    def test_bad_parameters_are_400(self):
        self.assertEqual(self.client.get(self.url(), {"since": "2d"}, **self.auth_headers(self.owner)).status_code, 400)
        self.assertEqual(self.client.get(self.url(), {"node_id": "x"}, **self.auth_headers(self.owner)).status_code, 400)

    def test_private_meshes_are_hidden_and_public_ones_open(self):
        outsider = self.create_owner(name="Outsider", email="outsider@example.com")
        self.assertEqual(self.client.get(self.url(), **self.auth_headers(outsider)).status_code, 404)
        self.assertEqual(self.client.get(self.url()).status_code, 404)

        Mesh.objects.filter(pk=self.mesh_id).update(is_public=True)
        self.assertEqual(self.client.get(self.url()).status_code, 200)

    def test_a_rejected_node_is_not_named_to_viewers(self):
        Device.objects.filter(pk=self.node_a["uuid"]).update(is_allowed=False)
        Mesh.objects.filter(pk=self.mesh_id).update(is_public=True)

        body = self.client.get(self.url()).json()

        self.assertIsNone(body[0]["from_device_uuid"] if body[0]["from_node"] == A else body[1]["from_device_uuid"])


class TraceroutesRouteTests(TopologyTestCase):
    def setUp(self):
        super().setUp()
        for packet_id, minutes in ((1, 0), (2, 10), (3, 20)):
            topology.record_decoded(
                {**_reply(self.mesh_id), "packet_id": packet_id}, now=NOW + timedelta(minutes=minutes)
            )
        topology.record_decoded(
            {"mesh_id": self.mesh_id, "node_id": 50, "to": 51, "packet_id": 9, "portnum": 70,
             "payload": {"route": [52], "snr_towards": [4]}},
            now=NOW + timedelta(minutes=30),
        )

    def url(self):
        return f"/meshes/{self.mesh_id}/traceroutes"

    def test_newest_first_with_both_directions_spelled_out(self):
        body = self.client.get(self.url(), **self.auth_headers(self.owner)).json()

        self.assertEqual([t["packet_id"] for t in body], [9, 3, 2, 1])
        request, reply = body[0], body[1]
        self.assertEqual((request["origin"], request["towards"], request["complete"]), (50, [50, 52], False))
        self.assertEqual((reply["origin"], reply["target"], reply["towards"]), (A, B, [A, R1, B]))
        self.assertTrue(reply["complete"])
        self.assertEqual(reply["snr_towards"], [6.0, 4.0])

    def test_pages_with_limit_and_before(self):
        first = self.client.get(self.url(), {"limit": 2}, **self.auth_headers(self.owner)).json()
        rest = self.client.get(
            self.url(), {"limit": 2, "before": first[-1]["heard_at"]}, **self.auth_headers(self.owner)
        ).json()

        self.assertEqual([t["packet_id"] for t in first + rest], [9, 3, 2, 1])

    def test_filter_by_a_node_on_the_route(self):
        body = self.client.get(self.url(), {"node_id": R1}, **self.auth_headers(self.owner)).json()

        self.assertEqual([t["packet_id"] for t in body], [3, 2, 1])


class PruneTests(TopologyTestCase):
    def test_the_lifecycle_pass_drops_what_was_not_heard_for_30_days(self):
        topology.record_decoded(_reply(self.mesh_id), now=NOW - timedelta(days=31))
        topology.add_link(self.mesh_id, 1, 2, "direct", 1, 1.0, 1.0, NOW, NOW)

        result = run_pass(now=NOW)

        self.assertEqual(result["topology_pruned"], 3)  # the traceroute and its two hops
        self.assertEqual(list(RfLink.objects.values_list("from_node", flat=True)), [1])
