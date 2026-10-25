"""Opting a device in to the archive, and keeping mesh.sink_config.v1 in step with it."""
import uuid
from io import StringIO

from django.core.management import call_command

from registry.models import Device, Mesh, SinkInstruction

from .helpers import RegistryTestCase


class ArchiveSinkTestCase(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.operator = self.create_owner(name="Operator", email="archive-operator@example.com")
        self.promote_to_operator(self.operator)
        self.mesh = self.create_mesh(self.operator)
        self.node = self.create_node(self.operator, self.mesh, device_id=42)
        self.fake_publisher.reset_mock()

    def put_device(self, owner, body, device=None):
        return self.client.put(
            f"/devices/{(device or self.node)['uuid']}", body, format="json", **self.auth_headers(owner)
        )

    def archive(self, owner=None, enabled=True, device=None):
        return self.put_device(owner or self.operator, {"archive_enabled": enabled}, device)

    def published_sinks(self):
        return [c.args for c in self.fake_publisher.publish_device_sinks.call_args_list]


class OptInTests(ArchiveSinkTestCase):
    def test_an_operator_archives_a_device(self):
        response = self.archive()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["archive_enabled"])
        self.assertEqual(self.published_sinks(), [(uuid.UUID(self.mesh["id"]), 42, ["archive"])])

    def test_turning_it_off_sends_no_sinks(self):
        self.archive()
        self.fake_publisher.reset_mock()

        self.assertEqual(self.archive(enabled=False).status_code, 200)

        self.assertEqual(self.published_sinks(), [(uuid.UUID(self.mesh["id"]), 42, [])])

    def test_an_unchanged_setting_publishes_nothing(self):
        self.assertEqual(self.put_device(self.operator, {"label": "kitchen"}).status_code, 200)
        self.assertEqual(self.archive(enabled=False).status_code, 200)

        self.fake_publisher.publish_device_sinks.assert_not_called()

    def test_a_member_cannot_archive(self):
        member = self.create_owner(name="Member", email="archive-member@example.com")
        mesh = self.create_mesh(member)
        node = self.create_node(member, mesh, device_id=7)

        response = self.archive(member, device=node)

        self.assertEqual(response.status_code, 400)
        self.assertIn("archive_enabled", response.json())
        self.assertFalse(Device.objects.get(pk=node["uuid"]).archive_enabled)

    def test_a_superuser_owns_meshes_that_can_be_archived(self):
        admin = self.create_owner(name="Admin", email="archive-admin@example.com")
        self.promote_to_superuser(admin)
        mesh = self.create_mesh(admin)
        node = self.create_node(admin, mesh, device_id=8)

        self.assertEqual(self.archive(admin, device=node).status_code, 200)

    def test_an_instance_without_an_archive_refuses(self):
        self.fake_store.archive_bucket = ""

        self.assertEqual(self.archive().status_code, 400)
        self.fake_publisher.publish_device_sinks.assert_not_called()

    def test_a_failed_publish_rolls_the_setting_back(self):
        self.fake_publisher.publish_device_sinks.side_effect = RuntimeError("kafka down")

        self.assertEqual(self.archive().status_code, 502)

        self.assertFalse(Device.objects.get(pk=self.node["uuid"]).archive_enabled)

    def test_a_failed_publish_applies_nothing_else_in_the_request(self):
        """A 502 that claims a rollback must not leave the rest of the request saved or sent."""
        self.fake_publisher.publish_device_sinks.side_effect = RuntimeError("kafka down")

        response = self.put_device(
            self.operator, {"archive_enabled": True, "label": "kitchen", "reading_interval_seconds": 600}
        )

        self.assertEqual(response.status_code, 502)
        device = Device.objects.get(pk=self.node["uuid"])
        self.assertNotEqual(device.label, "kitchen")
        self.assertNotEqual(device.reading_interval_seconds, 600)
        self.fake_publisher.publish_device_intervals.assert_not_called()
        self.assertFalse(SinkInstruction.objects.exists())

    def test_a_failed_reject_sends_the_archive_setting_back(self):
        """The archive is published before the rejection, so the pipeline must be told it was undone."""
        self.fake_publisher.publish_node_reject.side_effect = RuntimeError("kafka down")

        response = self.put_device(self.operator, {"archive_enabled": True, "is_allowed": False})

        self.assertEqual(response.status_code, 502)
        device = Device.objects.get(pk=self.node["uuid"])
        self.assertFalse(device.archive_enabled)
        self.assertTrue(device.is_allowed)
        self.assertEqual(self.published_sinks()[-1], (uuid.UUID(self.mesh["id"]), 42, []))
        self.assertFalse(SinkInstruction.objects.exists())

    def test_a_disallowed_registration_is_not_archived(self):
        self.archive()
        self.fake_publisher.reset_mock()

        self.assertEqual(self.put_device(self.operator, {"is_allowed": False}).status_code, 200)

        self.assertEqual(self.published_sinks(), [(uuid.UUID(self.mesh["id"]), 42, [])])


