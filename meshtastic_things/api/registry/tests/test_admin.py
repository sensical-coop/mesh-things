"""The Django admin at /admin"""
from django.contrib import admin
from django.urls import reverse

from django.utils import timezone

from registry.models import (
    BlueprintVersion,
    Device,
    DevicePostprocessing,
    DeviceTelemetryVariant,
    Measurement,
    MeasurementType,
    Mesh,
    Owner,
    PostprocessingBlueprint,
    PostprocessingInputBinding,
    PostprocessingStep,
    StepCalibration,
    TelemetryVariant,
    TelemetryVariantMeasurement,
)

from .helpers import RegistryTestCase


class ModelStrTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_owner(name="Alice", email="alice-admin@example.com")
        self.mesh = Mesh.objects.create(channel_id="SensorHub", psk_b64="AAAA", owner_id=self.owner["id"])

    def test_no_model_falls_back_to_the_default_object_repr(self):
        """The whole point: nothing should render as `<Model> object (<uuid>)`."""
        variant = TelemetryVariant.objects.create(payload_kind="telemetry:environment_metrics", name="EnvironmentMetrics")
        measurement_type = MeasurementType.objects.create(payload_kind="telemetry:environment_metrics", field_name="temperature")
        device = Device.objects.create(device_id=431637602, mesh=self.mesh, is_gateway=False, label="office node")
        link = TelemetryVariantMeasurement.objects.create(telemetry_variant=variant, measurement_type=measurement_type)
        dtv = DeviceTelemetryVariant.objects.create(device=device, telemetry_variant=variant)
        blueprint = PostprocessingBlueprint.objects.create(name="dew point", owner_id=self.owner["id"])
        version = BlueprintVersion.objects.create(blueprint=blueprint, number=1)
        measurement = Measurement.objects.create(device_telemetry_variant=dtv, measurement_type=measurement_type)
        attached = DevicePostprocessing.objects.create(device=device, blueprint_version=version)

        instances = [
            self.mesh,
            device,
            measurement_type,
            variant,
            link,
            dtv,
            blueprint,
            measurement,
            version,
            PostprocessingStep.objects.create(version=version, key="dew", order=1, function_name="dew_point"),
            attached,
            PostprocessingInputBinding.objects.create(device_postprocessing=attached, slot="t", measurement=measurement),
            StepCalibration.objects.create(
                device_postprocessing=attached, step_key="dew", function_name="dew_point", valid_from=timezone.now()
            ),
        ]

        for instance in instances:
            with self.subTest(model=type(instance).__name__):
                self.assertNotIn("object (", str(instance))
                self.assertTrue(str(instance).strip())

    def test_device_shows_the_node_number_in_wire_form(self):
        device = Device.objects.create(device_id=431637602, mesh=self.mesh, is_gateway=False, label="office node")
        self.assertEqual(str(device), "office node (!19ba4462)")

    def test_an_unlabelled_device_still_names_its_role(self):
        device = Device.objects.create(device_id=431637602, mesh=self.mesh, is_gateway=True)
        self.assertEqual(str(device), "gateway !19ba4462")

    def test_device_falls_back_through_the_names_it_has(self):
        device = Device.objects.create(device_id=1, mesh=self.mesh, is_gateway=False, short_name="ON")
        self.assertEqual(str(device), "ON (!00000001)")

    def test_measurement_type_reads_as_its_channel(self):
        measurement_type = MeasurementType.objects.create(
            payload_kind="telemetry:environment_metrics", field_name="temperature"
        )
        self.assertEqual(str(measurement_type), "environment_metrics.temperature")

    def test_mesh_does_not_repeat_the_channel_when_the_label_matches(self):
        self.assertEqual(str(self.mesh), "SensorHub")
        labelled = Mesh.objects.create(
            channel_id="LongFast", psk_b64="AAAA", label="roof", owner_id=self.owner["id"]
        )
        self.assertEqual(str(labelled), "roof (LongFast)")


class AdminRegistrationTests(RegistryTestCase):
    def test_every_model_a_person_curates_is_registered(self):
        registered = set(admin.site._registry)
        for model in (
            Mesh,
            Device,
            MeasurementType,
            TelemetryVariant,
            TelemetryVariantMeasurement,
            DeviceTelemetryVariant,
            Measurement,
            PostprocessingBlueprint,
            BlueprintVersion,
            DevicePostprocessing,
        ):
            with self.subTest(model=model.__name__):
                self.assertIn(model, registered)

    def test_device_admin_calls_the_node_number_node_id(self):
        """The API renamed this to node_id; the admin was the last place still showing the raw
        column name."""
        device_admin = admin.site._registry[Device]

        self.assertIn("node_id", device_admin.list_display)
        self.assertNotIn("device_id", device_admin.list_display)
        self.assertEqual(device_admin.node_id.short_description, "Node ID")

    def test_admins_whose_str_crosses_a_foreign_key_join_it_in(self):
        """Otherwise each row in a list view costs its own query."""
        for model in (Measurement, DeviceTelemetryVariant, TelemetryVariantMeasurement):
            with self.subTest(model=model.__name__):
                self.assertTrue(admin.site._registry[model].list_select_related)


class AdminMountTests(RegistryTestCase):
    """The admin is the one route with a trailing slash."""

    def test_admin_pages_live_under_a_slashed_prefix(self):
        self.assertEqual(reverse("admin:index"), "/admin/")
        self.assertEqual(reverse("admin:login"), "/admin/login/")
        self.assertEqual(reverse("admin:registry_device_changelist"), "/admin/registry/device/")

    def test_the_slashless_url_still_reaches_the_admin(self):
        resp = self.client.get("/admin")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/admin/")

    def test_a_staff_owner_can_open_every_registered_changelist(self):
        owner = self.create_owner(name="Admin", email="admin-mount@example.com")
        account = Owner.objects.get(pk=owner["id"])
        account.is_staff = True
        account.is_superuser = True
        account.set_password(self.DEFAULT_PASSWORD)
        account.save()
        self.assertTrue(self.client.login(email=account.email, password=self.DEFAULT_PASSWORD))

        for model in admin.site._registry:
            url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200)
                # The default repr, which is what makes an unlabelled admin unusable.
                self.assertNotIn(" object (", resp.content.decode("utf8", "replace"))
