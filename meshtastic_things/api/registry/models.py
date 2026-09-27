import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone
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
    # Length of a device's alarm-email window, in seconds. Null uses the server default.
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
        """Meshes this owner may read: their own and public ones. Every mesh for a
        superuser. The single definition of that rule."""
        if self.is_superuser:
            return Mesh.objects.all()
        return Mesh.objects.filter(models.Q(owner_id=self.id) | models.Q(is_public=True))

    @property
    def visible_devices(self):
        """Devices this owner may see: those on meshes they may read."""
        if self.is_superuser:
            return Device.objects.all()
        return Device.objects.filter(mesh__in=self.visible_meshes)

    @property
    def current_account_acceptance(self):
        return self.terms_acceptances.filter(kind="account").order_by("-accepted_at").first()

    @property
    def visible_sources(self):
        """Sources this owner may see: every one for a superuser, their own for an
        operator, none otherwise."""
        if self.is_superuser:
            return Source.objects.all()
        if self.role == OwnerRole.OPERATOR:
            return Source.objects.filter(created_by_id=self.id)
        return Source.objects.none()

    def can_view_mesh(self, mesh) -> bool:
        """Reads."""
        return self.is_superuser or mesh.owner_id == self.id or mesh.is_public

    def can_edit_mesh(self, mesh) -> bool:
        """Writes, which `is_public` never widens."""
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


class OperatorRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class OperatorRequest(models.Model):
    """An owner's request for the operator role, decided by a superuser."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(Owner, on_delete=models.CASCADE, related_name="operator_requests")
    reason = models.TextField(max_length=2000)
    status = models.CharField(
        max_length=16, choices=OperatorRequestStatus.choices, default=OperatorRequestStatus.PENDING
    )
    decided_by = models.ForeignKey(
        Owner, on_delete=models.SET_NULL, null=True, blank=True, related_name="decided_operator_requests"
    )
    decision_note = models.TextField(blank=True, default="")
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "operator_requests"
        constraints = [
            models.UniqueConstraint(
                fields=["owner"],
                condition=models.Q(status="pending"),
                name="uq_operator_request_pending_per_owner",
            )
        ]

    def __str__(self) -> str:
        return f"{self.owner.email} ({self.status})"


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
    # Set when its terms acceptance lapsed: the EMQX bridge is removed until renewed.
    paused_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sources"

    def __str__(self) -> str:
        return self.label or f"{self.server} {self.topic}"

    @property
    def current_terms_acceptance(self):
        return self.terms_acceptances.order_by("-accepted_at").first()


class TermsKind(models.TextChoices):
    # Accepted at signup; covers the account only, which stores no mesh data. Never lapses.
    ACCOUNT = "account", "Account"
    # Accepted per mesh on the default broker by its owner, as controller of its traffic.
    MESH = "mesh", "Mesh"
    # Accepted per source by the operator, as controller of the bridged traffic.
    SOURCE = "source", "Source"


class TermsAcceptance(models.Model):
    """Append-only proof that an owner accepted a version of the terms (GDPR Art. 5(2)).

    Kept after the source or owner is deleted, so the acceptor is snapshotted.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=16, choices=TermsKind.choices)
    owner = models.ForeignKey(
        Owner, on_delete=models.SET_NULL, null=True, blank=True, related_name="terms_acceptances"
    )
    # Set for mesh and source terms respectively.
    mesh = models.ForeignKey(
        "Mesh", on_delete=models.SET_NULL, null=True, blank=True, related_name="terms_acceptances"
    )
    source = models.ForeignKey(
        Source, on_delete=models.SET_NULL, null=True, blank=True, related_name="terms_acceptances"
    )
    acceptor_name = models.CharField(max_length=255)
    acceptor_email = models.EmailField()
    terms_version = models.CharField(max_length=64)
    locale = models.CharField(max_length=8)
    # sha256 of the exact text served for this version and locale.
    text_hash = models.CharField(max_length=64)
    accepted_at = models.DateTimeField(default=timezone.now)
    # Null when no retention period is configured.
    expires_at = models.DateTimeField(null=True, blank=True)
    renewal_notice_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "terms_acceptances"
        indexes = [models.Index(fields=["kind", "owner", "accepted_at"])]

    def __str__(self) -> str:
        return f"{self.acceptor_email} {self.terms_version} ({self.accepted_at:%Y-%m-%d})"


