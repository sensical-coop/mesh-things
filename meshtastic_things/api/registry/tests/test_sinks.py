import os
import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import call, patch

from django.core import mail
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator

from common import sinks as sink_names
from registry import data_lifecycle, sinks
from registry.models import Device, DeviceSink, Mesh, MeshSink, Owner, Sink, SinkInstruction, TermsAcceptance, TermsKind
from registry.terms import VERSIONS

from .helpers import RegistryTestCase

SINK_VERSION = VERSIONS[TermsKind.SINK]


class SinkTestCase(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self._env = patch.dict(os.environ, {"REGISTRY__EMQX_API_URL": "https://emqx.test/api/v5"})
        self._env.start()
        self.member = self.create_owner(name="Member", email="sink-member@example.com")
        self.operator = self.create_owner(name="Operator", email="sink-op@example.com")
        self.promote_to_operator(self.operator)

    def tearDown(self):
        self._env.stop()
        super().tearDown()

    def put_sink(self, sink_id, owner=None, **fields):
        return self.client.put(
            f"/sinks/{sink_id}", fields, format="json", **self.auth_headers(owner or self.operator)
        )

    def mesh_sink_events(self):
        return [c.args for c in self.fake_publisher.publish_mesh_sinks.call_args_list]

    def device_sink_events(self):
        return [c.args for c in self.fake_publisher.publish_device_sinks.call_args_list]


class PermissionTests(SinkTestCase):
    def test_a_member_cannot_create_or_list_sinks(self):
        post = self.client.post(
            "/sinks", {"terms_version": SINK_VERSION}, format="json", **self.auth_headers(self.member)
        )

        self.assertEqual(post.status_code, 403)
        self.assertEqual(self.client.get("/sinks", **self.auth_headers(self.member)).status_code, 403)
        self.fake_emqx.apply_sink.assert_not_called()

    def test_an_operator_sees_only_their_own_sinks(self):
        other = self.create_owner(name="Other", email="sink-other@example.com")
        self.promote_to_operator(other)
        mine = self.create_sink(self.operator)
        theirs = self.create_sink(other)

        listed = self.client.get("/sinks", **self.auth_headers(self.operator)).json()

        self.assertEqual([s["id"] for s in listed], [mine["id"]])
        self.assertEqual(self.client.get(f"/sinks/{theirs['id']}", **self.auth_headers(self.operator)).status_code, 404)
        self.assertEqual(self.put_sink(theirs["id"], label="x").status_code, 404)
        self.assertEqual(self.client.delete(f"/sinks/{theirs['id']}", **self.auth_headers(self.operator)).status_code, 404)

    def test_a_superuser_sees_every_sink(self):
        admin = self.create_owner(name="Admin", email="sink-admin@example.com")
        self.promote_to_superuser(admin)
        sink = self.create_sink(self.operator)

        self.assertEqual([s["id"] for s in self.client.get("/sinks", **self.auth_headers(admin)).json()], [sink["id"]])

    def test_without_emqx_the_routes_are_missing(self):
        with patch.dict(os.environ, {"REGISTRY__EMQX_API_URL": ""}):
            self.assertEqual(self.client.get("/sinks", **self.auth_headers(self.operator)).status_code, 404)
            self.assertEqual(self.client.get("/sinks/terms", **self.auth_headers(self.operator)).status_code, 404)


class CreateTests(SinkTestCase):
    def test_creating_returns_the_credentials_once(self):
        sink = self.create_sink(self.operator, label="Partner")

        self.assertTrue(sink["password"])
        self.assertEqual(sink["username"], sink_names.username(sink["id"]))
        self.assertEqual(sink["topic_filter"], sink_names.topic_filter(sink["id"]))
        self.assertEqual(sink["streams"], ["decoded"])
        self.fake_emqx.apply_sink.assert_called_once_with(sink["id"], sink["password"])
        self.fake_emqx.apply_sink_namespace.assert_called_once()
        self.fake_publisher.publish_sink.assert_called_once_with(Sink.objects.get().id, ["decoded"])

        read = self.client.get(f"/sinks/{sink['id']}", **self.auth_headers(self.operator)).json()
        self.assertNotIn("password", read)
        self.assertEqual(read["connections"], 0)

    def test_streams_are_kept_in_a_fixed_order_without_repeats(self):
        sink = self.create_sink(self.operator, streams=["alarms", "decoded", "alarms"])

        self.assertEqual(sink["streams"], ["decoded", "alarms"])

    def test_an_unknown_stream_is_refused(self):
        resp = self.client.post(
            "/sinks", {"terms_version": SINK_VERSION, "streams": ["raw"]}, format="json", **self.auth_headers(self.operator)
        )

        self.assertEqual(resp.status_code, 400)

    def test_attached_meshes_and_devices_are_published_and_recorded(self):
        mesh = self.create_mesh(self.operator, channel_id="A")
        other_mesh = self.create_mesh(self.operator, channel_id="B")
        node = self.create_node(self.operator, other_mesh, device_id=42)

        sink = self.create_sink(self.operator, mesh_ids=[mesh["id"]], device_ids=[node["uuid"]])

        ref = sink_names.ref(sink["id"])
        self.assertEqual(sink["mesh_ids"], [mesh["id"]])
        self.assertEqual(sink["device_ids"], [node["uuid"]])
        self.assertIn((Mesh.objects.get(pk=mesh["id"]).id, [ref]), self.mesh_sink_events())
        self.assertIn((Mesh.objects.get(pk=other_mesh["id"]).id, 42, [ref]), self.device_sink_events())
        instructions = SinkInstruction.objects.filter(sink=ref)
        self.assertEqual(
            sorted((str(i.mesh_id), i.node_id, i.enabled) for i in instructions),
            sorted([(mesh["id"], None, True), (other_mesh["id"], 42, True)]),
        )

    def test_a_members_mesh_cannot_be_attached(self):
        mesh = self.create_mesh(self.member)
        admin = self.create_owner(name="Admin", email="sink-admin2@example.com")
        self.promote_to_superuser(admin)

        by_operator = self.client.post(
            "/sinks", {"terms_version": SINK_VERSION, "mesh_ids": [mesh["id"]]}, format="json",
            **self.auth_headers(self.operator),
        )
        by_admin = self.client.post(
            "/sinks", {"terms_version": SINK_VERSION, "mesh_ids": [mesh["id"]]}, format="json",
            **self.auth_headers(admin),
        )

        self.assertEqual(by_operator.status_code, 400)
        self.assertIn("not found", str(by_operator.json()))
        self.assertEqual(by_admin.status_code, 400)
        self.assertIn("not owned by an operator", str(by_admin.json()))
        self.assertFalse(Sink.objects.exists())

    def test_nothing_is_created_while_the_broker_does_not_protect_sinks(self):
        self.fake_emqx.sink_authorization_problem.return_value = "the built_in_database authorization source is missing"

        resp = self.client.post("/sinks", {"terms_version": SINK_VERSION}, format="json", **self.auth_headers(self.operator))

        self.assertEqual(resp.status_code, 502)
        self.assertFalse(Sink.objects.exists())
        self.fake_emqx.apply_sink.assert_not_called()

    def test_a_failed_publish_keeps_nothing(self):
        mesh = self.create_mesh(self.operator)
        self.fake_publisher.publish_mesh_sinks.side_effect = RuntimeError("kafka down")

        resp = self.client.post(
            "/sinks", {"terms_version": SINK_VERSION, "mesh_ids": [mesh["id"]]}, format="json",
            **self.auth_headers(self.operator),
        )

        self.assertEqual(resp.status_code, 502)
        self.assertFalse(Sink.objects.exists())
        self.assertFalse(MeshSink.objects.exists())
        self.assertFalse(TermsAcceptance.objects.filter(kind=TermsKind.SINK).exists())
        self.fake_emqx.delete_sink.assert_called_once()
        self.assertEqual(self.fake_publisher.publish_sink.call_args.args[1], None)

    def test_the_terms_are_required_and_recorded(self):
        missing = self.client.post("/sinks", {}, format="json", **self.auth_headers(self.operator))
        stale = self.client.post("/sinks", {"terms_version": "old"}, format="json", **self.auth_headers(self.operator))
        sink = self.create_sink(self.operator)

        self.assertEqual((missing.status_code, stale.status_code), (400, 400))
        acceptance = TermsAcceptance.objects.get(sink_id=sink["id"])
        self.assertEqual((acceptance.kind, acceptance.terms_version), (TermsKind.SINK, SINK_VERSION))
        self.assertEqual(sink["terms_accepted_version"], SINK_VERSION)

    @override_settings(TERMS_ENFORCED=False)
    def test_without_terms_none_are_asked(self):
        resp = self.client.post("/sinks", {}, format="json", **self.auth_headers(self.operator))

        self.assertEqual(resp.status_code, 201)
        self.assertFalse(TermsAcceptance.objects.filter(kind=TermsKind.SINK).exists())


class UpdateTests(SinkTestCase):
    def setUp(self):
        super().setUp()
        self.mesh = self.create_mesh(self.operator)
        self.sink = self.create_sink(self.operator, mesh_ids=[self.mesh["id"]])
        self.fake_publisher.reset_mock()

    def test_changing_streams_republishes_the_sink(self):
        resp = self.put_sink(self.sink["id"], streams=["decoded", "derived"])

        self.assertEqual(resp.status_code, 200)
        self.fake_publisher.publish_sink.assert_called_once_with(Sink.objects.get().id, ["decoded", "derived"])
        self.fake_publisher.publish_mesh_sinks.assert_not_called()

    def test_a_failed_streams_publish_is_rolled_back(self):
        self.fake_publisher.publish_sink.side_effect = RuntimeError("kafka down")

        resp = self.put_sink(self.sink["id"], streams=["alarms"])

        self.assertEqual(resp.status_code, 502)
        self.assertEqual(Sink.objects.get().streams, ["decoded"])

    def test_detaching_a_mesh_publishes_it_empty_and_records_it(self):
        resp = self.put_sink(self.sink["id"], mesh_ids=[])

        self.assertEqual(resp.json()["mesh_ids"], [])
        self.fake_publisher.publish_mesh_sinks.assert_called_once_with(Mesh.objects.get().id, [])
        self.assertEqual(
            list(SinkInstruction.objects.filter(mesh_id=self.mesh["id"]).order_by("given_at").values_list("enabled", flat=True)),
            [True, False],
        )

    def test_a_failed_detach_keeps_the_mesh_attached(self):
        self.fake_publisher.publish_mesh_sinks.side_effect = [RuntimeError("kafka down"), None]

        resp = self.put_sink(self.sink["id"], mesh_ids=[])

        self.assertEqual(resp.status_code, 502)
        self.assertTrue(MeshSink.objects.exists())
        self.assertEqual(SinkInstruction.objects.filter(enabled=False).count(), 0)

    def test_omitted_lists_are_kept(self):
        self.put_sink(self.sink["id"], label="Renamed")

        self.assertTrue(MeshSink.objects.exists())
        self.fake_publisher.publish_mesh_sinks.assert_not_called()


class DeleteTests(SinkTestCase):
    def test_a_sink_with_attachments_cannot_be_deleted(self):
        mesh = self.create_mesh(self.operator)
        sink = self.create_sink(self.operator, mesh_ids=[mesh["id"]])

        resp = self.client.delete(f"/sinks/{sink['id']}", **self.auth_headers(self.operator))

        self.assertEqual(resp.status_code, 409)
        self.fake_emqx.delete_sink.assert_not_called()

    def test_deleting_revokes_the_credentials_first(self):
        sink = self.create_sink(self.operator)

        resp = self.client.delete(f"/sinks/{sink['id']}", **self.auth_headers(self.operator))

        self.assertEqual(resp.status_code, 204)
        self.fake_emqx.delete_sink.assert_called_once_with(sink["id"])
        self.assertEqual(self.fake_publisher.publish_sink.call_args.args[1], None)
        self.assertFalse(Sink.objects.exists())
        self.assertTrue(TermsAcceptance.objects.filter(kind=TermsKind.SINK).exists())

    def test_a_failed_revocation_keeps_the_sink(self):
        sink = self.create_sink(self.operator)
        self.fake_emqx.delete_sink.side_effect = RuntimeError("emqx down")

        resp = self.client.delete(f"/sinks/{sink['id']}", **self.auth_headers(self.operator))

        self.assertEqual(resp.status_code, 502)
        self.assertTrue(Sink.objects.exists())


class CredentialsTests(SinkTestCase):
    def test_rotating_returns_a_new_password_and_kicks_consumers(self):
        sink = self.create_sink(self.operator)

        resp = self.client.post(f"/sinks/{sink['id']}/credentials", **self.auth_headers(self.operator))

        new = resp.json()["password"]
        self.assertNotEqual(new, sink["password"])
        self.fake_emqx.set_sink_password.assert_called_once_with(sink["id"], new)
        self.fake_emqx.kick_sink_clients.assert_called_once_with(sink["id"])

    def test_a_failed_rotation_answers_502(self):
        sink = self.create_sink(self.operator)
        self.fake_emqx.set_sink_password.side_effect = RuntimeError("emqx down")

        resp = self.client.post(f"/sinks/{sink['id']}/credentials", **self.auth_headers(self.operator))

        self.assertEqual(resp.status_code, 502)


class RoutingTests(SinkTestCase):
    def setUp(self):
        super().setUp()
        self.mesh = self.create_mesh(self.operator)
        self.node = self.create_node(self.operator, self.mesh, device_id=7)
        self.sink = self.create_sink(self.operator, mesh_ids=[self.mesh["id"]], device_ids=[self.node["uuid"]])
        self.ref = sink_names.ref(self.sink["id"])

    def test_a_device_lists_the_archive_before_its_mqtt_sinks(self):
        mesh = Mesh.objects.get()
        Device.objects.filter(pk=self.node["uuid"]).update(archive_enabled=True)

        self.assertEqual(sinks.device_sinks(mesh, 7), ["archive", self.ref])
        self.assertEqual(sinks.mesh_sinks(mesh), [self.ref])

    def test_a_disallowed_registration_is_not_sent(self):
        Device.objects.filter(pk=self.node["uuid"]).update(is_allowed=False)

        self.assertEqual(sinks.device_sinks(Mesh.objects.get(), 7), [])

    def test_losing_the_operator_role_sends_nothing(self):
        admin = self.create_owner(name="Admin", email="sink-admin3@example.com")
        self.promote_to_superuser(admin)
        self.fake_publisher.reset_mock()

        resp = self.client.put(
            f"/owners/{self.operator['id']}", {"role": "member"}, format="json", **self.auth_headers(admin)
        )

        self.assertEqual(resp.status_code, 200, resp.content)
        mesh_id = Mesh.objects.get().id
        self.assertIn((mesh_id, []), self.mesh_sink_events())
        self.assertIn((mesh_id, 7, []), self.device_sink_events())

    def test_deleting_the_mesh_unpublishes_it(self):
        mesh_id = Mesh.objects.get().id
        self.fake_publisher.reset_mock()

        self.client.delete(f"/meshes/{self.mesh['id']}", **self.auth_headers(self.operator))

        self.assertIn((mesh_id, []), self.mesh_sink_events())
        self.assertIn((mesh_id, 7, []), self.device_sink_events())
        self.assertFalse(MeshSink.objects.exists())
        self.assertFalse(DeviceSink.objects.exists())

    def test_the_command_republishes_everything(self):
        self.fake_publisher.reset_mock()

        call_command("publish_sink_config", stdout=StringIO())

        self.fake_publisher.publish_sink.assert_called_once_with(Sink.objects.get().id, ["decoded"])
        self.assertEqual(self.mesh_sink_events(), [(Mesh.objects.get().id, [self.ref])])
        self.assertEqual(self.device_sink_events(), [(Mesh.objects.get().id, 7, [self.ref])])


@override_settings(DATA_RETENTION_DAYS=365, TERMS_RENEWAL_NOTICE_DAYS=30)
class LapseTests(SinkTestCase):
    def setUp(self):
        super().setUp()
        self.sink = self.create_sink(self.operator)
        self.acceptance = TermsAcceptance.objects.get(sink_id=self.sink["id"])
        mail.outbox.clear()
        self.fake_publisher.reset_mock()

    def test_the_operator_is_emailed_before_it_lapses(self):
        inside = self.acceptance.expires_at - timedelta(days=10)

        self.assertEqual(data_lifecycle.send_renewal_notices(inside), 1)
        self.assertIn(f"sinks/{self.sink['id']}", mail.outbox[0].body)

    def test_a_lapsed_sink_stops_sending_and_refuses_its_consumer(self):
        now = self.acceptance.expires_at + timedelta(minutes=1)

        self.assertEqual(data_lifecycle.pause_lapsed_sinks(now), 1)

        self.fake_publisher.publish_sink.assert_called_once_with(Sink.objects.get().id, None)
        self.fake_emqx.pause_sink.assert_called_once_with(self.sink["id"])
        self.assertIsNotNone(Sink.objects.get().paused_at)
        self.assertIn("paused", mail.outbox[0].body)

    def test_a_failed_pause_is_retried(self):
        self.fake_emqx.pause_sink.side_effect = RuntimeError("emqx down")

        self.assertEqual(data_lifecycle.pause_lapsed_sinks(self.acceptance.expires_at + timedelta(minutes=1)), 0)
        self.assertIsNone(Sink.objects.get().paused_at)

    def test_renewing_resumes_with_the_same_credentials(self):
        data_lifecycle.pause_lapsed_sinks(self.acceptance.expires_at + timedelta(minutes=1))
        self.fake_publisher.reset_mock()

        resp = self.client.post(
            f"/sinks/{self.sink['id']}/terms-acceptance", {"terms_version": SINK_VERSION}, format="json",
            **self.auth_headers(self.operator),
        )

        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(resp.json()["paused_at"])
        self.fake_emqx.apply_sink.assert_called_with(self.sink["id"])
        self.fake_publisher.publish_sink.assert_called_once_with(Sink.objects.get().id, ["decoded"])

    def test_a_paused_sinks_streams_are_not_published(self):
        Sink.objects.update(paused_at=timezone.now())

        self.put_sink(self.sink["id"], streams=["alarms"])

        self.fake_publisher.publish_sink.assert_not_called()


class SyncTests(SinkTestCase):
    def test_check_reports_authorization_and_differences(self):
        sink = self.create_sink(self.operator)
        self.fake_emqx.managed_sink_ids.return_value = (set(), {"orphan"})
        self.fake_emqx.sink_authorization_problem.return_value = "not first"
        out = StringIO()

        with self.assertRaises(CommandError):
            call_command("sync_sinks", "--check", stdout=out)

        self.assertIn(f"no user in EMQX: {sink['id']}", out.getvalue())
        self.assertIn("orphaned in EMQX: orphan", out.getvalue())
        self.assertIn("authorization: not first", out.getvalue())

    def test_syncing_refuses_until_authorization_is_installed(self):
        self.fake_emqx.sink_authorization_problem.return_value = "not first"
        self.fake_emqx.managed_sink_ids.return_value = (set(), set())

        with self.assertRaises(CommandError):
            call_command("sync_sinks", stdout=StringIO())
        self.fake_emqx.apply_sink.assert_not_called()

    def test_syncing_reapplies_rules_and_removes_orphans(self):
        sink = self.create_sink(self.operator)
        self.fake_emqx.reset_mock()
        self.fake_emqx.sink_authorization_problem.return_value = None
        self.fake_emqx.managed_sink_ids.return_value = ({sink["id"]}, {"orphan"})

        call_command("sync_sinks", "--install-authz", stdout=StringIO())

        self.fake_emqx.install_sink_authorization.assert_called_once()
        self.fake_emqx.apply_sink_namespace.assert_called_once()
        self.fake_emqx.apply_sink.assert_called_once_with(sink["id"])
        self.fake_emqx.delete_sink.assert_called_once_with("orphan")


class OwnerDeletionTests(SinkTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.create_owner(name="Admin", email="sink-admin4@example.com")
        self.promote_to_superuser(self.admin)
        self.other = self.create_owner(name="Other", email="sink-other2@example.com")
        self.promote_to_operator(self.other)

    def delete_operator(self):
        return self.client.delete(f"/owners/{self.operator['id']}", **self.auth_headers(self.admin))

    def test_deleting_an_owner_deletes_their_sinks_and_revokes_them(self):
        sink = self.create_sink(self.operator, mesh_ids=[self.create_mesh(self.operator)["id"]])
        kept = self.create_sink(self.other)

        resp = self.delete_operator()

        self.assertEqual(resp.status_code, 204, resp.content)
        self.assertEqual([str(s.id) for s in Sink.objects.all()], [kept["id"]])
        self.fake_emqx.delete_sink.assert_called_once_with(sink["id"])
        self.assertIn(call(uuid.UUID(sink["id"]), None), self.fake_publisher.publish_sink.call_args_list)

    def test_another_owners_mesh_on_a_deleted_sink_is_republished_without_it(self):
        other_mesh = self.create_mesh(self.other, channel_id="O")
        # A superuser may attach any operator's mesh to a sink.
        sink = self.create_sink(self.admin, mesh_ids=[other_mesh["id"]])
        self.fake_publisher.reset_mock()

        resp = self.client.delete(f"/owners/{self.admin['id']}", **self.auth_headers(self.admin))

        self.assertEqual(resp.status_code, 204, resp.content)
        self.assertFalse(Sink.objects.filter(pk=sink["id"]).exists())
        self.assertIn((Mesh.objects.get(pk=other_mesh["id"]).id, []), self.mesh_sink_events())

    def test_a_failed_revocation_keeps_the_owner_and_their_sinks(self):
        self.create_sink(self.operator)
        self.fake_emqx.delete_sink.side_effect = RuntimeError("emqx down")

        resp = self.delete_operator()

        self.assertEqual(resp.status_code, 502)
        self.assertTrue(Owner.objects.filter(pk=self.operator["id"]).exists())
        self.assertTrue(Sink.objects.exists())


class SchemaTests(SimpleTestCase):
    def test_streams_are_typed_in_every_sink_response(self):
        schemas = SchemaGenerator().get_schema(request=None, public=True)["components"]["schemas"]
        for name in ("SinkRead", "SinkCredentials"):
            streams = schemas[name]["properties"]["streams"]
            self.assertEqual(streams["type"], "array", name)
            self.assertEqual(streams["items"], {"$ref": "#/components/schemas/StreamsEnum"}, name)
        self.assertEqual(schemas["StreamsEnum"]["enum"], list(sink_names.STREAMS))
