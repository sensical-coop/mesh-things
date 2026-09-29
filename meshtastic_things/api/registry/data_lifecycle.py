"""Terms renewal, pausing on lapse, and scheduled deletion of stored readings.

Mesh terms (a mesh on the default broker), source terms and sink terms follow one workflow. With a
retention period, an acceptance lasts that long; its owner is emailed before it lapses
and renews by accepting again. A lapse stops ingestion first (the mesh's gateways are
deregistered, or the source's bridge removed), then schedules the affected readings for
deletion after `DATA_DELETION_GRACE_DAYS`, during which renewing cancels it. A sink stores
nothing, so its lapse only stops it sending and refuses its consumer. Account
terms never lapse. With terms not enforced (a self-hosted instance) none of this runs,
and anything a lapse paused is resumed. Each step is idempotent, so `run_pass` can
resume after a failure.
"""
from datetime import datetime, timedelta

import structlog
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .data_store import get_data_store
from .disk_alert import check_disk
from .emailing import (
    send_mesh_terms_lapsed_email,
    send_mesh_terms_renewal_email,
    send_sink_terms_lapsed_email,
    send_sink_terms_renewal_email,
    send_source_terms_lapsed_email,
    send_source_terms_renewal_email,
)
from .emqx_client import get_emqx_client
from .kafka_publisher import get_publisher
from .models import (
    DataDeletion,
    DataDeletionReason,
    DataDeletionStatus,
    Mesh,
    Owner,
    Sink,
    Source,
    TermsAcceptance,
    TermsKind,
)
from .terms import terms, terms_enforced, text_hash

log = structlog.get_logger()


def acceptance_expiry(kind: str, accepted_at: datetime) -> datetime | None:
    if kind == TermsKind.ACCOUNT or not settings.DATA_RETENTION_DAYS:
        return None
    return accepted_at + timedelta(days=settings.DATA_RETENTION_DAYS)


def record_acceptance(
    kind: str,
    owner: Owner,
    locale: str | None,
    mesh: Mesh | None = None,
    source: Source | None = None,
    sink: Sink | None = None,
) -> TermsAcceptance:
    """Record that `owner` accepted the current terms of `kind`, as served in `locale`.

    Records nothing, and returns None, when terms are not enforced.
    """
    if not terms_enforced():
        return None
    served = terms(kind, locale)
    now = timezone.now()
    return TermsAcceptance.objects.create(
        kind=kind,
        owner=owner,
        mesh=mesh,
        source=source,
        sink=sink,
        acceptor_name=owner.name,
        acceptor_email=owner.email,
        terms_version=served["version"],
        locale=served["locale"],
        text_hash=text_hash(served),
        accepted_at=now,
        expires_at=acceptance_expiry(kind, now),
    )


def _lapsed(acceptance: TermsAcceptance | None, now: datetime) -> bool:
    # No acceptance means nothing to lapse.
    return acceptance is not None and acceptance.expires_at is not None and acceptance.expires_at <= now


def _due_for_notice(acceptance: TermsAcceptance | None, now: datetime) -> bool:
    if acceptance is None or acceptance.expires_at is None or acceptance.renewal_notice_sent_at is not None:
        return False
    return now < acceptance.expires_at <= now + timedelta(days=settings.TERMS_RENEWAL_NOTICE_DAYS)


def schedule_mesh_deletion(
    mesh_id, reason: str, source_id=None, requested_by: Owner | None = None, data_until: datetime | None = None
) -> DataDeletion:
    now = timezone.now()
    deletion = DataDeletion.objects.create(
        mesh_id=mesh_id,
        source_id=source_id,
        reason=reason,
        requested_by=requested_by,
        requested_at=now,
        delete_after=now + timedelta(days=settings.DATA_DELETION_GRACE_DAYS),
        data_until=data_until,
    )
    log.info("Scheduled mesh data deletion", mesh_id=str(mesh_id), reason=reason, delete_after=str(deletion.delete_after))
    return deletion


def cancel_mesh_deletions(mesh_ids, reason: str, source_id) -> int:
    """Cancel pending deletions that are no longer wanted, e.g. after a renewal."""
    return DataDeletion.objects.filter(
        mesh_id__in=list(mesh_ids), reason=reason, source_id=source_id, status=DataDeletionStatus.PENDING
    ).update(status=DataDeletionStatus.CANCELLED, completed_at=timezone.now())


