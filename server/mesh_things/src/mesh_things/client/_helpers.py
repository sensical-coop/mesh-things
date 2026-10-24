"""What the hand-written helpers share between the sync and async clients."""
import time

from mesh_things import exports

from .errors import EXPORT_CREATE, ExportFailed

TERMS = {
    "account": "terms_retrieve",
    "meshes": "meshes_terms_retrieve",
    "sinks": "sinks_terms_retrieve",
    "sources": "sources_terms_retrieve",
}
EXPORT_GET = "readings_meshes_exports_retrieve"
PARTITION = "readings_archive_meshes_partitions_retrieve"
ARCHIVE_CREDENTIALS = "readings_archive_meshes_credentials_create"
TRACEROUTES = "meshes_traceroutes_list"
TRACEROUTES_MAX_PAGE = 500

# Every operationId named in hand-written code, checked against the snapshot by the tests.
REFERENCED = frozenset({EXPORT_CREATE, EXPORT_GET, PARTITION, ARCHIVE_CREDENTIALS, TRACEROUTES, *TERMS.values()})


def terms_fields(terms: dict | None) -> dict:
    """The fields that accept `terms` when sent with a create, or none where terms are not enforced."""
    if terms is None:
        return {}
    return {"terms_version": terms["version"], "terms_locale": terms["locale"]}


def terms_operation(kind: str) -> str:
    try:
        return TERMS[kind]
    except KeyError:
        raise ValueError(f"Unknown terms {kind!r} (expected one of {', '.join(TERMS)})") from None


def finished_export(export: dict) -> dict | None:
    """The export once it is ready, None while it is still running; raises if it never will be."""
    if export["status"] in exports.ACTIVE:
        return None
    if export["status"] != exports.READY:
        raise ExportFailed(export)
    return export


def deadline(timeout: float | None) -> float | None:
    return None if timeout is None else time.monotonic() + timeout


def check_deadline(until: float | None, export: dict) -> None:
    if until is not None and time.monotonic() >= until:
        raise TimeoutError(f"Export {export['id']} is still {export['status']}")


def page_size(size: int) -> int:
    if not 1 <= size <= TRACEROUTES_MAX_PAGE:
        raise ValueError(f"page_size must be between 1 and {TRACEROUTES_MAX_PAGE}")
    return size


def next_before(page: list[dict], size: int) -> str | None:
    """The cursor for the page after `page`, or None when it was the last."""
    return page[-1]["heard_at"] if len(page) == size else None
