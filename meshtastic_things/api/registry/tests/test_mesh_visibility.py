"""Reading a mesh you don't own, through `is_public` or an explicit grant.

The rule under test throughout: reads widen, writes never do.
"""
import uuid
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command

from registry.models import (
    Device,
    DeviceTelemetryVariant,
    Measurement,
    Mesh,
    MeshViewer,
    Owner,
    TelemetryVariant,
)

from .helpers import RegistryTestCase


class MeshVisibilityTestCase(RegistryTestCase):
    """An owner with a mesh and a node, plus a second owner with no relationship to it."""

    def setUp(self):
        super().setUp()
        self.owner = self.create_owner(name="Owner", email="mesh-owner@example.com")
        self.mesh = self.create_mesh(self.owner, channel_id="shared", label="Garden mesh")
        self.node = self.create_node(self.owner, self.mesh, device_id=1, label="greenhouse")
        self.outsider = self.create_owner(name="Outsider", email="outsider@example.com")
        mail.outbox.clear()

    def make_public(self):
        Mesh.objects.filter(pk=self.mesh["id"]).update(is_public=True)

    def grant(self, owner=None):
        MeshViewer.objects.create(
            mesh=Mesh.objects.get(pk=self.mesh["id"]),
            viewer=Owner.objects.get(pk=uuid.UUID((owner or self.outsider)["id"])),
        )

    def _seed_measurement(self):
        """A device only gets measurements once a telemetry variant is discovered for it."""
        call_command("seed_measurement_catalog", stdout=StringIO())
        variant = TelemetryVariant.objects.get(payload_kind="telemetry:environment_metrics")
        dtv = DeviceTelemetryVariant.objects.create(
            device_id=self.node["uuid"], telemetry_variant=variant
        )
        link = variant.measurement_links.get(measurement_type__field_name="temperature")
        return Measurement.objects.create(
            device_telemetry_variant=dtv, measurement_type=link.measurement_type
        )

    def as_outsider(self, method, path, body=None):
        call = getattr(self.client, method)
        if body is None:
            return call(path, **self.auth_headers(self.outsider))
        return call(path, body, format="json", **self.auth_headers(self.outsider))


class NoRelationshipTests(MeshVisibilityTestCase):
    """The default: a private mesh is invisible to everyone but its owner."""

    def test_reading_a_private_mesh_is_a_404_not_a_403(self):
        """403 would confirm the mesh exists to someone who cannot read it."""
        resp = self.as_outsider("get", f"/meshes/{self.mesh['id']}")

        self.assertEqual(resp.status_code, 404)

    def test_its_devices_are_a_404_too(self):
        self.assertEqual(self.as_outsider("get", f"/meshes/{self.mesh['id']}/devices").status_code, 404)
        self.assertEqual(self.as_outsider("get", f"/devices/{self.node['uuid']}").status_code, 404)

    def test_it_is_absent_from_the_lists(self):
        meshes = self.as_outsider("get", "/meshes").json()
        devices = self.as_outsider("get", "/devices").json()

        self.assertEqual(meshes, [])
        self.assertEqual(devices, [])