class InstructionRecordTests(ArchiveSinkTestCase):
    """Record who told the processor to archive a device, and when (GDPR Art. 5(2))."""

    def test_switching_on_records_who_and_when(self):
        body = self.archive().json()

        self.assertIsNotNone(body["archive_enabled_at"])
        self.assertEqual(str(body["archive_enabled_by"]), self.operator["id"])
        record = SinkInstruction.objects.get()
        self.assertEqual((record.sink, record.enabled, record.node_id), ("archive", True, 42))
        self.assertEqual((str(record.mesh_id), record.given_by_email), (self.mesh["id"], self.operator["email"]))

    def test_switching_off_clears_the_device_and_appends_to_the_history(self):
        self.archive()

        body = self.archive(enabled=False).json()

        self.assertIsNone(body["archive_enabled_at"])
        self.assertIsNone(body["archive_enabled_by"])
        self.assertEqual(list(SinkInstruction.objects.order_by("given_at").values_list("enabled", flat=True)), [True, False])

    def test_a_superuser_is_recorded_as_themselves(self):
        admin = self.create_owner(name="Admin", email="archive-record-admin@example.com")
        self.promote_to_superuser(admin)

        self.archive(admin)

        self.assertEqual(SinkInstruction.objects.get().given_by_email, admin["email"])

    def test_nothing_is_recorded_when_the_pipeline_was_not_told(self):
        self.fake_publisher.publish_device_sinks.side_effect = RuntimeError("kafka down")

        self.archive()

        self.assertFalse(SinkInstruction.objects.exists())
        self.assertIsNone(Device.objects.get(pk=self.node["uuid"]).archive_enabled_at)

    def test_the_history_outlives_the_device(self):
        self.archive()

        self.client.delete(f"/devices/{self.node['uuid']}", **self.auth_headers(self.operator))

        record = SinkInstruction.objects.get()
        self.assertIsNone(record.device)
        self.assertEqual((record.node_id, record.given_by_email), (42, self.operator["email"]))


class VisibilityTests(ArchiveSinkTestCase):
    def test_the_setting_is_shown_to_the_owner_and_superusers_only(self):
        Mesh.objects.filter(pk=self.mesh["id"]).update(is_public=True)
        viewer = self.create_owner(name="Viewer", email="archive-viewer@example.com")
        admin = self.create_owner(name="Admin", email="archive-admin2@example.com")
        self.promote_to_superuser(admin)

        for caller, shown in ((self.operator, True), (admin, True), (viewer, False)):
            with self.subTest(caller=caller["email"]):
                body = self.client.get(f"/devices/{self.node['uuid']}", **self.auth_headers(caller)).json()
                for field in ("archive_enabled", "archive_enabled_at", "archive_enabled_by"):
                    self.assertEqual(field in body, shown, field)


class RoleTests(ArchiveSinkTestCase):
    def setUp(self):
        super().setUp()
        self.archive()
        self.fake_publisher.reset_mock()
        self.admin = self.create_owner(name="Admin", email="archive-role-admin@example.com")
        self.promote_to_superuser(self.admin)

    def set_role(self, role):
        return self.client.put(
            f"/owners/{self.operator['id']}", {"role": role}, format="json", **self.auth_headers(self.admin)
        )

    def test_taking_the_role_away_stops_archiving(self):
        self.assertEqual(self.set_role("member").status_code, 200)

        self.assertEqual(self.published_sinks(), [(uuid.UUID(self.mesh["id"]), 42, [])])

    def test_granting_it_again_resumes(self):
        self.set_role("member")
        self.fake_publisher.reset_mock()

        self.set_role("operator")

        self.assertEqual(self.published_sinks(), [(uuid.UUID(self.mesh["id"]), 42, ["archive"])])

    def test_the_role_is_kept_if_archiving_cannot_be_stopped(self):
        self.fake_publisher.publish_device_sinks.side_effect = RuntimeError("kafka down")

        self.assertEqual(self.set_role("member").status_code, 502)

        self.assertEqual(self.client.get("/owners/me", **self.auth_headers(self.operator)).json()["role"], "operator")


class DeletionTests(ArchiveSinkTestCase):
    def test_deleting_an_archived_device_stops_archiving_it_first(self):
        self.archive()
        self.fake_publisher.reset_mock()

        response = self.client.delete(f"/devices/{self.node['uuid']}", **self.auth_headers(self.operator))

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.published_sinks(), [(uuid.UUID(self.mesh["id"]), 42, [])])

    def test_a_device_that_was_not_archived_sends_nothing(self):
        self.client.delete(f"/devices/{self.node['uuid']}", **self.auth_headers(self.operator))

        self.fake_publisher.publish_device_sinks.assert_not_called()

    def test_a_mesh_is_kept_if_archiving_cannot_be_stopped(self):
        self.archive()
        self.fake_publisher.publish_device_sinks.side_effect = RuntimeError("kafka down")

        response = self.client.delete(f"/meshes/{self.mesh['id']}", **self.auth_headers(self.operator))

        self.assertEqual(response.status_code, 502)
        self.assertTrue(Mesh.objects.filter(pk=self.mesh["id"]).exists())


class RepublishCommandTests(ArchiveSinkTestCase):
    def test_every_archived_device_is_republished(self):
        self.archive()
        self.create_node(self.operator, self.mesh, device_id=43)
        self.fake_publisher.reset_mock()
        out = StringIO()

        call_command("publish_sink_config", stdout=out)

        self.assertEqual(self.published_sinks(), [(uuid.UUID(self.mesh["id"]), 42, ["archive"])])
        self.assertIn("1 device", out.getvalue())
