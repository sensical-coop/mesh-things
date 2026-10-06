"""Reading a mesh you don't own, through `is_public`.

The rule under test throughout: reads widen, writes never do.
"""
from io import StringIO

from django.core import mail
from django.test import SimpleTestCase, override_settings
from django.core.management import call_command

from registry.models import (
    Device,
    DeviceTelemetryVariant,
    Measurement,
    Mesh,
    Source,
    TelemetryVariant,
)

from registry.emailing import console_url, frontend_url

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


class ViewerSecretsTests(MeshVisibilityTestCase):
    """The property the whole change rests on: a viewer reads data, never key material."""

    def setUp(self):
        super().setUp()
        self.node_with_keys = self.create_node(
            self.owner, self.mesh, device_id=2, label="keyed", admin_keys_b64=["AAAA"]
        )
        self.make_public()

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


class AnonymousViewerTests(MeshVisibilityTestCase):
    """A public mesh is readable without credentials, through the public fields only."""

    PUBLIC_FIELDS = {"id", "channel_id", "label", "owner_id", "is_public", "created_at", "updated_at"}

    def setUp(self):
        super().setUp()
        self.make_public()

    def test_a_public_mesh_is_readable_without_credentials(self):
        detail = self.client.get(f"/meshes/{self.mesh['id']}")
        listed = self.client.get("/meshes")

        self.assertEqual(detail.status_code, 200)
        self.assertEqual(set(detail.json()), self.PUBLIC_FIELDS)
        self.assertEqual([m["id"] for m in listed.json()], [self.mesh["id"]])
        self.assertEqual(set(listed.json()[0]), self.PUBLIC_FIELDS)

    def test_a_signed_in_viewer_gets_the_public_fields_too(self):
        detail = self.as_outsider("get", f"/meshes/{self.mesh['id']}").json()

        self.assertEqual(set(detail), self.PUBLIC_FIELDS)

    def test_its_devices_are_readable_without_admin_keys(self):
        self.create_node(self.owner, self.mesh, device_id=2, label="keyed", admin_keys_b64=["AAAA"])

        on_mesh = self.client.get(f"/meshes/{self.mesh['id']}/devices")

        self.assertEqual(on_mesh.status_code, 200)
        self.assertEqual(len(on_mesh.json()), 2)
        self.assertTrue(all("admin_keys_b64" not in d for d in on_mesh.json()))

    def test_rejected_devices_stay_hidden(self):
        Device.objects.filter(pk=self.node["uuid"]).update(is_allowed=False)

        self.assertEqual(self.client.get(f"/meshes/{self.mesh['id']}/devices").json(), [])

    def test_a_private_mesh_is_a_404(self):
        Mesh.objects.filter(pk=self.mesh["id"]).update(is_public=False)

        self.assertEqual(self.client.get(f"/meshes/{self.mesh['id']}").status_code, 404)
        self.assertEqual(self.client.get(f"/meshes/{self.mesh['id']}/devices").status_code, 404)
        self.assertEqual(self.client.get("/meshes").json(), [])

    def test_the_owned_filter_is_empty(self):
        self.assertEqual(self.client.get("/meshes?owned=true").json(), [])

    def test_the_source_filter_does_not_reveal_a_viewers_source(self):
        source = Source.objects.create(label="remote", server="mqtt.example.org", root="msh/EU_868")
        Mesh.objects.filter(pk=self.mesh["id"]).update(source=source)

        self.assertEqual(self.client.get(f"/meshes?source_id={source.id}").json(), [])
        self.assertEqual(self.as_outsider("get", f"/meshes?source_id={source.id}").json(), [])

    def test_writes_still_need_credentials(self):
        self.assertEqual(self.client.put(f"/meshes/{self.mesh['id']}", {"label": "x"}, format="json").status_code, 401)
        self.assertEqual(self.client.delete(f"/meshes/{self.mesh['id']}").status_code, 401)
        self.assertEqual(self.client.post("/meshes", {"channel_id": "x", "psk_b64": ""}, format="json").status_code, 401)


class ViewerCannotWriteTests(MeshVisibilityTestCase):
    """is_public widens reads only."""

    def setUp(self):
        super().setUp()
        self.make_public()

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


class RejectedDevicesTests(MeshVisibilityTestCase):
    """A rejected registration is the owner's business, not a viewer's."""

    def setUp(self):
        super().setUp()
        self.make_public()
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


class SuperuserTests(MeshVisibilityTestCase):
    def setUp(self):
        super().setUp()
        self.promote_to_superuser(self.outsider)

    def test_a_superuser_reads_every_private_mesh(self):
        resp = self.as_outsider("get", f"/meshes/{self.mesh['id']}")

        self.assertEqual(resp.status_code, 200)


class IsPublicToggleTests(MeshVisibilityTestCase):
    def test_making_a_mesh_public_emails_nobody(self):
        resp = self.client.put(
            f"/meshes/{self.mesh['id']}",
            {"is_public": True},
            format="json",
            **self.auth_headers(self.owner),
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

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


class FrontendUrlTests(SimpleTestCase):
    """Links are composed from the frontend base, the console prefix and the page."""

    @override_settings(PUBLIC_FRONTEND_URL="https://app.example.org/", FRONTEND_CONSOLE_PATH="/console")
    def test_console_pages_sit_under_the_prefix(self):
        self.assertEqual(console_url("meshes", "m1"), "https://app.example.org/console/meshes/m1")
        self.assertEqual(console_url("devices", "d1"), "https://app.example.org/console/devices/d1")

    @override_settings(PUBLIC_FRONTEND_URL="https://app.example.org", FRONTEND_CONSOLE_PATH="/")
    def test_a_root_prefix_puts_the_console_at_the_frontend_root(self):
        self.assertEqual(console_url("meshes", "m1"), "https://app.example.org/meshes/m1")

    @override_settings(PUBLIC_FRONTEND_URL="https://app.example.org", FRONTEND_CONSOLE_PATH="/console")
    def test_public_pages_are_outside_the_console(self):
        self.assertEqual(frontend_url("verify-email"), "https://app.example.org/verify-email")
