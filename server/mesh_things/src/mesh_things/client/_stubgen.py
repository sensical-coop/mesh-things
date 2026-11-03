"""Write `_namespaces.pyi`, the type stub naming every method the client generates.

Run by scripts/regen-client-schema.sh after the snapshot is refreshed.
"""
import sys
from collections import defaultdict

from .schema import Operation, Parameter, accepts_datetime, operations

_TYPES = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}


def _class_name(namespace: str, is_async: bool) -> str:
    name = "".join(part.title() for part in namespace.split("_"))
    return f"Async{name}" if is_async else name


def _type(param: Parameter) -> str:
    if param.enum is not None:
        text = f"Literal[{', '.join(map(repr, param.enum))}]"
    elif param.name == "node_id":
        text = "int | str"
    elif accepts_datetime(param):
        text = "str | datetime | date"
    else:
        text = _TYPES.get(param.type, "Any")
    return text if param.required else f"{text} | None = None"


def _docstring(text: str, indent: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"').strip()
    lines = escaped.splitlines() or [""]
    body = "\n".join(f"{indent}{line}" if line else "" for line in lines[1:])
    return f'{indent}"""{lines[0]}\n{body}\n{indent}"""' if body else f'{indent}"""{lines[0]}"""'


def _method(op: Operation, is_async: bool) -> str:
    args = ["self"] + [f"{p.name}: {_type(p)}" for p in op.path_params]
    keywords = []
    if op.has_body:
        keywords.append("body: dict[str, Any]" if op.body_required else "body: dict[str, Any] | None = None")
    keywords += [f"{p.name}: {_type(p)}" for p in op.query_params]
    if keywords:
        args += ["*"] + keywords
    prefix = "async def" if is_async else "def"
    return f"    {prefix} {op.name}({', '.join(args)}) -> Any:\n{_docstring(op.description, '        ')}\n"


def render() -> str:
    by_namespace: dict[str, list[Operation]] = defaultdict(list)
    for op in operations().values():
        by_namespace[op.namespace].append(op)
    namespaces = sorted(by_namespace)
    out = [
        "# Generated from openapi.json by mesh_things.client._stubgen. Do not edit.\n",
        "from datetime import date, datetime\n",
        "from typing import Any, Literal\n",
    ]
    for is_async in (False, True):
        for namespace in namespaces:
            methods = sorted(by_namespace[namespace], key=lambda op: op.name)
            out.append(f"\nclass {_class_name(namespace, is_async)}:\n")
            out.append("\n".join(_method(op, is_async) for op in methods))
    for is_async, holder in ((False, "SyncNamespaces"), (True, "AsyncNamespaces")):
        out.append(f"\nclass {holder}:\n")
        out.extend(f"    {ns}: {_class_name(ns, is_async)}\n" for ns in namespaces)
    return "".join(out)


if __name__ == "__main__":
    sys.stdout.write(render())
