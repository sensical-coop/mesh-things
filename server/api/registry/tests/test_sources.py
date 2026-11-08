import json
import uuid
from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import override_settings
from django.utils import timezone

from registry import broker_hosts
from registry.models import Mesh, Owner, Source, TermsKind
from registry.terms import VERSIONS

from .helpers import MESH_TERMS, RegistryTestCase


class SourcePermissionTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.member = self.create_owner(name="Member", email="src-member@example.com")
        self.operator = self.create_owner(name="Operator", email="src-operator@example.com")
        self.promote_to_operator(self.operator)

    def test_a_member_cannot_create_a_source(self):
        resp = self.client.post(
            "/sources", {"server": "r.example.org:1883", "topic": "msh/#", "terms_version": VERSIONS[TermsKind.SOURCE]},
            format="json",
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

    def test_a_member_cannot_list_or_read_sources(self):
        source = self.create_source(self.operator)

        self.assertEqual(self.client.get("/sources", **self.auth_headers(self.member)).status_code, 403)
        self.assertEqual(self.client.get(f"/sources/{source['id']}", **self.auth_headers(self.member)).status_code, 403)

    def test_a_member_cannot_update_or_delete_a_source(self):
        source = self.create_source(self.operator)

        self.assertEqual(
            self.client.put(f"/sources/{source['id']}", {"label": "x"}, format="json", **self.auth_headers(self.member)).status_code,
            403,
        )
        self.assertEqual(self.client.delete(f"/sources/{source['id']}", **self.auth_headers(self.member)).status_code, 403)

    def test_an_operator_sees_only_their_own_sources(self):
        other = self.create_owner(name="Other operator", email="src-other-op@example.com")
        self.promote_to_operator(other)
        mine = self.create_source(self.operator)
        theirs = self.create_source(other)

        listed = self.client.get("/sources", **self.auth_headers(self.operator)).json()

        self.assertEqual([s["id"] for s in listed], [mine["id"]])
        self.assertEqual(self.client.get(f"/sources/{theirs['id']}", **self.auth_headers(self.operator)).status_code, 404)

    def test_an_operator_cannot_update_or_delete_another_operators_source(self):
        other = self.create_owner(name="Other operator", email="src-other-op2@example.com")
        self.promote_to_operator(other)
        theirs = self.create_source(other)
        self.fake_emqx.apply_source.reset_mock()

        put = self.client.put(f"/sources/{theirs['id']}", {"label": "x"}, format="json", **self.auth_headers(self.operator))
        delete = self.client.delete(f"/sources/{theirs['id']}", **self.auth_headers(self.operator))

        self.assertEqual((put.status_code, delete.status_code), (404, 404))
        self.fake_emqx.apply_source.assert_not_called()
        self.fake_emqx.delete_source.assert_not_called()

    def test_a_superuser_sees_every_source(self):
        admin = self.create_owner(name="Admin", email="src-admin2@example.com")
        self.promote_to_superuser(admin)
        source = self.create_source(self.operator)

        self.assertEqual([s["id"] for s in self.client.get("/sources", **self.auth_headers(admin)).json()], [source["id"]])
        self.assertEqual(self.client.get(f"/sources/{source['id']}", **self.auth_headers(admin)).status_code, 200)

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
        body = {"server": "r.example.org:1883", "topic": "msh/#", "terms_version": VERSIONS[TermsKind.SOURCE], **fields}
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

    def test_our_own_broker_is_rejected_by_address_or_alias(self):
        own = {"mqtt.sensical.es": ["2.29.16.246"], "alias.example.org": ["2.29.16.246"], "r.example.org": ["9.9.9.9"]}
        env = {"REGISTRY__EMQX_API_URL": "https://mqtt.sensical.es:18084/api/v5"}
        with patch.dict("os.environ", env), patch.object(broker_hosts, "resolve", side_effect=lambda h: own.get(h, [])):
            self.assertEqual(self._post(server="2.29.16.246:8883").status_code, 400)
            self.assertEqual(self._post(server="alias.example.org:1883").status_code, 400)
            self.assertEqual(self._post(server="r.example.org:1883").status_code, 201)
        self.fake_emqx.apply_source.assert_called_once()

    def test_the_bridge_and_sinks_brokers_count_as_our_own(self):
        env = {"MQTT_BRIDGE__BROKER": "bridge.example.org", "REGISTRY__SINKS_BROKER": "sinks.example.org:8884"}
        with patch.dict("os.environ", env):
            self.assertEqual(self._post(server="bridge.example.org:8883").status_code, 400)
            self.assertEqual(self._post(server="sinks.example.org:1883").status_code, 400)

    def test_topics_reaching_republished_sources_or_sinks_are_rejected(self):
        for topic in ("+/#", "+/+/LongFast/#", "mt-sources/#", "mt-sources-sinks/abc/#", "mt-sources-dev/x/#"):
            self.assertEqual(self._post(topic=topic).status_code, 400, topic)
        self.assertEqual(self._post(topic="test/#").status_code, 201)
        self.fake_emqx.apply_source.assert_called_once()

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
            "/sources", {"server": "r.example.org:1883", "topic": "msh/#", "terms_version": VERSIONS[TermsKind.SOURCE]},
            format="json",
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
        mesh = self.create_mesh(self.operator)
        self.client.put(
            f"/meshes/{mesh['id']}", {"source_id": source["id"]}, format="json", **self.auth_headers(self.operator)
        )

        resp = self.client.delete(f"/sources/{source['id']}", **self.auth_headers(self.operator))

        self.assertEqual(resp.status_code, 409)
        self.fake_emqx.delete_source.assert_not_called()

    def test_status_is_unknown_when_emqx_is_unreachable(self):
        source = self.create_source(self.operator)
        self.fake_emqx.source_status.side_effect = RuntimeError("emqx down")

        resp = self.client.get(f"/sources/{source['id']}", **self.auth_headers(self.operator))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "unknown")


class SourceRestartTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.operator = self.create_owner(name="Operator", email="src-restart-op@example.com")
        self.promote_to_operator(self.operator)
        self.source = self.create_source(self.operator)
        self.fake_emqx.apply_source.reset_mock()

    def _restart(self, owner):
        return self.client.post(f"/sources/{self.source['id']}/restart", **self.auth_headers(owner))

    def test_restarting_reapplies_the_bridge_then_resubscribes(self):
        resp = self._restart(self.operator)

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["status"], "connected")
        self.assertEqual(str(self.fake_emqx.apply_source.call_args.args[0].id), self.source["id"])
        self.fake_emqx.restart_source.assert_called_once_with(self.source["id"])

    def test_a_superuser_restarts_any_source(self):
        admin = self.create_owner(name="Admin", email="src-restart-admin@example.com")
        self.promote_to_superuser(admin)

        self.assertEqual(self._restart(admin).status_code, 200)

    def test_another_operator_or_a_member_cannot_restart_it(self):
        other = self.create_owner(name="Second operator", email="src-restart-op2@example.com")
        self.promote_to_operator(other)
        member = self.create_owner(name="Member", email="src-restart-member@example.com")

        self.assertEqual((self._restart(other).status_code, self._restart(member).status_code), (404, 403))
        self.fake_emqx.restart_source.assert_not_called()

    def test_a_paused_source_is_not_restarted(self):
        Source.objects.filter(pk=self.source["id"]).update(paused_at=timezone.now())

        self.assertEqual(self._restart(self.operator).status_code, 409)
        self.fake_emqx.apply_source.assert_not_called()

    def test_a_broker_error_answers_502(self):
        self.fake_emqx.restart_source.side_effect = RuntimeError("emqx down")

        self.assertEqual(self._restart(self.operator).status_code, 502)

    def test_the_command_restarts_by_id_and_lists_without_one(self):
        out = StringIO()
        call_command("restart_source", self.source["id"], stdout=out)
        self.fake_emqx.restart_source.assert_called_once_with(self.source["id"])

        self.fake_emqx.source_message_count.return_value = 42
        out = StringIO()
        call_command("restart_source", stdout=out)
        self.assertIn(f"{self.source['id']}  connected", out.getvalue())
        self.assertIn("messages=42", out.getvalue())

    def test_the_command_refuses_an_unknown_or_paused_source(self):
        with self.assertRaises(CommandError):
            call_command("restart_source", str(uuid.uuid4()))
        with self.assertRaises(CommandError):
            call_command("restart_source", "not-a-uuid")
        Source.objects.filter(pk=self.source["id"]).update(paused_at=timezone.now())
        with self.assertRaises(CommandError):
            call_command("restart_source", self.source["id"])
        self.fake_emqx.restart_source.assert_not_called()


class MeshSourceTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.operator = self.create_owner(name="Operator", email="mesh-src-op@example.com")
        self.promote_to_operator(self.operator)
        self.source = self.create_source(self.operator)
        self.owner = self.operator
        self.member = self.create_owner(name="Member", email="mesh-src-member@example.com")

    def _create_on_source(self, owner, source_id):
        return self.client.post(
            "/meshes",
            {**MESH_TERMS, "channel_id": "LongFast", "psk_b64": "AQ==", "source_id": source_id},
            format="json",
            **self.auth_headers(owner),
        )

    def test_a_member_cannot_attach_a_mesh_to_a_source(self):
        mesh = self.create_mesh(self.member)

        created = self._create_on_source(self.member, self.source["id"])
        updated = self.client.put(
            f"/meshes/{mesh['id']}", {"source_id": self.source["id"]}, format="json", **self.auth_headers(self.member)
        )

        self.assertEqual((created.status_code, updated.status_code), (400, 400))
        # Indistinguishable from a source that does not exist.
        missing_id = str(uuid.uuid4())
        missing = self._create_on_source(self.member, missing_id).json()
        self.assertEqual(json.dumps(created.json()).replace(self.source["id"], missing_id), json.dumps(missing))

    def test_an_operator_cannot_attach_another_operators_source(self):
        other = self.create_owner(name="Other operator", email="mesh-src-op2@example.com")
        self.promote_to_operator(other)

        self.assertEqual(self._create_on_source(other, self.source["id"]).status_code, 400)

    def test_a_superuser_can_attach_any_source(self):
        admin = self.create_owner(name="Admin", email="mesh-src-admin@example.com")
        self.promote_to_superuser(admin)

        self.assertEqual(self._create_on_source(admin, self.source["id"]).status_code, 201)

    def test_resending_the_current_source_is_accepted(self):
        mesh = self.create_mesh(self.owner)
        self.client.put(f"/meshes/{mesh['id']}", {"source_id": self.source["id"]}, format="json", **self.auth_headers(self.owner))
        Owner.objects.filter(pk=self.owner["id"]).update(role="member")

        resp = self.client.put(
            f"/meshes/{mesh['id']}", {"label": "x", "source_id": self.source["id"]}, format="json",
            **self.auth_headers(self.owner),
        )

        self.assertEqual(resp.status_code, 200)

    def test_the_source_is_hidden_from_viewers_of_a_public_mesh(self):
        mesh = self.create_mesh(self.owner)
        self.client.put(
            f"/meshes/{mesh['id']}", {"source_id": self.source["id"], "is_public": True}, format="json",
            **self.auth_headers(self.owner),
        )

        self.assertNotIn("source_id", self.client.get(f"/meshes/{mesh['id']}", **self.auth_headers(self.member)).json())

    def test_an_operator_can_create_a_mesh_on_their_source(self):
        resp = self.client.post(
            "/meshes",
            {**MESH_TERMS, "channel_id": "LongFast", "psk_b64": "AQ==", "source_id": self.source["id"]},
            format="json",
            **self.auth_headers(self.owner),
        )

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["source_id"], self.source["id"])

    def test_an_unknown_source_is_rejected(self):
        resp = self.client.post(
            "/meshes",
            {**MESH_TERMS, "channel_id": "LongFast", "psk_b64": "AQ==", "source_id": str(uuid.uuid4())},
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
