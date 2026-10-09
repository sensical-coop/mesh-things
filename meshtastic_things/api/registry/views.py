import secrets
import uuid
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

import structlog
from django.conf import settings
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, RestrictedError
from django.middleware.csrf import get_token as get_csrf_token
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, NotFound, ParseError, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .auth import generate_api_key, hash_api_key
from .emailing import (
    send_operator_request_decided_email,
    send_operator_request_email,
    send_password_reset_email,
    send_verification_email,
)
from .data_lifecycle import (
    cancel_mesh_deletions,
    record_acceptance,
    resume_mesh,
    resume_sink,
    resume_source,
    schedule_mesh_deletion,
)
from . import email_health, postprocessing, sinks, topology
from .emqx_client import get_emqx_client
from .exceptions import BadGateway, Conflict
from .gateways import save_gateway
from .kafka_publisher import get_publisher, publish_gateway_state
from common import node_ids
from common.algorithms import REGISTRY, discover
from common.env import env_str
from common.detectors import DETECTOR_SPECS
from common.topology import distance_km, traceroute_paths

from .models import (
    BackfillStatus,
    BlueprintVersion,
    DataDeletion,
    DataDeletionReason,
    DataDeletionStatus,
    Device,
    DeviceSink,
    DeviceTelemetryVariant,
    DevicePostprocessing,
    Measurement,
    MeasurementType,
    Mesh,
    MeshSink,
    OperatorRequest,
    OperatorRequestStatus,
    Owner,
    OwnerRole,
    PostprocessingBackfill,
    PostprocessingBlueprint,
    Sink,
    Source,
    TermsKind,
    TelemetryVariant,
    TelemetryVariantMeasurement,
    Traceroute,
    can_edit_mesh,
    can_view_mesh,
    visible_meshes_for,
)
from .permissions import IsOperator, IsSuperuser, IsVerifiedOwner, ReadOnlyOrVerifiedOwner
from .serializers import (
    AlgorithmSerializer,
    BackfillClaimSerializer,
    BackfillResultSerializer,
    BlueprintVersionSerializer,
    DetailSerializer,
    DeviceCreateSerializer,
    DevicePostprocessingSerializer,
    DevicePostprocessingWriteSerializer,
    DeviceReadSerializer,
    DeviceUpdateSerializer,
    OwnerDevicesSerializer,
    OwnerProfileSerializer,
    MeasurementTypeCreateSerializer,
    MeasurementTypeReadSerializer,
    MeasurementTypeUpdateSerializer,
    MeshSerializer,
    MeshUpdateSerializer,
    EmailStatusSerializer,
    MetricsResponseSerializer,
    OperatorRequestAdminSerializer,
    OperatorRequestCreateSerializer,
    OperatorRequestDecisionSerializer,
    OperatorRequestSerializer,
    OwnerChangePasswordSerializer,
    OwnerCreateSerializer,
    OwnerLoginSerializer,
    OwnerPublicSerializer,
    OwnerReadSerializer,
    OwnerRequestPasswordResetSerializer,
    OwnerResetPasswordSerializer,
    OwnerRoleSerializer,
    OwnerUpdateSerializer,
    OwnerWithApiKeySerializer,
    PostprocessingBackfillSerializer,
    PostprocessingBlueprintCreateSerializer,
    PostprocessingBlueprintSerializer,
    PostprocessingBlueprintUpdateSerializer,
    StepCalibrationSerializer,
    DataDeletionSerializer,
    RfLinkSerializer,
    SinkCreateSerializer,
    SinkCredentialsSerializer,
    SinkReadSerializer,
    SinkTermsAcceptanceSerializer,
    SinkWriteSerializer,
    SourceCreateSerializer,
    SourceReadSerializer,
    AccountTermsAcceptanceSerializer,
    MeshTermsAcceptanceSerializer,
    SourceTermsAcceptanceSerializer,
    SourceUpdateSerializer,
    TermsSerializer,
    TracerouteSerializer,
    DeviceMeasurementSerializer,
    DeviceMeasurementUpdateSerializer,
    DetectorSerializer,
    DeviceTelemetryVariantSerializer,
    catalog_defaults_for,
    TelemetryVariantMeasurementReadSerializer,
    TelemetryVariantMeasurementUpdateSerializer,
    TelemetryVariantReadSerializer,
    TelemetryVariantUpdateSerializer,
)
from .terms import terms as current_terms
from .terms import terms_enforced
from .throttling import ResendVerificationThrottle

log = structlog.get_logger()


def _query(name, description, type_=OpenApiTypes.STR, **kwargs):
    return OpenApiParameter(name, type_, OpenApiParameter.QUERY, description=description, **kwargs)


def _flag(name, description):
    return _query(name, description, OpenApiTypes.BOOL)


MESH_FILTER_PARAMS = [
    _flag("owned", "Restrict to meshes the caller owns, excluding public ones."),
    _query(
        "source_id",
        "Restrict to meshes bridged from one source. Matches only meshes the caller owns.",
        OpenApiTypes.UUID,
    ),
]

TELEMETRY_VARIANT_FILTER_PARAM = _query(
    "telemetry_variant",
    "Restrict by the telemetry variants a device has reported. "
    "`has_any_of` matches devices that reported at least one of them, `has_all_of` those that reported "
    "every one, and `has_none_of` those that reported none. Bare ids mean `has_any_of`.",
)

DEVICE_FILTER_PARAMS = [
    _query("mesh_id", "Restrict to devices on one mesh.", OpenApiTypes.UUID),
    _flag("is_gateway", "Restrict to gateways, or to plain nodes when false."),
    _flag("is_allowed", "Restrict to allowed registrations, or to rejected ones when false."),
    _flag(
        "has_postprocessing",
        "Restrict to devices with a postprocessing attached, or to those without one when false.",
    ),
    TELEMETRY_VARIANT_FILTER_PARAM,
]

MEASUREMENT_FILTER_PARAMS = [
    _query("kind", "Restrict to one namespace.", enum=["telemetry", "device", "computed"]),
    _query("payload_kind", "Restrict to one exact payload kind, such as `telemetry:environment_metrics`."),
    _query("field_name", "Restrict to one field name, such as `temperature`."),
]

NO_CONTENT = OpenApiResponse(description="Deleted.")


class HealthView(APIView):
    """Report whether the service and its database are reachable."""

    # Open and unthrottled
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Both the service and its database are reachable."),
            503: OpenApiResponse(description="The database is unreachable."),
        }
    )
    def get(self, request):
        try:
            Mesh.objects.exists()
        except Exception as e:
            return Response({"detail": f"Database unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"status": "ok"})


class MetricsView(APIView):
    """Return totals for registered owners, meshes, devices and active gateways."""

    permission_classes = [AllowAny]

    @extend_schema(responses=MetricsResponseSerializer)
    def get(self, request):
        body = {
            "devices": Device.objects.count(),
            "owners": Owner.objects.count(),
            "meshes": Mesh.objects.count(),
            "active_gateways": Device.objects.filter(is_gateway=True, is_allowed=True).count(),
        }
        return Response(MetricsResponseSerializer(body).data)


class EmailStatusView(APIView):
    permission_classes = [IsSuperuser]

    @extend_schema(responses=EmailStatusSerializer)
    def get(self, request):
        """Report whether the instance's emails are being accepted by its mail server. Superusers only.

        Covers every email registry sends: alarms and their summaries, sign up,
        password resets, terms and status notices. `ok` is false while the most
        recent one failed to send, and turns true again with the next success.
        It says nothing about delivery beyond the mail server, such as spam
        filtering. Counts cover the last 24 hours and start empty after Redis is
        cleared.
        """
        health = email_health.summary()
        for field in ("last_sent_at", "last_failed_at"):
            if health[field] is not None:
                health[field] = datetime.fromtimestamp(health[field], tz=dt_timezone.utc)
        return Response(EmailStatusSerializer(health).data)


def _owner_serializer_for(request, owner=None):
    """The full record for the owner themselves and for superusers, otherwise
    the public directory.

    These routes are unauthenticated, avoid emails or anything like that.
    """
    if request.user.is_superuser:
        return OwnerReadSerializer
    if owner is not None and request.user.is_authenticated and request.user.id == owner.id:
        return OwnerReadSerializer
    return OwnerPublicSerializer


class OwnerListCreateView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="owners_list",
        responses=OpenApiResponse(
            response=OwnerPublicSerializer(many=True),
            description=(
                "The public fields shown here. A superuser receives the full "
                "record for every owner."
            ),
        )
    )
    def get(self, request):
        """List registered owners.

        A superuser sees the full record for every owner. Everyone else,
        including an authenticated owner reading their own row, gets the public
        fields only, so that the rows are all the same shape. Use the profile
        route to read your own record in full.
        """
        owners = Owner.objects.all()
        return Response(_owner_serializer_for(request)(owners, many=True).data)

    @extend_schema(request=OwnerCreateSerializer, responses={201: OwnerWithApiKeySerializer})
    def post(self, request):
        """Register an owner, sign it in and return its API key.

        Signing up accepts the current account terms, which are recorded. The
        key is for scripts and is shown in this response only; it cannot be
        retrieved again afterwards. A browser uses the session cookie set by
        this response instead. A new owner stays inactive until its email
        address is verified, and until then can only reach its own account.

        Args:
            terms_version: The `version` of the account terms accepted, as
                served by the terms endpoint. Required, and refused once the
                terms have changed, unless the instance does not enforce terms.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """
        serializer = OwnerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        api_key = generate_api_key()
        verification_token = generate_api_key()
        try:
            with transaction.atomic():
                owner = Owner.objects.create_user(
                    email=serializer.validated_data["email"],
                    name=serializer.validated_data["name"],
                    password=serializer.validated_data["password"],
                    api_key_hash=hash_api_key(api_key),
                    is_active=False,
                    email_verification_token_hash=hash_api_key(verification_token),
                    email_verification_sent_at=timezone.now(),
                )
                record_acceptance(TermsKind.ACCOUNT, owner, serializer.validated_data["terms_locale"])
        except IntegrityError:
            raise Conflict(f"Owner with email {serializer.validated_data['email']} already exists")
        auth_login(request, owner)
        # api_key is never persisted or retrievable again
        owner.api_key = api_key
        try:
            send_verification_email(owner, verification_token)
        except Exception as e:
            # Signup already succeeded, resend-verification can recover.
            log.warning("verification_email_send_failed", owner_id=str(owner.id), error=str(e))
        return Response(OwnerWithApiKeySerializer(owner).data, status=status.HTTP_201_CREATED)


class OwnerVerifyEmailView(APIView):
    """Confirm an owner's email address using the token from the verification link."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[
            _query("token", "The token from the verification link.", required=True),
        ],
        responses=DetailSerializer,
    )
    def get(self, request):
        token = request.query_params.get("token")
        if not token:
            raise ParseError("token query parameter is required")
        owner = Owner.objects.filter(email_verification_token_hash=hash_api_key(token)).first()
        if owner is not None and owner.is_active:
            return Response({"detail": "Email already verified"})
        ttl = timedelta(hours=settings.EMAIL_VERIFICATION_TTL_HOURS)
        expired = owner is None or owner.email_verification_sent_at is None or (
            timezone.now() > owner.email_verification_sent_at + ttl
        )
        if expired:
            raise ParseError(
                "Invalid or expired verification link - request a new one via "
                "POST /owners/me/resend-verification"
            )
        owner.is_active = True
        owner.email_verified_at = timezone.now()
        owner.save(update_fields=["is_active", "email_verified_at"])
        return Response({"detail": "Email verified"})


class OwnerResendVerificationView(APIView):
    """Send a fresh verification email to the authenticated owner."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ResendVerificationThrottle]

    @extend_schema(request=None, responses=DetailSerializer)
    def post(self, request):
        owner = request.user
        if owner.is_active:
            return Response({"detail": "Email already verified"})
        verification_token = generate_api_key()
        owner.email_verification_token_hash = hash_api_key(verification_token)
        owner.email_verification_sent_at = timezone.now()
        owner.save(update_fields=["email_verification_token_hash", "email_verification_sent_at"])
        try:
            send_verification_email(owner, verification_token)
        except Exception as e:
            log.warning("verification_email_send_failed", owner_id=str(owner.id), error=str(e))
            raise BadGateway("Failed to send verification email, try again shortly")
        return Response({"detail": "Verification email sent"})


class OwnerOperatorRequestView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=OperatorRequestSerializer)
    def get(self, request):
        """Return the caller's most recent operator request and its status."""
        operator_request = request.user.operator_requests.order_by("-created_at").first()
        if operator_request is None:
            raise NotFound("No operator request")
        return Response(OperatorRequestSerializer(operator_request).data)

    @extend_schema(request=OperatorRequestCreateSerializer, responses={201: OperatorRequestSerializer})
    def post(self, request):
        """Ask for the operator role, which lets an owner create sources.

        Every superuser is emailed and one of them approves or rejects the
        request. Only one request can be pending at a time, and an owner who
        is already an operator cannot file one. Limited to 3 requests a day.

        Args:
            reason: Why the role is needed. Shown to superusers. Required.
        """
        if request.user.is_operator:
            raise Conflict("You are already an operator")
        serializer = OperatorRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                operator_request = serializer.save(owner=request.user)
        except IntegrityError:
            raise Conflict("You already have a pending operator request")
        try:
            send_operator_request_email(operator_request)
        except Exception as e:
            # Superusers still find the request in the list.
            log.warning("operator_request_email_failed", request_id=str(operator_request.id), error=str(e))
        return Response(OperatorRequestSerializer(operator_request).data, status=status.HTTP_201_CREATED)


def _get_operator_request_or_404(request_id) -> OperatorRequest:
    try:
        return OperatorRequest.objects.select_related("owner").get(pk=request_id)
    except (OperatorRequest.DoesNotExist, ValueError, TypeError):
        raise NotFound("Operator request not found")


class OperatorRequestListView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(
        parameters=[
            _query(
                "status",
                "Restrict to one status: `pending` (the default), `approved`, `rejected`, or `all`.",
                OpenApiTypes.STR,
            )
        ],
        responses=OperatorRequestAdminSerializer(many=True),
    )
    def get(self, request):
        """List operator requests, newest first. Superusers only.

        Args:
            status: `pending`, the default, `approved`, `rejected`, or `all`.
        """
        _require_superuser(request)
        wanted = request.query_params.get("status", OperatorRequestStatus.PENDING)
        qs = OperatorRequest.objects.select_related("owner").order_by("-created_at")
        if wanted != "all":
            if wanted not in OperatorRequestStatus.values:
                raise ValidationError({"status": "Must be pending, approved, rejected or all."})
            qs = qs.filter(status=wanted)
        return Response(OperatorRequestAdminSerializer(qs, many=True).data)


