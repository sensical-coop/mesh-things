from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from common import node_ids

from .models import (
    Device,
    DeviceTelemetryVariant,
    Measurement,
    MeasurementType,
    Mesh,
    Owner,
    PostprocessingBlueprint,
    PostprocessingStep,
    TelemetryVariant,
    TelemetryVariantMeasurement,
)

@admin.register(Owner)
class OwnerAdmin(UserAdmin):
    # api_key_hash excluded
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("name",)}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login",)}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "name", "password1", "password2")}),)
    list_display = ("email", "name", "is_superuser", "is_staff", "created_at")
    search_fields = ("email", "name")
    ordering = ("email",)
    readonly_fields = ("last_login",)


@admin.register(Mesh)
class MeshAdmin(admin.ModelAdmin):
    # psk_b64 is a password field
    list_display = ("channel_id", "label", "owner", "is_public", "created_at")
    list_select_related = ("owner",)
    list_filter = ("is_public",)
    exclude = ("psk_b64",)
    readonly_fields = ("id", "created_at", "updated_at")
    search_fields = ("channel_id", "label")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    # admin_keys_b64 is a password field
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
    exclude = ("admin_keys_b64",)
    readonly_fields = ("id", "created_at", "updated_at")
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


class PostprocessingStepInline(admin.TabularInline):
    # Steps are only meaningful as part of their blueprint,
    # so they're edited inline rather than as a standalone admin model.
    model = PostprocessingStep
    extra = 0


@admin.register(PostprocessingBlueprint)
class PostprocessingBlueprintAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "created_at", "updated_at")
    list_select_related = ("owner",)
    readonly_fields = ("id", "created_at", "updated_at")
    search_fields = ("name", "owner__email")
    inlines = [PostprocessingStepInline]


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
