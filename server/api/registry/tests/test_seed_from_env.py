import os
from io import StringIO
from unittest.mock import MagicMock

from django.core.management import call_command
from django.test import TestCase

from registry import kafka_publisher
from registry.models import Device, Mesh, Owner

SEED_ENV = {
    "REGISTRY__SEED_OWNER_NAME": "Seed Owner",
    "REGISTRY__SEED_OWNER_EMAIL": "seed@example.com",
    "REGISTRY__SEED_CHANNEL_ID": "SeedChan",
    "REGISTRY__SEED_PSK_B64": "AAAA",
    "REGISTRY__SEED_GATEWAY_DEVICE_ID": "111222333",
}


class SeedFromEnvTests(TestCase):
    def setUp(self):
        self.fake_publisher = MagicMock()
        self._original_publisher = kafka_publisher._publisher
        kafka_publisher._publisher = self.fake_publisher

    def tearDown(self):
        kafka_publisher._publisher = self._original_publisher

    def test_noop_when_env_vars_not_fully_set(self):
        output = StringIO()
        call_command("seed_from_env", stdout=output)
        self.assertIn("nothing to seed", output.getvalue())
        self.assertEqual(Owner.objects.count(), 0)

    def test_seeds_owner_mesh_and_gateway(self):
        old = {k: os.environ.get(k) for k in SEED_ENV}
        os.environ.update(SEED_ENV)
        try:
            call_command("seed_from_env", stdout=StringIO())
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        owner = Owner.objects.get(email="seed@example.com")
        mesh = Mesh.objects.get(owner=owner, channel_id="SeedChan")
        gateway = Device.objects.get(mesh=mesh, device_id=111222333, is_gateway=True)
        self.assertTrue(gateway.is_allowed)
        self.fake_publisher.publish_gateway_upsert.assert_called_once()

    def test_is_idempotent(self):
        old = {k: os.environ.get(k) for k in SEED_ENV}
        os.environ.update(SEED_ENV)
        try:
            call_command("seed_from_env", stdout=StringIO())
            call_command("seed_from_env", stdout=StringIO())
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        self.assertEqual(Owner.objects.filter(email="seed@example.com").count(), 1)
        self.assertEqual(Mesh.objects.filter(channel_id="SeedChan").count(), 1)
        self.assertEqual(Device.objects.filter(device_id=111222333, is_gateway=True).count(), 1)
        self.assertEqual(self.fake_publisher.publish_gateway_upsert.call_count, 1)