class OperatorRequestDetailView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=OperatorRequestAdminSerializer)
    def get(self, request, request_id):
        """Return one operator request. Superusers only."""
        _require_superuser(request)
        return Response(OperatorRequestAdminSerializer(_get_operator_request_or_404(request_id)).data)

    @extend_schema(request=OperatorRequestDecisionSerializer, responses=OperatorRequestAdminSerializer)
    def put(self, request, request_id):
        """Approve or reject a pending operator request. Superusers only.

        Approving makes the requester an operator. The requester is emailed
        the decision, and the decision stands even if that email fails.

        Args:
            decision: `approve` or `reject`. Required.
            note: Message to the requester, included in the email. Optional.
        """
        _require_superuser(request)
        serializer = OperatorRequestDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        approve = serializer.validated_data["decision"] == "approve"
        with transaction.atomic():
            operator_request = (
                OperatorRequest.objects.select_for_update().select_related("owner").filter(pk=request_id).first()
            )
            if operator_request is None:
                raise NotFound("Operator request not found")
            if operator_request.status != OperatorRequestStatus.PENDING:
                raise Conflict(f"This request was already {operator_request.status}")
            operator_request.status = OperatorRequestStatus.APPROVED if approve else OperatorRequestStatus.REJECTED
            operator_request.decision_note = serializer.validated_data["note"]
            operator_request.decided_by = request.user
            operator_request.decided_at = timezone.now()
            operator_request.save(update_fields=["status", "decision_note", "decided_by", "decided_at"])
            promoted = approve and not operator_request.owner.is_operator
            if promoted:
                operator_request.owner.role = OwnerRole.OPERATOR
                operator_request.owner.save(update_fields=["role"])
        if promoted:
            try:
                sinks.publish_owner(operator_request.owner)
            except Exception as e:
                # Only re-enables archives the owner had before, so nothing is archived by mistake.
                log.warning("owner_sinks_publish_failed", owner_id=str(operator_request.owner_id), error=str(e))
        try:
            send_operator_request_decided_email(operator_request)
        except Exception as e:
            log.warning("operator_request_decision_email_failed", request_id=str(operator_request.id), error=str(e))
        return Response(OperatorRequestAdminSerializer(operator_request).data)


class CsrfCookieView(APIView):
    """Set the CSRF cookie a browser client needs before logging in."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(responses=DetailSerializer)
    def get(self, request):
        get_csrf_token(request)
        return Response({"detail": "CSRF cookie set"})


class OwnerLoginView(APIView):
    """Sign in with email and password, returning the owner profile and a session cookie.

    An owner whose email is not verified yet is signed in too, with `is_active`
    false in the profile, and can only reach its own account until it verifies.
    Attempts are limited per email and source address; once the limit is
    reached even the correct password is refused with `429` for about a minute.
    """

    permission_classes = [AllowAny]

    @extend_schema(request=OwnerLoginSerializer, responses=OwnerProfileSerializer)
    def post(self, request):
        serializer = OwnerLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        owner = Owner.objects.filter(email=serializer.validated_data["email"]).first()
        if owner is None or not owner.check_password(serializer.validated_data["password"]):
            raise AuthenticationFailed("Invalid email or password")

        auth_login(request, owner)
        data = OwnerReadSerializer(owner).data
        data["devices"] = _devices_for_owner(owner)
        return Response(data)


class OwnerLogoutView(APIView):
    """End the current session."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses=DetailSerializer)
    def post(self, request):
        auth_logout(request)
        return Response({"detail": "Logged out"})


class OwnerRequestPasswordResetView(APIView):
    """Email a password reset link.

    The response is the same whether or not the address is registered, so it
    cannot be used to discover accounts.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=OwnerRequestPasswordResetSerializer, responses=DetailSerializer)
    def post(self, request):
        serializer = OwnerRequestPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        owner = Owner.objects.filter(email=serializer.validated_data["email"]).first()
        if owner is not None:
            reset_token = generate_api_key()
            owner.password_reset_token_hash = hash_api_key(reset_token)
            owner.password_reset_sent_at = timezone.now()
            owner.save(update_fields=["password_reset_token_hash", "password_reset_sent_at"])
            try:
                send_password_reset_email(owner, reset_token)
            except Exception as e:
                log.warning("password_reset_email_send_failed", owner_id=str(owner.id), error=str(e))
        return Response({"detail": "If that email is registered, a reset link has been sent"})


class OwnerResetPasswordView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=OwnerResetPasswordSerializer, responses=DetailSerializer)
    def post(self, request):
        """Set a new password using the token from the password reset link.

        The token works once and expires after one hour by default. An invalid or
        expired token is refused with `400`; request a new link to try again.

        Args:
            token: The token from the password reset link. Required.
            new_password: The new password. Required.
        """
        serializer = OwnerResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        owner = Owner.objects.filter(
            password_reset_token_hash=hash_api_key(serializer.validated_data["token"])
        ).first()
        ttl = timedelta(hours=settings.PASSWORD_RESET_TTL_HOURS)
        if owner is None or owner.password_reset_sent_at is None or timezone.now() > owner.password_reset_sent_at + ttl:
            raise ValidationError({"token": ["Invalid or expired reset link, request a new one"]})
        try:
            validate_password(serializer.validated_data["new_password"], user=owner)
        except DjangoValidationError as e:
            raise ValidationError({"new_password": list(e.messages)})
        owner.set_password(serializer.validated_data["new_password"])
        owner.password_reset_token_hash = None
        owner.password_reset_sent_at = None
        owner.save(update_fields=["password", "password_reset_token_hash", "password_reset_sent_at"])
        return Response({"detail": "Password reset"})


def _get_owner_or_404(owner_id) -> Owner:
    try:
        return Owner.objects.get(pk=owner_id)
    except (Owner.DoesNotExist, ValueError, TypeError):
        raise NotFound("Owner not found")


def _delete_owner_cascading(owner: Owner) -> None:
    """Delete an owner along with their meshes, devices, blueprints and sinks.

    Their gateways are deregistered from the decoder and their sinks' credentials
    revoked first, and nothing is removed if that fails. Blueprints other owners'
    devices still use are kept without an owner.
    """
    blueprint_ids = list(owner.blueprints.values_list("id", flat=True))
    devices = Device.objects.filter(mesh__owner=owner)
    gateways = list(devices.filter(is_gateway=True, is_allowed=True))
    rejected_nodes = list(devices.filter(is_gateway=False, is_allowed=False))
    publisher = get_publisher()
    for gateway in gateways:
        try:
            publisher.publish_gateway_delete(gateway)
        except Exception as e:
            raise BadGateway(f"Failed to publish delete for device {gateway.id}, owner NOT removed: {e}")
    for node in rejected_nodes:
        try:
            publisher.publish_node_unreject(node)
        except Exception as e:
            raise BadGateway(f"Failed to publish unreject for device {node.id}, owner NOT removed: {e}")
    try:
        sinks.unpublish_devices(devices)
        sinks.unpublish_meshes(owner.meshes.all())
    except Exception as e:
        raise BadGateway(f"Failed to publish sink removal, owner NOT removed: {e}")
    try:
        # Last, since the broker cannot give a revoked password back.
        other_meshes, other_devices = sinks.revoke_owner_sinks(owner)
    except Exception as e:
        raise BadGateway(f"Failed to revoke the owner's sinks, owner NOT removed: {e}")
    processed = list(devices.filter(postprocessings__isnull=False).distinct())
    owner_id = str(owner.id)
    with transaction.atomic():
        meshes = list(owner.meshes.values_list("id", "source_id"))
        Sink.objects.filter(created_by=owner).delete()
        owner.delete()
        PostprocessingBlueprint.objects.filter(pk__in=blueprint_ids).exclude(
            versions__attachments__isnull=False
        ).delete()
        for mesh_id, source_id in meshes:
            schedule_mesh_deletion(mesh_id, DataDeletionReason.MESH_DELETED, source_id=source_id)
    postprocessing.unpublish_devices(processed)
    try:
        # Harmless if lost: the dispatcher sends nothing for a sink it no longer has.
        sinks.republish(other_meshes, other_devices)
    except Exception as e:
        log.warning("sink_detach_publish_failed", owner_id=owner_id, error=str(e))


class OwnerDetailView(APIView):
    """Return one owner.

    The full record comes back when the caller is the owner being requested, or
    a superuser. Everyone else gets the public fields only.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        responses=OpenApiResponse(
            response=OwnerPublicSerializer,
            description=(
                "The public fields shown here. The owner themselves and any "
                "superuser receive the full record."
            ),
        )
    )
    def get(self, request, owner_id):
        owner = _get_owner_or_404(owner_id)
        return Response(_owner_serializer_for(request, owner)(owner).data)

    @extend_schema(request=OwnerRoleSerializer, responses=OwnerReadSerializer)
    def put(self, request, owner_id):
        """Change an owner's role. Superusers only.

        Args:
            role: `member`, the default, or `operator`, which may also manage
                sources and archive devices. Granting `operator` also approves any
                pending operator request from this owner, without emailing them.
                Taking it away stops archiving the owner's devices, and the role
                is kept if the pipeline cannot be told.
        """
        _require_superuser(request)
        owner = _get_owner_or_404(owner_id)
        serializer = OwnerRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        previous_role = owner.role
        with transaction.atomic():
            owner.role = serializer.validated_data["role"]
            owner.save(update_fields=["role"])
            if owner.role == OwnerRole.OPERATOR:
                # A direct grant answers any request still waiting.
                owner.operator_requests.filter(status=OperatorRequestStatus.PENDING).update(
                    status=OperatorRequestStatus.APPROVED, decided_by=request.user, decided_at=timezone.now()
                )
        if owner.role != previous_role:
            try:
                sinks.publish_owner(owner)
            except Exception as e:
                if owner.role == OwnerRole.OPERATOR:
                    # A grant only re-enables archives the owner had before, so it stands.
                    log.warning("owner_sinks_publish_failed", owner_id=str(owner.id), error=str(e))
                else:
                    owner.role = previous_role
                    owner.save(update_fields=["role"])
                    raise BadGateway(f"Failed to stop archiving the owner's devices, role NOT changed: {e}")
        return Response(OwnerReadSerializer(owner).data)

    @extend_schema(responses={204: NO_CONTENT})
    def delete(self, request, owner_id):
        """Remove an owner, along with their meshes, devices, blueprints and sinks. Superusers only.

        Their gateways are deregistered from the decoder and the credentials of
        their sinks revoked first, and nothing is removed if that fails.
        Blueprints other owners' devices still use are kept without an owner,
        editable by superusers only.
        """
        _require_superuser(request)
        owner = _get_owner_or_404(owner_id)
        _delete_owner_cascading(owner)
        return Response(status=status.HTTP_204_NO_CONTENT)


class OwnerMeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OwnerProfileSerializer)
    def get(self, request):
        """Return the authenticated owner's own record, including their devices."""
        data = OwnerReadSerializer(request.user).data
        data["devices"] = _devices_for_owner(request.user)
        return Response(data)

    @extend_schema(request=OwnerUpdateSerializer, responses=OwnerReadSerializer)
    def put(self, request):
        """Update the authenticated owner's name, email address, or email preferences.

        Changing the email address deactivates the account until the new one
        is verified, and sends a fresh verification email.

        Args:
            alarm_email_cooldown_seconds: Length of a device's alarm window,
                in seconds. The first alarm on a device is emailed straight
                away; any further alarms on that device during the window are
                sent as one summary when it ends. Accepts 0 (email on every
                alarm, no summaries) up to 2592000 (30 days). Leave unset or
                null to use the server default.
            status_alerts_enabled: Email me when a source I created stays
                disconnected, or a sink I created with meshes or devices
                attached has nobody connected. Defaults to false.
            source_rate_alerts_enabled: Email me when a source I created
                averages more messages per second over an hour than this
                instance allows. Defaults to false. Superusers are always
                emailed about busy sources.
        """
        email_changing = "email" in request.data and request.data["email"] != request.user.email
        serializer = OwnerUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            owner = serializer.save()
        except IntegrityError:
            raise Conflict(f"Email {request.data.get('email')} already in use")
        if email_changing:
            verification_token = generate_api_key()
            owner.is_active = False
            owner.email_verified_at = None
            owner.email_verification_token_hash = hash_api_key(verification_token)
            owner.email_verification_sent_at = timezone.now()
            owner.save(
                update_fields=[
                    "is_active",
                    "email_verified_at",
                    "email_verification_token_hash",
                    "email_verification_sent_at",
                ]
            )
            try:
                send_verification_email(owner, verification_token)
            except Exception as e:
                # TODO - Evaluate if there is a place where failures can be visibly to user (for instance, a task manager UI)
                log.warning("verification_email_send_failed", owner_id=str(owner.id), error=str(e))
        return Response(OwnerReadSerializer(owner).data)

    @extend_schema(responses={204: NO_CONTENT})
    def delete(self, request):
        """Delete the authenticated owner, along with their meshes, devices, blueprints and sinks.

        Their gateways are deregistered from the decoder and the credentials of
        their sinks revoked first, and nothing is removed if that fails.
        Blueprints other owners' devices still use are kept without an owner,
        editable by superusers only.
        """
        _delete_owner_cascading(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class OwnerRotateKeyView(APIView):
    """Issue a new API key and revoke the previous one immediately.

    The new key is shown in this response and cannot be retrieved again.
    """

    permission_classes = [IsVerifiedOwner]

    @extend_schema(request=None, responses=OwnerWithApiKeySerializer)
    def post(self, request):
        new_api_key = generate_api_key()
        request.user.api_key_hash = hash_api_key(new_api_key)
        request.user.save(update_fields=["api_key_hash"])
        request.user.api_key = new_api_key
        return Response(OwnerWithApiKeySerializer(request.user).data)


class OwnerChangePasswordView(APIView):
    """Change the authenticated owner's password, confirming the current one first."""

    permission_classes = [IsVerifiedOwner]

    @extend_schema(request=OwnerChangePasswordSerializer, responses=DetailSerializer)
    def post(self, request):
        serializer = OwnerChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        owner = request.user
        if not owner.check_password(serializer.validated_data["current_password"]):
            raise ValidationError({"current_password": ["Incorrect password"]})
        try:
            validate_password(serializer.validated_data["new_password"], user=owner)
        except DjangoValidationError as e:
            raise ValidationError({"new_password": list(e.messages)})
        owner.set_password(serializer.validated_data["new_password"])
        owner.save(update_fields=["password"])
        return Response({"detail": "Password changed"})


def _devices_for_owner(owner: Owner) -> list[dict]:
    """Return the devices the given owner may access, or all of them for a superuser."""
    return DeviceReadSerializer(
        owner.visible_devices.select_related("mesh").prefetch_related("telemetry_variants").order_by("mesh_id", "device_id"),
        many=True,
        context={"viewer_id": owner.id, "viewer_is_superuser": owner.is_superuser},
    ).data


class OwnerDeviceIdsView(APIView):
    """List the devices the authenticated owner may access."""

    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=OwnerDevicesSerializer)
    def get(self, request):
        return Response({"devices": _devices_for_owner(request.user)})


