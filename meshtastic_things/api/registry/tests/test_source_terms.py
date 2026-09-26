from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from registry import terms
from registry.models import DataDeletion, Owner, Source, TermsAcceptance, TermsKind

SOURCE_VERSION = terms.VERSIONS[TermsKind.SOURCE]

from .helpers import MESH_TERMS, RegistryTestCase


class SourceTermsTestCase(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.operator = self.create_owner(name="Operator", email="terms-op@example.com")
        self.promote_to_operator(self.operator)

    def post_source(self, **fields):
        body = {"server": "r.example.org:1883", "topic": "msh/EU/#", "terms_version": SOURCE_VERSION, **fields}
        return self.client.post("/sources", body, format="json", **self.auth_headers(self.operator))


class ServingTests(SourceTermsTestCase):
    def test_operators_get_the_terms_in_their_locale(self):
        resp = self.client.get("/sources/terms?locale=es", **self.auth_headers(self.operator))

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual((body["version"], body["locale"]), (SOURCE_VERSION, "es"))
        self.assertEqual(
            [s["id"] for s in body["statements"]],
            ["controller", "authority", "lawfulBasis", "minimisation", "sensitive"],
        )

    def test_an_unknown_locale_falls_back_to_english(self):
        self.assertEqual(
            self.client.get("/sources/terms?locale=fr", **self.auth_headers(self.operator)).json()["locale"], "en"
        )

    def test_members_cannot_read_the_terms(self):
        member = self.create_owner(name="Member", email="terms-member@example.com")

        self.assertEqual(self.client.get("/sources/terms", **self.auth_headers(member)).status_code, 403)

    @override_settings(DATA_RETENTION_DAYS=365, DATA_DELETION_GRACE_DAYS=30)
    def test_the_footnote_states_the_retention_period(self):
        footnote = self.client.get("/sources/terms", **self.auth_headers(self.operator)).json()["footnote"]

        self.assertIn("365 days", footnote)
        self.assertIn("30 days", footnote)


class AcceptanceOnCreateTests(SourceTermsTestCase):
    def test_creating_a_source_records_the_acceptance(self):
        resp = self.post_source(terms_locale="es")

        self.assertEqual(resp.status_code, 201)
        acceptance = TermsAcceptance.objects.get(source_id=resp.json()["id"], kind="source")
        self.assertEqual(str(acceptance.owner_id), self.operator["id"])
        self.assertEqual(
            (acceptance.acceptor_email, acceptance.acceptor_name), ("terms-op@example.com", "Operator")
        )
        self.assertEqual((acceptance.terms_version, acceptance.locale), (SOURCE_VERSION, "es"))
        self.assertEqual(acceptance.text_hash, terms.text_hash(terms.terms(TermsKind.SOURCE, "es")))
        self.assertIsNone(acceptance.expires_at)
        self.assertEqual(resp.json()["terms_accepted_version"], SOURCE_VERSION)
        self.assertNotIn("terms_version", resp.json())

    def test_a_missing_or_stale_version_is_refused(self):
        self.assertIn("terms_version", self.post_source(terms_version=None).json())
        self.assertEqual(self.post_source(terms_version="sources-2020-01").status_code, 400)
        self.assertFalse(Source.objects.exists())
        self.fake_emqx.apply_source.assert_not_called()

    def test_a_failed_bridge_keeps_neither_the_source_nor_the_acceptance(self):
        self.fake_emqx.apply_source.side_effect = RuntimeError("emqx down")

        self.assertEqual(self.post_source().status_code, 502)
        self.assertFalse(Source.objects.exists())
        self.assertFalse(TermsAcceptance.objects.filter(kind="source").exists())

    @override_settings(DATA_RETENTION_DAYS=365)
    def test_with_a_retention_period_the_acceptance_expires(self):
        resp = self.post_source()

        acceptance = TermsAcceptance.objects.get(source_id=resp.json()["id"], kind="source")
        self.assertEqual((acceptance.expires_at - acceptance.accepted_at).days, 365)
        self.assertIsNotNone(resp.json()["terms_expires_at"])

    def test_the_acceptance_outlives_the_source_and_the_operator(self):
        source = self.post_source().json()
        self.client.delete(f"/sources/{source['id']}", **self.auth_headers(self.operator))
        Owner.objects.filter(pk=self.operator["id"]).delete()

        acceptance = TermsAcceptance.objects.get(kind="source")
        self.assertIsNone(acceptance.source_id)
        self.assertIsNone(acceptance.owner_id)
        self.assertEqual(acceptance.acceptor_email, "terms-op@example.com")

    def test_editing_does_not_ask_for_the_terms_again(self):
        source = self.post_source().json()

        resp = self.client.put(
            f"/sources/{source['id']}", {"topic": "msh/US/#"}, format="json", **self.auth_headers(self.operator)
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(TermsAcceptance.objects.filter(kind="source").count(), 1)


class RenewalTests(SourceTermsTestCase):
    def setUp(self):
        super().setUp()
        self.source = self.post_source().json()

    def renew(self, owner=None, **fields):
        return self.client.post(
            f"/sources/{self.source['id']}/terms-acceptance",
            {"terms_version": SOURCE_VERSION, **fields},
            format="json",
            **self.auth_headers(owner or self.operator),
        )

    def test_renewing_adds_an_acceptance(self):
        self.assertEqual(self.renew().status_code, 201)
        self.assertEqual(TermsAcceptance.objects.filter(source_id=self.source["id"]).count(), 2)

    def test_only_the_creating_operator_can_renew(self):
        admin = self.create_owner(name="Admin", email="terms-admin@example.com")
        self.promote_to_superuser(admin)

        self.assertEqual(self.renew(owner=admin).status_code, 403)

    def test_renewing_a_paused_source_restarts_it_and_cancels_its_deletions(self):
        mesh = self.create_mesh(self.operator)
        self.client.put(
            f"/meshes/{mesh['id']}", {"source_id": self.source["id"]}, format="json", **self.auth_headers(self.operator)
        )
        Source.objects.filter(pk=self.source["id"]).update(paused_at=timezone.now())
        DataDeletion.objects.create(
            mesh_id=mesh["id"], source_id=self.source["id"], reason="terms_lapsed", delete_after=timezone.now()
        )
        self.fake_emqx.apply_source.reset_mock()

        resp = self.renew()

        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(resp.json()["paused_at"])
        self.fake_emqx.apply_source.assert_called_once()
        self.assertEqual(DataDeletion.objects.get().status, "cancelled")

    def test_a_failed_restart_keeps_the_source_paused(self):
        Source.objects.filter(pk=self.source["id"]).update(paused_at=timezone.now())
        self.fake_emqx.apply_source.side_effect = RuntimeError("emqx down")

        self.assertEqual(self.renew().status_code, 502)
        self.assertIsNotNone(Source.objects.get(pk=self.source["id"]).paused_at)
        self.assertEqual(TermsAcceptance.objects.filter(kind="source").count(), 1)


class SourceApiFixesTests(SourceTermsTestCase):
    def test_the_list_carries_each_status_from_one_call(self):
        source = self.post_source().json()
        self.fake_emqx.source_statuses.return_value = {source["id"]: "disconnected"}
        self.fake_emqx.source_status.reset_mock()

        listed = self.client.get("/sources", **self.auth_headers(self.operator)).json()

        self.assertEqual(listed[0]["status"], "disconnected")
        self.fake_emqx.source_status.assert_not_called()

    def test_a_paused_source_reads_paused(self):
        source = self.post_source().json()
        Source.objects.filter(pk=source["id"]).update(paused_at=timezone.now() - timedelta(days=1))

        self.assertEqual(self.client.get("/sources", **self.auth_headers(self.operator)).json()[0]["status"], "paused")
        self.assertEqual(
            self.client.get(f"/sources/{source['id']}", **self.auth_headers(self.operator)).json()["status"], "paused"
        )

    def test_a_password_needs_a_username(self):
        self.assertEqual(self.post_source(password="secret").json(), {"username": ["A password needs a username."]})
        source = self.post_source(username="u", password="secret").json()

        resp = self.client.put(
            f"/sources/{source['id']}", {"username": ""}, format="json", **self.auth_headers(self.operator)
        )

        self.assertEqual(resp.status_code, 400)

    def test_a_username_alone_is_accepted(self):
        resp = self.post_source(username="meshdev")

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(self.fake_emqx.apply_source.call_args.args[0].username, "meshdev")

    def test_an_empty_password_removes_it(self):
        source = self.post_source(username="u", password="secret").json()

        self.client.put(f"/sources/{source['id']}", {"password": ""}, format="json", **self.auth_headers(self.operator))

        stored = Source.objects.get(pk=source["id"])
        self.assertEqual((stored.username, stored.password), ("u", None))
        self.assertIsNone(self.fake_emqx.apply_source.call_args.args[0].password)

    def test_a_paused_source_cannot_take_new_meshes(self):
        source = self.post_source().json()
        Source.objects.filter(pk=source["id"]).update(paused_at=timezone.now())

        resp = self.client.post(
            "/meshes",
            {**MESH_TERMS, "channel_id": "X", "psk_b64": "AQ==", "source_id": source["id"]},
            format="json",
            **self.auth_headers(self.operator),
        )

        self.assertEqual(resp.status_code, 400)

    def test_superusers_see_the_source_of_a_mesh_they_do_not_own(self):
        source = self.post_source().json()
        mesh = self.create_mesh(self.operator)
        self.client.put(
            f"/meshes/{mesh['id']}", {"source_id": source["id"]}, format="json", **self.auth_headers(self.operator)
        )
        admin = self.create_owner(name="Admin", email="terms-admin2@example.com")
        self.promote_to_superuser(admin)

        body = self.client.get(f"/meshes/{mesh['id']}", **self.auth_headers(admin)).json()

        self.assertEqual(body["source_id"], source["id"])
        self.assertNotIn("psk_b64", body)


class AccountTermsTests(RegistryTestCase):
    def test_anyone_can_read_the_account_terms(self):
        body = self.client.get("/terms?locale=es").json()

        self.assertEqual((body["version"], body["locale"]), (terms.VERSIONS[TermsKind.ACCOUNT], "es"))
        self.assertEqual([s["id"] for s in body["statements"]], ["terms", "privacy"])

    @override_settings(DATA_RETENTION_DAYS=180)
    def test_the_account_terms_carry_no_retention_period(self):
        self.assertNotIn("180", self.client.get("/terms").json()["footnote"])

    @override_settings(DATA_RETENTION_DAYS=180)
    def test_signing_up_records_an_account_acceptance_that_never_lapses(self):
        owner = self.create_owner(name="Signup", email="terms-signup@example.com")

        acceptance = TermsAcceptance.objects.get(owner_id=owner["id"])
        self.assertEqual((acceptance.kind, acceptance.terms_version), ("account", terms.VERSIONS[TermsKind.ACCOUNT]))
        self.assertIsNone(acceptance.expires_at)
        self.assertEqual(acceptance.text_hash, terms.text_hash(terms.terms(TermsKind.ACCOUNT, "en")))
        me = self.client.get("/owners/me", **self.auth_headers(owner)).json()
        self.assertEqual(me["terms_accepted_version"], terms.VERSIONS[TermsKind.ACCOUNT])

    def test_signing_up_without_the_terms_is_refused(self):
        resp = self.client.post(
            "/owners", {"name": "No", "email": "terms-none@example.com", "password": self.DEFAULT_PASSWORD}, format="json"
        )

        self.assertIn("terms_version", resp.json())
        self.assertFalse(Owner.objects.filter(email="terms-none@example.com").exists())

    def test_the_mesh_version_is_not_the_account_version(self):
        resp = self.client.post(
            "/owners",
            {
                "name": "X",
                "email": "terms-x@example.com",
                "password": self.DEFAULT_PASSWORD,
                "terms_version": terms.VERSIONS[TermsKind.MESH],
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 400)

    def test_an_owner_accepts_changed_account_terms(self):
        owner = self.create_owner(name="Renew", email="terms-renew@example.com")

        resp = self.client.post(
            "/owners/me/terms-acceptance",
            {"terms_version": terms.VERSIONS[TermsKind.ACCOUNT]},
            format="json",
            **self.auth_headers(owner),
        )

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(TermsAcceptance.objects.filter(owner_id=owner["id"], kind="account").count(), 2)


MESH_VERSION = terms.VERSIONS[TermsKind.MESH]


class MeshTermsTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_owner(name="Owner", email="mesh-terms@example.com")

    def post_mesh(self, owner=None, **fields):
        body = {"channel_id": "LongFast", "psk_b64": "AQ==", **fields}
        return self.client.post("/meshes", body, format="json", **self.auth_headers(owner or self.owner))

    def test_verified_owners_read_the_mesh_terms(self):
        body = self.client.get("/meshes/terms", **self.auth_headers(self.owner)).json()

        self.assertEqual(body["version"], MESH_VERSION)
        self.assertEqual([s["id"] for s in body["statements"]], ["controller", "lawfulBasis", "sensitive"])

    @override_settings(DATA_RETENTION_DAYS=180)
    def test_the_mesh_terms_state_the_period(self):
        self.assertIn("180 days", self.client.get("/meshes/terms", **self.auth_headers(self.owner)).json()["footnote"])

    @override_settings(DATA_RETENTION_DAYS=180)
    def test_a_default_broker_mesh_records_its_acceptance(self):
        resp = self.post_mesh(terms_version=MESH_VERSION, terms_locale="es")

        self.assertEqual(resp.status_code, 201)
        acceptance = TermsAcceptance.objects.get(mesh_id=resp.json()["id"])
        self.assertEqual((acceptance.kind, acceptance.locale), ("mesh", "es"))
        self.assertEqual((acceptance.expires_at - acceptance.accepted_at).days, 180)
        self.assertEqual(resp.json()["terms_accepted_version"], MESH_VERSION)
        self.assertIsNotNone(resp.json()["terms_expires_at"])
        self.assertIsNone(resp.json()["paused_at"])

    def test_a_default_broker_mesh_needs_its_terms(self):
        self.assertIn("terms_version", self.post_mesh().json())
        self.assertEqual(self.post_mesh(terms_version="meshes-2020-01").status_code, 400)
        self.assertEqual(self.post_mesh(terms_version=terms.VERSIONS[TermsKind.ACCOUNT]).status_code, 400)

    def test_a_mesh_on_a_source_ignores_the_mesh_terms(self):
        self.promote_to_operator(self.owner)
        source = self.create_source(self.owner)

        resp = self.post_mesh(source_id=source["id"], terms_version="anything")

        self.assertEqual(resp.status_code, 201)
        self.assertFalse(TermsAcceptance.objects.filter(mesh_id=resp.json()["id"]).exists())
        self.assertIsNone(resp.json()["terms_accepted_version"])

    def test_moving_onto_the_default_broker_asks_for_the_terms(self):
        self.promote_to_operator(self.owner)
        source = self.create_source(self.owner)
        mesh = self.post_mesh(source_id=source["id"]).json()

        refused = self.client.put(
            f"/meshes/{mesh['id']}", {"source_id": None}, format="json", **self.auth_headers(self.owner)
        )
        accepted = self.client.put(
            f"/meshes/{mesh['id']}",
            {"source_id": None, "terms_version": MESH_VERSION},
            format="json",
            **self.auth_headers(self.owner),
        )

        self.assertEqual(refused.status_code, 400)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(TermsAcceptance.objects.filter(mesh_id=mesh["id"]).count(), 1)

    def test_a_mesh_with_a_current_acceptance_moves_back_without_asking(self):
        self.promote_to_operator(self.owner)
        source = self.create_source(self.owner)
        mesh = self.post_mesh(terms_version=MESH_VERSION).json()
        self.client.put(f"/meshes/{mesh['id']}", {"source_id": source["id"]}, format="json", **self.auth_headers(self.owner))

        resp = self.client.put(f"/meshes/{mesh['id']}", {"source_id": None}, format="json", **self.auth_headers(self.owner))

        self.assertEqual(resp.status_code, 200)

    def test_other_owners_do_not_see_the_mesh_terms_standing(self):
        mesh = self.post_mesh(terms_version=MESH_VERSION, is_public=True).json()
        other = self.create_owner(name="Other", email="mesh-terms-other@example.com")

        body = self.client.get(f"/meshes/{mesh['id']}", **self.auth_headers(other)).json()

        for field in ("terms_accepted_version", "terms_expires_at", "paused_at"):
            self.assertNotIn(field, body)

    def test_only_the_owner_renews_and_not_on_a_source(self):
        mesh = self.post_mesh(terms_version=MESH_VERSION, is_public=True).json()
        other = self.create_owner(name="Other", email="mesh-terms-other2@example.com")

        by_other = self.client.post(
            f"/meshes/{mesh['id']}/terms-acceptance", {"terms_version": MESH_VERSION}, format="json",
            **self.auth_headers(other),
        )
        by_owner = self.client.post(
            f"/meshes/{mesh['id']}/terms-acceptance", {"terms_version": MESH_VERSION}, format="json",
            **self.auth_headers(self.owner),
        )

        self.assertEqual((by_other.status_code, by_owner.status_code), (403, 201))
        self.promote_to_operator(self.owner)
        source = self.create_source(self.owner)
        self.client.put(f"/meshes/{mesh['id']}", {"source_id": source["id"]}, format="json", **self.auth_headers(self.owner))
        self.assertEqual(
            self.client.post(
                f"/meshes/{mesh['id']}/terms-acceptance", {"terms_version": MESH_VERSION}, format="json",
                **self.auth_headers(self.owner),
            ).status_code,
            409,
        )
