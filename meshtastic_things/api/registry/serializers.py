from datetime import datetime
from fnmatch import fnmatch
from urllib.parse import urlsplit

from django.conf import settings

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from common.algorithms import validate_step
from common.channels import channel_name, origin_of
from common.detectors import DETECTOR_CHOICES, MEASUREMENT_DETECTORS, enabled_detectors_for
from common.env import env_str

from .broker_hosts import refusal as broker_refusal
from .emailing import ALARM_EMAIL_COOLDOWN_MAX_SECONDS
from .terms import DEFAULT_LOCALE, LOCALES, VERSIONS, is_current, terms_enforced
from .models import (
    Device,
    DeviceTelemetryVariant,
    Measurement,
    MeasurementType,
    Mesh,
    OperatorRequest,
    Owner,
    OwnerRole,
    PostprocessingBlueprint,
    PostprocessingStep,
    DataDeletion,
    Source,
    TermsKind,
    TelemetryVariant,
    TelemetryVariantMeasurement,
)


class OwnerPublicSerializer(serializers.ModelSerializer):
    """Public directory"""

    class Meta:
        model = Owner
        fields = ["id", "name", "created_at"]
        read_only_fields = fields


class MetricsResponseSerializer(serializers.Serializer):
    devices = serializers.IntegerField()
    owners = serializers.IntegerField()
    meshes = serializers.IntegerField()
    active_gateways = serializers.IntegerField()


class _TermsAcceptanceInputMixin(serializers.Serializer):
    """Accepting the current terms of `terms_kind`."""

    terms_kind: str

    terms_version = serializers.CharField(
        write_only=True, help_text="Version of the terms accepted, as served by the terms endpoint."
    )
    terms_locale = serializers.ChoiceField(
        choices=LOCALES,
        write_only=True,
        required=False,
        default=DEFAULT_LOCALE,
        help_text="Locale the terms were shown in.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not terms_enforced():
            self.fields["terms_version"].required = False

    def validate_terms_version(self, value):
        if not terms_enforced():
            return value
        if value != VERSIONS[self.terms_kind]:
            raise serializers.ValidationError("These terms are out of date. Load the current terms and accept them again.")
        return value


class OwnerReadSerializer(serializers.ModelSerializer):
    """The full record, for the owner themselves and for superusers.

    `last_login` tracks password logins only: a bearer-key request never
    updates it, so it is null for an owner who has only ever used their API key.
    """

    class Meta:
        model = Owner
        fields = [
            "id",
            "name",
            "email",
            "is_superuser",
            "is_staff",
            "role",
            "is_active",
            "email_verified_at",
            "email_verification_sent_at",
            "last_login",
            "created_at",
            "alarm_email_cooldown_seconds",
            "terms_accepted_version",
        ]
        read_only_fields = fields

    terms_accepted_version = serializers.SerializerMethodField()

    def get_terms_accepted_version(self, instance) -> str | None:
        """Version of the account terms last accepted. Null if never accepted. They never lapse."""
        acceptance = instance.current_account_acceptance
        return acceptance.terms_version if acceptance else None


class OwnerCreateSerializer(_TermsAcceptanceInputMixin, serializers.ModelSerializer):
    terms_kind = TermsKind.ACCOUNT

    email = serializers.EmailField(validators=[])
    password = serializers.CharField(write_only=True)

    class Meta:
        model = Owner
        fields = ["name", "email", "password", "terms_version", "terms_locale"]

    def validate(self, attrs):
        try:
            validate_password(attrs["password"], user=Owner(email=attrs.get("email"), name=attrs.get("name")))
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})
        return attrs


class OwnerUpdateSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(validators=[], required=False)

    class Meta:
        model = Owner
        fields = ["name", "email", "alarm_email_cooldown_seconds"]
        extra_kwargs = {"name": {"required": False}}

    def validate_alarm_email_cooldown_seconds(self, value):
        if value is not None and value > ALARM_EMAIL_COOLDOWN_MAX_SECONDS:
            raise serializers.ValidationError(
                f"Must be at most {ALARM_EMAIL_COOLDOWN_MAX_SECONDS} seconds (30 days), "
                "or null to use the server default."
            )
        return value


class OwnerRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=OwnerRole.choices)


class OperatorRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperatorRequest
        fields = ["reason"]
        extra_kwargs = {"reason": {"help_text": "Why the operator role is needed. Shown to superusers."}}


class OperatorRequestSerializer(serializers.ModelSerializer):
    """An operator request as its requester sees it."""

    class Meta:
        model = OperatorRequest
        fields = ["id", "reason", "status", "decision_note", "decided_at", "created_at"]
        read_only_fields = fields


class OperatorRequestAdminSerializer(OperatorRequestSerializer):
    """An operator request as a superuser sees it."""

    owner_id = serializers.UUIDField(read_only=True)
    owner_name = serializers.CharField(source="owner.name", read_only=True)
    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    decided_by_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta(OperatorRequestSerializer.Meta):
        fields = OperatorRequestSerializer.Meta.fields + ["owner_id", "owner_name", "owner_email", "decided_by_id"]
        read_only_fields = fields


class OperatorRequestDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["approve", "reject"])
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)


class OwnerWithApiKeySerializer(OwnerReadSerializer):
    """In POST /owners and POST /owners/me/rotate-key"""

    api_key = serializers.CharField(read_only=True)

    class Meta(OwnerReadSerializer.Meta):
        fields = OwnerReadSerializer.Meta.fields + ["api_key"]


class OwnerLoginSerializer(serializers.Serializer):
    """POST /owners/login input"""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class OwnerRequestPasswordResetSerializer(serializers.Serializer):
    """POST /owners/request-password-reset input"""

    email = serializers.EmailField()


class OwnerResetPasswordSerializer(serializers.Serializer):
    """POST /owners/reset-password input"""

    new_password = serializers.CharField(write_only=True)


class OwnerChangePasswordSerializer(serializers.Serializer):
    """POST /owners/me/change-password input"""

    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)


def _validate_detectors(value):
    unknown = sorted(set(value or ()) - set(MEASUREMENT_DETECTORS))
    if unknown:
        raise serializers.ValidationError(
            f"Unknown detector(s) {unknown}. Valid: {sorted(MEASUREMENT_DETECTORS)}"
        )
    return value


_DETECTORS_HELP = "Detectors to run on this channel. See GET /detectors."


def _detector_field(**kwargs):
    return serializers.ListField(
        child=serializers.ChoiceField(choices=DETECTOR_CHOICES),
        validators=[_validate_detectors],
        help_text=_DETECTORS_HELP,
        **kwargs,
    )


class DetectorSerializer(serializers.Serializer):

    name = serializers.CharField()
    scope = serializers.CharField()
    requires = serializers.ListField(child=serializers.CharField())
    description = serializers.CharField()


_PSK_HELP = "Base64-encoded channel PSK"
_SOURCE_HELP = "Source the mesh's traffic is bridged from. Null for this instance's own broker."


def _validate_visible_source(serializer, source):
    """Only a source the caller may see can be attached. Keeping the current one is always allowed."""
    if source is None:
        return source
    current = getattr(serializer.instance, "source_id", None)
    owner = serializer.context.get("owner")
    if source.id == current:
        return source
    if owner is None or not owner.visible_sources.filter(pk=source.pk).exists():
        raise serializers.ValidationError(f'Invalid pk "{source.pk}" - object does not exist.')
    if source.paused_at is not None:
        raise serializers.ValidationError("This source is paused until its terms are renewed.")
    return source