def _publish_mesh_gateways(mesh: Mesh, paused: bool) -> None:
    """Deregister (paused) or re-register the mesh's allowed gateways."""
    publisher = get_publisher()
    for gateway in mesh.devices.filter(is_gateway=True, is_allowed=True):
        if paused:
            publisher.publish_gateway_delete(gateway)
        else:
            publisher.publish_gateway_upsert(gateway, mesh)


def resume_source(source: Source) -> None:
    """Re-create a paused source's bridge and cancel the deletions its lapse scheduled.

    Raises if the bridge cannot be re-created; the source then stays paused.
    """
    if source.paused_at is None:
        return
    get_emqx_client().apply_source(source)
    with transaction.atomic():
        source.paused_at = None
        source.save(update_fields=["paused_at"])
        cancel_mesh_deletions(
            source.meshes.values_list("id", flat=True), DataDeletionReason.TERMS_LAPSED, source.id
        )


def resume_sink(sink: Sink) -> None:
    """Let a paused sink's consumer back in and start sending again.

    Raises if the broker or the pipeline cannot be told; the sink then stays paused.
    """
    if sink.paused_at is None:
        return
    get_emqx_client().apply_sink(str(sink.id))
    get_publisher().publish_sink(sink.id, sink.streams)
    sink.paused_at = None
    sink.save(update_fields=["paused_at"])


def resume_mesh(mesh: Mesh) -> None:
    """Re-register a paused mesh's gateways and cancel the deletion its lapse scheduled.

    Raises if a gateway cannot be republished; the mesh then stays paused.
    """
    if mesh.paused_at is None:
        return
    paused_at = mesh.paused_at
    # Cleared first, so the upserts carry the resumed mesh.
    mesh.paused_at = None
    try:
        _publish_mesh_gateways(mesh, paused=False)
    except Exception:
        mesh.paused_at = paused_at
        raise
    with transaction.atomic():
        mesh.save(update_fields=["paused_at"])
        cancel_mesh_deletions([mesh.id], DataDeletionReason.TERMS_LAPSED, None)


def send_renewal_notices(now: datetime) -> int:
    """Email the owner of every mesh or source whose acceptance lapses within the notice window."""
    if not terms_enforced() or not settings.DATA_RETENTION_DAYS:
        return 0
    sent = 0
    for source in Source.objects.filter(paused_at__isnull=True, created_by__isnull=False).select_related("created_by"):
        acceptance = source.current_terms_acceptance
        if _due_for_notice(acceptance, now) and _notify(send_source_terms_renewal_email, source, acceptance):
            sent += _mark_notified(acceptance, now)
    for mesh in Mesh.objects.filter(source__isnull=True, paused_at__isnull=True).select_related("owner"):
        acceptance = mesh.current_terms_acceptance
        if _due_for_notice(acceptance, now) and _notify(send_mesh_terms_renewal_email, mesh, acceptance):
            sent += _mark_notified(acceptance, now)
    for sink in Sink.objects.filter(paused_at__isnull=True, created_by__isnull=False).select_related("created_by"):
        acceptance = sink.current_terms_acceptance
        if _due_for_notice(acceptance, now) and _notify(send_sink_terms_renewal_email, sink, acceptance):
            sent += _mark_notified(acceptance, now)
    return sent


def _notify(send, *args) -> bool:
    try:
        send(*args)
    except Exception as e:
        log.warning("terms_email_failed", email=send.__name__, error=str(e))
        return False
    return True


def _mark_notified(acceptance: TermsAcceptance, now: datetime) -> int:
    acceptance.renewal_notice_sent_at = now
    acceptance.save(update_fields=["renewal_notice_sent_at"])
    return 1


def pause_lapsed_sources(now: datetime) -> int:
    """Remove the bridge of every source whose acceptance lapsed, and schedule its meshes' readings."""
    if not terms_enforced():
        return 0
    paused = 0
    for source in Source.objects.filter(paused_at__isnull=True).select_related("created_by"):
        if not _lapsed(source.current_terms_acceptance, now):
            continue
        try:
            get_emqx_client().delete_source(str(source.id))
        except Exception as e:
            log.warning("source_pause_failed", source_id=str(source.id), error=str(e))
            continue
        with transaction.atomic():
            source.paused_at = now
            source.save(update_fields=["paused_at"])
            for mesh in source.meshes.all():
                schedule_mesh_deletion(mesh.id, DataDeletionReason.TERMS_LAPSED, source_id=source.id, data_until=now)
        if source.created_by is not None:
            _notify(send_source_terms_lapsed_email, source)
        paused += 1
    return paused


