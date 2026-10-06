from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from common import node_ids

from .models import (
    BlueprintVersion,
    DataDeletion,
    Device,
    DevicePostprocessing,
    DeviceTelemetryVariant,
    Measurement,
    MeasurementType,
    Mesh,
    OperatorRequest,
    Owner,
    PostprocessingBackfill,
    PostprocessingBlueprint,
    PostprocessingInputBinding,
    PostprocessingStep,
    Sink,
    SinkInstruction,
    Source,
    StepCalibration,
    TelemetryVariant,
    TelemetryVariantMeasurement,
    TermsAcceptance,
)

@admin.register(Owner)
class OwnerAdmin(UserAdmin):
    # api_key_hash excluded
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("name",)}),
        ("Permissions", {"fields": ("is_active", "role", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login",)}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "name", "password1", "password2")}),)
    list_display = ("email", "name", "role", "is_superuser", "is_staff", "created_at")
    list_filter = ("role", "is_superuser", "is_staff", "is_active")
    search_fields = ("email", "name")
    ordering = ("email",)
    readonly_fields = ("last_login",)


@admin.register(Mesh)
class MeshAdmin(admin.ModelAdmin):
    list_display = ("channel_id", "label", "owner", "source", "is_public", "created_at")
    list_select_related = ("owner", "source")
    list_filter = ("is_public",)
    # A new key here would not reach the decoder; use PUT /meshes/{id}.
    readonly_fields = ("id", "psk_b64", "created_at", "updated_at")
    search_fields = ("channel_id", "label")


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    """Read-only: a source is only consistent with its EMQX bridge when written through the API."""

    list_display = ("label", "server", "root", "qos", "ssl", "created_by", "created_at")
    list_select_related = ("created_by",)
    exclude = ("password",)
    search_fields = ("label", "server", "root")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class _ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Sink)
class SinkAdmin(_ReadOnlyAdmin):
    """Read-only: a sink is only consistent with its EMQX user and the pipeline when written through the API."""

    list_display = ("label", "streams", "created_by", "paused_at", "created_at")
    list_select_related = ("created_by",)
    search_fields = ("label",)


@admin.register(TermsAcceptance)
class TermsAcceptanceAdmin(_ReadOnlyAdmin):
    """Read-only: acceptances are append-only evidence."""

    list_display = (
        "acceptor_email", "kind", "mesh", "source", "sink", "terms_version", "locale", "accepted_at", "expires_at"
    )
    list_filter = ("kind", "terms_version", "locale")
    search_fields = ("acceptor_email", "acceptor_name")


@admin.register(SinkInstruction)
class SinkInstructionAdmin(_ReadOnlyAdmin):
    """Read-only: instructions are append-only evidence."""

    list_display = ("given_by_email", "sink", "enabled", "mesh_id", "node_id", "given_at")
    list_filter = ("sink", "enabled")
    search_fields = ("given_by_email", "given_by_name")


@admin.register(DataDeletion)
class DataDeletionAdmin(_ReadOnlyAdmin):
    """Read-only: the lifecycle job owns these rows."""

    list_display = ("mesh_id", "reason", "status", "requested_at", "delete_after", "completed_at", "attempts")
    list_filter = ("status", "reason")
    search_fields = ("mesh_id", "source_id")


@admin.register(OperatorRequest)
class OperatorRequestAdmin(_ReadOnlyAdmin):
    """Read-only: deciding through the API sets the role and emails the requester."""

    list_display = ("owner", "status", "created_at", "decided_by", "decided_at")
    list_filter = ("status",)
    list_select_related = ("owner", "decided_by")
    search_fields = ("owner__email", "owner__name")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = (
        "node_id",
        "label",
        "mesh",
        "is_gateway",
        "is_allowed",
        "name",
        "short_name",
        "hardware_type",
        "role",
        "latitude",
        "longitude",
        "last_seen",
        "created_at",
    )
    list_filter = ("is_gateway", "is_allowed")
    list_select_related = ("mesh",)
    # A write here would neither reach the pipeline nor be recorded; use PUT /devices/{uuid}.
    readonly_fields = (
        "id",
        "admin_keys_b64",
        "created_at",
        "updated_at",
        "archive_enabled",
        "archive_enabled_at",
        "archive_enabled_by",
    )
    search_fields = ("device_id", "label", "name", "short_name")

    @admin.display(description="Node ID", ordering="device_id")
    def node_id(self, obj):
        return f"{obj.device_id} ({node_ids.to_hex(obj.device_id)})"


@admin.register(MeasurementType)
class MeasurementTypeAdmin(admin.ModelAdmin):
    list_display = ("payload_kind", "field_name", "native_unit", "quantity_kind", "vocabulary_uri", "updated_at")
    list_filter = ("quantity_kind",)
    readonly_fields = ("id", "created_at", "updated_at")
    search_fields = ("payload_kind", "field_name", "display_name")


class _ReadOnlyInline(admin.TabularInline):
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class BlueprintVersionInline(_ReadOnlyInline):
    model = BlueprintVersion
    fields = ("number", "notes", "created_at")
    readonly_fields = fields
    show_change_link = True


@admin.register(PostprocessingBlueprint)
class PostprocessingBlueprintAdmin(admin.ModelAdmin):
    """Versions are immutable and created through the API, which validates their steps."""

    list_display = ("name", "owner", "is_public", "created_at", "updated_at")
    list_select_related = ("owner",)
    list_filter = ("is_public",)
    readonly_fields = ("id", "created_at", "updated_at")
    search_fields = ("name", "owner__email")
    inlines = [BlueprintVersionInline]


class PostprocessingStepInline(_ReadOnlyInline):
    model = PostprocessingStep
    fields = ("order", "key", "function_name", "inputs", "params", "outputs")
    readonly_fields = fields


@admin.register(BlueprintVersion)
class BlueprintVersionAdmin(_ReadOnlyAdmin):
    list_display = ("blueprint", "number", "created_at")
    list_select_related = ("blueprint",)
    search_fields = ("blueprint__name",)
    inlines = [PostprocessingStepInline]


class PostprocessingInputBindingInline(_ReadOnlyInline):
    model = PostprocessingInputBinding
    fields = ("slot", "measurement")
    readonly_fields = fields


class StepCalibrationInline(_ReadOnlyInline):
    model = StepCalibration
    fields = ("step_key", "function_name", "params", "valid_from", "created_at")
    readonly_fields = fields


@admin.register(DevicePostprocessing)
class DevicePostprocessingAdmin(_ReadOnlyAdmin):
    """Read-only: changes must go through the API so the stream job receives them."""

    list_display = ("device", "blueprint_version", "output_prefix", "is_enabled", "updated_at")
    list_select_related = ("device", "blueprint_version__blueprint")
    list_filter = ("is_enabled",)
    search_fields = ("device__device_id", "device__label", "blueprint_version__blueprint__name")
    inlines = [PostprocessingInputBindingInline, StepCalibrationInline]


@admin.register(PostprocessingBackfill)
class PostprocessingBackfillAdmin(_ReadOnlyAdmin):
    """Read-only: requested through the API and run by the quality worker."""

    list_display = ("device_postprocessing", "start", "stop", "status", "points_published", "created_at", "finished_at")
    list_select_related = ("device_postprocessing__device", "device_postprocessing__blueprint_version__blueprint")
    list_filter = ("status",)


@admin.register(TelemetryVariant)
class TelemetryVariantAdmin(admin.ModelAdmin):
    list_display = ("payload_kind", "name", "model", "datasheet_url", "updated_at")
    readonly_fields = ("id", "created_at", "updated_at")
    search_fields = ("payload_kind", "name", "model")


@admin.register(TelemetryVariantMeasurement)
class TelemetryVariantMeasurementAdmin(admin.ModelAdmin):
    """Which detectors default on per channel, read by the quality checks."""

    list_display = ("measurement_type", "telemetry_variant", "default_enabled_detectors")
    list_select_related = ("measurement_type", "telemetry_variant")
    list_filter = ("telemetry_variant",)
    readonly_fields = ("id", "created_at", "updated_at")
    search_fields = ("measurement_type__field_name", "telemetry_variant__payload_kind")


@admin.register(DeviceTelemetryVariant)
class DeviceTelemetryVariantAdmin(admin.ModelAdmin):
    list_display = ("device", "telemetry_variant", "first_seen", "last_seen")
    list_select_related = ("device", "telemetry_variant")
    readonly_fields = ("id", "device", "telemetry_variant", "first_seen", "last_seen")
    search_fields = ("device__device_id", "device__label")

    def has_add_permission(self, request):
        return False


@admin.register(Measurement)
class MeasurementAdmin(admin.ModelAdmin):
    list_display = (
        "device_telemetry_variant", "measurement_type", "valid_min", "valid_max", "first_seen", "last_seen",
    )
    list_select_related = ("measurement_type", "device_telemetry_variant__device")
    readonly_fields = ("id", "device_telemetry_variant", "measurement_type", "first_seen", "last_seen")
    search_fields = ("device_telemetry_variant__device__device_id", "measurement_type__field_name")

    def has_add_permission(self, request):
        return False