class _MeshTermsMixin(serializers.Serializer):
    """Mesh terms, needed only for a mesh on the default broker; a source's terms cover the rest."""

    terms_version = serializers.CharField(
        write_only=True,
        required=False,
        help_text=(
            "Version of the mesh terms accepted, from /meshes/terms. Required when the mesh uses "
            "the default broker (no source) and has no current acceptance; ignored otherwise."
        ),
    )
    terms_locale = serializers.ChoiceField(
        choices=LOCALES, write_only=True, required=False, default=DEFAULT_LOCALE, help_text="Locale the terms were shown in."
    )
    terms_accepted_version = serializers.SerializerMethodField()
    terms_expires_at = serializers.SerializerMethodField()
    paused_at = serializers.DateTimeField(
        read_only=True, allow_null=True, help_text="Set while its mesh terms have lapsed; the mesh stores no new data."
    )

    # The locale to record an acceptance in, once validated; None when none is recorded.
    accept_terms_locale: str | None = None

    def get_terms_accepted_version(self, instance) -> str | None:
        """Mesh terms version accepted. Null on a source, whose terms apply instead."""
        if instance.source_id is not None:
            return None
        acceptance = instance.current_terms_acceptance
        return acceptance.terms_version if acceptance else None

    def get_terms_expires_at(self, instance) -> datetime | None:
        """When the mesh terms acceptance lapses. Null for no time limit, or on a source."""
        if instance.source_id is not None:
            return None
        acceptance = instance.current_terms_acceptance
        return acceptance.expires_at if acceptance else None

    def _take_mesh_terms(self, attrs, needed: bool):
        version = attrs.pop("terms_version", None)
        locale = attrs.pop("terms_locale", DEFAULT_LOCALE)
        if not needed or not terms_enforced():
            return attrs
        if not version:
            raise serializers.ValidationError(
                {"terms_version": ["A mesh on the default broker needs its terms accepted."]}
            )
        if version != VERSIONS[TermsKind.MESH]:
            raise serializers.ValidationError(
                {"terms_version": ["These terms are out of date. Load the current terms and accept them again."]}
            )
        self.accept_terms_locale = locale
        return attrs

    def _hide_mesh_terms(self, data, instance):
        # Like source_id: for the owner, and read-only for superusers.
        if self.context.get("viewer_id") != instance.owner_id and not self.context.get("viewer_is_superuser"):
            for field in ("terms_accepted_version", "terms_expires_at", "paused_at"):
                data.pop(field, None)
        return data