def _get_mesh_or_404(mesh_id) -> Mesh:
    try:
        return Mesh.objects.get(pk=mesh_id)
    except (Mesh.DoesNotExist, ValueError, TypeError):
        raise NotFound("Mesh not found")


def _require_mesh_ownership(mesh: Mesh, owner: Owner) -> None:
    if not owner.can_edit_mesh(mesh):
        raise PermissionDenied("You do not own this mesh")


def _require_mesh_visible(mesh: Mesh, user) -> None:
    """404 rather than 403, so a private mesh doesn't confirm its own existence."""
    if not can_view_mesh(user, mesh):
        raise NotFound("Mesh not found")


def _hide_rejected_from_viewers(qs, owner: Owner):
    """A rejected registration is the mesh owner's business, not a viewer's."""
    if owner.is_superuser:
        return qs
    return qs.filter(Q(mesh__owner_id=owner.id) | Q(is_allowed=True))


def _get_device_or_404(device_uuid) -> Device:
    try:
        return Device.objects.select_related("mesh").get(pk=device_uuid)
    except (Device.DoesNotExist, ValueError, TypeError):
        raise NotFound("Device not found")


class MeshListCreateView(APIView):
    permission_classes = [ReadOnlyOrVerifiedOwner]

    @extend_schema(parameters=MESH_FILTER_PARAMS, responses=MeshSerializer(many=True))
    def get(self, request):
        """List the meshes the caller may read, or every mesh for a superuser.

        Alongside their own, this includes public meshes. Without credentials,
        only public meshes are listed. The pre-shared key, the source and the
        terms status are included only for meshes the caller owns.

        Args:
            owned: Restrict to meshes the caller owns. Defaults to false.
            source_id: Restrict to meshes bridged from one source. Matches
                only meshes the caller owns, or any mesh for a superuser.
        """
        qs = visible_meshes_for(request.user)
        if request.query_params.get("owned", "").lower() in ("true", "1"):
            qs = qs.filter(owner_id=request.user.id)
        source_id = request.query_params.get("source_id")
        if source_id:
            try:
                qs = qs.filter(source_id=source_id)
            except (ValueError, DjangoValidationError):
                raise ValidationError({"source_id": "Must be a UUID."})
            # The source is hidden from viewers, so the filter must not reveal it either.
            if not request.user.is_superuser:
                qs = qs.filter(owner_id=request.user.id)
        return Response(MeshSerializer(qs, many=True, context=_viewer_context(request)).data)

    @extend_schema(request=MeshSerializer, responses={201: MeshSerializer})
    def post(self, request):
        """Create a mesh owned by the caller.

        A mesh on the default broker needs its mesh terms accepted, which are
        recorded with it. A mesh on a source is covered by the source's terms.

        Args:
            source_id: Source the mesh's traffic is bridged from, which must be
                one the caller created, or any source for a superuser. Leave
                unset for traffic on this instance's own broker.
            discover_gateways: Register gateways automatically once one of their
                packets decodes with this mesh's channel and pre-shared key.
                Defaults to `false`. Only an operator may switch it on for a mesh
                with a default or blank key.
            terms_version: The `version` of the mesh terms accepted. Required
                without a source, ignored with one, and ignored on an instance
                that does not enforce terms.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """
        serializer = MeshSerializer(data=request.data, context={"owner": request.user})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            mesh = serializer.save(owner=request.user)
            if serializer.accept_terms_locale:
                record_acceptance(TermsKind.MESH, request.user, serializer.accept_terms_locale, mesh=mesh)
        return Response(
            MeshSerializer(mesh, context=_viewer_context(request)).data, status=status.HTTP_201_CREATED
        )


def _viewer_context(request) -> dict:
    return {"viewer_id": request.user.id, "viewer_is_superuser": request.user.is_superuser}


def _publish_mesh_gateways(mesh: Mesh, previous: dict) -> None:
    """Republish every allowed gateway on the mesh, restoring `previous` on failure.

    Gateways already republished are sent the restored values again, so the
    decoder does not keep the new ones for part of the mesh.
    """
    publisher = get_publisher()
    published = []
    for gateway in mesh.devices.filter(is_gateway=True, is_allowed=True):
        try:
            publish_gateway_state(publisher, gateway, mesh)
        except Exception as e:
            for field, value in previous.items():
                setattr(mesh, field, value)
            mesh.save(update_fields=list(previous))
            for done in published:
                try:
                    publish_gateway_state(publisher, done, mesh)
                except Exception as restore_error:
                    log.error("gateway_restore_failed", device_id=str(done.id), error=str(restore_error))
            raise BadGateway(f"Failed to publish mesh change, rolled back: {e}")
        published.append(gateway)


class MeshDetailView(APIView):
    permission_classes = [ReadOnlyOrVerifiedOwner]

    @extend_schema(responses=MeshSerializer)
    def get(self, request, mesh_id):
        """Return one mesh.

        A public mesh is readable without credentials. The pre-shared key, the
        source and the terms status are included only for the mesh's owner.
        """
        mesh = _get_mesh_or_404(mesh_id)
        _require_mesh_visible(mesh, request.user)
        return Response(MeshSerializer(mesh, context=_viewer_context(request)).data)

    @extend_schema(request=MeshUpdateSerializer, responses=MeshSerializer)
    def put(self, request, mesh_id):
        """Update a mesh.

        Changing the channel_id, the pre-shared key or the source redistributes
        them to every allowed gateway on the mesh, and the whole update is
        rolled back if that fails. Once the source changes, the mesh's gateways
        are only accepted through the new one.

        Args:
            source_id: Source to bridge the mesh's traffic from, which must be one
                the caller created, or any source for a superuser, and not paused.
                Null moves it to the default broker. Moving a mesh off a source
                schedules the readings stored until then for deletion after the
                grace period; moving it back within that period cancels it.
            discover_gateways: Register gateways automatically once one of their
                packets decodes with this mesh's channel and pre-shared key. A
                gateway is skipped when another mesh shares the same source,
                channel and key, when it is registered elsewhere, or when it was
                rejected on this mesh. Switching it off keeps the gateways
                already found. Only an operator may switch it on for a mesh with
                a default or blank key.
            terms_version: The `version` of the mesh terms accepted. Required when
                moving the mesh onto the default broker unless it already holds a
                current acceptance, or the instance does not enforce terms;
                ignored otherwise.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """
        mesh = _get_mesh_or_404(mesh_id)
        _require_mesh_ownership(mesh, request.user)
        redistributed = ("channel_id", "psk_b64", "source_id")
        changing_gateway_state = any(field in request.data for field in redistributed)
        previous = {"channel_id": mesh.channel_id, "psk_b64": mesh.psk_b64, "source_id": mesh.source_id}
        serializer = MeshUpdateSerializer(mesh, data=request.data, partial=True, context={"owner": request.user})
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        accept_locale = serializer.accept_terms_locale
        was_paused = updated.paused_at is not None
        if accept_locale:
            # Accepting the terms resumes a mesh paused by an earlier lapse, so its gateways
            # are published as registered below.
            updated.paused_at = None
        if changing_gateway_state:
            _publish_mesh_gateways(updated, previous)
        if accept_locale:
            with transaction.atomic():
                if was_paused:
                    updated.save(update_fields=["paused_at"])
                    cancel_mesh_deletions([updated.id], DataDeletionReason.TERMS_LAPSED, None)
                record_acceptance(TermsKind.MESH, request.user, accept_locale, mesh=updated)
        old_source, new_source = previous["source_id"], updated.source_id
        if old_source != new_source:
            if old_source is not None:
                # Readings bridged so far belonged to the old source's service.
                schedule_mesh_deletion(
                    updated.id,
                    DataDeletionReason.SOURCE_DETACHED,
                    source_id=old_source,
                    requested_by=request.user,
                    data_until=timezone.now(),
                )
            if new_source is not None:
                cancel_mesh_deletions([updated.id], DataDeletionReason.SOURCE_DETACHED, new_source)
        return Response(MeshSerializer(updated, context=_viewer_context(request)).data)

    @extend_schema(responses={204: NO_CONTENT})
    def delete(self, request, mesh_id):
        """Delete a mesh and every device registered on it.

        Its gateways are deregistered from the decoder first, and nothing is
        removed if that fails. The mesh's stored readings are deleted after the
        grace period, so export them first if they are needed.
        """
        mesh = _get_mesh_or_404(mesh_id)
        _require_mesh_ownership(mesh, request.user)
        gateways = list(mesh.devices.filter(is_gateway=True, is_allowed=True))
        rejected_nodes = list(mesh.devices.filter(is_gateway=False, is_allowed=False))
        publisher = get_publisher()
        for gateway in gateways:
            try:
                publisher.publish_gateway_delete(gateway)
            except Exception as e:
                raise BadGateway(f"Failed to publish delete for device {gateway.id}, mesh NOT removed: {e}")
        for node in rejected_nodes:
            try:
                publisher.publish_node_unreject(node)
            except Exception as e:
                raise BadGateway(f"Failed to publish unreject for device {node.id}, mesh NOT removed: {e}")
        try:
            sinks.unpublish_devices(mesh.devices.all())
            sinks.unpublish_meshes([mesh])
        except Exception as e:
            raise BadGateway(f"Failed to publish sink removal, mesh NOT removed: {e}")
        processed = list(mesh.devices.filter(postprocessings__isnull=False).distinct())
        with transaction.atomic():
            mesh_id, source_id = mesh.id, mesh.source_id
            mesh.delete()
            schedule_mesh_deletion(
                mesh_id, DataDeletionReason.MESH_DELETED, source_id=source_id, requested_by=request.user
            )
        postprocessing.unpublish_devices(processed)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _filter_by_telemetry_variants(devices, raw: str | None):
    """Apply the `telemetry_variant` query parameter, raising a 400 when it is malformed."""
    if not raw:
        return devices
    operator, _, values = raw.rpartition(":")
    operator = operator or "has_any_of"
    if operator not in ("has_any_of", "has_all_of", "has_none_of"):
        raise ValidationError({"telemetry_variant": "Operator must be has_any_of, has_all_of or has_none_of."})
    try:
        variant_ids = {uuid.UUID(value) for value in values.split("|")}
    except ValueError:
        raise ValidationError({"telemetry_variant": "Each value must be a telemetry variant id."})

    def reporting(ids):
        return DeviceTelemetryVariant.objects.filter(telemetry_variant_id__in=ids).values("device_id")

    if operator == "has_any_of":
        return devices.filter(id__in=reporting(variant_ids))
    if operator == "has_none_of":
        return devices.exclude(id__in=reporting(variant_ids))
    for variant_id in variant_ids:
        devices = devices.filter(id__in=reporting([variant_id]))
    return devices


class MeshDevicesView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(parameters=[TELEMETRY_VARIANT_FILTER_PARAM], responses=DeviceReadSerializer(many=True))
    def get(self, request, mesh_id):
        """List every device registered on this mesh, gateways and nodes alike.

        A public mesh's devices are readable without credentials. Rejected
        registrations and admin keys are shown only to the mesh's owner.

        Args:
            telemetry_variant: Restrict by reported telemetry variants, as
                `has_any_of`, `has_all_of` or `has_none_of` followed by `:` and
                variant ids separated by `|`. Bare ids mean `has_any_of`.
        """
        mesh = _get_mesh_or_404(mesh_id)
        _require_mesh_visible(mesh, request.user)
        devices = mesh.devices.select_related("mesh").prefetch_related("telemetry_variants")
        if not can_edit_mesh(request.user, mesh):
            devices = devices.filter(is_allowed=True)
        devices = _filter_by_telemetry_variants(devices, request.query_params.get("telemetry_variant"))
        return Response(
            DeviceReadSerializer(devices, many=True, context=_viewer_context(request)).data
        )


LINK_WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
TRACEROUTE_PAGE = 50
TRACEROUTE_PAGE_MAX = 500


def _node_filter(request) -> int | None:
    raw = request.query_params.get("node_id")
    if raw in (None, ""):
        return None
    parsed = node_ids.to_num(raw) if str(raw).startswith("!") else None
    if parsed is None:
        try:
            parsed = int(raw)
        except ValueError:
            raise ValidationError({"node_id": ["Expected a node number or its !aabbccdd form."]})
    return parsed


def _mesh_positions(mesh: Mesh, user) -> dict[int, tuple[str, tuple[float, float] | None]]:
    """Registration ID and position of each device the caller may see on the mesh."""
    devices = mesh.devices.all()
    if not can_edit_mesh(user, mesh):
        devices = devices.filter(is_allowed=True)
    return {
        device_id: (str(pk), (lat, lon) if lat is not None and lon is not None else None)
        for device_id, pk, lat, lon in devices.values_list("device_id", "id", "latitude", "longitude")
    }