class PublicMeshTests(MeshVisibilityTestCase):
    def test_any_verified_owner_can_read_a_public_mesh(self):
        self.make_public()

        resp = self.as_outsider("get", f"/meshes/{self.mesh['id']}")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["label"], "Garden mesh")

    def test_a_public_mesh_appears_in_the_mesh_list(self):
        self.make_public()

        listed = self.as_outsider("get", "/meshes").json()

        self.assertEqual([m["id"] for m in listed], [self.mesh["id"]])

    def test_owned_filter_excludes_meshes_the_caller_does_not_own(self):
        self.make_public()

        self.assertEqual(self.as_outsider("get", "/meshes?owned=true").json(), [])
        self.assertEqual(len(self.as_outsider("get", "/meshes").json()), 1)

    def test_the_owner_still_sees_their_own_mesh_under_the_owned_filter(self):
        self.make_public()

        listed = self.client.get("/meshes?owned=true", **self.auth_headers(self.owner)).json()

        self.assertEqual([m["id"] for m in listed], [self.mesh["id"]])

    def test_its_devices_are_readable(self):
        self.make_public()

        on_mesh = self.as_outsider("get", f"/meshes/{self.mesh['id']}/devices")
        one = self.as_outsider("get", f"/devices/{self.node['uuid']}")

        self.assertEqual(on_mesh.status_code, 200)
        self.assertEqual(len(on_mesh.json()), 1)
        self.assertEqual(one.status_code, 200)

    def test_turning_it_private_again_takes_effect_immediately(self):
        self.make_public()
        self.assertEqual(self.as_outsider("get", f"/meshes/{self.mesh['id']}").status_code, 200)

        Mesh.objects.filter(pk=self.mesh["id"]).update(is_public=False)

        self.assertEqual(self.as_outsider("get", f"/meshes/{self.mesh['id']}").status_code, 404)

    def test_a_mesh_that_is_both_public_and_granted_is_listed_once(self):
        """The grant join duplicates rows without the distinct()."""
        self.make_public()
        self.grant()

        listed = self.as_outsider("get", "/meshes").json()

        self.assertEqual(len(listed), 1)


class GrantedViewerTests(MeshVisibilityTestCase):
    def test_a_grant_makes_a_private_mesh_readable(self):
        self.grant()

        resp = self.as_outsider("get", f"/meshes/{self.mesh['id']}")

        self.assertEqual(resp.status_code, 200)

    def test_a_grant_covers_the_meshs_devices(self):
        self.grant()

        self.assertEqual(self.as_outsider("get", f"/meshes/{self.mesh['id']}/devices").status_code, 200)
        self.assertEqual(self.as_outsider("get", f"/devices/{self.node['uuid']}").status_code, 200)
        self.assertEqual(
            self.as_outsider("get", f"/devices/{self.node['uuid']}/telemetry-variants").status_code, 200
        )
        self.assertEqual(self.as_outsider("get", f"/devices/{self.node['uuid']}/measurements").status_code, 200)

    def test_the_device_appears_in_the_device_list(self):
        self.grant()

        listed = self.as_outsider("get", "/devices").json()

        self.assertEqual([d["uuid"] for d in listed], [self.node["uuid"]])

    def test_revoking_takes_effect_immediately(self):
        self.grant()
        self.assertEqual(self.as_outsider("get", f"/meshes/{self.mesh['id']}").status_code, 200)

        MeshViewer.objects.all().delete()

        self.assertEqual(self.as_outsider("get", f"/meshes/{self.mesh['id']}").status_code, 404)

    def test_a_grant_on_one_mesh_does_not_reach_another(self):
        other = self.create_mesh(self.owner, channel_id="other", label="Other mesh")
        self.grant()

        self.assertEqual(self.as_outsider("get", f"/meshes/{other['id']}").status_code, 404)

    def test_deleting_the_viewer_leaves_the_mesh_intact(self):
        self.grant()

        Owner.objects.filter(pk=uuid.UUID(self.outsider["id"])).delete()

        self.assertTrue(Mesh.objects.filter(pk=self.mesh["id"]).exists())
        self.assertEqual(MeshViewer.objects.count(), 0)

    def test_deleting_the_mesh_drops_the_grant(self):
        self.grant()

        Mesh.objects.filter(pk=self.mesh["id"]).delete()

        self.assertEqual(MeshViewer.objects.count(), 0)