class MeshSerializer(_MeshTermsMixin, serializers.ModelSerializer):

    owner_id = serializers.UUIDField(read_only=True)
    # blank psk_b64 is mesh without encryption"
    psk_b64 = serializers.CharField(allow_blank=True, help_text=_PSK_HELP)
    source_id = serializers.PrimaryKeyRelatedField(
        source="source", queryset=Source.objects.all(), allow_null=True, required=False, help_text=_SOURCE_HELP
    )

    class Meta:
        model = Mesh
        fields = [
            "id",
            "channel_id",
            "psk_b64",
            "label",
            "owner_id",
            "is_public",
            "source_id",
            "terms_version",
            "terms_locale",
            "terms_accepted_version",
            "terms_expires_at",
            "paused_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "paused_at"]
        extra_kwargs = {"is_public": {"required": False}}

    def validate_source_id(self, value):
        return _validate_visible_source(self, value)

    def validate(self, attrs):
        return self._take_mesh_terms(super().validate(attrs), needed=attrs.get("source") is None)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        viewer_id = self.context.get("viewer_id")
        if viewer_id is None or viewer_id != instance.owner_id:
            data.pop("psk_b64", None)
            # Superusers see which source a mesh uses, read-only; nobody else but its owner does.
            if not self.context.get("viewer_is_superuser"):
                data.pop("source_id", None)
        return self._hide_mesh_terms(data, instance)


class MeshUpdateSerializer(_MeshTermsMixin, serializers.ModelSerializer):
    """PUT /meshes/{id}: channel_id, psk_b64, label, is_public and source_id are editable.

    channel_id/psk_b64 are a pair configured together on the physical
    devices, so both can change here the same way - the pipeline decrypts by
    gateway_id/psk_b64 alone, not by channel_id, so this is a metadata update.
    """

    psk_b64 = serializers.CharField(write_only=True, required=False, allow_blank=True, help_text=_PSK_HELP)
    source_id = serializers.PrimaryKeyRelatedField(
        source="source", queryset=Source.objects.all(), allow_null=True, required=False, help_text=_SOURCE_HELP
    )

    class Meta:
        model = Mesh
        fields = ["channel_id", "psk_b64", "label", "is_public", "source_id", "terms_version", "terms_locale"]
        extra_kwargs = {
            "label": {"required": False},
            "channel_id": {"required": False},
            "is_public": {"required": False},
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        mesh = self.instance
        moving_to_default = "source" in attrs and attrs["source"] is None and mesh.source_id is not None
        needed = moving_to_default and not is_current(mesh.current_terms_acceptance, TermsKind.MESH)
        return self._take_mesh_terms(attrs, needed=needed)

    def validate_source_id(self, value):
        return _validate_visible_source(self, value)


def _own_emqx_host() -> str:
    return urlsplit(env_str("REGISTRY__EMQX_API_URL")).hostname or ""


class SourceSerializer(serializers.ModelSerializer):
    """A source. The remote password is accepted but never returned."""

    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Remote broker password. Never returned. An empty string or null removes it.",
    )
    qos = serializers.ChoiceField(choices=[(0, "0"), (1, "1")], default=1)
    created_by_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = Source
        fields = [
            "id",
            "label",
            "server",
            "ssl",
            "username",
            "password",
            "topic",
            "qos",
            "created_by_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by_id", "created_at", "updated_at"]
        extra_kwargs = {
            "server": {"help_text": "Remote broker as host:port."},
            "topic": {"help_text": "Remote topic filter, for example msh/EU_868/2/e/MyChannel/#."},
        }

    def validate_password(self, value):
        return value or None

    def validate_username(self, value):
        return value or None

    def validate(self, attrs):
        attrs = super().validate(attrs)
        username = attrs["username"] if "username" in attrs else getattr(self.instance, "username", None)
        password = attrs["password"] if "password" in attrs else getattr(self.instance, "password", None)
        # A broker may take a username alone, but never a password alone.
        if password and not username:
            raise serializers.ValidationError({"username": ["A password needs a username."]})
        return attrs

    def validate_server(self, value):
        value = value.strip()
        host, sep, port = value.rpartition(":")
        if not sep or not host or not port.isdigit() or not 0 < int(port) < 65536:
            raise serializers.ValidationError("Must be host:port.")
        # Bridging our own broker into itself would loop through the republished topics.
        if host.strip("[]").rstrip(".").lower() == _own_emqx_host().lower():
            raise serializers.ValidationError("A source cannot point at this instance's own broker.")
        reason = broker_refusal(host)
        if reason:
            raise serializers.ValidationError(reason)
        if any(fnmatch(candidate, pattern.lower()) for pattern in settings.SOURCES_BLOCKED_BROKERS
               for candidate in (host.lower(), value.lower())):
            raise serializers.ValidationError("This broker is not allowed as a source.")
        return value

    def validate_topic(self, value):
        value = value.strip()
        if not value or value.startswith("$"):
            raise serializers.ValidationError("Must be a plain topic filter; $share and $SYS topics are not accepted.")
        if value in settings.SOURCES_BLOCKED_TOPICS:
            raise serializers.ValidationError("This topic filter is not allowed as a source.")
        return value



class SourceCreateSerializer(_TermsAcceptanceInputMixin, SourceSerializer):
    terms_kind = TermsKind.SOURCE

    class Meta(SourceSerializer.Meta):
        fields = SourceSerializer.Meta.fields + ["terms_version", "terms_locale"]

    def create(self, validated_data):
        validated_data.pop("terms_version", None)
        validated_data.pop("terms_locale", None)
        return super().create(validated_data)


class SourceUpdateSerializer(SourceSerializer):
    """Any subset of the create fields."""

    qos = serializers.ChoiceField(choices=[(0, "0"), (1, "1")], required=False)

    class Meta(SourceSerializer.Meta):
        extra_kwargs = {
            "server": {"help_text": "Remote broker as host:port.", "required": False},
            "topic": {"help_text": "Remote topic filter, for example msh/EU_868/2/e/MyChannel/#.", "required": False},
        }


class SourceTermsAcceptanceSerializer(_TermsAcceptanceInputMixin):
    terms_kind = TermsKind.SOURCE


class AccountTermsAcceptanceSerializer(_TermsAcceptanceInputMixin):
    terms_kind = TermsKind.ACCOUNT


class MeshTermsAcceptanceSerializer(_TermsAcceptanceInputMixin):
    terms_kind = TermsKind.MESH


class SourceReadSerializer(SourceSerializer):
    status = serializers.CharField(
        read_only=True, help_text="The bridge's connection status, `paused`, or unknown when it cannot be checked."
    )
    paused_at = serializers.DateTimeField(
        read_only=True, allow_null=True, help_text="When the source was paused because its terms lapsed."
    )
    terms_accepted_version = serializers.SerializerMethodField()
    terms_expires_at = serializers.SerializerMethodField()

    class Meta(SourceSerializer.Meta):
        fields = SourceSerializer.Meta.fields + ["status", "paused_at", "terms_accepted_version", "terms_expires_at"]

    def get_terms_accepted_version(self, instance) -> str | None:
        acceptance = instance.current_terms_acceptance
        return acceptance.terms_version if acceptance else None

    def get_terms_expires_at(self, instance) -> datetime | None:
        """When the terms acceptance lapses. Null when data is kept without a time limit."""
        acceptance = instance.current_terms_acceptance
        return acceptance.expires_at if acceptance else None


class TermsStatementSerializer(serializers.Serializer):
    id = serializers.CharField()
    text = serializers.CharField()


class TermsSerializer(serializers.Serializer):
    version = serializers.CharField()
    locale = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    statements = TermsStatementSerializer(many=True)
    footnote = serializers.CharField(help_text="Includes how long data is kept, from the server's retention settings.")


class DataDeletionSerializer(serializers.ModelSerializer):
    requested_by_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = DataDeletion
        fields = [
            "id",
            "mesh_id",
            "source_id",
            "reason",
            "requested_by_id",
            "requested_at",
            "delete_after",
            "data_until",
            "status",
            "attempts",
            "last_error",
            "completed_at",
        ]
        read_only_fields = fields


def _max_three_admin_keys(value):
    if value is not None and len(value) > 3:
        raise serializers.ValidationError(
            "Meshtastic firmware supports at most 3 admin keys (Config.SecurityConfig.admin_key)"
        )
    return value


_ADMIN_KEYS_HELP = "Base64-encoded admin keys (up to 3). Warning: PUT replaces the whole list."


def _validate_location_pair(serializer, attrs):
    """latitude/longitude are always set/cleared together"""
    has_lat = "latitude" in serializer.initial_data
    has_lon = "longitude" in serializer.initial_data
    if has_lat != has_lon:
        raise serializers.ValidationError("latitude and longitude must be provided together")
    return attrs


def _validate_range_pair(serializer, attrs):
    """valid_min/valid_max are always set/cleared together"""
    has_min = "valid_min" in serializer.initial_data
    has_max = "valid_max" in serializer.initial_data
    if has_min != has_max:
        raise serializers.ValidationError("valid_min and valid_max must be provided together")
    return attrs


class DeviceCreateSerializer(serializers.Serializer):
    """POST /devices input"""

    node_id = serializers.IntegerField(source="device_id")
    mesh_id = serializers.UUIDField()
    # Required
    is_gateway = serializers.BooleanField()
    label = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    admin_keys_b64 = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        required=False,
        default=list,
        validators=[_max_three_admin_keys],
        help_text=_ADMIN_KEYS_HELP,
    )
    latitude = serializers.FloatField(required=False, allow_null=True, default=None)
    longitude = serializers.FloatField(required=False, allow_null=True, default=None)
    name = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    short_name = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    hardware_type = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)
    role = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)

    def validate(self, attrs):
        return _validate_location_pair(self, attrs)


