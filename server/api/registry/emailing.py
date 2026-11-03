import os
from urllib.parse import urlencode

import structlog
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string

from . import email_health
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
    """Render registry/emails/<template_name>.txt and send it, with an HTML part when
    registry/emails/<template_name>.html exists, recording whether the mail server took it."""
    context = {"subject": subject, **context}
    message = EmailMultiAlternatives(
        subject, render_to_string(f"registry/emails/{template_name}.txt", context), settings.DEFAULT_FROM_EMAIL, [to_email]
    )
    try:
        html = render_to_string(f"registry/emails/{template_name}.html", context)
    except TemplateDoesNotExist:
        html = None
    if html:
        message.attach_alternative(html, "text/html")
    try:
        message.send(fail_silently=False)
    except Exception as e:
        email_health.record_failed(template_name, e)
        raise
    email_health.record_sent(template_name)


def send_verification_email(owner, token: str, next_path: str | None = None) -> None:
    """Email the owner a verification link, which sends them on to `next_path` once verified."""
    query = {"next": next_path, "token": token} if next_path else {"token": token}
    verify_link = f"{frontend_url('verify-email')}?{urlencode(query)}"
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


def send_sink_terms_renewal_email(sink, acceptance) -> None:
    operator = sink.created_by
    send_templated_email(
        to_email=operator.email,
        subject="Renew the terms for your sink - Mesh Things",
        template_name="sink_terms_renewal",
        context={
            "name": operator.name,
            "sink": str(sink),
            "expires_at": acceptance.expires_at,
            "sink_link": console_url("sinks", sink.id),
        },
    )


def send_sink_terms_lapsed_email(sink) -> None:
    operator = sink.created_by
    send_templated_email(
        to_email=operator.email,
        subject="Your sink has been paused - Mesh Things",
        template_name="sink_terms_lapsed",
        context={"name": operator.name, "sink": str(sink), "sink_link": console_url("sinks", sink.id)},
    )


def send_source_disconnected_email(source, status: str, since) -> None:
    operator = source.created_by
    send_templated_email(
        to_email=operator.email,
        subject="Your source is not connected - Mesh Things",
        template_name="source_disconnected",
        context={
            "name": operator.name,
            "source": str(source),
            "server": source.server,
            "status": status,
            "since": since,
            "source_link": console_url("sources", source.id),
        },
    )


def _superusers_and_operator(source, operator_opted_in: bool) -> list:
    """Every active superuser, plus the source's operator when they opted in, once each."""
    recipients = {
        owner.email: owner for owner in Owner.objects.filter(is_superuser=True, is_active=True).exclude(email="")
    }
    operator = source.created_by
    if operator and operator.is_active and operator.email and operator_opted_in:
        recipients.setdefault(operator.email, operator)
    return list(recipients.values())


def send_source_busy_email(source, rate: float) -> None:
    """Tell every active superuser, and the source's operator if they opted in, that a source is busy."""
    operator = source.created_by
    for owner in _superusers_and_operator(source, bool(operator and operator.source_rate_alerts_enabled)):
        send_templated_email(
            to_email=owner.email,
            subject="A source is unusually busy - Mesh Things",
            template_name="source_busy",
            context={
                "name": owner.name,
                "source": str(source),
                "server": source.server,
                "topic": source.topic,
                "rate": f"{rate:.1f}",
                "threshold": settings.SOURCE_RATE_ALERT_MSGS_PER_S,
                "source_link": console_url("sources", source.id),
            },
        )


def send_source_silent_email(source, status: str, since) -> None:
    """Tell every active superuser, and the source's operator if they opted in, that a source has gone silent."""
    operator = source.created_by
    for owner in _superusers_and_operator(source, bool(operator and operator.status_alerts_enabled)):
        send_templated_email(
            to_email=owner.email,
            subject="A source has stopped receiving messages - Mesh Things",
            template_name="source_silent",
            context={
                "name": owner.name,
                "source": str(source),
                "server": source.server,
                "topic": source.topic,
                "status": status,
                "since": since,
                "source_link": console_url("sources", source.id),
            },
        )


def send_sink_unused_email(sink, since) -> None:
    operator = sink.created_by
    send_templated_email(
        to_email=operator.email,
        subject="Nobody is connected to your sink - Mesh Things",
        template_name="sink_unused",
        context={
            "name": operator.name,
            "sink": str(sink),
            "since": since,
            "max_offline_hours": settings.SINKS_MAX_OFFLINE_HOURS,
            "sink_link": console_url("sinks", sink.id),
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
