"""setup.py's console_scripts call main() themselves.

A module-level main() call therefore runs the service twice over: once while the
entry point imports the module, and never again because the first one blocks in
its event loop. It also makes the module impossible to import - from a test, or
from anything that just wants to read a constant out of it. Two writers shipped
that way and it went unnoticed because the service still started.
"""
import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "setup.py"

# 'kafka_influx_writer=writer.kafka_influx_writer:main'
_ENTRY = re.compile(r"'([\w.]+)=([\w.]+):(\w+)'")
ENTRY_POINTS = _ENTRY.findall(SETUP.read_text())


def _module_path(module: str) -> Path:
    return ROOT.joinpath(*module.split(".")).with_suffix(".py")


def test_setup_py_declares_entry_points():
    assert ENTRY_POINTS, "no console_scripts found - did setup.py's format change?"


@pytest.mark.parametrize("script,module,attr", ENTRY_POINTS)
def test_entry_point_target_exists(script, module, attr):
    tree = ast.parse(_module_path(module).read_text())
    functions = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert attr in functions, f"{script} points at {module}:{attr}, which is not defined there"


@pytest.mark.parametrize("script,module,attr", ENTRY_POINTS)
def test_entry_point_module_does_not_run_on_import(script, module, attr):
    tree = ast.parse(_module_path(module).read_text())
    called = [
        node.value.func.id
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
    ]
    assert attr not in called, (
        f"{module} calls {attr}() at module level, so importing it starts the service. "
        f"The console_script already calls it."
    )
