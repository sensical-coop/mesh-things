from datetime import datetime
from fnmatch import fnmatch
from urllib.parse import urlsplit

from django.conf import settings

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from common import sinks as sink_names
from common.codec import is_well_known_psk
from common import sources as source_names
from common.algorithms import validate_calibration, validate_step
from common.channels import channel_name, origin_of
from common.detectors import DETECTOR_CHOICES, MEASUREMENT_DETECTORS, enabled_detectors_for
from common.env import env_str

from .broker_hosts import is_own_broker
from .broker_hosts import refusal as broker_refusal
from .emailing import ALARM_EMAIL_COOLDOWN_MAX_SECONDS
from . import postprocessing
from .terms import DEFAULT_LOCALE, LOCALES, VERSIONS, is_current, terms_enforced
from .models import (
    BlueprintVersion,
    Device,
    DevicePostprocessing,
    DeviceTelemetryVariant,
    Measurement,
    MeasurementType,
    Mesh,
    OperatorRequest,
    Owner,
    OwnerRole,
    PostprocessingBackfill,
    PostprocessingBlueprint,
    PostprocessingStep,
    StepCalibration,
    DataDeletion,
    Sink,
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

    # Not required in the schema, since an instance without terms takes none; enforced below.
    terms_version = serializers.CharField(
        write_only=True,
        required=False,
        help_text=(
            "Version of the terms accepted, as served by the terms endpoint. "
            "Required unless the instance does not enforce terms."
        ),
    )
    terms_locale = serializers.ChoiceField(
        choices=LOCALES,
        write_only=True,
        required=False,
        default=DEFAULT_LOCALE,
        help_text="Locale the terms were shown in.",
    )

    def to_internal_value(self, data):
        missing = terms_enforced() and hasattr(data, "get") and data.get("terms_version") is None
        required = {"terms_version": [self.fields["terms_version"].error_messages["required"]]}
        try:
            attrs = super().to_internal_value(data)
        except serializers.ValidationError as e:
            if missing and isinstance(e.detail, dict):
                e.detail.setdefault("terms_version", required["terms_version"])
            raise
        if missing:
            raise serializers.ValidationError(required)
        return attrs

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
            "status_alerts_enabled",
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
        fields = ["name", "email", "alarm_email_cooldown_seconds", "status_alerts_enabled"]
        extra_kwargs = {
            "name": {"required": False},
            "status_alerts_enabled": {
                "help_text": (
                    "Email me when a source I created stays disconnected, or a sink I created with "
                    "meshes or devices attached has nobody connected. Off by default."
                )
            },
        }

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
_DISCOVER_HELP = (
    "Register gateways whose packets decode with this mesh's channel and PSK automatically. "
    "Only an operator may switch it on for a mesh with a default or blank PSK."
)


def _check_discovery_psk(serializer, attrs) -> None:
    """Refuse discovery on a well-known PSK unless the caller is an operator, since every gateway on the channel matches it."""
    if "discover_gateways" not in attrs and "psk_b64" not in attrs:
        return
    instance = serializer.instance
    discover = attrs.get("discover_gateways", getattr(instance, "discover_gateways", False))
    psk_b64 = attrs.get("psk_b64", getattr(instance, "psk_b64", ""))
    owner = serializer.context.get("owner")
    if discover and is_well_known_psk(psk_b64) and not (owner and owner.is_operator):
        raise PermissionDenied(
            "Only an operator may use gateway discovery on a mesh with a default or blank PSK."
        )


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


class MeshPublicSerializer(serializers.ModelSerializer):
    """A mesh as shown to anyone but its owner and superusers, without key material or account state."""

    owner_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Mesh
        fields = ["id", "channel_id", "label", "owner_id", "is_public", "created_at", "updated_at"]
        read_only_fields = fields


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
            "discover_gateways",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "paused_at"]
        extra_kwargs = {
            "is_public": {"required": False},
            "discover_gateways": {"required": False, "help_text": _DISCOVER_HELP},
        }

    def validate_source_id(self, value):
        return _validate_visible_source(self, value)

    def validate(self, attrs):
        _check_discovery_psk(self, attrs)
        return self._take_mesh_terms(super().validate(attrs), needed=attrs.get("source") is None)

    def to_representation(self, instance):
        viewer_id = self.context.get("viewer_id")
        # The key is stored in plain text, so hiding it from superusers would protect nothing.
        if (viewer_id is None or viewer_id != instance.owner_id) and not self.context.get("viewer_is_superuser"):
            return MeshPublicSerializer(instance).data
        return super().to_representation(instance)


