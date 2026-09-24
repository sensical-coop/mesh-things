import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils.functional import cached_property

from common import node_ids
from common.channels import channel_name


class OwnerManager(BaseUserManager):
    """Owners authenticate via bearer API key"""

    def create_user(self, email: str, name: str, password: str | None = None, **extra_fields):
        if not email:
            raise ValueError("Owners must have an email")
        owner = self.model(email=self.normalize_email(email), name=name, **extra_fields)
        if password:
            owner.set_password(password)
        else:
            owner.set_unusable_password()
        owner.save(using=self._db)
        return owner

    def create_superuser(self, email: str, name: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, name, password, **extra_fields)


class OwnerRole(models.TextChoices):
    MEMBER = "member", "Member"
    # Manages shared ingest infrastructure such as sources, without being a superuser.
    OPERATOR = "operator", "Operator"


class Owner(AbstractBaseUser, PermissionsMixin):
    """A registered account"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)
    # sha256 hex digest
    api_key_hash = models.CharField(max_length=64, unique=True, db_index=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    # is_active means "email-verified"
    email_verified_at = models.DateTimeField(null=True, blank=True)
    email_verification_token_hash = models.CharField(max_length=64, unique=True, db_index=True, null=True, blank=True)
    email_verification_sent_at = models.DateTimeField(null=True, blank=True)
    password_reset_token_hash = models.CharField(max_length=64, unique=True, db_index=True, null=True, blank=True)
    password_reset_sent_at = models.DateTimeField(null=True, blank=True)
    # Minimum seconds between quality-alarm emails. Null uses the server default.
    alarm_email_cooldown_seconds = models.PositiveIntegerField(null=True, blank=True)
    role = models.CharField(max_length=16, choices=OwnerRole.choices, default=OwnerRole.MEMBER)

    objects = OwnerManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        db_table = "owners"

    def __str__(self) -> str:
        return self.email

    @property
    def is_operator(self) -> bool:
        return self.is_superuser or self.role == OwnerRole.OPERATOR

    @property
    def visible_meshes(self):
        """Meshes this owner may read: their own, public ones, and ones they hold a
        viewer grant on. Every mesh for a superuser. The single definition of that rule."""
        if self.is_superuser:
            return Mesh.objects.all()
        return Mesh.objects.filter(
            models.Q(owner_id=self.id)
            | models.Q(is_public=True)
            | models.Q(viewer_grants__viewer_id=self.id)
            # The grant join duplicates a mesh that is both public and granted.
        ).distinct()

    @property
    def visible_devices(self):
        """Devices this owner may see: those on meshes they may read."""
        if self.is_superuser:
            return Device.objects.all()
        return Device.objects.filter(mesh__in=self.visible_meshes)

    def can_view_mesh(self, mesh) -> bool:
        """Reads. The grant lookup only runs once the cheaper cases have missed."""
        return (
            self.is_superuser
            or mesh.owner_id == self.id
            or mesh.is_public
            or mesh.viewer_grants.filter(viewer_id=self.id).exists()
        )

    def can_edit_mesh(self, mesh) -> bool:
        """Writes, which a grant and `is_public` never widen."""
        return self.is_superuser or mesh.owner_id == self.id

    def _device_addresses(self):
        """Only the three columns the readings role is granted."""
        return self.visible_devices.values_list("id", "mesh_id", "device_id")

    @cached_property
    def devices_by_uuid(self) -> dict[str, tuple[str, int]]:
        """Registration ID to the store-native address it resolves to."""
        return {
            str(pk): (str(mesh_id), device_id) for pk, mesh_id, device_id in self._device_addresses()
        }


class Source(models.Model):
    """A remote MQTT broker and topic filter, bridged into this instance by EMQX."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    label = models.CharField(max_length=255, null=True, blank=True)
    # host:port
    server = models.CharField(max_length=255)
    ssl = models.BooleanField(default=True)
    username = models.CharField(max_length=255, null=True, blank=True)
    # Write-only over the API, never returned to anyone.
    password = models.TextField(null=True, blank=True)
    topic = models.CharField(max_length=1024)
    qos = models.PositiveSmallIntegerField(default=1)
    created_by = models.ForeignKey(
        Owner, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_sources"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sources"

    def __str__(self) -> str:
        return self.label or f"{self.server} {self.topic}"


class Mesh(models.Model):
    """Physical Meshtastic network"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel_id = models.CharField(max_length=255, db_index=True)
    # PSK is password field: write-only over the API
    psk_b64 = models.TextField()
    label = models.CharField(max_length=255, null=True, blank=True)
    owner = models.ForeignKey(Owner, on_delete=models.CASCADE, related_name="meshes")
    # Readable by any verified owner. Never widens writes.
    is_public = models.BooleanField(default=False)
    # Null means the traffic arrives on this instance's own broker topic.
    source = models.ForeignKey(Source, on_delete=models.PROTECT, null=True, blank=True, related_name="meshes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "meshes"

    def __str__(self) -> str:
        if not self.label or self.label == self.channel_id:
            return self.channel_id
        return f"{self.label} ({self.channel_id})"


class MeshViewer(models.Model):
    """Grants one owner read access to a mesh they do not own."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mesh = models.ForeignKey(Mesh, on_delete=models.CASCADE, related_name="viewer_grants")
    viewer = models.ForeignKey(Owner, on_delete=models.CASCADE, related_name="mesh_view_grants")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mesh_viewers"
        constraints = [
            models.UniqueConstraint(fields=["mesh", "viewer"], name="uq_mesh_viewer")
        ]

    def __str__(self) -> str:
        return f"{self.viewer.email} -> {self.mesh}"


def _max_three_admin_keys(value: list[str]) -> None:
    from django.core.exceptions import ValidationError

    if value is not None and len(value) > 3:
        raise ValidationError("Meshtastic firmware supports at most 3 admin keys (Config.SecurityConfig.admin_key)")


class PostprocessingBlueprint(models.Model):
    """Reusable recipe for calculating new channels."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    owner = models.ForeignKey(Owner, on_delete=models.CASCADE, related_name="blueprints")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "postprocessing_blueprints"
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="uq_blueprint_owner_name")
        ]

    def __str__(self) -> str:
        return self.name


class PostprocessingStep(models.Model):
    """One step for a blueprint, run in `order`"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    blueprint = models.ForeignKey(PostprocessingBlueprint, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveIntegerField()
    function_name = models.CharField(max_length=128)
    inputs = models.JSONField(default=dict, blank=True)
    params = models.JSONField(default=dict, blank=True)
    outputs = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "postprocessing_steps"
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["blueprint", "order"], name="uq_step_blueprint_order")
        ]

    def __str__(self) -> str:
        return f"{self.order}. {self.function_name}"