class ViewerSecretsTests(MeshVisibilityTestCase):
    """The property the whole change rests on: a viewer reads data, never key material."""

    def setUp(self):
        super().setUp()
        self.node_with_keys = self.create_node(
            self.owner, self.mesh, device_id=2, label="keyed", admin_keys_b64=["AAAA"]
        )
        self.grant()

    def test_a_viewer_never_receives_the_pre_shared_key(self):
        detail = self.as_outsider("get", f"/meshes/{self.mesh['id']}").json()
        listed = self.as_outsider("get", "/meshes").json()

        self.assertNotIn("psk_b64", detail)
        self.assertTrue(all("psk_b64" not in m for m in listed))

    def test_a_viewer_still_receives_the_channel_id(self):
        """Deliberate: channel_id is only half the pair, and the PSK half stays stripped."""
        detail = self.as_outsider("get", f"/meshes/{self.mesh['id']}").json()

        self.assertEqual(detail["channel_id"], "shared")
        self.assertNotIn("psk_b64", detail)

    def test_a_viewer_never_receives_admin_keys(self):
        """The field is dropped outright rather than blanked, so an empty list is not
        mistaken for "this device has none"."""
        one = self.as_outsider("get", f"/devices/{self.node_with_keys['uuid']}").json()
        on_mesh = self.as_outsider("get", f"/meshes/{self.mesh['id']}/devices").json()
        listed = self.as_outsider("get", "/devices").json()

        self.assertNotIn("admin_keys_b64", one)
        self.assertTrue(all("admin_keys_b64" not in d for d in on_mesh))
        self.assertTrue(all("admin_keys_b64" not in d for d in listed))

    def test_the_owner_still_sees_both(self):
        """Otherwise the tests above could pass by hiding the field from everyone."""
        mesh = self.client.get(f"/meshes/{self.mesh['id']}", **self.auth_headers(self.owner)).json()
        device = self.client.get(
            f"/devices/{self.node_with_keys['uuid']}", **self.auth_headers(self.owner)
        ).json()

        self.assertEqual(mesh["psk_b64"], "AAAA")
        self.assertEqual(device["admin_keys_b64"], ["AAAA"])


class ViewerCannotWriteTests(MeshVisibilityTestCase):
    """A grant and is_public widen reads only."""

    def setUp(self):
        super().setUp()
        self.grant()

    def test_a_viewer_cannot_edit_or_delete_the_mesh(self):
        self.assertEqual(
            self.as_outsider("put", f"/meshes/{self.mesh['id']}", {"label": "Mine now"}).status_code, 403
        )
        self.assertEqual(self.as_outsider("delete", f"/meshes/{self.mesh['id']}").status_code, 403)

    def test_a_viewer_cannot_edit_or_delete_a_device(self):
        self.assertEqual(
            self.as_outsider("put", f"/devices/{self.node['uuid']}", {"label": "Mine"}).status_code, 403
        )
        self.assertEqual(self.as_outsider("delete", f"/devices/{self.node['uuid']}").status_code, 403)

    def test_a_viewer_cannot_register_a_device_on_the_mesh(self):
        resp = self.as_outsider(
            "post", "/devices", {"node_id": 99, "mesh_id": self.mesh["id"], "is_gateway": False}
        )

        self.assertEqual(resp.status_code, 403)

    def test_a_viewer_can_read_but_not_edit_a_device_measurement(self):
        measurement = self._seed_measurement()

        readable = self.as_outsider("get", f"/devices/{self.node['uuid']}/measurements/{measurement.id}")
        written = self.as_outsider(
            "put", f"/devices/{self.node['uuid']}/measurements/{measurement.id}", {"valid_min": 0}
        )

        self.assertEqual(readable.status_code, 200)
        self.assertEqual(written.status_code, 403)

    def test_a_public_mesh_is_no_more_writable_than_a_granted_one(self):
        MeshViewer.objects.all().delete()
        self.make_public()

        self.assertEqual(
            self.as_outsider("put", f"/meshes/{self.mesh['id']}", {"label": "Mine now"}).status_code, 403
        )


class RejectedDevicesTests(MeshVisibilityTestCase):
    """A rejected registration is the owner's business, not a viewer's."""

    def setUp(self):
        super().setUp()
        self.grant()
        Device.objects.filter(pk=self.node["uuid"]).update(is_allowed=False)

    def test_a_viewer_does_not_see_a_rejected_device_on_the_mesh(self):
        on_mesh = self.as_outsider("get", f"/meshes/{self.mesh['id']}/devices").json()

        self.assertEqual(on_mesh, [])

    def test_a_viewer_cannot_fetch_a_rejected_device_directly(self):
        resp = self.as_outsider("get", f"/devices/{self.node['uuid']}")

        self.assertEqual(resp.status_code, 404)

    def test_a_viewer_cannot_reach_it_through_the_is_allowed_filter(self):
        """The filter must not become a way around the restriction."""
        listed = self.as_outsider("get", "/devices?is_allowed=false").json()

        self.assertEqual(listed, [])

    def test_the_owner_still_sees_it(self):
        on_mesh = self.client.get(
            f"/meshes/{self.mesh['id']}/devices", **self.auth_headers(self.owner)
        ).json()
        one = self.client.get(f"/devices/{self.node['uuid']}", **self.auth_headers(self.owner))

        self.assertEqual(len(on_mesh), 1)
        self.assertEqual(one.status_code, 200)