def pause_lapsed_meshes(now: datetime) -> int:
    """Deregister the gateways of every default-broker mesh whose terms lapsed, and schedule its readings."""
    if not terms_enforced():
        return 0
    paused = 0
    for mesh in Mesh.objects.filter(source__isnull=True, paused_at__isnull=True).select_related("owner"):
        if not _lapsed(mesh.current_terms_acceptance, now):
            continue
        try:
            _publish_mesh_gateways(mesh, paused=True)
        except Exception as e:
            log.warning("mesh_pause_failed", mesh_id=str(mesh.id), error=str(e))
            continue
        with transaction.atomic():
            mesh.paused_at = now
            mesh.save(update_fields=["paused_at"])
            schedule_mesh_deletion(mesh.id, DataDeletionReason.TERMS_LAPSED, data_until=now)
        _notify(send_mesh_terms_lapsed_email, mesh)
        paused += 1
    return paused


def pause_lapsed_sinks(now: datetime) -> int:
    """Stop sending for every sink whose acceptance lapsed, and refuse its consumer."""
    if not terms_enforced():
        return 0
    paused = 0
    for sink in Sink.objects.filter(paused_at__isnull=True).select_related("created_by"):
        if not _lapsed(sink.current_terms_acceptance, now):
            continue
        try:
            get_publisher().publish_sink(sink.id, None)
            get_emqx_client().pause_sink(str(sink.id))
        except Exception as e:
            log.warning("sink_pause_failed", sink_id=str(sink.id), error=str(e))
            continue
        sink.paused_at = now
        sink.save(update_fields=["paused_at"])
        if sink.created_by is not None:
            _notify(send_sink_terms_lapsed_email, sink)
        paused += 1
    return paused


def purge_due_deletions(now: datetime) -> int:
    """Delete the readings of every deletion past its grace period. Failures are retried next pass."""
    store = get_data_store()
    done = 0
    for deletion in DataDeletion.objects.filter(status=DataDeletionStatus.PENDING, delete_after__lte=now):
        try:
            store.delete_mesh_readings(str(deletion.mesh_id), deletion.data_until or now)
        except Exception as e:
            deletion.attempts += 1
            deletion.last_error = str(e)[:2000]
            deletion.save(update_fields=["attempts", "last_error"])
            log.warning("data_deletion_failed", deletion_id=str(deletion.id), error=str(e))
            continue
        deletion.status = DataDeletionStatus.DONE
        deletion.attempts += 1
        deletion.last_error = ""
        deletion.completed_at = timezone.now()
        deletion.save(update_fields=["status", "attempts", "last_error", "completed_at"])
        log.info("Data deletion done", deletion_id=str(deletion.id), mesh_id=str(deletion.mesh_id), reason=deletion.reason)
        done += 1
    return done


def resume_paused() -> int:
    """With terms no longer enforced, resume every mesh, source and sink a lapse paused.

    Their `terms_lapsed` deletions are cancelled; a failure is retried next pass.
    """
    if terms_enforced():
        return 0
    resumed = 0
    for mesh in Mesh.objects.filter(paused_at__isnull=False).select_related("owner"):
        try:
            resume_mesh(mesh)
            resumed += 1
        except Exception as e:
            log.warning("mesh_resume_failed", mesh_id=str(mesh.id), error=str(e))
    for source in Source.objects.filter(paused_at__isnull=False):
        try:
            resume_source(source)
            resumed += 1
        except Exception as e:
            log.warning("source_resume_failed", source_id=str(source.id), error=str(e))
    for sink in Sink.objects.filter(paused_at__isnull=False):
        try:
            resume_sink(sink)
            resumed += 1
        except Exception as e:
            log.warning("sink_resume_failed", sink_id=str(sink.id), error=str(e))
    return resumed


def run_pass(now: datetime | None = None) -> dict:
    now = now or timezone.now()
    return {
        "renewal_notices": send_renewal_notices(now),
        "paused_sources": pause_lapsed_sources(now),
        "paused_meshes": pause_lapsed_meshes(now),
        "paused_sinks": pause_lapsed_sinks(now),
        "resumed": resume_paused(),
        "deletions_done": purge_due_deletions(now),
        "disk_alerts": int(check_disk()),
    }