class DeviceReadSerializer(serializers.ModelSerializer):
    """admin_keys_b64 is ONLY shown to the device's actual mesh owner (superusers can't see this).

    `uuid` is the registration; `node_id` is the Meshtastic node number.
    The storage column is `device_id`.
    """

    uuid = serializers.UUIDField(source="id", read_only=True)
    node_id = serializers.IntegerField(source="device_id", read_only=True)
    mesh_id = serializers.UUIDField(read_only=True)
    postprocessing_blueprint_id = serializers.UUIDField(read_only=True)
    admin_keys_b64 = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = Device
        fields = [
            "uuid",
            "node_id",
            "mesh_id",
            "label",
            "is_gateway",
            "is_allowed",
            "admin_keys_b64",
            "latitude",
            "longitude",
            "location_overridden",
            "name",
            "short_name",
            "hardware_type",
            "role",
            "nodeinfo_overridden",
            "postprocessing_blueprint_id",
            "reading_interval_seconds",
            "publish_interval_seconds",
            "absence_detection_enabled",
            "last_seen",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        viewer_id = self.context.get("viewer_id")
        if viewer_id is None or viewer_id != instance.mesh.owner_id:
            data.pop("admin_keys_b64", None)
        return data


class OwnerProfileSerializer(OwnerReadSerializer):
    """An owner's own record together with the devices they may access."""

    devices = DeviceReadSerializer(many=True, read_only=True)

    class Meta(OwnerReadSerializer.Meta):
        fields = OwnerReadSerializer.Meta.fields + ["devices"]


class OwnerDevicesSerializer(serializers.Serializer):
    """Documents the body of the owner device listing."""

    devices = DeviceReadSerializer(many=True, read_only=True)


class DetailSerializer(serializers.Serializer):
    """The single-message body used by the routes that return no resource."""

    detail = serializers.CharField()


class AlgorithmParamSerializer(serializers.Serializer):
    """One keyword argument of an algorithm."""

    name = serializers.CharField()
    calibration = serializers.BooleanField(
        help_text="Set per device rather than on the blueprint step, because it describes one physical sensor."
    )
    required = serializers.BooleanField()
    default = serializers.JSONField(allow_null=True)
    unit = serializers.CharField(allow_null=True)
    doc = serializers.CharField(allow_blank=True)


class AlgorithmSerializer(serializers.Serializer):
    """One entry of the postprocessing function registry."""

    name = serializers.CharField()
    inputs = serializers.ListField(child=serializers.CharField())
    outputs = serializers.ListField(child=serializers.CharField())
    params = AlgorithmParamSerializer(many=True)
    mode = serializers.CharField()
    doc = serializers.CharField(allow_null=True)
    output_units = serializers.DictField(child=serializers.CharField(allow_null=True))


class DeviceUpdateSerializer(serializers.ModelSerializer):
    """node_id/mesh are fixed at creation. Role is editable"""

    admin_keys_b64 = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        required=False,
        validators=[_max_three_admin_keys],
        help_text=_ADMIN_KEYS_HELP,
    )

    # Ownership is checked in the view (the blueprint must belong to the same
    # owner as the device's mesh).
    postprocessing_blueprint_id = serializers.PrimaryKeyRelatedField(
        source="postprocessing_blueprint",
        queryset=PostprocessingBlueprint.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Device
        fields = [
            "label",
            "admin_keys_b64",
            "is_allowed",
            "latitude",
            "longitude",
            "name",
            "short_name",
            "hardware_type",
            "role",
            "postprocessing_blueprint_id",
            "reading_interval_seconds",
            "publish_interval_seconds",
            "absence_detection_enabled",
        ]
        extra_kwargs = {
            "label": {"required": False},
            "is_allowed": {"required": False},
            "reading_interval_seconds": {"required": False},
            "publish_interval_seconds": {"required": False},
            "absence_detection_enabled": {"required": False},
        }

    def validate(self, attrs):
        return _validate_location_pair(self, attrs)


class MeasurementTypeReadSerializer(serializers.ModelSerializer):
    """Freely readable by any verified owner."""

    origin = serializers.SerializerMethodField()  # "measured" | "device" | "computed"
    channel = serializers.SerializerMethodField()

    class Meta:
        model = MeasurementType
        fields = [
            "id", "payload_kind", "field_name", "channel", "origin", "display_name",
            "description", "native_unit", "quantity_kind", "vocabulary_uri",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_origin(self, obj) -> str:
        return origin_of(obj.payload_kind)

    def get_channel(self, obj) -> str:
        return channel_name(obj.payload_kind, obj.field_name)


class MeasurementTypeCreateSerializer(serializers.ModelSerializer):
    """POST /measurements - superuser-only"""

    class Meta:
        model = MeasurementType
        fields = [
            "payload_kind", "field_name", "display_name", "description",
            "native_unit", "quantity_kind", "vocabulary_uri",
        ]
        validators = [] # Avoid DRF's auto UniqueTogetherValidator


class MeasurementTypeUpdateSerializer(serializers.ModelSerializer):
    """PUT /measurements/{id} - payload_kind/field_name are immutable"""

    class Meta:
        model = MeasurementType
        fields = ["display_name", "description", "native_unit", "quantity_kind", "vocabulary_uri"]
        extra_kwargs = {field: {"required": False} for field in fields}


class TelemetryVariantReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelemetryVariant
        fields = [
            "id", "payload_kind", "name", "description",
            "default_reading_interval_seconds", "created_at", "updated_at",
        ]
        read_only_fields = fields


class TelemetryVariantUpdateSerializer(serializers.ModelSerializer):
    """PUT /telemetry-variants/{id} - payload_kind is immutable"""

    class Meta:
        model = TelemetryVariant
        fields = ["name", "description", "default_reading_interval_seconds"]
        extra_kwargs = {field: {"required": False} for field in fields}


class TelemetryVariantMeasurementReadSerializer(serializers.ModelSerializer):
    """GET /telemetry-variants/{id}/measurements. Readable by
    any verified owner, same as MeasurementTypeReadSerializer."""

    measurement_type = MeasurementTypeReadSerializer(read_only=True)

    class Meta:
        model = TelemetryVariantMeasurement
        fields = ["id", "measurement_type", "default_enabled_detectors", "created_at", "updated_at"]
        read_only_fields = fields


class TelemetryVariantMeasurementUpdateSerializer(serializers.ModelSerializer):
    """PUT /telemetry-variants/{id}/measurements/{link_id}. Only
    default_enabled_detectors is editable."""

    default_enabled_detectors = _detector_field(required=False)

    class Meta:
        model = TelemetryVariantMeasurement
        fields = ["default_enabled_detectors"]
        extra_kwargs = {field: {"required": False} for field in fields}


class DeviceTelemetryVariantSerializer(serializers.ModelSerializer):
    """GET /devices/{uuid}/telemetry-variants - which telemetry types this device
    has actually been seen reporting. Read-only (auto-discovered)"""

    telemetry_variant = TelemetryVariantReadSerializer(read_only=True)

    class Meta:
        model = DeviceTelemetryVariant
        fields = ["id", "telemetry_variant", "first_seen", "last_seen"]
        read_only_fields = fields


class DeviceMeasurementSerializer(serializers.ModelSerializer):
    """GET /devices/{uuid}/measurements - a flat list of the channels for this device"""

    # payload_kind/channel/origin live on the nested catalog entry, not here too.
    measurement_type = MeasurementTypeReadSerializer(read_only=True)
    telemetry_variant_id = serializers.UUIDField(source="device_telemetry_variant.telemetry_variant_id", read_only=True)
    # enabled_detectors is what this device sets, and may be null; this is what
    # results once the catalog default is applied.
    effective_detectors = serializers.SerializerMethodField()

    class Meta:
        model = Measurement
        fields = [
            "id",
            "telemetry_variant_id",
            "measurement_type",
            "enabled_detectors",
            "effective_detectors",
            "valid_min",
            "valid_max",
            "first_seen",
            "last_seen",
        ]
        read_only_fields = fields

    def get_effective_detectors(self, obj) -> list[str]:
        return sorted(enabled_detectors_for(obj.enabled_detectors, catalog_default_for(obj, self.context)))


def catalog_defaults_for(measurements) -> dict[tuple, list[str]]:
    links = TelemetryVariantMeasurement.objects.filter(
        telemetry_variant_id__in={m.device_telemetry_variant.telemetry_variant_id for m in measurements},
        measurement_type_id__in={m.measurement_type_id for m in measurements},
    ).values_list("telemetry_variant_id", "measurement_type_id", "default_enabled_detectors")
    return {(variant, mt): default for variant, mt, default in links}


def catalog_default_for(measurement, context=None) -> list[str] | None:
    key = (measurement.device_telemetry_variant.telemetry_variant_id, measurement.measurement_type_id)
    defaults = (context or {}).get("catalog_defaults")
    if defaults is not None:
        return defaults.get(key)
    return catalog_defaults_for([measurement]).get(key)


class DeviceMeasurementUpdateSerializer(serializers.ModelSerializer):
    """PUT /devices/{uuid}/measurements/{id}

    Sets which detectors this channel runs, and the range they check against.

    enabled_detectors: null inherits the catalog default; [] silences the
    channel on this device. valid_min/valid_max have no catalog default,
    and must be set or cleared together.
    """

    enabled_detectors = _detector_field(required=False, allow_null=True)
    valid_min = serializers.FloatField(required=False, allow_null=True)
    valid_max = serializers.FloatField(required=False, allow_null=True)

    class Meta:
        model = Measurement
        fields = ["enabled_detectors", "valid_min", "valid_max"]

    def validate(self, attrs):
        return _validate_range_pair(self, attrs)


class PostprocessingStepSerializer(serializers.ModelSerializer):
    """Validates each step against common/algorithms"""

    class Meta:
        model = PostprocessingStep
        fields = ["id", "order", "function_name", "inputs", "params", "outputs"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        errors = validate_step(
            attrs.get("function_name"), attrs.get("inputs"), attrs.get("params"), attrs.get("outputs") or {}
        )
        if errors:
            raise serializers.ValidationError({"function_name": errors})
        return attrs


class PostprocessingBlueprintSerializer(serializers.ModelSerializer):
    """Steps are nested in read and write"""

    steps = PostprocessingStepSerializer(many=True)
    owner_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = PostprocessingBlueprint
        fields = ["id", "name", "description", "owner_id", "steps", "created_at", "updated_at"]
        read_only_fields = ["id", "owner_id", "created_at", "updated_at"]
        validators = []

    def validate_steps(self, steps):
        if not steps:
            raise serializers.ValidationError("A blueprint needs at least one step")
        orders = [step["order"] for step in steps]
        if len(set(orders)) != len(orders):
            raise serializers.ValidationError("Step `order` values must be unique within a blueprint")
        return steps

    def create(self, validated_data):
        steps = validated_data.pop("steps")
        blueprint = PostprocessingBlueprint.objects.create(**validated_data)
        self._replace_steps(blueprint, steps)
        return blueprint

    def update(self, instance, validated_data):
        steps = validated_data.pop("steps", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if steps is not None:
            self._replace_steps(instance, steps)
        return instance

    @staticmethod
    def _replace_steps(blueprint, steps) -> None:
        blueprint.steps.all().delete()
        PostprocessingStep.objects.bulk_create(
            [PostprocessingStep(blueprint=blueprint, **step) for step in steps]
        )