class MeshUpdateSerializer(_MeshTermsMixin, serializers.ModelSerializer):
    """PUT /meshes/{id}: channel_id, psk_b64, label, is_public, source_id and discover_gateways are editable.

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
        fields = [
            "channel_id",
            "psk_b64",
            "label",
            "is_public",
            "source_id",
            "discover_gateways",
            "terms_version",
            "terms_locale",
        ]
        extra_kwargs = {
            "label": {"required": False},
            "channel_id": {"required": False},
            "is_public": {"required": False},
            "discover_gateways": {"required": False, "help_text": _DISCOVER_HELP},
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        _check_discovery_psk(self, attrs)
        mesh = self.instance
        moving_to_default = "source" in attrs and attrs["source"] is None and mesh.source_id is not None
        needed = moving_to_default and not is_current(mesh.current_terms_acceptance, TermsKind.MESH)
        return self._take_mesh_terms(attrs, needed=needed)

    def validate_source_id(self, value):
        return _validate_visible_source(self, value)


def _own_broker_hosts() -> list[str]:
    """Every name this instance's broker goes by: its API, the bridge's and the sinks' address."""
    return [
        urlsplit(env_str("REGISTRY__EMQX_API_URL")).hostname or "",
        env_str("MQTT_BRIDGE__BROKER"),
        sinks_broker().rpartition(":")[0],
    ]


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
        if is_own_broker(host, _own_broker_hosts()):
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
        if source_names.reaches_reserved_topics(value):
            raise serializers.ValidationError(
                "This topic filter could match the topics sources are republished and sinks are sent on."
            )
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


def sinks_broker() -> str:
    """The broker a sink's consumer connects to, as host:port."""
    default = f"{env_str('MQTT_BRIDGE__BROKER')}:{env_str('MQTT_BRIDGE__PORT', '8883')}"
    return env_str("REGISTRY__SINKS_BROKER", default)


class SinkWriteSerializer(serializers.Serializer):
    """Create or update a sink. Every field is optional on update; lists replace what is there."""

    label = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    streams = serializers.ListField(
        child=serializers.ChoiceField(choices=sink_names.STREAMS),
        allow_empty=False,
        required=False,
        help_text="Which readings are sent: `decoded`, `derived`, `alarms`. Defaults to `decoded`.",
    )
    mesh_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="Meshes whose every node is sent, including nodes that appear later.",
    )
    device_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="Registrations (`uuid`) of single devices to send.",
    )

    def validate_streams(self, value):
        return [stream for stream in sink_names.STREAMS if stream in value]

    def _editable(self, obj, mesh: Mesh) -> None:
        owner = self.context["owner"]
        if not owner.can_edit_mesh(mesh):
            raise serializers.ValidationError(f"{obj} not found.")
        if not mesh.owner.is_operator:
            raise serializers.ValidationError(f"{obj} is on a mesh not owned by an operator.")

    def validate_mesh_ids(self, value):
        meshes = {mesh.id: mesh for mesh in Mesh.objects.filter(pk__in=value).select_related("owner")}
        for mesh_id in value:
            if mesh_id not in meshes:
                raise serializers.ValidationError(f"Mesh {mesh_id} not found.")
            self._editable(f"Mesh {mesh_id}", meshes[mesh_id])
        return list(meshes.values())

    def validate_device_ids(self, value):
        devices = {d.id: d for d in Device.objects.filter(pk__in=value).select_related("mesh__owner")}
        for device_id in value:
            if device_id not in devices:
                raise serializers.ValidationError(f"Device {device_id} not found.")
            self._editable(f"Device {device_id}", devices[device_id].mesh)
        return list(devices.values())