class MeshLinksView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[
            _query("since", "How far back a link must have been heard.", enum=list(LINK_WINDOWS), default="7d"),
            _query("node_id", "Only links to or from this node, as a number or in its `!aabbccdd` form."),
        ],
        responses=RfLinkSerializer(many=True),
    )
    def get(self, request, mesh_id):
        """List the radio links heard on this mesh, longest first.

        A link is one node heard by another, as one source reports it:
        `traceroute` hops, `neighborinfo` reports, or `direct` receptions by a
        gateway with no hop in between. Each is directional, since the SNR is
        measured by the receiving node, so a pair heard both ways has two links.
        Direct links are added once an hour. Links not heard for 30 days are
        deleted. A public mesh's links are readable without credentials.

        Args:
            since: How far back a link must have been heard, one of `24h`, `7d`
                or `30d`. Defaults to `7d`.
            node_id: Only links to or from this node.
        """
        mesh = _get_mesh_or_404(mesh_id)
        _require_mesh_visible(mesh, request.user)
        window = LINK_WINDOWS.get(request.query_params.get("since", "7d"))
        if window is None:
            raise ValidationError({"since": [f"Expected one of {', '.join(LINK_WINDOWS)}."]})
        links = mesh.rf_links.filter(last_seen__gte=timezone.now() - window)
        node = _node_filter(request)
        if node is not None:
            links = links.filter(Q(from_node=node) | Q(to_node=node))
        known = _mesh_positions(mesh, request.user)
        body = []
        for link in links:
            src, dst = known.get(link.from_node), known.get(link.to_node)
            body.append(
                {
                    "from_node": link.from_node,
                    "to_node": link.to_node,
                    "from_device_uuid": src[0] if src else None,
                    "to_device_uuid": dst[0] if dst else None,
                    "source": link.source,
                    "samples": link.samples,
                    "snr_mean": link.snr_sum / link.samples if link.samples else 0.0,
                    "last_snr": link.last_snr,
                    "first_seen": link.first_seen,
                    "last_seen": link.last_seen,
                    "distance_km": distance_km(src and src[1], dst and dst[1]),
                }
            )
        body.sort(key=lambda row: (row["distance_km"] is None, -(row["distance_km"] or 0), -row["samples"]))
        return Response(RfLinkSerializer(body, many=True).data)


class MeshTraceroutesView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[
            _query("limit", "How many to return.", OpenApiTypes.INT, default=TRACEROUTE_PAGE),
            _query("before", "Only traceroutes heard before this time, for the next page."),
            _query("node_id", "Only traceroutes through, from or to this node."),
        ],
        responses=TracerouteSerializer(many=True),
    )
    def get(self, request, mesh_id):
        """List the traceroutes heard on this mesh, newest first.

        A traceroute heard by several gateways is listed once, with the most
        complete route any of them saw. `towards` runs from the node that started
        the traceroute to its target and `back` returns; each SNR is the one
        measured on arriving at the next node. A reply carries both directions,
        a request only the hops taken so far. Traceroutes are kept 30 days. A
        public mesh's traceroutes are readable without credentials.

        Args:
            limit: How many to return, up to 500. Defaults to 50.
            before: Only traceroutes heard before this time, as an ISO 8601
                timestamp. Pass the `heard_at` of the last one received to read
                the next page.
            node_id: Only traceroutes from, to or through this node.
        """
        mesh = _get_mesh_or_404(mesh_id)
        _require_mesh_visible(mesh, request.user)
        try:
            limit = min(int(request.query_params.get("limit", TRACEROUTE_PAGE)), TRACEROUTE_PAGE_MAX)
        except ValueError:
            raise ValidationError({"limit": ["Expected a number."]})
        traceroutes = mesh.traceroutes.order_by("-heard_at", "-id")
        before = request.query_params.get("before")
        if before:
            try:
                traceroutes = traceroutes.filter(heard_at__lt=datetime.fromisoformat(before.replace("Z", "+00:00")))
            except ValueError:
                raise ValidationError({"before": ["Expected an ISO 8601 timestamp."]})
        node = _node_filter(request)
        known = _mesh_positions(mesh, request.user)
        body = []
        for traceroute in traceroutes.iterator():
            paths = traceroute_paths(topology.as_event(traceroute))
            nodes = set(paths["towards"]) | set(paths["back"])
            if node is not None and node not in nodes:
                continue
            body.append(_traceroute_row(traceroute, paths, known))
            if len(body) >= limit:
                break
        return Response(TracerouteSerializer(body, many=True).data)


def _traceroute_row(traceroute: Traceroute, paths: dict, known: dict) -> dict:
    towards = paths["towards"]
    positions = [known.get(n, (None, None))[1] for n in towards]
    hops = [distance_km(a, b) for a, b in zip(positions, positions[1:])]
    return {
        "id": traceroute.id,
        "from_node": traceroute.from_node,
        "to_node": traceroute.to_node,
        "packet_id": traceroute.packet_id,
        "request_id": traceroute.request_id,
        "origin": paths["origin"],
        "target": paths["target"],
        "towards": towards,
        "snr_towards": paths["snr_towards"],
        "back": paths["back"],
        "snr_back": paths["snr_back"],
        "complete": bool(towards) and towards[-1] == paths["target"],
        "gateway_ids": traceroute.gateway_ids,
        "heard_at": traceroute.heard_at,
        "distance_km": sum(hops) if hops and None not in hops else None,
    }


class DeviceListCreateView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(parameters=DEVICE_FILTER_PARAMS, responses=DeviceReadSerializer(many=True))
    def get(self, request):
        """List the devices the caller may read, or every device for a superuser.

        Alongside devices on their own meshes, this includes those on public
        meshes. Rejected registrations are shown only to the mesh's owner.

        Args:
            mesh_id: Restrict to devices on one mesh.
            is_gateway: Restrict to gateways, or to plain nodes when false.
            is_allowed: Restrict to allowed registrations, or to rejected ones
                when false.
            has_postprocessing: Restrict to devices with a postprocessing
                attached, or to those without one when false.
            telemetry_variant: Restrict by reported telemetry variants, as
                `has_any_of`, `has_all_of` or `has_none_of` followed by `:` and
                variant ids separated by `|`. Bare ids mean `has_any_of`.
        """
        qs = Device.objects.select_related("mesh").prefetch_related("telemetry_variants")
        qs = qs.all() if request.user.is_superuser else qs.filter(mesh__in=request.user.visible_meshes)
        qs = _hide_rejected_from_viewers(qs, request.user)
        mesh_id = request.query_params.get("mesh_id")
        if mesh_id:
            qs = qs.filter(mesh_id=mesh_id)
        for flag in ("is_gateway", "is_allowed"):
            value = request.query_params.get(flag)
            if value is not None:
                qs = qs.filter(**{flag: value.lower() in ("true", "1")})
        has_postprocessing = request.query_params.get("has_postprocessing")
        if has_postprocessing is not None:
            with_any = DevicePostprocessing.objects.values("device_id")
            qs = qs.filter(id__in=with_any) if has_postprocessing.lower() in ("true", "1") else qs.exclude(id__in=with_any)
        qs = _filter_by_telemetry_variants(qs, request.query_params.get("telemetry_variant"))
        return Response(DeviceReadSerializer(qs, many=True, context=_viewer_context(request)).data)

    @extend_schema(request=DeviceCreateSerializer, responses={201: DeviceReadSerializer})
    def post(self, request):
        """Register a device on a mesh the caller owns.

        Registering a gateway authorizes its traffic to be decoded. A
        device can only move to another mesh once its current registration has
        been disallowed.
        """
        input_serializer = DeviceCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data
        mesh = _get_mesh_or_404(data["mesh_id"])
        _require_mesh_ownership(mesh, request.user)
        device = Device(
            device_id=data["device_id"],
            mesh=mesh,
            is_gateway=data["is_gateway"],
            label=data.get("label"),
            admin_keys_b64=data.get("admin_keys_b64", []),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            location_overridden=data.get("latitude") is not None,
            name=data.get("name"),
            short_name=data.get("short_name"),
            hardware_type=data.get("hardware_type"),
            role=data.get("role"),
            nodeinfo_overridden=any(
                data.get(f) for f in ("name", "short_name", "hardware_type", "role")
            ),
        )
        try:
            if device.is_gateway:
                save_gateway(device)
            else:
                device.save()
        except IntegrityError:
            raise Conflict(f"Device with device_id {data['device_id']} already has an allowed registration")
        return Response(
            DeviceReadSerializer(device, context=_viewer_context(request)).data,
            status=status.HTTP_201_CREATED,
        )


class DeviceDetailView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=DeviceReadSerializer)
    def get(self, request, device_uuid):
        """Return one registered device.

        Rejected registrations are visible only to the mesh's owner.
        """
        device = _get_device_or_404(device_uuid)
        _require_mesh_visible(device.mesh, request.user)
        if not device.is_allowed and not request.user.can_edit_mesh(device.mesh):
            raise NotFound("Device not found")
        return Response(DeviceReadSerializer(device, context=_viewer_context(request)).data)

    @extend_schema(request=DeviceUpdateSerializer, responses=DeviceReadSerializer)
    def put(self, request, device_uuid):
        """Update a registered device.

        Position and identity fields are filled in from what the device reports
        until they are set here, after which the values given take precedence.
        Disallowing a gateway stops its traffic being decoded.

        `archive_enabled` stores the device's readings in the Parquet archive from
        then on. It is accepted only on a mesh owned by an operator and on
        instances that run the archive. Turning it off stops storing new readings
        and keeps those already stored.

        Nothing in the request is applied if the pipeline cannot be told about a
        change to `archive_enabled` or `is_allowed`.
        """
        device = _get_device_or_404(device_uuid)
        _require_mesh_ownership(device.mesh, request.user)
        changing_allowed = "is_allowed" in request.data
        previous_allowed = device.is_allowed
        previous_archive = device.archive_enabled
        location_keys_present = "latitude" in request.data and "longitude" in request.data
        nodeinfo_fields = ("name", "short_name", "hardware_type", "role")
        nodeinfo_keys_present = any(k in request.data for k in nodeinfo_fields)
        nodeinfo_keys_all_present = all(k in request.data for k in nodeinfo_fields)

        serializer = DeviceUpdateSerializer(
            device, data=request.data, partial=True, context={"archive_available": sinks.archive_available()}
        )
        serializer.is_valid(raise_exception=True)
        sinks_published = False
        try:
            with transaction.atomic():
                updated = serializer.save()

                override_fields = []
                if location_keys_present:
                    pinned = updated.latitude is not None or updated.longitude is not None
                    if updated.location_overridden != pinned:
                        updated.location_overridden = pinned
                        override_fields.append("location_overridden")
                if nodeinfo_keys_present:
                    cleared = nodeinfo_keys_all_present and all(getattr(updated, f) is None for f in nodeinfo_fields)
                    pinned = not cleared
                    if updated.nodeinfo_overridden != pinned:
                        updated.nodeinfo_overridden = pinned
                        override_fields.append("nodeinfo_overridden")
                if override_fields:
                    updated.save(update_fields=override_fields)

                archive_changed = updated.archive_enabled != previous_archive
                if archive_changed:
                    try:
                        sinks.publish_device(updated)
                    except Exception as e:
                        raise BadGateway(f"Failed to publish the archive setting, nothing changed: {e}")
                    sinks_published = True

                allowed_changed = changing_allowed and updated.is_allowed != previous_allowed
                if allowed_changed:
                    publisher = get_publisher()
                    try:
                        if updated.is_gateway:
                            if updated.is_allowed:
                                publish_gateway_state(publisher, updated, updated.mesh)
                            else:
                                publisher.publish_gateway_delete(updated)
                        elif updated.is_allowed:
                            publisher.publish_node_unreject(updated)
                        else:
                            publisher.publish_node_reject(updated)
                    except Exception as e:
                        action = "allow" if updated.is_allowed else "reject"
                        raise BadGateway(f"Failed to publish device {action}, nothing changed: {e}")
        except IntegrityError:
            raise Conflict(f"Device with device_id {device.device_id} already has an allowed registration")
        except BadGateway:
            if sinks_published:
                # The pipeline already holds the new archive setting; send it the restored one.
                try:
                    sinks.publish_device(_get_device_or_404(device_uuid))
                except Exception as e:
                    log.error("device_sinks_restore_failed", device_id=str(device_uuid), error=str(e))
            raise

        if archive_changed:
            sinks.record_archive_instruction(updated, request.user)

        if any(
            k in request.data
            for k in ("reading_interval_seconds", "publish_interval_seconds", "absence_detection_enabled")
        ):
            # Carries the absence switch as well as the intervals.
            try:
                get_publisher().publish_device_intervals(updated)
            except Exception as e:
                log.warning("device_intervals_publish_failed", device_id=str(updated.id), error=str(e))

        if "reading_interval_seconds" in request.data and updated.postprocessings.filter(
            is_enabled=True, tolerance_seconds__isnull=True
        ).exists():
            # Their join tolerance follows the reading interval.
            try:
                postprocessing.publish_device(updated)
            except Exception as e:
                log.warning("postprocessing_publish_failed", device_id=str(updated.id), error=str(e))

        if allowed_changed and not archive_changed and (updated.archive_enabled or updated.sink_links.exists()):
            # Only an allowed registration is sent to a sink.
            try:
                sinks.publish_device(updated)
            except Exception as e:
                log.warning("device_sinks_publish_failed", device_id=str(updated.id), error=str(e))
        return Response(DeviceReadSerializer(updated, context=_viewer_context(request)).data)

    @extend_schema(responses={204: NO_CONTENT})
    def delete(self, request, device_uuid):
        """Delete a device registration.

        The device is deregistered from the decoder first, and the record is
        kept if that fails.
        """
        device = _get_device_or_404(device_uuid)
        _require_mesh_ownership(device.mesh, request.user)
        publisher = get_publisher()
        try:
            if device.is_gateway and device.is_allowed:
                publisher.publish_gateway_delete(device)
            elif not device.is_gateway and not device.is_allowed:
                publisher.publish_node_unreject(device)
            sinks.unpublish_devices([device])
        except Exception as e:
            raise BadGateway(f"Failed to publish device deletion, device NOT removed: {e}")
        had_postprocessing = device.postprocessings.exists()
        device.delete()
        if had_postprocessing:
            postprocessing.unpublish_devices([device])
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeviceTelemetryVariantsView(APIView):
    """List the telemetry types this device has been seen reporting.

    Entries appear on their own as telemetry arrives and cannot be edited here.
    """

    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=DeviceTelemetryVariantSerializer(many=True))
    def get(self, request, device_uuid):
        device = _get_device_or_404(device_uuid)
        _require_mesh_visible(device.mesh, request.user)
        variants = device.telemetry_variants.select_related("telemetry_variant")
        return Response(DeviceTelemetryVariantSerializer(variants, many=True).data)