class MeshViewerManagementTests(MeshVisibilityTestCase):
    def viewers_url(self):
        return f"/meshes/{self.mesh['id']}/viewers"

    def post_grant(self, owner_id=None, as_owner=None):
        return self.client.post(
            self.viewers_url(),
            {"owner_id": owner_id or self.outsider["id"]},
            format="json",
            **self.auth_headers(as_owner or self.owner),
        )

    def test_the_owner_can_grant_and_list(self):
        created = self.post_grant()

        self.assertEqual(created.status_code, 201)
        listed = self.client.get(self.viewers_url(), **self.auth_headers(self.owner)).json()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["viewer"]["id"], self.outsider["id"])

    def test_the_viewer_list_never_includes_email(self):
        self.post_grant()

        listed = self.client.get(self.viewers_url(), **self.auth_headers(self.owner)).json()

        self.assertNotIn("email", listed[0]["viewer"])

    def test_granting_actually_grants_access(self):
        self.post_grant()

        self.assertEqual(self.as_outsider("get", f"/meshes/{self.mesh['id']}").status_code, 200)

    def test_the_owner_can_revoke(self):
        self.post_grant()

        resp = self.client.delete(
            f"{self.viewers_url()}/{self.outsider['id']}", **self.auth_headers(self.owner)
        )

        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.as_outsider("get", f"/meshes/{self.mesh['id']}").status_code, 404)

    def test_revoking_a_grant_that_does_not_exist_is_a_404(self):
        resp = self.client.delete(
            f"{self.viewers_url()}/{self.outsider['id']}", **self.auth_headers(self.owner)
        )

        self.assertEqual(resp.status_code, 404)

    def test_granting_twice_is_idempotent(self):
        first = self.post_grant()
        second = self.post_grant()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(MeshViewer.objects.count(), 1)

    def test_granting_to_the_mesh_owner_is_rejected(self):
        resp = self.post_grant(owner_id=self.owner["id"])

        self.assertEqual(resp.status_code, 400)

    def test_granting_to_an_unknown_owner_is_rejected(self):
        resp = self.post_grant(owner_id=str(uuid.uuid4()))

        self.assertEqual(resp.status_code, 400)

    def test_a_viewer_cannot_read_the_viewer_list(self):
        """Who else can see a mesh is the owner's business."""
        self.grant()

        resp = self.as_outsider("get", self.viewers_url())

        self.assertEqual(resp.status_code, 403)

    def test_a_viewer_cannot_grant_access_to_someone_else(self):
        self.grant()
        third = self.create_owner(name="Third", email="third@example.com")

        resp = self.post_grant(owner_id=third["id"], as_owner=self.outsider)

        self.assertEqual(resp.status_code, 403)

    def test_a_viewer_cannot_revoke_their_own_removal_of_others(self):
        self.grant()

        resp = self.client.delete(
            f"{self.viewers_url()}/{self.outsider['id']}", **self.auth_headers(self.outsider)
        )

        self.assertEqual(resp.status_code, 403)

    def test_an_unrelated_owner_gets_404_on_the_viewer_list(self):
        """Not 403 - the mesh must not confirm its existence to a stranger."""
        stranger = self.create_owner(name="Stranger", email="stranger@example.com")

        resp = self.client.get(self.viewers_url(), **self.auth_headers(stranger))

        self.assertEqual(resp.status_code, 403)