class SinkCreateSerializer(_TermsAcceptanceInputMixin, SinkWriteSerializer):
    terms_kind = TermsKind.SINK


class SinkTermsAcceptanceSerializer(_TermsAcceptanceInputMixin):
    terms_kind = TermsKind.SINK


class SinkReadSerializer(serializers.ModelSerializer):
    # Declared because the model's JSONField would reach the schema untyped.
    streams = serializers.ListField(
        child=serializers.ChoiceField(choices=sink_names.STREAMS),
        read_only=True,
        help_text="Which readings are sent: `decoded`, `derived`, `alarms`.",
    )
    created_by_id = serializers.UUIDField(read_only=True, allow_null=True)
    paused_at = serializers.DateTimeField(
        read_only=True, allow_null=True, help_text="When the sink was paused because its terms lapsed."
    )
    terms_accepted_version = serializers.SerializerMethodField()
    terms_expires_at = serializers.SerializerMethodField()
    mesh_ids = serializers.SerializerMethodField()
    device_ids = serializers.SerializerMethodField()
    broker = serializers.SerializerMethodField(help_text="Broker the consumer connects to over TLS, as host:port.")
    username = serializers.SerializerMethodField()
    topic_filter = serializers.SerializerMethodField(help_text="Everything the consumer may subscribe to.")
    connections = serializers.IntegerField(
        read_only=True, allow_null=True, help_text="Consumers connected now. Null when the broker cannot be asked."
    )

    class Meta:
        model = Sink
        fields = [
            "id",
            "label",
            "streams",
            "mesh_ids",
            "device_ids",
            "broker",
            "username",
            "topic_filter",
            "connections",
            "paused_at",
            "terms_accepted_version",
            "terms_expires_at",
            "created_by_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_terms_accepted_version(self, instance) -> str | None:
        acceptance = instance.current_terms_acceptance
        return acceptance.terms_version if acceptance else None

    def get_terms_expires_at(self, instance) -> datetime | None:
        """When the terms acceptance lapses. Null for no time limit."""
        acceptance = instance.current_terms_acceptance
        return acceptance.expires_at if acceptance else None

    def get_mesh_ids(self, instance) -> list[str]:
        return [str(mesh_id) for mesh_id in instance.mesh_links.order_by("created_at").values_list("mesh_id", flat=True)]

    def get_device_ids(self, instance) -> list[str]:
        return [
            str(device_id) for device_id in instance.device_links.order_by("created_at").values_list("device_id", flat=True)
        ]

    def get_broker(self, instance) -> str:
        return sinks_broker()

    def get_username(self, instance) -> str:
        return sink_names.username(instance.id)

    def get_topic_filter(self, instance) -> str:
        return sink_names.topic_filter(instance.id)


class SinkCredentialsSerializer(SinkReadSerializer):
    password = serializers.CharField(read_only=True, help_text="Shown only in this response.")

    class Meta(SinkReadSerializer.Meta):
        fields = SinkReadSerializer.Meta.fields + ["password"]
        read_only_fields = fields


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
_ARCHIVE_HELP = (
    "Store this device's readings in the Parquet archive from now on. Only on a mesh owned by an "
    "operator, and only on instances that run the archive. Turning it off keeps what was stored."
)


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
    """admin_keys_b64 and the archive fields are shown only to the mesh owner and superusers.

    `uuid` is the registration; `node_id` is the Meshtastic node number.
    The storage column is `device_id`.
    """

    uuid = serializers.UUIDField(source="id", read_only=True)
    node_id = serializers.IntegerField(source="device_id", read_only=True)
    mesh_id = serializers.UUIDField(read_only=True)
    admin_keys_b64 = serializers.ListField(child=serializers.CharField(), read_only=True)
    telemetry_variant_ids = serializers.SerializerMethodField(
        help_text="Telemetry variants this device has been seen reporting."
    )

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
            "reading_interval_seconds",
            "publish_interval_seconds",
            "absence_detection_enabled",
            "archive_enabled",
            "archive_enabled_at",
            "archive_enabled_by",
            "last_seen",
            "discovered_at",
            "telemetry_variant_ids",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.ListField(child=serializers.UUIDField()))
    def get_telemetry_variant_ids(self, instance) -> list[str]:
        # Sorted in Python so a list view's prefetch of the links is reused.
        links = sorted(instance.telemetry_variants.all(), key=lambda link: link.first_seen)
        return [str(link.telemetry_variant_id) for link in links]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        viewer_id = self.context.get("viewer_id")
        if (viewer_id is None or viewer_id != instance.mesh.owner_id) and not self.context.get("viewer_is_superuser"):
            for field in ("admin_keys_b64", "archive_enabled", "archive_enabled_at", "archive_enabled_by"):
                data.pop(field, None)
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
            "reading_interval_seconds",
            "publish_interval_seconds",
            "absence_detection_enabled",
            "archive_enabled",
        ]
        extra_kwargs = {
            "label": {"required": False},
            "is_allowed": {"required": False},
            "reading_interval_seconds": {"required": False},
            "publish_interval_seconds": {"required": False},
            "absence_detection_enabled": {"required": False},
            "archive_enabled": {"required": False, "help_text": _ARCHIVE_HELP},
        }

    def validate_archive_enabled(self, value):
        if value and not self.instance.archive_enabled:
            if not self.context.get("archive_available"):
                raise serializers.ValidationError("This instance has no archive.")
            if not self.instance.mesh.owner.is_operator:
                raise serializers.ValidationError("Only devices on a mesh owned by an operator can be archived.")
        return value

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
    produced_by = serializers.UUIDField(
        source="produced_by_id",
        read_only=True,
        allow_null=True,
        help_text="The device postprocessing computing this channel, null for a channel the device reports.",
    )

    class Meta:
        model = Measurement
        fields = [
            "id",
            "telemetry_variant_id",
            "measurement_type",
            "produced_by",
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


class BlueprintInputSerializer(serializers.Serializer):
    """An input slot a blueprint version reads, bound to a channel by each device."""

    slot = serializers.CharField(max_length=64)
    default_channel = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Channel bound automatically when the device has it, such as `environment_metrics.temperature`.",
    )


