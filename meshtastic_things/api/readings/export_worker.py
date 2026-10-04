"""Builds queued exports one at a time and emails the owner when each is ready or has failed."""
import structlog
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.defaultfilters import filesizeformat
from django.template.loader import render_to_string

from registry.models import Owner

from . import exports
from .influx_client import get_client
from .measurement_catalog import get_measurement_types

log = structlog.get_logger()


def _details(job: dict) -> list[dict]:
    """Rows of the email's summary table."""
    # Non-breaking hyphens, so a narrow screen wraps between the dates and not inside one.
    start, stop = (f"{d:%Y-%m-%d}".replace("-", "\u2011") for d in (job["start"], job["stop"]))
    rows = [
        {"label": "Mesh", "value": str(job["mesh_id"]), "mono": True},
        {"label": "File", "value": exports.filename(job), "mono": True},
        {"label": "Format", "value": job["format"].upper()},
        {"label": "Days (UTC)", "value": start if start == stop else f"{start} to {stop}"},
        {
            "label": "Devices",
            "value": ", ".join(str(n) for n in job["node_ids"]) if job["node_ids"] else "All",
            "mono": bool(job["node_ids"]),
        },
    ]
    if job["size"] is not None:
        rows.append({"label": "Size", "value": filesizeformat(job["size"]).replace("\xa0", " ")})
    return rows


def notify(job: dict) -> None:
    """Email the owner that their export is ready or has failed. A mail failure is logged, not raised."""
    if not settings.EXPORT_EMAIL:
        return
    owner = Owner.objects.filter(pk=job["owner_id"]).only("email", "name").first()
    if owner is None:
        return
    ready = job["status"] == exports.READY
    subject = "Your export is ready" if ready else "Your export failed"
    context = {
        "name": owner.name,
        "job": job,
        "filename": exports.filename(job),
        "url": exports.download_url(job) if ready else None,
        "details": _details(job),
        "subject": subject,
        "preheader": f"{exports.filename(job)} can be downloaded for 24 hours." if ready else job["error"],
    }
    template = "export_ready" if ready else "export_failed"
    try:
        message = EmailMultiAlternatives(
            subject,
            render_to_string(f"readings/emails/{template}.txt", context),
            settings.DEFAULT_FROM_EMAIL,
            [owner.email],
        )
        message.attach_alternative(render_to_string(f"readings/emails/{template}.html", context), "text/html")
        message.send()
    except Exception as e:
        log.warning("export_email_failed", job_id=job["id"], error=str(e))


def run(job: dict) -> dict:
    """Build one taken job, then mark it ready or failed and notify its owner."""
    log.info("export_started", job_id=job["id"], mesh_id=job["mesh_id"], format=job["format"])
    try:
        if job["format"] == exports.CSV:
            size = exports.build(job, influx=get_client(), catalog=get_measurement_types())
        else:
            size = exports.build(job)
    except exports.NothingToExport as e:
        job = exports.fail(job, str(e))
    except (BotoCoreError, ClientError) as e:
        log.warning("export_storage_failed", job_id=job["id"], error=str(e))
        job = exports.fail(job, "The archive storage could not be reached")
    except Exception as e:
        log.exception("export_failed", job_id=job["id"], error=str(e))
        job = exports.fail(job, "The export could not be built")
    else:
        job = exports.finish(job, size)
        log.info("export_ready", job_id=job["id"], size=size)
    notify(job)
    return job


def recover() -> None:
    """Fail the jobs whose worker stopped mid-build, so their owners can request again."""
    for job in exports.stalled():
        log.warning("export_stalled", job_id=job["id"], worker=job.get("worker"))
        notify(exports.fail(job, "The export stopped before it finished. Request it again"))
