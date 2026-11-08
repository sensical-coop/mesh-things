"""The broker and shared login verified owners set their gateways up with."""
from django.test import override_settings

from registry.models import Owner

from .helpers import RegistryTestCase

BROKER = {
    "GATEWAY_BROKER_HOST": "mqtt.example.org",
    "GATEWAY_BROKER_PORT": 8883,
    "GATEWAY_BROKER_TLS": True,
    "GATEWAY_BROKER_USERNAME": "gateways",
    "GATEWAY_BROKER_PASSWORD": "shared-secret",
}


@override_settings(**BROKER)
class GatewayBrokerTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_owner()

    def test_a_verified_owner_gets_the_broker_and_login(self):
        resp = self.client.get("/owners/me/gateway-broker", **self.auth_headers(self.owner))

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            resp.json(),
            {"host": "mqtt.example.org", "port": 8883, "tls": True, "username": "gateways", "password": "shared-secret"},
        )

    def test_an_unverified_owner_is_refused(self):
        Owner.objects.filter(pk=self.owner["id"]).update(is_active=False)

        resp = self.client.get("/owners/me/gateway-broker", **self.auth_headers(self.owner))

        self.assertEqual(resp.status_code, 403)

    def test_an_anonymous_caller_is_refused(self):
        resp = self.client.get("/owners/me/gateway-broker")

        self.assertIn(resp.status_code, (401, 403))
        self.assertNotIn("shared-secret", resp.content.decode())

    @override_settings(GATEWAY_BROKER_HOST="")
    def test_an_instance_without_a_broker_answers_not_found(self):
        resp = self.client.get("/owners/me/gateway-broker", **self.auth_headers(self.owner))

        self.assertEqual(resp.status_code, 404)