class Device(models.Model):
    """A physical Meshtastic device (either gateway or node)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device_id = models.BigIntegerField(db_index=True)
    mesh = models.ForeignKey(Mesh, on_delete=models.CASCADE, related_name="devices")
    label = models.CharField(max_length=255, null=True, blank=True)
    # A Device is either a gateway or a node
    is_gateway = models.BooleanField(default=False)
    is_allowed = models.BooleanField(default=True)
    # DeviceReadSerializer only shows this to the
    # device's actual mesh owner
    admin_keys_b64 = models.JSONField(default=list, blank=True, validators=[_max_three_admin_keys])
    # Optional Blueprint
    postprocessing_blueprint = models.ForeignKey(
        PostprocessingBlueprint, on_delete=models.SET_NULL, null=True, blank=True, related_name="devices"
    )
    reading_interval_seconds = models.PositiveIntegerField(null=True, blank=True)
    publish_interval_seconds = models.PositiveIntegerField(null=True, blank=True)
    # The absence detector is device-wide rather than per channel, so it is
    # switched on here rather than in a Measurement's enabled_detectors.
    absence_detection_enabled = models.BooleanField(default=False)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location_overridden = models.BooleanField(default=False)
    # Auto-filled from NodeInfo
    name = models.CharField(max_length=255, null=True, blank=True)
    short_name = models.CharField(max_length=32, null=True, blank=True)
    hardware_type = models.CharField(max_length=64, null=True, blank=True)
    role = models.CharField(max_length=32, null=True, blank=True)
    nodeinfo_overridden = models.BooleanField(default=False)
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "devices"
        constraints = [
            # Node numbers may repeat across meshes, e.g. two sources hearing the same node.
            models.UniqueConstraint(
                fields=["mesh", "device_id"],
                condition=models.Q(is_allowed=True),
                name="uq_devices_mesh_device_id_allowed",
            ),
            # Gateways may not: mesh.keys.v1 is keyed by the gateway node number alone.
            models.UniqueConstraint(
                fields=["device_id"],
                condition=models.Q(is_allowed=True, is_gateway=True),
                name="uq_devices_gateway_device_id_allowed",
            ),
        ]

    def __str__(self) -> str:
        """Node number in the wire form a Meshtastic client shows, plus whatever
        name is known for it."""
        described = self.label or self.name or self.short_name
        if described:
            return f"{described} ({node_ids.to_hex(self.device_id)})"
        return f"{'gateway' if self.is_gateway else 'node'} {node_ids.to_hex(self.device_id)}"


class MeasurementType(models.Model):
    """Definition of one physical quantity"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payload_kind = models.CharField(max_length=64)  # e.g. "telemetry:environment_metrics"
    field_name = models.CharField(max_length=64)  # e.g. "temperature"
    display_name = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)  # proto comment
    native_unit = models.CharField(max_length=32, null=True, blank=True)  # "degC", "V", "ug/m3", "%"
    quantity_kind = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        choices=[
            ("physical_property", "Physical property"),
            ("concentration", "Concentration"),
            ("count", "Count"),
            ("ratio", "Ratio/percent"),
            ("other", "Other"),
        ],
    )
    vocabulary_uri = models.URLField(null=True, blank=True)  # QUDT/EIONET concept URI
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "measurement_types"
        constraints = [models.UniqueConstraint(fields=["payload_kind", "field_name"], name="uq_measurement_type")]

    def __str__(self) -> str:
        return channel_name(self.payload_kind, self.field_name)