class PostprocessingStepSerializer(serializers.ModelSerializer):
    """Validates each step against common/algorithms"""

    class Meta:
        model = PostprocessingStep
        fields = ["key", "order", "function_name", "inputs", "params", "outputs"]

    def validate(self, attrs):
        errors = validate_step(
            attrs.get("function_name"), attrs.get("inputs"), attrs.get("params"), attrs.get("outputs") or {}
        )
        if errors:
            raise serializers.ValidationError({"function_name": errors})
        return attrs


class BlueprintVersionSerializer(serializers.ModelSerializer):
    """Immutable once created. Steps are nested in read and write."""

    blueprint_id = serializers.UUIDField(read_only=True)
    inputs = BlueprintInputSerializer(many=True)
    steps = PostprocessingStepSerializer(many=True)
    device_count = serializers.IntegerField(source="attachments.count", read_only=True)

    class Meta:
        model = BlueprintVersion
        fields = ["blueprint_id", "number", "inputs", "steps", "notes", "device_count", "created_at"]
        read_only_fields = ["number", "created_at"]

    def validate(self, attrs):
        steps = attrs.get("steps") or []
        if not steps:
            raise serializers.ValidationError({"steps": "A blueprint version needs at least one step"})
        orders = [step["order"] for step in steps]
        if len(set(orders)) != len(orders):
            raise serializers.ValidationError({"steps": "Step `order` values must be unique within a version"})
        errors = postprocessing.validate_version(attrs.get("inputs") or [], steps)
        if errors:
            raise serializers.ValidationError({"steps": errors})
        return attrs

    def create(self, validated_data):
        steps = validated_data.pop("steps")
        inputs = [
            {k: v for k, v in dict(entry).items() if v is not None} for entry in validated_data.pop("inputs")
        ]
        version = BlueprintVersion.objects.create(inputs=inputs, **validated_data)
        PostprocessingStep.objects.bulk_create([PostprocessingStep(version=version, **step) for step in steps])
        return version