class DataDeletionReason(models.TextChoices):
    MESH_DELETED = "mesh_deleted", "Mesh deleted"
    SOURCE_DETACHED = "source_detached", "Mesh moved off its source"
    TERMS_LAPSED = "terms_lapsed", "Source terms lapsed"


class DataDeletionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CANCELLED = "cancelled", "Cancelled"
    DONE = "done", "Done"


class DataDeletion(models.Model):
    """A mesh's stored readings, scheduled for deletion after a grace period.

    Holds ids rather than foreign keys, since the mesh is often gone by the time it runs.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mesh_id = models.UUIDField()
    source_id = models.UUIDField(null=True, blank=True)
    reason = models.CharField(max_length=32, choices=DataDeletionReason.choices)
    requested_by = models.ForeignKey(
        Owner, on_delete=models.SET_NULL, null=True, blank=True, related_name="requested_data_deletions"
    )
    requested_at = models.DateTimeField(default=timezone.now)
    delete_after = models.DateTimeField()
    # Readings up to here are deleted. Null deletes every reading of the mesh.
    data_until = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=DataDeletionStatus.choices, default=DataDeletionStatus.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "data_deletions"
        indexes = [models.Index(fields=["status", "delete_after"])]

    def __str__(self) -> str:
        return f"{self.mesh_id} {self.reason} ({self.status})"


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
    # Set when its mesh terms lapsed (default broker only): its gateways are deregistered until renewed.
    paused_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "meshes"

    def __str__(self) -> str:
        if not self.label or self.label == self.channel_id:
            return self.channel_id
        return f"{self.label} ({self.channel_id})"

    @property
    def ingest_paused(self) -> bool:
        """Whether lapsed terms stop this mesh's traffic: its source's terms, or its own on the default broker."""
        if self.source_id is not None:
            return self.source.paused_at is not None
        return self.paused_at is not None

    @property
    def current_terms_acceptance(self):
        return self.terms_acceptances.filter(kind="mesh").order_by("-accepted_at").first()


def _max_three_admin_keys(value: list[str]) -> None:
    from django.core.exceptions import ValidationError

    if value is not None and len(value) > 3:
        raise ValidationError("Meshtastic firmware supports at most 3 admin keys (Config.SecurityConfig.admin_key)")


class PostprocessingBlueprint(models.Model):
    """Reusable recipe for calculating new channels, identified across its versions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    # Null once the owner is deleted while other owners' devices still use it;
    # only superusers edit it from then on.
    owner = models.ForeignKey(Owner, on_delete=models.SET_NULL, null=True, blank=True, related_name="blueprints")
    # Attachable to any owner's devices. Existing attachments survive it being unset.
    is_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "postprocessing_blueprints"
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="uq_blueprint_owner_name")
        ]

    def __str__(self) -> str:
        return self.name


