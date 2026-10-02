"""A self-hosted instance with REGISTRY__TERMS_ENFORCED=false asks for no terms at all."""
from datetime import timedelta

from django.core import mail
from django.test import override_settings
from django.utils import timezone

from registry import data_lifecycle
from registry.models import DataDeletion, Mesh, Owner, Source, TermsAcceptance, TermsKind

from .helpers import RegistryTestCase


@override_settings(TERMS_ENFORCED=False, DATA_RETENTION_DAYS=30)
class TermsOffTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_owner(name="Pi", email="pi@example.com")
        self.promote_to_operator(self.owner)

    def test_every_terms_route_is_not_found(self):
        mesh = self.create_mesh(self.owner)
        source = self.create_source(self.owner)
        headers = self.auth_headers(self.owner)

        for path in ("/terms", "/meshes/terms", "/sources/terms"):
            self.assertEqual(self.client.get(path, **headers).status_code, 404, path)
        for path in (
            "/owners/me/terms-acceptance",
            f"/meshes/{mesh['id']}/terms-acceptance",
            f"/sources/{source['id']}/terms-acceptance",
        ):
            self.assertEqual(
                self.client.post(path, {"terms_version": "x"}, format="json", **headers).status_code, 404, path
            )

    def test_nothing_needs_terms_and_nothing_is_recorded(self):
        signup = self.client.post(
            "/owners", {"name": "Solo", "email": "solo@example.com", "password": self.DEFAULT_PASSWORD}, format="json"
        )
        headers = self.auth_headers(self.owner)
        mesh = self.client.post("/meshes", {"channel_id": "A", "psk_b64": "AQ=="}, format="json", **headers)
        stale = self.client.post(
            "/meshes", {"channel_id": "B", "psk_b64": "AQ==", "terms_version": "meshes-2020-01"}, format="json", **headers
        )
        source = self.client.post(
            "/sources", {"server": "r.example.org:1883", "topic": "msh/EU/#"}, format="json", **headers
        )

        self.assertEqual(
            (signup.status_code, mesh.status_code, stale.status_code, source.status_code), (201, 201, 201, 201)
        )
        self.assertIsNone(mesh.json()["terms_accepted_version"])
        self.assertFalse(TermsAcceptance.objects.exists())

    def test_moving_a_mesh_onto_the_default_broker_needs_no_terms(self):
        source = self.create_source(self.owner)
        mesh = self.client.post(
            "/meshes", {"channel_id": "A", "psk_b64": "AQ==", "source_id": source["id"]}, format="json",
            **self.auth_headers(self.owner),
        ).json()

        resp = self.client.put(
            f"/meshes/{mesh['id']}", {"source_id": None}, format="json", **self.auth_headers(self.owner)
        )

        self.assertEqual(resp.status_code, 200)

    def test_the_lifecycle_neither_notifies_nor_pauses(self):
        mesh = self.create_mesh(self.owner)
        source = self.create_source(self.owner)
        past = timezone.now() - timedelta(days=1)
        for kwargs in ({"mesh_id": mesh["id"]}, {"source_id": source["id"]}):
            TermsAcceptance.objects.create(
                kind=TermsKind.MESH if "mesh_id" in kwargs else TermsKind.SOURCE,
                owner_id=self.owner["id"],
                acceptor_name="Pi",
                acceptor_email="pi@example.com",
                terms_version="x",
                locale="en",
                text_hash="x",
                expires_at=past,
                **kwargs,
            )
        mail.outbox.clear()

        result = data_lifecycle.run_pass()

        self.assertEqual((result["renewal_notices"], result["paused_meshes"], result["paused_sources"]), (0, 0, 0))
        self.assertEqual(mail.outbox, [])

    def test_switching_terms_off_resumes_what_a_lapse_paused(self):
        mesh = self.create_mesh(self.owner)
        self.create_gateway(self.owner, mesh, device_id=5)
        source = self.create_source(self.owner)
        now = timezone.now()
        Mesh.objects.filter(pk=mesh["id"]).update(paused_at=now)
        Source.objects.filter(pk=source["id"]).update(paused_at=now)
        lapsed = DataDeletion.objects.create(
            mesh_id=mesh["id"], reason="terms_lapsed", delete_after=now + timedelta(days=30), data_until=now
        )
        self.fake_publisher.reset_mock()
        self.fake_emqx.apply_source.reset_mock()

        self.assertEqual(data_lifecycle.resume_paused(), 2)

        self.assertIsNone(Mesh.objects.get(pk=mesh["id"]).paused_at)
        self.assertIsNone(Source.objects.get(pk=source["id"]).paused_at)
        self.fake_publisher.publish_gateway_upsert.assert_called_once()
        self.fake_emqx.apply_source.assert_called_once()
        lapsed.refresh_from_db()
        self.assertEqual(lapsed.status, "cancelled")

    def test_deleting_a_mesh_still_schedules_its_readings(self):
        mesh = self.create_mesh(self.owner)

        self.client.delete(f"/meshes/{mesh['id']}", **self.auth_headers(self.owner))

        self.assertEqual(DataDeletion.objects.get().reason, "mesh_deleted")


class TermsOnByDefaultTests(RegistryTestCase):
    def test_resume_does_nothing_while_terms_are_enforced(self):
        owner = self.create_owner(name="Prod", email="prod@example.com")
        mesh = self.create_mesh(owner)
        Mesh.objects.filter(pk=mesh["id"]).update(paused_at=timezone.now())

        self.assertEqual(data_lifecycle.resume_paused(), 0)
        self.assertIsNotNone(Mesh.objects.get(pk=mesh["id"]).paused_at)

    def test_signup_without_terms_is_refused(self):
        resp = self.client.post(
            "/owners", {"name": "No", "email": "no@example.com", "password": self.DEFAULT_PASSWORD}, format="json"
        )

        self.assertIn("terms_version", resp.json())
        self.assertFalse(Owner.objects.filter(email="no@example.com").exists())
