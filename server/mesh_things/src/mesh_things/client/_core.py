"""Request building and response handling shared by the sync and async clients."""
import inspect
import ipaddress
import os
import warnings
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Literal
from urllib.parse import quote, urlsplit

import httpx

import mesh_things
from mesh_things import node_ids
from mesh_things.env import env_bool
from mesh_things.influx_query import split_channel, validate_duration, validate_range_bound

from .errors import InsecureTransport, error_for
from .schema import Operation, Parameter, accepts_datetime

URL_ENV = "MESH_THINGS_URL"
API_KEY_ENV = "MESH_THINGS_API_KEY"
ALLOW_HTTP_ENV = "MESH_THINGS_ALLOW_HTTP"
_READINGS_PREFIX = "/readings/"
_PYTHON_TYPES = {"string": str, "integer": int, "number": float, "boolean": bool}
# The readings query parameters the schema types only as strings, checked with the
# validators the readings API itself uses.
_FREE_TEXT_CHECKS = {
    "start": lambda value: validate_range_bound(value, "start"),
    "stop": lambda value: validate_range_bound(value, "stop"),
    "lookback": lambda value: validate_range_bound(value, "lookback"),
    "window": lambda value: validate_duration(value, "window"),
    "channel": split_channel,
}


class MeshThingsVersionWarning(UserWarning):
    """The API runs a different version than the one this package was built for."""


@dataclass(frozen=True)
class PreparedRequest:
    method: str
    url: str
    params: dict[str, Any]
    json: Any


def resolve_base_url(base_url: str | None) -> str:
    url = base_url or os.environ.get(URL_ENV, "").strip()
    if not url:
        raise ValueError(f"No API URL: pass base_url or set {URL_ENV}.")
    return url.rstrip("/")


def resolve_allow_insecure_http(allow: bool | None) -> bool:
    return env_bool(ALLOW_HTTP_ENV) if allow is None else allow


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def require_secure(url: str, what: str, allow_insecure_http: bool) -> None:
    """Refuse to send `what` over plain HTTP, except to this machine or when allowed."""
    parts = urlsplit(url)
    if parts.scheme == "http" and not allow_insecure_http and not _is_loopback(parts.hostname):
        raise InsecureTransport(
            f"Refusing to send {what} over plain HTTP to {parts.hostname}. Use https://, or, on a network "
            f"you trust, pass allow_insecure_http=True or set {ALLOW_HTTP_ENV}=1."
        )


def resolve_api_key(api_key: str | None) -> str | None:
    """The key to send: the one given, none for an empty string, else the environment's."""
    if api_key is not None:
        return api_key or None
    return os.environ.get(API_KEY_ENV, "").strip() or None


def signature(op: Operation) -> inspect.Signature:
    """Path parameters positional, in path order; the body and query parameters keyword-only."""
    empty = inspect.Parameter.empty
    params = [
        inspect.Parameter(p.name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=_annotation(p))
        for p in op.path_params
    ]
    if op.has_body:
        params.append(inspect.Parameter(
            "body", inspect.Parameter.KEYWORD_ONLY,
            default=empty if op.body_required else None, annotation=dict[str, Any],
        ))
    params += [
        inspect.Parameter(
            p.name, inspect.Parameter.KEYWORD_ONLY,
            default=empty if p.required else None, annotation=_annotation(p),
        )
        for p in op.query_params
    ]
    return inspect.Signature(params, return_annotation=Any)


def _annotation(param) -> Any:
    python_type = _PYTHON_TYPES.get(param.type, Any)
    if param.enum is not None:
        python_type = Literal[param.enum]
    elif param.name == "node_id":
        python_type = int | str
    elif accepts_datetime(param):
        python_type = str | datetime | date
    return python_type if param.required else python_type | None


def _path_value(name: str, value: Any) -> str:
    if name == "node_id" and isinstance(value, str):
        number = node_ids.to_num(value)
        if number is None:
            raise ValueError(f"node_id {value!r} is neither a number nor a !aabbccdd id")
        value = number
    return quote(str(value), safe="")


def _query_value(param: Parameter, value: Any) -> Any:
    """Dates and datetimes as ISO 8601 in UTC, after checking the value the way the API will."""
    if isinstance(value, datetime):
        value = value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if value.tzinfo else value.isoformat()
    elif isinstance(value, date):
        value = value.isoformat()
    if param.enum is not None and value not in param.enum:
        raise ValueError(f"Invalid {param.name}: {value!r} (allowed: {', '.join(map(str, param.enum))})")
    check = _FREE_TEXT_CHECKS.get(param.name) if param.format is None else None
    if check is not None:
        check(value)
    return value


def prepare(op: Operation, base_url: str, readings_url: str | None, args: tuple, kwargs: dict) -> PreparedRequest:
    bound = signature(op).bind(*args, **kwargs)
    values = bound.arguments
    path = op.path
    for p in op.path_params:
        path = path.replace(f"{{{p.name}}}", _path_value(p.name, values[p.name]))
    params = {
        p.name: _query_value(p, values[p.name]) for p in op.query_params if values.get(p.name) is not None
    }
    root = readings_url if readings_url and path.startswith(_READINGS_PREFIX) else base_url
    return PreparedRequest(op.method, f"{root}{path}", params, values.get("body"))


def warn_if_deprecated(op: Operation) -> None:
    if op.deprecated:
        warnings.warn(f"{op.method} {op.path} is deprecated by the API.", DeprecationWarning, stacklevel=4)


def check_version(response: httpx.Response, seen: set) -> None:
    """Warn once per client when the API reports a version other than this package's."""
    version = response.headers.get("api-version")
    if version and version != mesh_things.__version__ and version not in seen:
        seen.add(version)
        warnings.warn(
            f"The API runs version {version} but mesh-things is {mesh_things.__version__}; "
            "install the matching mesh-things release.",
            MeshThingsVersionWarning,
            stacklevel=4,
        )


def result(op: Operation, response: httpx.Response) -> Any:
    """The decoded body of a success, the `Location` of a redirect, or the matching ApiError."""
    if response.is_redirect:
        return response.headers.get("location")
    if response.is_success:
        if response.status_code == 204 or not response.content:
            return None
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.content
    try:
        body = response.json()
    except ValueError:
        body = response.text
    raise error_for(op.operation_id, response.status_code, body, dict(response.headers))