class PostprocessingBlueprintSerializer(serializers.ModelSerializer):
    owner_id = serializers.UUIDField(
        read_only=True, allow_null=True, help_text="Null once its owner was deleted while devices still used it."
    )
    latest_version = serializers.SerializerMethodField()

    class Meta:
        model = PostprocessingBlueprint
        fields = ["id", "name", "description", "is_public", "owner_id", "latest_version", "created_at", "updated_at"]
        read_only_fields = fields

    @extend_schema_field(BlueprintVersionSerializer)
    def get_latest_version(self, obj):
        version = obj.versions.order_by("-number").first()
        return BlueprintVersionSerializer(version).data if version else None


class PostprocessingBlueprintCreateSerializer(BlueprintVersionSerializer):
    """A new blueprint together with its first version."""

    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    is_public = serializers.BooleanField(required=False, default=False)

    class Meta(BlueprintVersionSerializer.Meta):
        fields = ["name", "description", "is_public", "inputs", "steps", "notes"]

    def create(self, validated_data):
        blueprint = PostprocessingBlueprint.objects.create(
            owner=validated_data.pop("owner"),
            name=validated_data.pop("name"),
            description=validated_data.pop("description", None),
            is_public=validated_data.pop("is_public", False),
        )
        super().create({**validated_data, "blueprint": blueprint, "number": 1})
        return blueprint


class PostprocessingBlueprintUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostprocessingBlueprint
        fields = ["name", "description", "is_public"]
        extra_kwargs = {"name": {"required": False}}


class DerivedOutputSerializer(serializers.Serializer):
    field_name = serializers.CharField()
    channel = serializers.CharField()
    measurement_id = serializers.UUIDField()
    unit = serializers.CharField(allow_null=True)