class BlueprintVersion(models.Model):
    """An immutable set of steps. Editing a blueprint means adding a version."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    blueprint = models.ForeignKey(PostprocessingBlueprint, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    # [{"slot": "temperature", "default_channel": "environment_metrics.temperature"}, ...]
    inputs = models.JSONField(default=list)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "blueprint_versions"
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["blueprint", "number"], name="uq_blueprint_version_number")
        ]

    def __str__(self) -> str:
        return f"{self.blueprint} v{self.number}"


class PostprocessingStep(models.Model):
    """One step of a blueprint version, run in `order`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(BlueprintVersion, on_delete=models.CASCADE, related_name="steps")
    # Stable across versions, so a device's calibration carries over.
    key = models.SlugField(max_length=64)
    order = models.PositiveIntegerField()
    function_name = models.CharField(max_length=128)
    # {algorithm input: "slot:<name>" | "step:<key>.<output>"}
    inputs = models.JSONField(default=dict)
    # Configuration only; calibration is per device.
    params = models.JSONField(default=dict, blank=True)
    # {algorithm output: derived field name}
    outputs = models.JSONField(default=dict)

    class Meta:
        db_table = "postprocessing_steps"
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["version", "order"], name="uq_step_version_order"),
            models.UniqueConstraint(fields=["version", "key"], name="uq_step_version_key"),
        ]

    def __str__(self) -> str:
        return f"{self.order}. {self.key} ({self.function_name})"


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
    # The postprocessing computing this channel; null for anything the device reports.
    produced_by = models.ForeignKey(
        "DevicePostprocessing", on_delete=models.CASCADE, null=True, blank=True, related_name="outputs"
    )
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


class DevicePostprocessing(models.Model):
    """A blueprint version applied to one device, with its own wiring and calibration."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="postprocessings")
    # RESTRICT rather than PROTECT so deleting the owner of both still cascades.
    blueprint_version = models.ForeignKey(BlueprintVersion, on_delete=models.RESTRICT, related_name="attachments")
    # Prepended to every derived field name, so one blueprint can run twice on a device.
    output_prefix = models.CharField(max_length=64, blank=True, default="")
    # Null falls back to half the device's reading interval.
    tolerance_seconds = models.PositiveIntegerField(null=True, blank=True)
    is_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "device_postprocessings"

    def __str__(self) -> str:
        return f"{self.blueprint_version} on {self.device}"


class PostprocessingInputBinding(models.Model):
    """Wires one blueprint input slot to a channel of the device."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device_postprocessing = models.ForeignKey(
        DevicePostprocessing, on_delete=models.CASCADE, related_name="input_bindings"
    )
    slot = models.CharField(max_length=64)
    # RESTRICT keeps a postprocessing from losing an input that another one
    # produces, while still letting a whole device be deleted.
    measurement = models.ForeignKey(Measurement, on_delete=models.RESTRICT, related_name="consumers")

    class Meta:
        db_table = "postprocessing_input_bindings"
        constraints = [
            models.UniqueConstraint(fields=["device_postprocessing", "slot"], name="uq_input_binding_slot")
        ]

    def __str__(self) -> str:
        return f"{self.slot} <- {self.measurement.measurement_type}"


class StepCalibration(models.Model):
    """Calibration of one step on one device, in force from `valid_from`.

    Append-only history, so reprocessing old data applies the calibration that
    was in force at the time.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device_postprocessing = models.ForeignKey(
        DevicePostprocessing, on_delete=models.CASCADE, related_name="calibrations"
    )
    step_key = models.SlugField(max_length=64)
    # A calibration only applies to a step still running the same algorithm.
    function_name = models.CharField(max_length=128)
    params = models.JSONField(default=dict)
    valid_from = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "step_calibrations"
        ordering = ["step_key", "valid_from"]

    def __str__(self) -> str:
        return f"{self.step_key} from {self.valid_from:%Y-%m-%d %H:%M}"


class BackfillStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    DONE = "done", "Done"
    FAILED = "failed", "Failed"


class PostprocessingBackfill(models.Model):
    """A request to run a postprocessing over stored history, picked up by the quality worker."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device_postprocessing = models.ForeignKey(
        DevicePostprocessing, on_delete=models.CASCADE, related_name="backfills"
    )
    start = models.DateTimeField()
    stop = models.DateTimeField()
    # Also rerun the postprocessings reading this one's outputs, in order.
    include_dependants = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=BackfillStatus.choices, default=BackfillStatus.PENDING)
    requested_by = models.ForeignKey(Owner, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    points_published = models.PositiveIntegerField(default=0)
    error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "postprocessing_backfills"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.device_postprocessing} {self.start:%Y-%m-%d}..{self.stop:%Y-%m-%d} ({self.status})"