class DeviceMeasurementsView(APIView):
    """List the measurement channels this device produces, measured and computed alike.

    Entries appear on their own as telemetry arrives. `enabled_detectors` is set by
    this device and may be null; `effective_detectors` is the result once
    the shared catalog default is applied.
    """

    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=DeviceMeasurementSerializer(many=True))
    def get(self, request, device_uuid):
        device = _get_device_or_404(device_uuid)
        _require_mesh_visible(device.mesh, request.user)
        measurements = list(
            Measurement.objects.filter(device_telemetry_variant__device=device)
            .select_related("measurement_type", "device_telemetry_variant")
            .order_by("measurement_type__payload_kind", "measurement_type__field_name")
        )
        return Response(
            DeviceMeasurementSerializer(
                measurements, many=True, context={"catalog_defaults": catalog_defaults_for(measurements)}
            ).data
        )


def _get_device_measurement_or_404(device, measurement_id) -> Measurement:
    try:
        return Measurement.objects.select_related("measurement_type", "device_telemetry_variant").get(
            pk=measurement_id, device_telemetry_variant__device=device
        )
    except (Measurement.DoesNotExist, ValueError, TypeError):
        raise NotFound("Measurement not found on this device")


class DeviceMeasurementDetailView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=DeviceMeasurementSerializer)
    def get(self, request, device_uuid, measurement_id):
        """Return one of this device's measurement channels."""
        device = _get_device_or_404(device_uuid)
        _require_mesh_visible(device.mesh, request.user)
        measurement = _get_device_measurement_or_404(device, measurement_id)
        return Response(DeviceMeasurementSerializer(measurement).data)

    @extend_schema(request=DeviceMeasurementUpdateSerializer, responses=DeviceMeasurementSerializer)
    def put(self, request, device_uuid, measurement_id):
        """Choose which detectors alarm on this channel, and the range they
        check against, for this device.

        Alarms are off until enabled. Sending `null` for enabled_detectors
        inherits whatever the shared catalog sets for the channel; sending an
        empty list silences it here regardless of that default. valid_min/
        valid_max have no catalog default: the range detector remains off
        until both are set here.

        Args:
            enabled_detectors: Detectors to run, or `null` to inherit.
            valid_min: Lower bound for the range detector. Must be provided together with valid_max.
            valid_max: Upper bound for the range detector. Must be provided together with valid_min.
        """
        device = _get_device_or_404(device_uuid)
        _require_mesh_ownership(device.mesh, request.user)
        measurement = _get_device_measurement_or_404(device, measurement_id)
        serializer = DeviceMeasurementUpdateSerializer(measurement, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        _publish_measurement_alarms(device, updated)
        return Response(DeviceMeasurementSerializer(updated).data)


def _publish_measurement_alarms(device, measurement) -> None:
    """Best-effort: a failed publish must not fail the API write."""
    try:
        get_publisher().publish_measurement_alarms(device, measurement)
    except Exception as e:
        log.warning("measurement_alarms_publish_failed", measurement_id=str(measurement.id), error=str(e))


def _require_operator(request, what: str = "sources") -> None:
    if not request.user.is_authenticated:
        raise AuthenticationFailed()
    if not IsOperator().has_permission(request, None):
        raise PermissionDenied(f"Only an operator may access {what}")


def _require_superuser(request) -> None:
    if not request.user.is_authenticated:
        raise AuthenticationFailed()
    if not IsSuperuser().has_permission(request, None):
        raise PermissionDenied("Only a superuser may modify this")


def filter_measurement_types(qs, request):
    kind = request.query_params.get("kind")
    if kind:
        # Every payload_kind is "<namespace>:<measurement>", so kind is the namespace.
        qs = qs.filter(payload_kind__startswith=f"{kind}:")
    payload_kind = request.query_params.get("payload_kind")
    if payload_kind:
        qs = qs.filter(payload_kind=payload_kind)
    field_name = request.query_params.get("field_name")
    if field_name:
        qs = qs.filter(field_name=field_name)
    return qs


def _get_measurement_type_or_404(measurement_id) -> MeasurementType:
    try:
        return MeasurementType.objects.get(pk=measurement_id)
    except (MeasurementType.DoesNotExist, ValueError, TypeError):
        raise NotFound("MeasurementType not found")


def _get_telemetry_variant_or_404(telemetry_variant_id) -> TelemetryVariant:
    try:
        return TelemetryVariant.objects.get(pk=telemetry_variant_id)
    except (TelemetryVariant.DoesNotExist, ValueError, TypeError):
        raise NotFound("TelemetryVariant not found")


class MeasurementTypeListCreateView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(parameters=MEASUREMENT_FILTER_PARAMS, responses=MeasurementTypeReadSerializer(many=True))
    def get(self, request):
        """List the shared catalog of measurement types and their units.

        Sensor fields are named `telemetry:<variant>`. Blueprint outputs from
        every postprocessing share `computed:derived`, and data quality metrics
        use `computed:quality`.

        Args:
            kind: Restrict to one namespace, one of `telemetry`, `device` or
                `computed`.
            payload_kind: Restrict to one exact payload kind, such as
                `telemetry:environment_metrics`.
            field_name: Restrict to one field name, such as `temperature`.
        """
        return Response(
            MeasurementTypeReadSerializer(filter_measurement_types(MeasurementType.objects.all(), request), many=True).data
        )

    @extend_schema(request=MeasurementTypeCreateSerializer, responses={201: MeasurementTypeReadSerializer})
    def post(self, request):
        """Add a measurement type to the shared catalog. Superusers only."""
        _require_superuser(request)
        serializer = MeasurementTypeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            measurement_type = serializer.save()
        except IntegrityError:
            raise Conflict(
                f"MeasurementType for {serializer.validated_data['payload_kind']}:"
                f"{serializer.validated_data['field_name']} already exists"
            )
        return Response(MeasurementTypeReadSerializer(measurement_type).data, status=status.HTTP_201_CREATED)


class MeasurementTypeDetailView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=MeasurementTypeReadSerializer)
    def get(self, request, measurement_id):
        """Return one measurement type."""
        return Response(MeasurementTypeReadSerializer(_get_measurement_type_or_404(measurement_id)).data)

    @extend_schema(request=MeasurementTypeUpdateSerializer, responses=MeasurementTypeReadSerializer)
    def put(self, request, measurement_id):
        """Update a measurement type. Its payload kind and field name are fixed. Superusers only."""
        _require_superuser(request)
        measurement_type = _get_measurement_type_or_404(measurement_id)
        serializer = MeasurementTypeUpdateSerializer(measurement_type, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        return Response(MeasurementTypeReadSerializer(updated).data)

    @extend_schema(responses={204: NO_CONTENT})
    def delete(self, request, measurement_id):
        """Remove a measurement type from the catalog. Superusers only."""
        _require_superuser(request)
        _get_measurement_type_or_404(measurement_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TelemetryVariantListCreateView(APIView):
    """List the known telemetry variants, such as device or environment metrics.

    Variants are registered automatically as devices report them, so there is
    no way to create one here.
    """

    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=TelemetryVariantReadSerializer(many=True))
    def get(self, request):
        return Response(TelemetryVariantReadSerializer(TelemetryVariant.objects.all(), many=True).data)


class TelemetryVariantDetailView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=TelemetryVariantReadSerializer)
    def get(self, request, telemetry_variant_id):
        """Return one telemetry variant."""
        return Response(TelemetryVariantReadSerializer(_get_telemetry_variant_or_404(telemetry_variant_id)).data)

    @extend_schema(request=TelemetryVariantUpdateSerializer, responses=TelemetryVariantReadSerializer)
    def put(self, request, telemetry_variant_id):
        """Update a telemetry variant. Its payload kind is fixed. Superusers only.

        The expected reading interval set here is used to judge whether devices
        reporting this variant are publishing as often as they should.
        """
        _require_superuser(request)
        telemetry_variant = _get_telemetry_variant_or_404(telemetry_variant_id)
        serializer = TelemetryVariantUpdateSerializer(telemetry_variant, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        # default_reading_interval_seconds lives on the variant but is used
        # per-channel, so one edit re-publishes every field under it.
        _publish_quality_config(updated.measurement_links.select_related("measurement_type", "telemetry_variant"))
        return Response(TelemetryVariantReadSerializer(updated).data)

    @extend_schema(responses={204: NO_CONTENT})
    def delete(self, request, telemetry_variant_id):
        """Delete a telemetry variant. Superusers only."""
        _require_superuser(request)
        _get_telemetry_variant_or_404(telemetry_variant_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TelemetryVariantMeasurementsView(APIView):
    """List the measurement types reported under this telemetry variant."""

    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=TelemetryVariantMeasurementReadSerializer(many=True))
    def get(self, request, telemetry_variant_id):
        telemetry_variant = _get_telemetry_variant_or_404(telemetry_variant_id)
        links = telemetry_variant.measurement_links.select_related("measurement_type").all()
        return Response(TelemetryVariantMeasurementReadSerializer(links, many=True).data)


def _publish_quality_config(links) -> None:
    """Best-effort: a failed publish must not fail the API write."""
    publisher = get_publisher()
    for link in links:
        try:
            publisher.publish_variant_measurement_config(link)
        except Exception as e:
            log.warning("quality_config_publish_failed", link_id=str(link.id), error=str(e))


def _get_telemetry_variant_measurement_or_404(telemetry_variant_id, link_id) -> TelemetryVariantMeasurement:
    """Scoped to the parent, so a link id from another variant is a 404 rather than an edit."""
    try:
        return TelemetryVariantMeasurement.objects.get(pk=link_id, telemetry_variant_id=telemetry_variant_id)
    except (TelemetryVariantMeasurement.DoesNotExist, ValueError, TypeError):
        raise NotFound("Measurement not found on this telemetry variant")


class TelemetryVariantMeasurementDetailView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=TelemetryVariantMeasurementReadSerializer)
    def get(self, request, telemetry_variant_id, link_id):
        """Return one measurement channel."""
        link = _get_telemetry_variant_measurement_or_404(telemetry_variant_id, link_id)
        return Response(TelemetryVariantMeasurementReadSerializer(link).data)

    @extend_schema(
        request=TelemetryVariantMeasurementUpdateSerializer,
        responses=TelemetryVariantMeasurementReadSerializer,
    )
    def put(self, request, telemetry_variant_id, link_id):
        """Set which detectors run by default for a channel. Superusers only.
        """
        _require_superuser(request)
        link = _get_telemetry_variant_measurement_or_404(telemetry_variant_id, link_id)
        serializer = TelemetryVariantMeasurementUpdateSerializer(link, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        _publish_quality_config([updated])
        return Response(TelemetryVariantMeasurementReadSerializer(updated).data)


class DetectorListView(APIView):
    """List the alarm detectors and what each one needs to trigger.

    - `scope`: where a detector is switched on: `measurement` ones go in a
    channel's `enabled_detectors`, `device` ones in the device's own
    `absence_detection_enabled`.
    - `requires` is the config that must also be set before the
    detector can trigger in the first place.
    """

    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=DetectorSerializer(many=True))
    def get(self, request):
        return Response(DetectorSerializer(DETECTOR_SPECS, many=True).data)


class AlgorithmListView(APIView):
    """List the functions available to postprocessing steps.

    Each entry declares the inputs it needs, the outputs it produces and the
    parameters it accepts.
    """

    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=AlgorithmSerializer(many=True))
    def get(self, request):
        discover()
        return Response([spec.as_dict() for spec in sorted(REGISTRY.values(), key=lambda s: s.name)])


def _postprocessing_failed(e: postprocessing.PostprocessingError):
    return Conflict(e.errors) if e.conflict else ValidationError(e.errors)


def _publish_postprocessing(device: Device) -> None:
    """Called inside the transaction, so a failed publish rolls the change back."""
    try:
        postprocessing.publish_device(device)
    except Exception as e:
        raise BadGateway(f"Failed to publish postprocessing plans, rolled back: {e}")


def _clear_alarm_config(device: Device, measurements) -> None:
    """Withdraw detector config for derived channels that no longer exist."""
    for measurement in measurements:
        if measurement.enabled_detectors is None and measurement.valid_min is None and measurement.valid_max is None:
            continue
        measurement.enabled_detectors = measurement.valid_min = measurement.valid_max = None
        _publish_measurement_alarms(device, measurement)


def _get_visible_blueprint_or_404(request, blueprint_id) -> PostprocessingBlueprint:
    """A private blueprint of another owner is reported as missing, not forbidden."""
    try:
        return postprocessing.visible_blueprints(request.user).distinct().get(pk=blueprint_id)
    except (PostprocessingBlueprint.DoesNotExist, ValueError, TypeError):
        raise NotFound("Postprocessing blueprint not found")


def _require_blueprint_ownership(blueprint: PostprocessingBlueprint, owner: Owner) -> None:
    if not owner.is_superuser and blueprint.owner_id != owner.id:
        raise PermissionDenied("You do not own this postprocessing blueprint")


class PostprocessingBlueprintListCreateView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(
        parameters=[_flag("owned", "Restrict to the caller's own blueprints, excluding public ones.")],
        responses=PostprocessingBlueprintSerializer(many=True),
    )
    def get(self, request):
        """List the postprocessing blueprints the caller may use: their own and public ones.

        A superuser sees every blueprint.

        Args:
            owned: Restrict to the caller's own blueprints, excluding public ones.
        """
        qs = postprocessing.visible_blueprints(request.user).distinct()
        if request.query_params.get("owned", "").lower() in ("true", "1"):
            qs = qs.filter(owner_id=request.user.id)
        return Response(
            PostprocessingBlueprintSerializer(qs.order_by("name").prefetch_related("versions"), many=True).data
        )

    @extend_schema(
        request=PostprocessingBlueprintCreateSerializer, responses={201: PostprocessingBlueprintSerializer}
    )
    def post(self, request):
        """Create a postprocessing blueprint together with its first version.

        A version declares the input slots it reads and an ordered list of
        steps. Each step runs one algorithm, takes its inputs from a slot or
        from an earlier step's output, and names the derived channels its
        outputs are stored as. Calibration parameters are not set here: each
        device supplies its own when the blueprint is attached to it.

        Args:
            name: Unique among the caller's blueprints.
            description: Free text.
            is_public: Lets any owner attach the blueprint to their devices. Defaults to false.
            inputs: Input slots, each with an optional `default_channel`.
            steps: Steps, each with a `key` that stays the same across versions.
            notes: Free text describing this version.
        """
        serializer = PostprocessingBlueprintCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                blueprint = serializer.save(owner=request.user)
        except IntegrityError:
            raise Conflict(f"You already have a blueprint named {request.data.get('name')!r}")
        return Response(PostprocessingBlueprintSerializer(blueprint).data, status=status.HTTP_201_CREATED)