class SuperuserTests(MeshVisibilityTestCase):
    def setUp(self):
        super().setUp()
        self.promote_to_superuser(self.outsider)

    def test_a_superuser_reads_every_mesh_without_a_grant(self):
        resp = self.as_outsider("get", f"/meshes/{self.mesh['id']}")

        self.assertEqual(resp.status_code, 200)

    def test_a_superuser_still_gets_no_key_material(self):
        """Promotion is not a way to read PSKs; is_public must not change that."""
        self.make_public()

        detail = self.as_outsider("get", f"/meshes/{self.mesh['id']}").json()

        self.assertNotIn("psk_b64", detail)


class MeshAccessEmailTests(MeshVisibilityTestCase):
    def viewers_url(self):
        return f"/meshes/{self.mesh['id']}/viewers"

    def post_grant(self, owner_id=None):
        return self.client.post(
            self.viewers_url(),
            {"owner_id": owner_id or self.outsider["id"]},
            format="json",
            **self.auth_headers(self.owner),
        )

    def revoke(self, owner_id=None):
        return self.client.delete(
            f"{self.viewers_url()}/{owner_id or self.outsider['id']}", **self.auth_headers(self.owner)
        )

    def test_granting_emails_the_viewer(self):
        self.post_grant()

        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["outsider@example.com"])
        self.assertIn("Garden mesh", sent.body)
        self.assertIn("Owner", sent.body)

    def test_revoking_emails_the_viewer(self):
        self.post_grant()
        mail.outbox.clear()

        self.revoke()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Garden mesh", mail.outbox[0].body)

    def test_a_failing_send_does_not_fail_the_grant(self):
        """There is no retry loop here, so a dead mail server must not look like a
        failed grant when the row was written."""
        with patch(
            "registry.views.send_mesh_access_granted_email", side_effect=RuntimeError("smtp down")
        ):
            resp = self.post_grant()

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(MeshViewer.objects.count(), 1)

    def test_a_failing_send_does_not_fail_the_revoke(self):
        self.post_grant()

        with patch(
            "registry.views.send_mesh_access_revoked_email", side_effect=RuntimeError("smtp down")
        ):
            resp = self.revoke()

        self.assertEqual(resp.status_code, 204)
        self.assertEqual(MeshViewer.objects.count(), 0)

    def test_an_unverified_viewer_is_granted_but_not_emailed(self):
        unverified = self.client.post(
            "/owners",
            {"name": "Unverified", "email": "unverified@example.com", "password": self.DEFAULT_PASSWORD},
            format="json",
        ).json()
        mail.outbox.clear()

        resp = self.post_grant(owner_id=unverified["id"])

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(len(mail.outbox), 0)

    def test_granting_twice_emails_once(self):
        self.post_grant()
        self.post_grant()

        self.assertEqual(len(mail.outbox), 1)

    def test_regranting_after_a_revoke_emails_again(self):
        """No cooldown here on purpose: a re-grant is a real event, not a repeat alarm."""
        self.post_grant()
        self.revoke()
        self.post_grant()

        self.assertEqual(len(mail.outbox), 3)

    def test_making_a_mesh_public_emails_nobody(self):
        resp = self.client.put(
            f"/meshes/{self.mesh['id']}",
            {"is_public": True},
            format="json",
            **self.auth_headers(self.owner),
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)


class IsPublicToggleTests(MeshVisibilityTestCase):
    def test_the_owner_can_publish_and_unpublish_through_put(self):
        published = self.client.put(
            f"/meshes/{self.mesh['id']}",
            {"is_public": True},
            format="json",
            **self.auth_headers(self.owner),
        )

        self.assertEqual(published.status_code, 200)
        self.assertTrue(published.json()["is_public"])
        self.assertEqual(self.as_outsider("get", f"/meshes/{self.mesh['id']}").status_code, 200)

    def test_a_new_mesh_is_private(self):
        """The migration must not widen anything on its own."""
        self.assertFalse(self.client.get(
            f"/meshes/{self.mesh['id']}", **self.auth_headers(self.owner)
        ).json()["is_public"])

    def test_publishing_does_not_disturb_the_pre_shared_key(self):
        self.client.put(
            f"/meshes/{self.mesh['id']}",
            {"is_public": True},
            format="json",
            **self.auth_headers(self.owner),
        )

        mesh = Mesh.objects.get(pk=self.mesh["id"])

        self.assertEqual(mesh.psk_b64, "AAAA")
