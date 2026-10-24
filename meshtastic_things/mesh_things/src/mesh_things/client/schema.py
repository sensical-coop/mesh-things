"""The API's operations, read from the OpenAPI snapshot shipped with the package."""
import json
import re
from dataclasses import dataclass
from functools import cache
from importlib import resources

HTTP_METHODS = ("get", "post", "put", "patch", "delete")
# operationId verbs renamed to read as Python: `meshes_retrieve` becomes `meshes.get`.
_VERBS = {"retrieve": "get", "destroy": "delete"}
_PATH_PARAM = re.compile(r"{(\w+)}")


@dataclass(frozen=True)
class Parameter:
    name: str
    location: str
    required: bool
    type: str | None
    format: str | None
    enum: tuple | None
    description: str


@dataclass(frozen=True)
class Operation:
    operation_id: str
    namespace: str
    name: str
    method: str
    path: str
    path_params: tuple[Parameter, ...]
    query_params: tuple[Parameter, ...]
    has_body: bool
    body_required: bool
    deprecated: bool
    description: str


def accepts_datetime(param: Parameter) -> bool:
    """Whether a parameter is a date or a time, so a `date` or `datetime` may be passed."""
    return param.format in ("date", "date-time") or param.name in ("start", "stop", "lookback", "before")


def method_name(operation_id: str, namespace: str) -> str:
    """The method an operation is exposed as within its namespace."""
    prefix = f"{namespace}_"
    rest = operation_id[len(prefix):] if operation_id.startswith(prefix) else operation_id
    head, _, verb = rest.rpartition("_")
    verb = _VERBS.get(verb, verb)
    return f"{head}_{verb}" if head else verb


@cache
def snapshot() -> dict:
    return json.loads(resources.files(__package__).joinpath("openapi.json").read_text())


def _parameter(spec: dict) -> Parameter:
    schema = spec.get("schema", {})
    return Parameter(
        name=spec["name"],
        location=spec["in"],
        required=spec.get("required", False),
        type=schema.get("type"),
        format=schema.get("format"),
        enum=tuple(schema["enum"]) if "enum" in schema else None,
        description=spec.get("description", ""),
    )


def _operation(path: str, method: str, spec: dict) -> Operation:
    namespace = spec["tags"][0].replace("-", "_")
    params = [_parameter(p) for p in spec.get("parameters", [])]
    by_name = {p.name: p for p in params if p.location == "path"}
    body = spec.get("requestBody")
    return Operation(
        operation_id=spec["operationId"],
        namespace=namespace,
        name=method_name(spec["operationId"], namespace),
        method=method.upper(),
        path=path,
        path_params=tuple(by_name[name] for name in _PATH_PARAM.findall(path)),
        query_params=tuple(p for p in params if p.location == "query"),
        has_body=body is not None,
        body_required=bool(body and body.get("required")),
        deprecated=spec.get("deprecated", False),
        description=spec.get("description", ""),
    )


@cache
def operations() -> dict[str, Operation]:
    """Every operation in the snapshot, by operationId."""
    found = (
        _operation(path, method, spec)
        for path, item in snapshot()["paths"].items()
        for method, spec in item.items()
        if method in HTTP_METHODS
    )
    return {op.operation_id: op for op in found}


def api_version() -> str:
    """The API version the snapshot was taken from."""
    return snapshot()["info"]["version"]