class PostprocessingBlueprintDetailView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=PostprocessingBlueprintSerializer)
    def get(self, request, blueprint_id):
        """Return one postprocessing blueprint and its latest version."""
        return Response(PostprocessingBlueprintSerializer(_get_visible_blueprint_or_404(request, blueprint_id)).data)

    @extend_schema(request=PostprocessingBlueprintUpdateSerializer, responses=PostprocessingBlueprintSerializer)
    def put(self, request, blueprint_id):
        """Rename or describe a blueprint, or change whether it is public.

        Steps cannot be changed here: create a new version instead. Making a
        blueprint private does not detach it from devices already using it.
        """
        blueprint = _get_visible_blueprint_or_404(request, blueprint_id)
        _require_blueprint_ownership(blueprint, request.user)
        serializer = PostprocessingBlueprintUpdateSerializer(blueprint, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            updated = serializer.save()
        except IntegrityError:
            raise Conflict(f"You already have a blueprint named {request.data.get('name')!r}")
        return Response(PostprocessingBlueprintSerializer(updated).data)

    @extend_schema(responses={204: NO_CONTENT})
    def delete(self, request, blueprint_id):
        """Delete a blueprint and all of its versions.

        Refused while any device still uses one of its versions.
        """
        blueprint = _get_visible_blueprint_or_404(request, blueprint_id)
        _require_blueprint_ownership(blueprint, request.user)
        try:
            blueprint.delete()
        except RestrictedError:
            raise Conflict("Devices still use a version of this blueprint. Detach it from them first")
        return Response(status=status.HTTP_204_NO_CONTENT)


class BlueprintVersionListCreateView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=BlueprintVersionSerializer(many=True))
    def get(self, request, blueprint_id):
        """List every version of a blueprint, oldest first."""
        blueprint = _get_visible_blueprint_or_404(request, blueprint_id)
        versions = blueprint.versions.prefetch_related("steps")
        return Response(BlueprintVersionSerializer(versions, many=True).data)

    @extend_schema(request=BlueprintVersionSerializer, responses={201: BlueprintVersionSerializer})
    def post(self, request, blueprint_id):
        """Add a version of a blueprint.

        Versions are immutable, so this is how a blueprint's steps change.
        Devices keep running the version they use until they are moved to the
        new one. Keeping a step's `key` and algorithm lets a device keep its
        calibration when it moves.

        Args:
            inputs: Input slots, each with an optional `default_channel`.
            steps: Steps, each with a `key` that stays the same across versions.
            notes: Free text describing what changed.
        """
        blueprint = _get_visible_blueprint_or_404(request, blueprint_id)
        _require_blueprint_ownership(blueprint, request.user)
        serializer = BlueprintVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            locked = PostprocessingBlueprint.objects.select_for_update().get(pk=blueprint.pk)
            latest = locked.versions.order_by("-number").values_list("number", flat=True).first() or 0
            version = serializer.save(blueprint=locked, number=latest + 1)
        return Response(BlueprintVersionSerializer(version).data, status=status.HTTP_201_CREATED)


class BlueprintVersionDetailView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=BlueprintVersionSerializer)
    def get(self, request, blueprint_id, number):
        """Return one version of a blueprint and its steps."""
        blueprint = _get_visible_blueprint_or_404(request, blueprint_id)
        try:
            version = blueprint.versions.get(number=number)
        except BlueprintVersion.DoesNotExist:
            raise NotFound("Blueprint version not found")
        return Response(BlueprintVersionSerializer(version).data)


def _get_device_postprocessing_or_404(device: Device, postprocessing_id) -> DevicePostprocessing:
    try:
        return postprocessing.with_relations(DevicePostprocessing.objects.filter(device=device)).get(
            pk=postprocessing_id
        )
    except (DevicePostprocessing.DoesNotExist, ValueError, TypeError):
        raise NotFound("Postprocessing not found on this device")


def _postprocessing_data(dp: DevicePostprocessing) -> dict:
    fresh = postprocessing.with_relations(DevicePostprocessing.objects.filter(pk=dp.pk)).get()
    return DevicePostprocessingSerializer(fresh).data


def _apply_enabled(dp: DevicePostprocessing, requested: bool | None) -> None:
    """Enable or disable, refusing to leave an enabled postprocessing unable to run."""
    target = dp.is_enabled if requested is None else requested
    if target:
        dp = postprocessing.with_relations(DevicePostprocessing.objects.filter(pk=dp.pk)).get()
        if found := postprocessing.problems(dp):
            raise ValidationError({"is_enabled": found})
    DevicePostprocessing.objects.filter(pk=dp.pk).update(is_enabled=target)


class DevicePostprocessingListView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=DevicePostprocessingSerializer(many=True))
    def get(self, request, device_uuid):
        """List the blueprints attached to a device, with their wiring, outputs and state.

        `problems` lists what keeps a postprocessing from being enabled, and is
        empty once it can run.
        """
        device = _get_device_or_404(device_uuid)
        _require_mesh_visible(device.mesh, request.user)
        attached = postprocessing.with_relations(device.postprocessings.order_by("created_at"))
        return Response(DevicePostprocessingSerializer(attached, many=True).data)

    @extend_schema(request=DevicePostprocessingWriteSerializer, responses={201: DevicePostprocessingSerializer})
    def post(self, request, device_uuid):
        """Attach a blueprint to a device.

        Slots not given in `input_bindings` are bound to the device's channel
        named by their `default_channel` when it has one. The derived channels
        the blueprint produces are registered on the device straight away, so
        detectors and ranges can be configured on them before any data
        arrives. A postprocessing starts disabled unless `is_enabled` is set,
        and can only be enabled once every slot is bound and every step that
        needs one has a calibration. Changes are rolled back if the stream
        tier cannot be notified.

        Args:
            blueprint_id: Blueprint to attach, the caller's own or a public one. Required.
            blueprint_version: Version number. Defaults to the latest.
            input_bindings: {slot: measurement id of this device}.
            output_prefix: Prepended to every derived field name, so a blueprint can run twice on one device.
            tolerance_seconds: Maximum distance between samples joined into one row. Defaults to half the device's
                reading interval.
            is_enabled: Start running straight away. Defaults to false.
        """
        device = _get_device_or_404(device_uuid)
        _require_mesh_ownership(device.mesh, request.user)
        serializer = DevicePostprocessingWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "blueprint_id" not in data:
            raise ValidationError({"blueprint_id": "This field is required."})
        blueprint = _get_visible_blueprint_or_404(request, data["blueprint_id"])
        if not postprocessing.can_attach(request.user, blueprint, device):
            raise PermissionDenied("This blueprint is neither public nor owned by the device's mesh owner")
        versions = blueprint.versions.order_by("-number")
        version = versions.filter(number=data["blueprint_version"]).first() if "blueprint_version" in data else versions.first()
        if version is None:
            raise ValidationError({"blueprint_version": "No such version of this blueprint"})
        try:
            with transaction.atomic():
                dp = DevicePostprocessing.objects.create(
                    device=device,
                    blueprint_version=version,
                    output_prefix=data.get("output_prefix", ""),
                    tolerance_seconds=data.get("tolerance_seconds"),
                )
                postprocessing.set_bindings(dp, data.get("input_bindings") or {})
                postprocessing.sync_outputs(dp)
                _apply_enabled(dp, data.get("is_enabled", False))
                _publish_postprocessing(device)
        except postprocessing.PostprocessingError as e:
            raise _postprocessing_failed(e)
        return Response(_postprocessing_data(dp), status=status.HTTP_201_CREATED)


class DevicePostprocessingDetailView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=DevicePostprocessingSerializer)
    def get(self, request, device_uuid, postprocessing_id):
        """Return one blueprint attachment on a device."""
        device = _get_device_or_404(device_uuid)
        _require_mesh_visible(device.mesh, request.user)
        return Response(DevicePostprocessingSerializer(_get_device_postprocessing_or_404(device, postprocessing_id)).data)

    @extend_schema(request=DevicePostprocessingWriteSerializer, responses=DevicePostprocessingSerializer)
    def put(self, request, device_uuid, postprocessing_id):
        """Rewire, move to another version, or enable or disable a postprocessing.

        Moving to another version keeps bindings for slots it still declares
        and calibrations for steps with the same key and algorithm. Derived
        channels the new wiring no longer produces are removed from the device,
        which is refused while another postprocessing reads them. Changes are
        rolled back if the stream tier cannot be notified.

        Args:
            blueprint_version: Version number of the same blueprint.
            input_bindings: {slot: measurement id of this device}. Null unbinds a slot. Slots not given keep
                their binding.
            output_prefix: Prepended to every derived field name.
            tolerance_seconds: Maximum distance between samples joined into one row. Null uses half the device's
                reading interval.
            is_enabled: Run or stop the postprocessing.
        """
        device = _get_device_or_404(device_uuid)
        _require_mesh_ownership(device.mesh, request.user)
        dp = _get_device_postprocessing_or_404(device, postprocessing_id)
        serializer = DevicePostprocessingWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "blueprint_id" in data and data["blueprint_id"] != dp.blueprint_version.blueprint_id:
            raise ValidationError({"blueprint_id": "Detach this postprocessing and attach the other blueprint instead"})

        removed = []
        try:
            with transaction.atomic():
                rewired = "input_bindings" in data or "output_prefix" in data
                if "blueprint_version" in data and data["blueprint_version"] != dp.blueprint_version.number:
                    try:
                        dp.blueprint_version = dp.blueprint_version.blueprint.versions.get(
                            number=data["blueprint_version"]
                        )
                    except BlueprintVersion.DoesNotExist:
                        raise ValidationError({"blueprint_version": "No such version of this blueprint"})
                    rewired = True
                for field in ("output_prefix", "tolerance_seconds"):
                    if field in data:
                        setattr(dp, field, data[field])
                dp.save()
                if rewired:
                    postprocessing.set_bindings(dp, data.get("input_bindings") or {})
                    removed = postprocessing.sync_outputs(dp)
                _apply_enabled(dp, data.get("is_enabled"))
                _publish_postprocessing(device)
        except postprocessing.PostprocessingError as e:
            raise _postprocessing_failed(e)
        _clear_alarm_config(device, removed)
        return Response(_postprocessing_data(dp))

    @extend_schema(responses={204: NO_CONTENT})
    def delete(self, request, device_uuid, postprocessing_id):
        """Detach a blueprint from a device.

        Its derived channels are removed from the device, while readings
        already stored remain queryable. Refused while another postprocessing
        on the device reads one of those channels.
        """
        device = _get_device_or_404(device_uuid)
        _require_mesh_ownership(device.mesh, request.user)
        dp = _get_device_postprocessing_or_404(device, postprocessing_id)
        outputs = list(dp.outputs.all())
        try:
            with transaction.atomic():
                postprocessing.delete_outputs(outputs)
                dp.delete()
                _publish_postprocessing(device)
        except postprocessing.PostprocessingError as e:
            raise _postprocessing_failed(e)
        _clear_alarm_config(device, outputs)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DevicePostprocessingCalibrationsView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=StepCalibrationSerializer(many=True))
    def get(self, request, device_uuid, postprocessing_id):
        """List the calibration history of a postprocessing, per step and oldest first."""
        device = _get_device_or_404(device_uuid)
        _require_mesh_visible(device.mesh, request.user)
        dp = _get_device_postprocessing_or_404(device, postprocessing_id)
        return Response(StepCalibrationSerializer(dp.calibrations.all(), many=True).data)

    @extend_schema(request=StepCalibrationSerializer, responses={201: StepCalibrationSerializer})
    def post(self, request, device_uuid, postprocessing_id):
        """Record a calibration for one step, in force from `valid_from` onwards.

        History is kept: readings are processed with the calibration in force
        when they were taken, so recalibrating a sensor never rewrites the
        past. Every required calibration parameter of the step's algorithm
        must be given. Rolled back if the stream tier cannot be notified.

        Args:
            step_key: Step being calibrated.
            params: Calibration parameters of the step's algorithm.
            valid_from: When this calibration takes effect. Defaults to now.
        """
        device = _get_device_or_404(device_uuid)
        _require_mesh_ownership(device.mesh, request.user)
        dp = _get_device_postprocessing_or_404(device, postprocessing_id)
        serializer = StepCalibrationSerializer(data=request.data, context={"device_postprocessing": dp})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            calibration = serializer.save(
                device_postprocessing=dp,
                valid_from=serializer.validated_data.get("valid_from") or timezone.now(),
            )
            if dp.is_enabled:
                _publish_postprocessing(device)
        return Response(StepCalibrationSerializer(calibration).data, status=status.HTTP_201_CREATED)


