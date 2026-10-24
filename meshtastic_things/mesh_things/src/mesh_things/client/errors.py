"""Errors raised for API responses that are not a success."""
from typing import Any


class ApiError(Exception):
    """A response with an error status. `body` is the decoded JSON, or the raw text."""

    def __init__(self, status: int, detail: str, body: Any = None, headers: dict | None = None):
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail
        self.body = body
        self.headers = headers or {}


class ValidationFailed(ApiError):
    """400. `errors` maps each rejected field to its messages."""

    @property
    def errors(self) -> dict[str, list[str]]:
        if isinstance(self.body, dict):
            return {k: v if isinstance(v, list) else [v] for k, v in self.body.items()}
        if isinstance(self.body, list):
            return {"non_field_errors": self.body}
        return {}


class Unauthorized(ApiError):
    """401: the API key is missing or not valid."""


class Forbidden(ApiError):
    """403."""


class NotFound(ApiError):
    """404. Also what the API answers for a mesh the caller may not see."""


class Conflict(ApiError):
    """409."""


class Throttled(ApiError):
    """429 from a rate limit. `retry_after` is in seconds, when the API gave one."""

    @property
    def retry_after(self) -> float | None:
        value = self.headers.get("retry-after")
        try:
            return float(value) if value is not None else None
        except ValueError:
            return None


class ExportInProgress(ApiError):
    """429 because an export of yours is already queued or running. Retrying will not help."""


class ServerError(ApiError):
    """5xx."""


_BY_STATUS = {400: ValidationFailed, 401: Unauthorized, 403: Forbidden, 404: NotFound, 409: Conflict, 429: Throttled}

# The one 429 that is not a rate limit, and so carries no Retry-After.
EXPORT_CREATE = "readings_meshes_exports_create"


def _detail(body: Any, fallback: str) -> str:
    if isinstance(body, dict) and isinstance(body.get("detail"), str):
        return body["detail"]
    if isinstance(body, list) and body:
        return "; ".join(map(str, body))
    if isinstance(body, dict) and body:
        return "; ".join(f"{k}: {v}" for k, v in body.items())
    return fallback


def error_for(operation_id: str, status: int, body: Any, headers: dict) -> ApiError:
    """The exception for an error response."""
    if status == 429 and operation_id == EXPORT_CREATE and "retry-after" not in headers:
        cls = ExportInProgress
    elif status >= 500:
        cls = ServerError
    else:
        cls = _BY_STATUS.get(status, ApiError)
    return cls(status, _detail(body, f"HTTP {status}"), body, headers)
