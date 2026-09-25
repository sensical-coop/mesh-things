import uuid
from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import override_settings

from registry.models import Mesh, Owner, Source

from .helpers import RegistryTestCase


class SourcePermissionTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.member = self.create_owner(name="Member", email="src-member@example.com")
        self.operator = self.create_owner(name="Operator", email="src-operator@example.com")
        self.promote_to_operator(self.operator)

    def test_a_member_cannot_create_a_source(self):
        resp = self.client.post(
            "/sources", {"server": "r.example.org:1883", "topic": "msh/#"}, format="json",
            **self.auth_headers(self.member),
        )

        self.assertEqual(resp.status_code, 403)
        self.fake_emqx.apply_source.assert_not_called()

    def test_an_operator_creates_a_source_and_its_bridge(self):
        source = self.create_source(self.operator)

        self.assertEqual(source["created_by_id"], self.operator["id"])
        self.assertEqual(source["status"], "connected")
        self.fake_emqx.apply_source.assert_called_once()
        self.assertEqual(str(self.fake_emqx.apply_source.call_args.args[0].id), source["id"])

    def test_a_superuser_is_an_operator(self):
        admin = self.create_owner(name="Admin", email="src-admin@example.com")
        self.promote_to_superuser(admin)

        self.create_source(admin)

    def test_any_verified_owner_can_list_and_read_sources(self):
        source = self.create_source(self.operator)

        self.assertEqual([s["id"] for s in self.client.get("/sources", **self.auth_headers(self.member)).json()], [source["id"]])
        self.assertEqual(self.client.get(f"/sources/{source['id']}", **self.auth_headers(self.member)).status_code, 200)

    def test_a_member_cannot_update_or_delete_a_source(self):
        source = self.create_source(self.operator)

        self.assertEqual(
            self.client.put(f"/sources/{source['id']}", {"label": "x"}, format="json", **self.auth_headers(self.member)).status_code,
            403,
        )
        self.assertEqual(self.client.delete(f"/sources/{source['id']}", **self.auth_headers(self.member)).status_code, 403)

    def test_sources_require_auth(self):
        self.assertEqual(self.client.get("/sources").status_code, 401)


class SourceSecretTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.operator = self.create_owner(name="Operator", email="src-secret-op@example.com")
        self.promote_to_operator(self.operator)

    def test_the_password_is_stored_but_never_returned(self):
        source = self.create_source(self.operator, username="u", password="hunter2")

        self.assertNotIn("password", source)
        self.assertNotIn("password", self.client.get(f"/sources/{source['id']}", **self.auth_headers(self.operator)).json())
        self.assertNotIn("password", self.client.get("/sources", **self.auth_headers(self.operator)).json()[0])
        self.assertEqual(Source.objects.get(pk=source["id"]).password, "hunter2")


class SourceValidationTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.operator = self.create_owner(name="Operator", email="src-valid-op@example.com")
        self.promote_to_operator(self.operator)

    def _post(self, **fields):
        body = {"server": "r.example.org:1883", "topic": "msh/#", **fields}
        return self.client.post("/sources", body, format="json", **self.auth_headers(self.operator))

    def test_server_must_be_host_and_port(self):
        self.assertEqual(self._post(server="r.example.org").status_code, 400)
        self.assertEqual(self._post(server="r.example.org:99999").status_code, 400)

    def test_qos_2_is_rejected(self):
        self.assertEqual(self._post(qos=2).status_code, 400)

    def test_share_and_sys_topics_are_rejected(self):
        self.assertEqual(self._post(topic="$share/g/msh/#").status_code, 400)
        self.assertEqual(self._post(topic="$SYS/#").status_code, 400)

    def test_our_own_broker_is_rejected(self):
        with patch.dict("os.environ", {"REGISTRY__EMQX_API_URL": "https://mqtt.sensical.es:18084/api/v5"}):
            self.assertEqual(self._post(server="MQTT.sensical.es:8883").status_code, 400)
        self.fake_emqx.apply_source.assert_not_called()


    @override_settings(SOURCES_BLOCKED_BROKERS=["*.meshtastic.org", "blocked.example.org:1883"])
    def test_blocked_brokers_are_rejected(self):
        self.assertEqual(self._post(server="MQTT.meshtastic.org:1883").status_code, 400)
        self.assertEqual(self._post(server="blocked.example.org:1883").status_code, 400)
        self.assertEqual(self._post(server="blocked.example.org:8883").status_code, 201)

    @override_settings(SOURCES_BLOCKED_TOPICS=["#", "msh/#"])
    def test_blocked_topics_are_rejected(self):
        self.assertEqual(self._post(topic="#").status_code, 400)
        self.assertEqual(self._post(topic=" msh/# ").status_code, 400)
        self.assertEqual(self._post(topic="msh/EU_868/#").status_code, 201)

    def test_hash_is_blocked_by_default(self):
        self.assertEqual(self._post(topic="#").status_code, 400)

    def test_an_update_is_validated_against_the_blocklist(self):
        source = self._post().json()

        with override_settings(SOURCES_BLOCKED_TOPICS=["msh/EU_868/#"]):
            resp = self.client.put(
                f"/sources/{source['id']}", {"topic": "msh/EU_868/#"}, format="json", **self.auth_headers(self.operator)
            )

        self.assertEqual(resp.status_code, 400)

class SourceFailurePolicyTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.operator = self.create_owner(name="Operator", email="src-fail-op@example.com")
        self.promote_to_operator(self.operator)

    def test_create_is_rolled_back_when_the_bridge_fails(self):
        self.fake_emqx.apply_source.side_effect = RuntimeError("emqx down")

        resp = self.client.post(
            "/sources", {"server": "r.example.org:1883", "topic": "msh/#"}, format="json",
            **self.auth_headers(self.operator),
        )

        self.assertEqual(resp.status_code, 502)
        self.assertFalse(Source.objects.exists())

    def test_update_is_rolled_back_and_reapplied_when_the_bridge_fails(self):
        source = self.create_source(self.operator, topic="msh/old/#")
        self.fake_emqx.apply_source.reset_mock()
        self.fake_emqx.apply_source.side_effect = [RuntimeError("emqx down"), None]

        resp = self.client.put(
            f"/sources/{source['id']}", {"topic": "msh/new/#"}, format="json", **self.auth_headers(self.operator)
        )

        self.assertEqual(resp.status_code, 502)
        self.assertEqual(Source.objects.get(pk=source["id"]).topic, "msh/old/#")
        self.assertEqual(self.fake_emqx.apply_source.call_count, 2)
        self.assertEqual(self.fake_emqx.apply_source.call_args.args[0].topic, "msh/old/#")

    def test_update_reapplies_the_bridge(self):
        source = self.create_source(self.operator)
        self.fake_emqx.apply_source.reset_mock()

        resp = self.client.put(
            f"/sources/{source['id']}", {"topic": "msh/US/#"}, format="json", **self.auth_headers(self.operator)
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["topic"], "msh/US/#")
        self.assertEqual(self.fake_emqx.apply_source.call_args.args[0].topic, "msh/US/#")

    def test_delete_removes_the_bridge_then_the_row(self):
        source = self.create_source(self.operator)

        resp = self.client.delete(f"/sources/{source['id']}", **self.auth_headers(self.operator))

        self.assertEqual(resp.status_code, 204)
        self.fake_emqx.delete_source.assert_called_once_with(source["id"])
        self.assertFalse(Source.objects.exists())

    def test_delete_keeps_the_row_when_the_bridge_cannot_be_removed(self):
        source = self.create_source(self.operator)
        self.fake_emqx.delete_source.side_effect = RuntimeError("emqx down")

        resp = self.client.delete(f"/sources/{source['id']}", **self.auth_headers(self.operator))

        self.assertEqual(resp.status_code, 502)
        self.assertTrue(Source.objects.filter(pk=source["id"]).exists())

    def test_a_source_with_meshes_cannot_be_deleted(self):
        source = self.create_source(self.operator)
        owner = self.create_owner(name="Owner", email="src-fail-owner@example.com")
        mesh = self.create_mesh(owner)
        self.client.put(f"/meshes/{mesh['id']}", {"source_id": source["id"]}, format="json", **self.auth_headers(owner))

        resp = self.client.delete(f"/sources/{source['id']}", **self.auth_headers(self.operator))

        self.assertEqual(resp.status_code, 409)
        self.fake_emqx.delete_source.assert_not_called()

    def test_status_is_unknown_when_emqx_is_unreachable(self):
        source = self.create_source(self.operator)
        self.fake_emqx.source_status.side_effect = RuntimeError("emqx down")

        resp = self.client.get(f"/sources/{source['id']}", **self.auth_headers(self.operator))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "unknown")


class MeshSourceTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.operator = self.create_owner(name="Operator", email="mesh-src-op@example.com")
        self.promote_to_operator(self.operator)
        self.source = self.create_source(self.operator)
        self.owner = self.create_owner(name="Owner", email="mesh-src-owner@example.com")

    def test_a_member_can_create_a_mesh_on_a_source(self):
        resp = self.client.post(
            "/meshes",
            {"channel_id": "LongFast", "psk_b64": "AQ==", "source_id": self.source["id"]},
            format="json",
            **self.auth_headers(self.owner),
        )

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["source_id"], self.source["id"])

    def test_an_unknown_source_is_rejected(self):
        resp = self.client.post(
            "/meshes",
            {"channel_id": "LongFast", "psk_b64": "AQ==", "source_id": str(uuid.uuid4())},
            format="json",
            **self.auth_headers(self.owner),
        )

        self.assertEqual(resp.status_code, 400)

    def test_a_mesh_without_a_source_reads_null(self):
        self.assertIsNone(self.create_mesh(self.owner)["source_id"])

    def test_the_gateway_upsert_carries_the_mesh_source(self):
        mesh = self.create_mesh(self.owner)
        self.client.put(f"/meshes/{mesh['id']}", {"source_id": self.source["id"]}, format="json", **self.auth_headers(self.owner))
        self.fake_publisher.publish_gateway_upsert.reset_mock()

        self.create_gateway(self.owner, mesh, device_id=1)

        _, published_mesh = self.fake_publisher.publish_gateway_upsert.call_args.args
        self.assertEqual(str(published_mesh.source_id), self.source["id"])

    def test_changing_the_source_republishes_every_allowed_gateway(self):
        mesh = self.create_mesh(self.owner)
        self.create_gateway(self.owner, mesh, device_id=1)
        self.create_gateway(self.owner, mesh, device_id=2)
        self.fake_publisher.publish_gateway_upsert.reset_mock()

        resp = self.client.put(
            f"/meshes/{mesh['id']}", {"source_id": self.source["id"]}, format="json", **self.auth_headers(self.owner)
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.fake_publisher.publish_gateway_upsert.call_count, 2)
        for call in self.fake_publisher.publish_gateway_upsert.call_args_list:
            self.assertEqual(str(call.args[1].source_id), self.source["id"])

    def test_a_failed_republish_restores_the_source_on_every_gateway(self):
        mesh = self.create_mesh(self.owner)
        self.create_gateway(self.owner, mesh, device_id=1)
        self.create_gateway(self.owner, mesh, device_id=2)
        self.fake_publisher.publish_gateway_upsert.reset_mock()
        sent_sources = []

        def publish(gateway, published_mesh):
            sent_sources.append(published_mesh.source_id)
            if len(sent_sources) == 2:
                raise RuntimeError("kafka down")

        self.fake_publisher.publish_gateway_upsert.side_effect = publish

        resp = self.client.put(
            f"/meshes/{mesh['id']}", {"source_id": self.source["id"]}, format="json", **self.auth_headers(self.owner)
        )

        self.assertEqual(resp.status_code, 502)
        self.assertIsNone(Mesh.objects.get(pk=mesh["id"]).source_id)
        # The gateway republished before the failure is sent the restored value.
        self.assertEqual(sent_sources, [uuid.UUID(self.source["id"]), uuid.UUID(self.source["id"]), None])

    def test_meshes_filter_by_source(self):
        on_source = self.create_mesh(self.owner, channel_id="A")
        self.create_mesh(self.owner, channel_id="B")
        self.client.put(
            f"/meshes/{on_source['id']}", {"source_id": self.source["id"]}, format="json", **self.auth_headers(self.owner)
        )

        resp = self.client.get(f"/meshes?source_id={self.source['id']}", **self.auth_headers(self.owner))

        self.assertEqual([m["id"] for m in resp.json()], [on_source["id"]])
        self.assertEqual(self.client.get("/meshes?source_id=nope", **self.auth_headers(self.owner)).status_code, 400)


class OwnerRoleTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_owner(name="Owner", email="role-owner@example.com")
        self.admin = self.create_owner(name="Admin", email="role-admin@example.com")
        self.promote_to_superuser(self.admin)

    def test_a_superuser_grants_the_operator_role(self):
        resp = self.client.put(
            f"/owners/{self.owner['id']}", {"role": "operator"}, format="json", **self.auth_headers(self.admin)
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["role"], "operator")
        self.create_source(self.owner)

    def test_an_operator_cannot_grant_roles(self):
        self.promote_to_operator(self.owner)
        other = self.create_owner(name="Other", email="role-other@example.com")

        resp = self.client.put(
            f"/owners/{other['id']}", {"role": "operator"}, format="json", **self.auth_headers(self.owner)
        )

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(Owner.objects.get(pk=other["id"]).role, "member")

    def test_an_unknown_role_is_rejected(self):
        resp = self.client.put(
            f"/owners/{self.owner['id']}", {"role": "root"}, format="json", **self.auth_headers(self.admin)
        )

        self.assertEqual(resp.status_code, 400)

    def test_new_owners_are_members(self):
        self.assertEqual(self.client.get("/owners/me", **self.auth_headers(self.owner)).json()["role"], "member")


class SyncSourcesCommandTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.operator = self.create_owner(name="Operator", email="sync-op@example.com")
        self.promote_to_operator(self.operator)
        self.kept = self.create_source(self.operator)
        self.missing = self.create_source(self.operator, topic="msh/US/#")
        self.orphan = str(uuid.uuid4())
        self.fake_emqx.managed_source_ids.return_value = {self.kept["id"], self.orphan}
        self.fake_emqx.apply_source.reset_mock()

    def test_check_reports_differences_without_changing_emqx(self):
        out = StringIO()

        with self.assertRaises(CommandError):
            call_command("sync_sources", "--check", stdout=out)

        self.assertIn(f"missing in EMQX: {self.missing['id']}", out.getvalue())
        self.assertIn(f"orphaned in EMQX: {self.orphan}", out.getvalue())
        self.fake_emqx.apply_source.assert_not_called()
        self.fake_emqx.delete_source.assert_not_called()

    def test_sync_applies_every_source_and_removes_orphans(self):
        call_command("sync_sources", stdout=StringIO())

        self.assertEqual(
            {str(c.args[0].id) for c in self.fake_emqx.apply_source.call_args_list},
            {self.kept["id"], self.missing["id"]},
        )
        self.fake_emqx.delete_source.assert_called_once_with(self.orphan)