class DevicePostprocessingCalibrationDetailView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses={204: NO_CONTENT})
    def delete(self, request, device_uuid, postprocessing_id, calibration_id):
        """Delete a calibration recorded by mistake.

        Refused when it would leave an enabled postprocessing without a
        calibration it needs. To change a calibration from some point onwards,
        record a new one instead.
        """
        device = _get_device_or_404(device_uuid)
        _require_mesh_ownership(device.mesh, request.user)
        dp = _get_device_postprocessing_or_404(device, postprocessing_id)
        with transaction.atomic():
            deleted, _ = dp.calibrations.filter(pk=calibration_id).delete()
            if not deleted:
                raise NotFound("Calibration not found")
            if dp.is_enabled:
                fresh = postprocessing.with_relations(DevicePostprocessing.objects.filter(pk=dp.pk)).get()
                if found := postprocessing.problems(fresh):
                    raise Conflict(found)
                _publish_postprocessing(device)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DevicePostprocessingBackfillsView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=PostprocessingBackfillSerializer(many=True))
    def get(self, request, device_uuid, postprocessing_id):
        """List the backfills requested for a postprocessing and how they went, oldest first."""
        device = _get_device_or_404(device_uuid)
        _require_mesh_visible(device.mesh, request.user)
        dp = _get_device_postprocessing_or_404(device, postprocessing_id)
        return Response(PostprocessingBackfillSerializer(dp.backfills.all(), many=True).data)

    @extend_schema(request=PostprocessingBackfillSerializer, responses={202: PostprocessingBackfillSerializer})
    def post(self, request, device_uuid, postprocessing_id):
        """Recompute a postprocessing's derived channels over stored history.

        Readings already stored between `start` and `stop` are run through the
        postprocessing with the calibration in force when each was taken, and
        the results replace any derived values stored for the same times.
        Backfilled values are stored and archived but never raise alarms. The
        request is queued and runs within about a minute; its progress is
        reported in `status`. The postprocessing must be runnable, although it
        does not need to be enabled.

        Args:
            start: Start of the range to recompute.
            stop: End of the range. Defaults to now. At most 90 days after `start`.
            include_dependants: Also recompute every enabled postprocessing that reads this one's outputs. Defaults
                to false.
        """
        device = _get_device_or_404(device_uuid)
        _require_mesh_ownership(device.mesh, request.user)
        dp = _get_device_postprocessing_or_404(device, postprocessing_id)
        if found := postprocessing.problems(dp):
            raise ValidationError({"postprocessing": found})
        serializer = PostprocessingBackfillSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        backfill = serializer.save(device_postprocessing=dp, requested_by=request.user)
        return Response(PostprocessingBackfillSerializer(backfill).data, status=status.HTTP_202_ACCEPTED)


class PostprocessingBackfillListView(APIView):
    permission_classes = [IsSuperuser]

    @extend_schema(
        parameters=[_query("status", "Restrict to one status.", enum=[s.value for s in BackfillStatus])],
        responses=PostprocessingBackfillSerializer(many=True),
    )
    def get(self, request):
        """List backfills across every device, oldest first. Superusers only.

        Args:
            status: Restrict to one status, such as `pending`.
        """
        qs = PostprocessingBackfill.objects.all()
        if status_filter := request.query_params.get("status"):
            qs = qs.filter(status=status_filter)
        return Response(PostprocessingBackfillSerializer(qs, many=True).data)


def _get_backfill_or_404(backfill_id, lock: bool = False) -> PostprocessingBackfill:
    qs = PostprocessingBackfill.objects.select_for_update() if lock else PostprocessingBackfill.objects
    try:
        return qs.get(pk=backfill_id)
    except (PostprocessingBackfill.DoesNotExist, ValueError, TypeError):
        raise NotFound("Backfill not found")


class PostprocessingBackfillClaimView(APIView):
    permission_classes = [IsSuperuser]

    @extend_schema(request=None, responses=BackfillClaimSerializer)
    def post(self, request, backfill_id):
        """Claim a pending backfill for processing and return everything needed to run it. Superusers only.

        Only one caller can claim a backfill. A backfill left running for over
        an hour is presumed abandoned and can be claimed again.
        """
        with transaction.atomic():
            backfill = _get_backfill_or_404(backfill_id, lock=True)
            stale_before = timezone.now() - postprocessing.BACKFILL_CLAIM_TIMEOUT
            abandoned = backfill.status == BackfillStatus.RUNNING and backfill.started_at < stale_before
            if backfill.status != BackfillStatus.PENDING and not abandoned:
                raise Conflict(f"Backfill is {backfill.status}")
            backfill.status = BackfillStatus.RUNNING
            backfill.started_at = timezone.now()
            backfill.error = None
            backfill.save(update_fields=["status", "started_at", "error"])
        return Response(BackfillClaimSerializer(backfill).data)


class PostprocessingBackfillDetailView(APIView):
    permission_classes = [IsSuperuser]

    @extend_schema(request=BackfillResultSerializer, responses=PostprocessingBackfillSerializer)
    def put(self, request, backfill_id):
        """Record how a claimed backfill finished. Superusers only.

        Args:
            status: `done` or `failed`.
            points_published: Derived values published.
            error: Why it failed.
        """
        serializer = BackfillResultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            backfill = _get_backfill_or_404(backfill_id, lock=True)
            if backfill.status != BackfillStatus.RUNNING:
                raise Conflict(f"Backfill is {backfill.status}, not running")
            backfill.status = serializer.validated_data["status"]
            backfill.points_published = serializer.validated_data["points_published"]
            backfill.error = serializer.validated_data.get("error")
            backfill.finished_at = timezone.now()
            backfill.save(update_fields=["status", "points_published", "error", "finished_at"])
        return Response(PostprocessingBackfillSerializer(backfill).data)


def _get_source_or_404(request, source_id) -> Source:
    """A source outside the caller's reach is reported as missing, not forbidden."""
    try:
        return request.user.visible_sources.get(pk=source_id)
    except (Source.DoesNotExist, ValueError, TypeError):
        raise NotFound("Source not found")


def _source_status(source: Source) -> str:
    if source.paused_at is not None:
        return "paused"
    try:
        return get_emqx_client().source_status(str(source.id))
    except Exception as e:
        log.warning("source_status_unavailable", source_id=str(source.id), error=str(e))
        return "unknown"


def _source_read_data(source: Source) -> dict:
    source.status = _source_status(source)
    return SourceReadSerializer(source).data


_SOURCE_FIELDS = ("label", "server", "ssl", "username", "password", "topic", "qos")


def _require_terms_enforced() -> None:
    if not terms_enforced():
        raise NotFound("Terms are not enforced on this instance")


class TermsView(APIView):
    """Readable without an account, since signing up accepts these terms."""

    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[_query("locale", "`en` or `es`. Defaults to `en`; unknown locales fall back to it.")],
        responses=TermsSerializer,
    )
    def get(self, request):
        """Return the account terms, which signing up accepts.

        They cover the account only (Terms of Use and Privacy Policy): signing up
        stores no mesh data. Creating a mesh on the default broker accepts the
        mesh terms instead. Every statement must be accepted. Send the returned
        `version` back as `terms_version` when signing up. They never lapse.
        Answers `404` on an instance that does not enforce terms.

        Args:
            locale: `en` or `es`. Defaults to `en`, which is also used for any
                other value.
        """
        _require_terms_enforced()
        return Response(TermsSerializer(current_terms(TermsKind.ACCOUNT, request.query_params.get("locale"))).data)


class OwnerTermsAcceptanceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=AccountTermsAcceptanceSerializer, responses={201: OwnerReadSerializer})
    def post(self, request):
        """Accept the current account terms, when they have changed since signing up.

        Account terms never lapse, so this pauses and resumes nothing. Answers
        `404` on an instance that does not enforce terms.

        Args:
            terms_version: The `version` of the account terms accepted. Required.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """
        _require_terms_enforced()
        serializer = AccountTermsAcceptanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record_acceptance(TermsKind.ACCOUNT, request.user, serializer.validated_data["terms_locale"])
        return Response(OwnerReadSerializer(request.user).data, status=status.HTTP_201_CREATED)


class MeshTermsView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(
        parameters=[_query("locale", "`en` or `es`. Defaults to `en`; unknown locales fall back to it.")],
        responses=TermsSerializer,
    )
    def get(self, request):
        """Return the terms an owner accepts to create a mesh on the default broker.

        Every statement must be accepted. Send the returned `version` back as
        `terms_version` when creating the mesh, or when moving a mesh from a
        source onto the default broker. The footnote states how long the mesh's
        data is kept. Answers `404` on an instance that does not enforce terms.

        Args:
            locale: `en` or `es`. Defaults to `en`, which is also used for any
                other value.
        """
        _require_terms_enforced()
        return Response(TermsSerializer(current_terms(TermsKind.MESH, request.query_params.get("locale"))).data)


class MeshTermsAcceptanceView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(request=MeshTermsAcceptanceSerializer, responses={201: MeshSerializer})
    def post(self, request, mesh_id):
        """Accept the current mesh terms again, renewing the mesh. Its owner only.

        With a retention period configured, an acceptance lapses after that
        period and the mesh is paused: its gateways are deregistered and its
        readings are scheduled for deletion. Renewing resumes it and cancels the
        deletion, as long as the grace period has not ended. A mesh on a source
        is covered by the source's terms and answers `409`. Answers `404` on an
        instance that does not enforce terms.

        Args:
            terms_version: The `version` of the mesh terms accepted. Required.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """
        _require_terms_enforced()
        mesh = _get_mesh_or_404(mesh_id)
        if mesh.owner_id != request.user.id:
            _require_mesh_visible(mesh, request.user)
            raise PermissionDenied("Only the mesh's owner can accept its terms")
        if mesh.source_id is not None:
            raise Conflict("This mesh is covered by its source's terms")
        serializer = MeshTermsAcceptanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            resume_mesh(mesh)
        except Exception as e:
            raise BadGateway(f"Failed to resume the mesh's gateways, terms NOT renewed: {e}")
        record_acceptance(TermsKind.MESH, request.user, serializer.validated_data["terms_locale"], mesh=mesh)
        return Response(MeshSerializer(mesh, context=_viewer_context(request)).data, status=status.HTTP_201_CREATED)


class SourceTermsView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(
        parameters=[_query("locale", "`en` or `es`. Defaults to `en`; unknown locales fall back to it.")],
        responses=TermsSerializer,
    )
    def get(self, request):
        """Return the terms an operator must accept to add a source. Operators only.

        Every statement must be accepted. Send the returned `version` back as
        `terms_version` when creating the source. The footnote states how long
        the source's data is kept. Answers `404` on an instance that does not
        enforce terms.

        Args:
            locale: `en` or `es`. Defaults to `en`, which is also used for any
                other value.
        """
        _require_operator(request)
        _require_terms_enforced()
        return Response(TermsSerializer(current_terms(TermsKind.SOURCE, request.query_params.get("locale"))).data)


class SourceListCreateView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=SourceReadSerializer(many=True))
    def get(self, request):
        """List the sources the caller created, or every source for a superuser. Operators only.

        Each carries its bridge's status, `unknown` for all of them when the
        broker cannot be asked. Remote passwords are never included.
        """
        _require_operator(request)
        sources_qs = list(request.user.visible_sources.order_by("created_at"))
        try:
            statuses = get_emqx_client().source_statuses()
        except Exception as e:
            log.warning("source_statuses_unavailable", error=str(e))
            statuses = None
        for source in sources_qs:
            if source.paused_at is not None:
                source.status = "paused"
            elif statuses is None:
                source.status = "unknown"
            else:
                source.status = statuses.get(str(source.id), "missing")
        return Response(SourceReadSerializer(sources_qs, many=True).data)

    @extend_schema(request=SourceCreateSerializer, responses={201: SourceReadSerializer})
    def post(self, request):
        """Create a source and start bridging its remote topic into this instance. Operators only.

        The caller must first accept the current source terms. The acceptance
        is recorded with the source. Nothing is kept if the bridge cannot be set
        up.

        Args:
            server: Remote broker as `host:port`. Cannot be this instance's own
                broker or one the server has blocked.
            ssl: Connect to the remote broker over TLS. Defaults to true.
            username: Remote broker username, if it requires one.
            password: Remote broker password. Accepted but never returned.
            topic: Remote topic filter, for example `msh/EU_868/2/e/MyChannel/#`.
                `$share`, `$SYS` and filters the server has blocked, such as `#`,
                are rejected.
            qos: 0 or 1. Defaults to 1.
            terms_version: The `version` of the source terms the caller accepted.
                Required, and refused once the terms have changed, unless the
                instance does not enforce terms.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """
        _require_operator(request)
        serializer = SourceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        locale = serializer.validated_data["terms_locale"]
        try:
            with transaction.atomic():
                source = serializer.save(created_by=request.user)
                get_emqx_client().apply_source(source)
                # Only once the bridge exists, since a failed bridge rolls the source back.
                record_acceptance(TermsKind.SOURCE, request.user, locale, source=source)
        except Exception as e:
            raise BadGateway(f"Failed to create the bridge, source NOT created: {e}")
        return Response(_source_read_data(source), status=status.HTTP_201_CREATED)


