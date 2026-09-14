import uuid
from io import StringIO
from unittest.mock import MagicMock

from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase

from registry import kafka_publisher
from registry.models import Owner


class RegistryTestCase(APITestCase):
    """Base class for every registry test"""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.fake_publisher = MagicMock()
        self._original_publisher = kafka_publisher._publisher
        kafka_publisher._publisher = self.fake_publisher

    def tearDown(self):
        kafka_publisher._publisher = self._original_publisher
        cache.clear()
        super().tearDown()

    DEFAULT_PASSWORD = "Correct-Horse-Battery-42"

    def create_owner(self, name="Test Owner", email="owner@example.com", password=None) -> dict:
        """Signs up then marks verified directly in the DB"""
        resp = self.client.post(
            "/owners",
            {"name": name, "email": email, "password": password or self.DEFAULT_PASSWORD},
            format="json",
        )
        assert resp.status_code == 201, resp.content
        body = resp.json()
        o = Owner.objects.get(pk=uuid.UUID(body["id"]))
        o.is_active = True
        o.email_verified_at = timezone.now()
        o.save(update_fields=["is_active", "email_verified_at"])
        body["is_active"] = True
        body["email_verified_at"] = o.email_verified_at.isoformat()
        return body

    @staticmethod
    def auth_headers(owner_or_key) -> dict:
        key = owner_or_key["api_key"] if isinstance(owner_or_key, dict) else owner_or_key
        return {"HTTP_AUTHORIZATION": f"Bearer {key}"}

    def create_mesh(self, owner, channel_id="X", psk_b64="AAAA", label=None) -> dict:
        resp = self.client.post(
            "/meshes",
            {"channel_id": channel_id, "psk_b64": psk_b64, "label": label},
            format="json",
            **self.auth_headers(owner),
        )
        assert resp.status_code == 201, resp.content
        return resp.json()

    def create_gateway(self, owner, mesh, device_id=1, label=None) -> dict:
        resp = self.client.post(
            "/devices",
            {"device_id": device_id, "mesh_id": mesh["id"], "is_gateway": True, "label": label},
            format="json",
            **self.auth_headers(owner),
        )
        assert resp.status_code == 201, resp.content
        return resp.json()

    def create_node(self, owner, mesh, device_id=1, label=None, admin_keys_b64=None) -> dict:
        resp = self.client.post(
            "/devices",
            {
                "device_id": device_id,
                "mesh_id": mesh["id"],
                "is_gateway": False,
                "label": label,
                "admin_keys_b64": admin_keys_b64 or [],
            },
            format="json",
            **self.auth_headers(owner),
        )
        assert resp.status_code == 201, resp.content
        return resp.json()

    @staticmethod
    def promote_to_superuser(owner) -> None:
        o = Owner.objects.get(pk=uuid.UUID(owner["id"]))
        o.is_superuser = True
        o.save(update_fields=["is_superuser"])


class SeededCatalogTestCase(RegistryTestCase):
    """For tests needing the protobuf catalog. setUpTestData adds once per class."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        call_command("seed_measurement_catalog", stdout=StringIO())
