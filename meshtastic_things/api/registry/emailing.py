import os

import structlog
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from .models import OperatorRequestStatus, Owner

log = structlog.get_logger()

ALARM_EMAIL_COOLDOWN_MIN_SECONDS = 0
ALARM_EMAIL_COOLDOWN_MAX_SECONDS = 30 * 24 * 3600  # 30 days


def default_alarm_email_cooldown_seconds() -> int:
    """Server-wide fallback cooldown, used when an owner hasn't set their own."""
    return int(os.environ.get("REGISTRY__ALARM_EMAIL_COOLDOWN_SECONDS", 3600))


def frontend_url(*segments) -> str:
    """A page of the frontend app, e.g. frontend_url("verify-email")."""
    parts = [settings.PUBLIC_FRONTEND_URL.rstrip("/")]
    parts += [str(segment).strip("/") for segment in segments if str(segment).strip("/")]
    return "/".join(parts)


def console_url(*segments) -> str:
    """A page in the frontend's console, e.g. console_url("meshes", mesh.id)."""
    return frontend_url(settings.FRONTEND_CONSOLE_PATH, *segments)


def send_templated_email(to_email: str, subject: str, template_name: str, context: dict) -> None:
    """Renders registry/templates/registry/emails/<template_name>.txt with context and
    sends it plaintext-only via the configured EMAIL_BACKEND"""

    body = render_to_string(f"registry/emails/{template_name}.txt", context)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)


def send_verification_email(owner, token: str) -> None:

    verify_link = f"{frontend_url('verify-email')}?token={token}"
    send_templated_email(
        to_email=owner.email,
        subject="Verify your email - Mesh Things",
        template_name="verify_email",
        context={"name": owner.name, "verify_link": verify_link, "ttl_hours": settings.EMAIL_VERIFICATION_TTL_HOURS},
    )


def send_password_reset_email(owner, token: str) -> None:

    reset_link = f"{frontend_url('reset-password')}?token={token}"
    send_templated_email(
        to_email=owner.email,
        subject="Reset your password - Mesh Things",
        template_name="password_reset",
        context={"name": owner.name, "reset_link": reset_link, "ttl_hours": settings.PASSWORD_RESET_TTL_HOURS},
    )


def send_operator_request_email(operator_request) -> None:
    """Notify every active superuser with an email address of a new operator request."""
    requester = operator_request.owner
    recipients = Owner.objects.filter(is_superuser=True, is_active=True).exclude(email="")
    for superuser in recipients:
        send_templated_email(
            to_email=superuser.email,
            subject="Operator role requested - Mesh Things",
            template_name="operator_request_received",
            context={
                "name": superuser.name,
                "requester_name": requester.name,
                "requester_email": requester.email,
                "reason": operator_request.reason,
                "request_link": console_url("operator-requests", operator_request.id),
            },
        )


def send_operator_request_decided_email(operator_request) -> None:
    owner = operator_request.owner
    send_templated_email(
        to_email=owner.email,
        subject=f"Operator request {operator_request.status} - Mesh Things",
        template_name="operator_request_decided",
        context={
            "name": owner.name,
            "approved": operator_request.status == OperatorRequestStatus.APPROVED,
            "note": operator_request.decision_note,
            "sources_link": console_url("sources"),
        },
    )


def send_source_terms_renewal_email(source, acceptance) -> None:
    operator = source.created_by
    send_templated_email(
        to_email=operator.email,
        subject="Renew the terms for your source - Mesh Things",
        template_name="source_terms_renewal",
        context={
            "name": operator.name,
            "source": str(source),
            "expires_at": acceptance.expires_at,
            "grace_days": settings.DATA_DELETION_GRACE_DAYS,
            "source_link": console_url("sources", source.id),
        },
    )


def send_source_terms_lapsed_email(source) -> None:
    operator = source.created_by
    send_templated_email(
        to_email=operator.email,
        subject="Your source has been paused - Mesh Things",
        template_name="source_terms_lapsed",
        context={
            "name": operator.name,
            "source": str(source),
            "grace_days": settings.DATA_DELETION_GRACE_DAYS,
            "source_link": console_url("sources", source.id),
        },
    )


def send_mesh_terms_renewal_email(mesh, acceptance) -> None:
    owner = mesh.owner
    send_templated_email(
        to_email=owner.email,
        subject="Renew the terms for your mesh - Mesh Things",
        template_name="mesh_terms_renewal",
        context={
            "name": owner.name,
            "mesh": str(mesh),
            "expires_at": acceptance.expires_at,
            "grace_days": settings.DATA_DELETION_GRACE_DAYS,
            "mesh_link": console_url("meshes", mesh.id),
        },
    )


def send_mesh_terms_lapsed_email(mesh) -> None:
    owner = mesh.owner
    send_templated_email(
        to_email=owner.email,
        subject="Your mesh has stopped storing data - Mesh Things",
        template_name="mesh_terms_lapsed",
        context={
            "name": owner.name,
            "mesh": str(mesh),
            "grace_days": settings.DATA_DELETION_GRACE_DAYS,
            "mesh_link": console_url("meshes", mesh.id),
        },
    )


def send_disk_space_email(percent: float, free_bytes: int) -> None:
    """Warn every active superuser with an email address that the disk is nearly full."""
    recipients = Owner.objects.filter(is_superuser=True, is_active=True).exclude(email="")
    for superuser in recipients:
        send_templated_email(
            to_email=superuser.email,
            subject=f"Disk {percent:.0f}% full - Mesh Things",
            template_name="disk_space",
            context={
                "name": superuser.name,
                "percent": round(percent),
                "free_gb": round(free_bytes / 1e9, 1),
                "threshold": settings.DISK_ALERT_PERCENT,
                "instance": getattr(settings, "PUBLIC_FRONTEND_URL", "") or "this instance",
            },
        )