class SourceDetailView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=SourceReadSerializer)
    def get(self, request, source_id):
        """Return one source and the live status of its bridge. Operators only.

        An operator can read only the sources they created; a superuser can read
        any. The status is `unknown` when the broker cannot be reached to check
        it, and `paused` once its terms have lapsed.
        """
        _require_operator(request)
        return Response(_source_read_data(_get_source_or_404(request, source_id)))

    @extend_schema(request=SourceUpdateSerializer, responses=SourceReadSerializer)
    def put(self, request, source_id):
        """Update a source and reconfigure its bridge. Operators only, on the sources they created.

        Any subset of the create fields may be sent. The update is rolled back
        if the bridge cannot be reconfigured. A paused source is updated
        without touching the broker. Send an empty `password` to remove it.
        """
        _require_operator(request)
        source = _get_source_or_404(request, source_id)
        previous = {field: getattr(source, field) for field in _SOURCE_FIELDS}
        serializer = SourceUpdateSerializer(source, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        if updated.paused_at is not None:
            return Response(_source_read_data(updated))
        client = get_emqx_client()
        try:
            client.apply_source(updated)
        except Exception as e:
            for field, value in previous.items():
                setattr(updated, field, value)
            updated.save(update_fields=list(previous))
            try:
                client.apply_source(updated)
            except Exception as restore_error:
                log.error("source_restore_failed", source_id=str(updated.id), error=str(restore_error))
            raise BadGateway(f"Failed to reconfigure the bridge, rolled back: {e}")
        return Response(_source_read_data(updated))

    @extend_schema(responses={204: NO_CONTENT})
    def delete(self, request, source_id):
        """Delete a source and stop bridging it. Operators only, on the sources they created.

        A source with meshes attached cannot be deleted. Nothing is removed if
        the bridge cannot be torn down. Its terms acceptances are kept.
        """
        _require_operator(request)
        source = _get_source_or_404(request, source_id)
        if source.meshes.exists():
            raise Conflict("Source has meshes attached; move or delete them first")
        try:
            get_emqx_client().delete_source(str(source.id))
        except Exception as e:
            raise BadGateway(f"Failed to remove the bridge, source NOT deleted: {e}")
        source.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SourceTermsAcceptanceView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(request=SourceTermsAcceptanceSerializer, responses={201: SourceReadSerializer})
    def post(self, request, source_id):
        """Accept the current source terms again, renewing the source. Only the operator who created it.

        With a retention period configured, an acceptance lapses after that
        period and the source is paused. Renewing a paused source restarts its
        bridge and cancels the deletion of its meshes' data, as long as the
        grace period has not ended. Answers `404` on an instance that does not
        enforce terms.

        Args:
            terms_version: The `version` of the source terms accepted. Required.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """
        _require_terms_enforced()
        _require_operator(request)
        source = _get_source_or_404(request, source_id)
        if source.created_by_id != request.user.id:
            raise PermissionDenied("Only the operator who created this source can accept its terms")
        serializer = SourceTermsAcceptanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            resume_source(source)
        except Exception as e:
            raise BadGateway(f"Failed to restart the bridge, terms NOT renewed: {e}")
        record_acceptance(TermsKind.SOURCE, request.user, serializer.validated_data["terms_locale"], source=source)
        return Response(_source_read_data(source), status=status.HTTP_201_CREATED)


def _require_sinks_available() -> None:
    if not env_str("REGISTRY__EMQX_API_URL"):
        raise NotFound("Sinks are not available on this instance")


def _get_sink_or_404(request, sink_id) -> Sink:
    """A sink outside the caller's reach is reported as missing, not forbidden."""
    try:
        return request.user.visible_sinks.get(pk=sink_id)
    except (Sink.DoesNotExist, ValueError, TypeError):
        raise NotFound("Sink not found")


def _sink_connections() -> dict[str, int] | None:
    try:
        return get_emqx_client().sink_connections()
    except Exception as e:
        log.warning("sink_connections_unavailable", error=str(e))
        return None


def _sink_read_data(sink: Sink, connections: dict[str, int] | None = None, password: str | None = None) -> dict:
    if connections is None:
        connections = _sink_connections()
    sink.connections = None if connections is None else connections.get(str(sink.id), 0)
    if password is None:
        return SinkReadSerializer(sink).data
    sink.password = password
    return SinkCredentialsSerializer(sink).data


def _require_sink_authorization(client) -> None:
    """Refuse while the broker would let other clients read or write sink topics."""
    try:
        problem = client.sink_authorization_problem()
    except Exception as e:
        raise BadGateway(f"Failed to check the broker's authorization: {e}")
    if problem:
        raise BadGateway(f"The broker does not protect sinks yet: {problem}")


def _link_sink(sink: Sink, mesh_ids, device_ids) -> None:
    with transaction.atomic():
        sink.mesh_links.exclude(mesh_id__in=list(mesh_ids)).delete()
        sink.device_links.exclude(device_id__in=list(device_ids)).delete()
        MeshSink.objects.bulk_create([MeshSink(sink=sink, mesh_id=i) for i in mesh_ids], ignore_conflicts=True)
        DeviceSink.objects.bulk_create([DeviceSink(sink=sink, device_id=i) for i in device_ids], ignore_conflicts=True)


def _publish_sink_targets(meshes, devices) -> None:
    for mesh in meshes:
        sinks.publish_mesh(mesh)
    for device in devices:
        sinks.publish_device(device)


def _set_sink_targets(sink: Sink, owner: Owner, meshes=None, devices=None) -> None:
    """Replace the sink's meshes and devices and publish each one that changed.

    None keeps the current list. The previous attachments are restored, and
    BadGateway raised, when the pipeline cannot be told.
    """
    old_meshes = {link.mesh_id: link.mesh for link in sink.mesh_links.select_related("mesh__owner")}
    old_devices = {link.device_id: link.device for link in sink.device_links.select_related("device__mesh__owner")}
    new_meshes = old_meshes if meshes is None else {mesh.id: mesh for mesh in meshes}
    new_devices = old_devices if devices is None else {device.id: device for device in devices}
    changed_meshes = {m: m.id in new_meshes for m in {**old_meshes, **new_meshes}.values() if (m.id in old_meshes) != (m.id in new_meshes)}
    changed_devices = {
        d: d.id in new_devices for d in {**old_devices, **new_devices}.values() if (d.id in old_devices) != (d.id in new_devices)
    }
    if not changed_meshes and not changed_devices:
        return
    _link_sink(sink, new_meshes, new_devices)
    try:
        _publish_sink_targets(changed_meshes, changed_devices)
    except Exception as e:
        _link_sink(sink, old_meshes, old_devices)
        try:
            _publish_sink_targets(changed_meshes, changed_devices)
        except Exception as restore_error:
            log.error("sink_targets_restore_failed", sink_id=str(sink.id), error=str(restore_error))
        raise BadGateway(f"Failed to publish the sink's meshes and devices, rolled back: {e}")
    sinks.record_sink_instructions(sink, owner, changed_meshes, changed_devices)


def _discard_sink(sink: Sink) -> None:
    """Undo a sink whose setup failed, as far as the broker and the pipeline allow."""
    try:
        get_emqx_client().delete_sink(str(sink.id))
    except Exception as e:
        log.error("sink_discard_failed", sink_id=str(sink.id), error=str(e))
    try:
        get_publisher().publish_sink(sink.id, None)
    except Exception as e:
        log.error("sink_discard_failed", sink_id=str(sink.id), error=str(e))
    sink.delete()


class SinkTermsView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(
        parameters=[_query("locale", "`en` or `es`. Defaults to `en`; unknown locales fall back to it.")],
        responses=TermsSerializer,
    )
    def get(self, request):
        """Return the terms an operator must accept to create a sink. Operators only.

        Every statement must be accepted. Send the returned `version` back as
        `terms_version` when creating the sink. Answers `404` on an instance that
        does not enforce terms or has no sinks.

        Args:
            locale: `en` or `es`. Defaults to `en`, which is also used for any
                other value.
        """
        _require_sinks_available()
        _require_operator(request, "sinks")
        _require_terms_enforced()
        return Response(TermsSerializer(current_terms(TermsKind.SINK, request.query_params.get("locale"))).data)


class SinkListCreateView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=SinkReadSerializer(many=True))
    def get(self, request):
        """List the sinks the caller created, or every sink for a superuser. Operators only.

        Each carries how many consumers are connected, null for all of them when
        the broker cannot be asked. Passwords are never included.
        """
        _require_sinks_available()
        _require_operator(request, "sinks")
        sinks_qs = list(request.user.visible_sinks.order_by("created_at"))
        connections = _sink_connections()
        for sink in sinks_qs:
            sink.connections = None if connections is None else connections.get(str(sink.id), 0)
        return Response(SinkReadSerializer(sinks_qs, many=True).data)

    @extend_schema(request=SinkCreateSerializer, responses={201: SinkCredentialsSerializer})
    def post(self, request):
        """Create a sink and return the credentials its consumer subscribes with. Operators only.

        The consumer connects to `broker` over TLS as `username` with the returned
        password and subscribes under `topic_filter`, where each message is one
        reading or alarm as JSON. The password is shown in this response only.
        The caller must first accept the current sink terms. Nothing is kept if
        the broker or the pipeline cannot be set up, or if the broker does not
        yet keep sink topics private.

        Args:
            label: Name for the sink.
            streams: Which readings are sent: `decoded`, `derived` and `alarms`.
                Defaults to `decoded`. Derived readings are sent only by
                instances that run postprocessing, and alarms only by those that
                run quality checks.
            mesh_ids: Meshes whose every node is sent, including nodes that
                appear later. Each must be one the caller may edit, owned by an
                operator.
            device_ids: Registrations of single devices to send, under the same
                conditions.
            terms_version: The `version` of the sink terms the caller accepted.
                Required unless the instance does not enforce terms.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """
        _require_sinks_available()
        _require_operator(request, "sinks")
        serializer = SinkCreateSerializer(data=request.data, context={"owner": request.user})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        client = get_emqx_client()
        _require_sink_authorization(client)
        password = secrets.token_urlsafe(24)
        sink = Sink.objects.create(
            label=data.get("label") or None, streams=data.get("streams") or ["decoded"], created_by=request.user
        )
        try:
            client.apply_sink_namespace()
            client.apply_sink(str(sink.id), password)
            get_publisher().publish_sink(sink.id, sink.streams)
            _set_sink_targets(sink, request.user, data.get("mesh_ids", []), data.get("device_ids", []))
            record_acceptance(TermsKind.SINK, request.user, data["terms_locale"], sink=sink)
        except Exception as e:
            _discard_sink(sink)
            raise BadGateway(f"Failed to set up the sink, sink NOT created: {e}")
        return Response(_sink_read_data(sink, password=password), status=status.HTTP_201_CREATED)


class SinkDetailView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(responses=SinkReadSerializer)
    def get(self, request, sink_id):
        """Return one sink and how many consumers are connected to it. Operators only.

        An operator can read only the sinks they created; a superuser can read
        any. The password is never included.
        """
        _require_sinks_available()
        _require_operator(request, "sinks")
        return Response(_sink_read_data(_get_sink_or_404(request, sink_id)))

    @extend_schema(request=SinkWriteSerializer, responses=SinkReadSerializer)
    def put(self, request, sink_id):
        """Update a sink. Operators only, on the sinks they created.

        Any subset of the create fields may be sent, except the terms. A list
        sent replaces the current one, so an empty `mesh_ids` detaches every
        mesh. Changes the pipeline cannot be told about are rolled back.
        """
        _require_sinks_available()
        _require_operator(request, "sinks")
        sink = _get_sink_or_404(request, sink_id)
        serializer = SinkWriteSerializer(data=request.data, context={"owner": request.user})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        previous_streams = sink.streams
        if "label" in data:
            sink.label = data["label"] or None
        if "streams" in data:
            sink.streams = data["streams"]
        sink.save()
        if sink.streams != previous_streams and sink.paused_at is None:
            try:
                get_publisher().publish_sink(sink.id, sink.streams)
            except Exception as e:
                sink.streams = previous_streams
                sink.save(update_fields=["streams"])
                raise BadGateway(f"Failed to publish the sink's streams, rolled back: {e}")
        _set_sink_targets(sink, request.user, data.get("mesh_ids"), data.get("device_ids"))
        return Response(_sink_read_data(sink))

    @extend_schema(responses={204: NO_CONTENT})
    def delete(self, request, sink_id):
        """Delete a sink, revoke its credentials and disconnect its consumers. Operators only.

        A sink with meshes or devices attached cannot be deleted. Nothing is
        removed if the broker cannot be told. Its terms acceptances are kept.
        """
        _require_sinks_available()
        _require_operator(request, "sinks")
        sink = _get_sink_or_404(request, sink_id)
        if sink.mesh_links.exists() or sink.device_links.exists():
            raise Conflict("Sink has meshes or devices attached; detach them first")
        try:
            get_emqx_client().delete_sink(str(sink.id))
        except Exception as e:
            raise BadGateway(f"Failed to revoke the sink's credentials, sink NOT deleted: {e}")
        try:
            get_publisher().publish_sink(sink.id, None)
        except Exception as e:
            # Harmless: with nothing attached the dispatcher sends nothing for it.
            log.warning("sink_unpublish_failed", sink_id=str(sink.id), error=str(e))
        sink.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SinkCredentialsView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(request=None, responses=SinkCredentialsSerializer)
    def post(self, request, sink_id):
        """Replace a sink's password and disconnect its consumers. Operators only, on the sinks they created.

        The new password is shown in this response only. The old one is kept if
        the broker cannot be told.
        """
        _require_sinks_available()
        _require_operator(request, "sinks")
        sink = _get_sink_or_404(request, sink_id)
        client = get_emqx_client()
        password = secrets.token_urlsafe(24)
        try:
            client.set_sink_password(str(sink.id), password)
        except Exception as e:
            raise BadGateway(f"Failed to change the password, credentials NOT changed: {e}")
        try:
            client.kick_sink_clients(str(sink.id))
        except Exception as e:
            log.warning("sink_kick_failed", sink_id=str(sink.id), error=str(e))
        return Response(_sink_read_data(sink, password=password))


class SinkTermsAcceptanceView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(request=SinkTermsAcceptanceSerializer, responses={201: SinkReadSerializer})
    def post(self, request, sink_id):
        """Accept the current sink terms again, renewing the sink. Only the operator who created it.

        With a retention period configured, an acceptance lapses after that
        period and the sink is paused: nothing is sent and its consumers are
        refused. Renewing a paused sink resumes it with the same credentials.
        Answers `404` on an instance that does not enforce terms.

        Args:
            terms_version: The `version` of the sink terms accepted. Required.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """
        _require_sinks_available()
        _require_terms_enforced()
        _require_operator(request, "sinks")
        sink = _get_sink_or_404(request, sink_id)
        if sink.created_by_id != request.user.id:
            raise PermissionDenied("Only the operator who created this sink can accept its terms")
        serializer = SinkTermsAcceptanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            resume_sink(sink)
        except Exception as e:
            raise BadGateway(f"Failed to resume the sink, terms NOT renewed: {e}")
        record_acceptance(TermsKind.SINK, request.user, serializer.validated_data["terms_locale"], sink=sink)
        return Response(_sink_read_data(sink), status=status.HTTP_201_CREATED)


class DataDeletionListView(APIView):
    permission_classes = [IsVerifiedOwner]

    @extend_schema(
        parameters=[
            _query("status", "`pending` (the default), `cancelled`, `done`, or `all`."),
            _query("mesh_id", "Restrict to one mesh.", OpenApiTypes.UUID),
        ],
        responses=DataDeletionSerializer(many=True),
    )
    def get(self, request):
        """List scheduled deletions of stored readings, newest first. Superusers only.

        A mesh's readings are scheduled for deletion when the mesh is deleted,
        moved off its source, or its source's terms lapse. They stay in place
        until `delete_after`, then are deleted from both the time-series store
        and the archive.

        Args:
            status: `pending`, the default, `cancelled`, `done`, or `all`.
            mesh_id: Restrict to one mesh.
        """
        _require_superuser(request)
        wanted = request.query_params.get("status", DataDeletionStatus.PENDING)
        qs = DataDeletion.objects.order_by("-requested_at")
        if wanted != "all":
            if wanted not in DataDeletionStatus.values:
                raise ValidationError({"status": "Must be pending, cancelled, done or all."})
            qs = qs.filter(status=wanted)
        mesh_id = request.query_params.get("mesh_id")
        if mesh_id:
            try:
                qs = qs.filter(mesh_id=mesh_id)
            except (ValueError, DjangoValidationError):
                raise ValidationError({"mesh_id": "Must be a UUID."})
        return Response(DataDeletionSerializer(qs, many=True).data)
