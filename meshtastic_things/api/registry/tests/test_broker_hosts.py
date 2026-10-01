from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from registry import broker_hosts

from .helpers import RegistryTestCase

LOCAL = [
    "localhost",
    "LOCALHOST.",
    "localhost.localdomain",
    "api.localhost",
    "127.0.0.1",
    "127.8.9.10",
    "127.1",
    "2130706433",
    "0x7f000001",
    "0.0.0.0",
    "0",
    "::1",
    "[::1]",
    "::",
    "::ffff:127.0.0.1",
]
INTERNAL = ["169.254.169.254", "fe80::1", "224.0.0.1", "240.0.0.1"]
PRIVATE = ["10.0.0.5", "172.16.3.4", "192.168.1.20", "100.64.0.1", "fd12:3456::1"]


class RefusalTests(SimpleTestCase):
    def setUp(self):
        patcher = patch.object(broker_hosts, "resolve", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_this_machine_is_refused_however_it_is_spelled(self):
        for host in LOCAL:
            self.assertIsNotNone(broker_hosts.refusal(host), host)

    def test_link_local_multicast_and_reserved_are_refused(self):
        for host in INTERNAL:
            self.assertIsNotNone(broker_hosts.refusal(host), host)

    def test_bare_hostnames_are_refused(self):
        for host in ("emqx", "kafka", "mosquitto", "registry_api"):
            self.assertIsNotNone(broker_hosts.refusal(host), host)

    def test_private_addresses_are_refused_by_default(self):
        for host in PRIVATE:
            self.assertIsNotNone(broker_hosts.refusal(host), host)

    @override_settings(SOURCES_ALLOW_PRIVATE_BROKERS=True)
    def test_private_addresses_can_be_allowed_but_never_this_machine(self):
        for host in PRIVATE:
            self.assertIsNone(broker_hosts.refusal(host), host)
        for host in LOCAL + INTERNAL:
            self.assertIsNotNone(broker_hosts.refusal(host), host)

    def test_public_addresses_and_names_are_accepted(self):
        for host in ("mqtt.meshtastic.org", "8.8.8.8", "2001:4860:4860::8888"):
            self.assertIsNone(broker_hosts.refusal(host), host)

    def test_a_name_resolving_to_this_machine_is_refused(self):
        with patch.object(broker_hosts, "resolve", return_value=["93.184.215.14", "127.0.0.1"]):
            reason = broker_hosts.refusal("sneaky.example.org")

        self.assertIn("resolves to 127.0.0.1", reason)

    def test_legacy_ipv4_forms_parse(self):
        self.assertEqual(str(broker_hosts.parse_ip("127.1")), "127.0.0.1")
        self.assertIsNone(broker_hosts.parse_ip("beef.example.org"))


class SourceServerTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.operator = self.create_owner(name="Operator", email="hosts-op@example.com")
        self.promote_to_operator(self.operator)

    def post(self, server):
        return self.client.post(
            "/sources", {"server": server, "topic": "msh/EU/#", "terms_version": "sources-2026-09"}, format="json",
            **self.auth_headers(self.operator),
        )

    def test_local_brokers_are_refused_on_create(self):
        for server in ("localhost:1883", "127.0.0.1:1883", "[::1]:1883", "emqx:1883", "169.254.169.254:80"):
            resp = self.post(server)
            self.assertEqual(resp.status_code, 400, server)
            self.assertIn("server", resp.json())
        self.fake_emqx.apply_source.assert_not_called()

    def test_local_brokers_are_refused_on_update(self):
        source = self.create_source(self.operator)

        resp = self.client.put(
            f"/sources/{source['id']}", {"server": "127.0.0.1:1883"}, format="json", **self.auth_headers(self.operator)
        )

        self.assertEqual(resp.status_code, 400)

    @override_settings(SOURCES_ALLOW_PRIVATE_BROKERS=True)
    def test_a_lan_broker_is_accepted_when_allowed(self):
        self.assertEqual(self.post("192.168.1.20:1883").status_code, 201)


class OwnBrokerTests(SimpleTestCase):
    ADDRESSES = {"mqtt.example.org": ["203.0.113.7"], "alias.example.org": ["203.0.113.7"], "other.example.org": ["198.51.100.1"]}

    def setUp(self):
        patcher = patch.object(broker_hosts, "resolve", side_effect=lambda host: self.ADDRESSES.get(host, []))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_same_name_however_it_is_spelled(self):
        self.assertTrue(broker_hosts.is_own_broker("MQTT.example.org.", ["mqtt.example.org"]))

    def test_an_address_or_another_name_for_the_same_broker(self):
        self.assertTrue(broker_hosts.is_own_broker("203.0.113.7", ["mqtt.example.org"]))
        self.assertTrue(broker_hosts.is_own_broker("alias.example.org", ["mqtt.example.org"]))

    def test_another_broker_or_an_unresolvable_one(self):
        self.assertFalse(broker_hosts.is_own_broker("other.example.org", ["mqtt.example.org"]))
        self.assertFalse(broker_hosts.is_own_broker("unknown.example.org", ["mqtt.example.org", "", "nowhere.example.org"]))