class TelemetryVariant(models.Model):
    """Meshtastic Telemetry protobuf "variant"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payload_kind = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    model = models.CharField(max_length=255, null=True, blank=True)
    datasheet_url = models.URLField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    default_reading_interval_seconds = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "telemetry_variants"

    def __str__(self) -> str:
        return self.name or self.payload_kind


class TelemetryVariantMeasurement(models.Model):
    """Declares that a TelemetryVariant has a given MeasurementType."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    telemetry_variant = models.ForeignKey(TelemetryVariant, on_delete=models.CASCADE, related_name="measurement_links")
    measurement_type = models.ForeignKey(
        MeasurementType, on_delete=models.CASCADE, related_name="telemetry_variant_links"
    )
    # Detectors every device reporting this channel runs unless it overrides them.
    default_enabled_detectors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "telemetry_variant_measurements"
        constraints = [
            models.UniqueConstraint(
                fields=["telemetry_variant", "measurement_type"], name="uq_telemetry_variant_measurement"
            )
        ]

    def __str__(self) -> str:
        return f"{self.measurement_type} on {self.telemetry_variant}"


class DeviceTelemetryVariant(models.Model):
    """
    Auto-created.
    Read via GET /devices/{uuid}/telemetry-variants.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="telemetry_variants")
    telemetry_variant = models.ForeignKey(TelemetryVariant, on_delete=models.CASCADE, related_name="device_links")
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "device_telemetry_variants"
        constraints = [
            models.UniqueConstraint(fields=["device", "telemetry_variant"], name="uq_device_telemetry_variant")
        ]

    def __str__(self) -> str:
        return f"{self.telemetry_variant} on {self.device}"


class Measurement(models.Model):
    """One measurement channel a DeviceTelemetryVariant produces"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device_telemetry_variant = models.ForeignKey(DeviceTelemetryVariant, on_delete=models.CASCADE, related_name="measurements")
    measurement_type = models.ForeignKey(MeasurementType, on_delete=models.CASCADE, related_name="measurements")
    # null inherits the catalog default; [] silences this channel on this device.
    enabled_detectors = models.JSONField(null=True, blank=True, default=None)
    # Range is checked per-device. Both null means
    # the range detector is a not checked for this channel; set/cleared together.
    valid_min = models.FloatField(null=True, blank=True)
    valid_max = models.FloatField(null=True, blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "measurements"
        constraints = [
            models.UniqueConstraint(
                fields=["device_telemetry_variant", "measurement_type"],
                name="uq_measurement_device_telemetry_variant_type",
            )
        ]

    def __str__(self) -> str:
        return f"{self.measurement_type} on {self.device_telemetry_variant.device}"