class DevicePostprocessingSerializer(serializers.ModelSerializer):
    device_uuid = serializers.UUIDField(source="device_id", read_only=True)
    blueprint_id = serializers.UUIDField(source="blueprint_version.blueprint_id", read_only=True)
    blueprint_name = serializers.CharField(source="blueprint_version.blueprint.name", read_only=True)
    blueprint_version = serializers.IntegerField(source="blueprint_version.number", read_only=True)
    input_bindings = serializers.SerializerMethodField()
    effective_tolerance_seconds = serializers.SerializerMethodField()
    outputs = serializers.SerializerMethodField()
    problems = serializers.SerializerMethodField()

    class Meta:
        model = DevicePostprocessing
        fields = [
            "id",
            "device_uuid",
            "blueprint_id",
            "blueprint_name",
            "blueprint_version",
            "input_bindings",
            "output_prefix",
            "tolerance_seconds",
            "effective_tolerance_seconds",
            "is_enabled",
            "outputs",
            "problems",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_input_bindings(self, obj) -> dict[str, str]:
        return {b.slot: str(b.measurement_id) for b in obj.input_bindings.all()}

    def get_effective_tolerance_seconds(self, obj) -> float:
        return postprocessing.tolerance_for(obj)

    @extend_schema_field(DerivedOutputSerializer(many=True))
    def get_outputs(self, obj):
        return [
            {
                "field_name": m.measurement_type.field_name,
                "channel": postprocessing.measurement_channel(m),
                "measurement_id": str(m.id),
                "unit": m.measurement_type.native_unit,
            }
            for m in sorted(obj.outputs.all(), key=lambda m: m.measurement_type.field_name)
        ]

    def get_problems(self, obj) -> list[str]:
        return postprocessing.problems(obj)


class DevicePostprocessingWriteSerializer(serializers.Serializer):
    blueprint_id = serializers.UUIDField(required=False, help_text="Required when attaching.")
    blueprint_version = serializers.IntegerField(
        required=False, min_value=1, help_text="Defaults to the latest version when attaching."
    )
    input_bindings = serializers.DictField(
        child=serializers.UUIDField(allow_null=True),
        required=False,
        help_text="{slot: measurement id of this device}. Null unbinds a slot.",
    )
    output_prefix = serializers.CharField(required=False, allow_blank=True, max_length=64)
    tolerance_seconds = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    is_enabled = serializers.BooleanField(required=False)

    def validate_output_prefix(self, value):
        if not postprocessing.PREFIX_PATTERN.match(value):
            raise serializers.ValidationError("Use lowercase letters, digits and underscores")
        return value


class StepCalibrationSerializer(serializers.ModelSerializer):
    valid_from = serializers.DateTimeField(required=False, help_text="Defaults to now.")

    class Meta:
        model = StepCalibration
        fields = ["id", "step_key", "function_name", "params", "valid_from", "created_at"]
        read_only_fields = ["id", "function_name", "created_at"]

    def validate(self, attrs):
        steps = {step.key: step for step in self.context["device_postprocessing"].blueprint_version.steps.all()}
        step = steps.get(attrs["step_key"])
        if step is None:
            raise serializers.ValidationError({"step_key": f"No step {attrs['step_key']!r}, expected one of {sorted(steps)}"})
        errors = validate_calibration(step.function_name, attrs.get("params"))
        if errors:
            raise serializers.ValidationError({"params": errors})
        attrs["function_name"] = step.function_name
        return attrs


class PostprocessingBackfillSerializer(serializers.ModelSerializer):
    postprocessing_id = serializers.UUIDField(source="device_postprocessing_id", read_only=True)
    stop = serializers.DateTimeField(required=False, help_text="Defaults to now.")

    class Meta:
        model = PostprocessingBackfill
        fields = [
            "id",
            "postprocessing_id",
            "start",
            "stop",
            "include_dependants",
            "status",
            "points_published",
            "error",
            "created_at",
            "started_at",
            "finished_at",
        ]
        read_only_fields = ["id", "status", "points_published", "error", "created_at", "started_at", "finished_at"]

    def validate(self, attrs):
        stop = attrs.get("stop") or timezone.now()
        if attrs["start"] >= stop:
            raise serializers.ValidationError({"start": "Must be before stop"})
        if stop - attrs["start"] > postprocessing.MAX_BACKFILL_SPAN:
            raise serializers.ValidationError(
                {"start": f"A backfill covers at most {postprocessing.MAX_BACKFILL_SPAN.days} days. Split it"}
            )
        attrs["stop"] = stop
        return attrs


class BackfillClaimSerializer(PostprocessingBackfillSerializer):
    """What the quality worker needs to run a claimed backfill."""

    mesh_id = serializers.UUIDField(source="device_postprocessing.device.mesh_id", read_only=True)
    node_id = serializers.IntegerField(source="device_postprocessing.device.device_id", read_only=True)
    plans = serializers.SerializerMethodField()

    class Meta(PostprocessingBackfillSerializer.Meta):
        fields = PostprocessingBackfillSerializer.Meta.fields + ["mesh_id", "node_id", "plans"]

    def get_plans(self, obj) -> list[dict]:
        return [
            plan.to_dict()
            for plan in postprocessing.backfill_plans(obj.device_postprocessing, obj.include_dependants)
        ]


class BackfillResultSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["done", "failed"])
    points_published = serializers.IntegerField(min_value=0, required=False, default=0)
    error = serializers.CharField(required=False, allow_null=True, allow_blank=True)

