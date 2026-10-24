"""Every example still starts against the current client: its imports resolve and its arguments parse."""
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).parents[1] / "examples"
# Optional libraries some examples use beyond the package's own extras.
OPTIONAL = ("duckdb", "pyarrow", "pandas")


def _scripts():
    return sorted(EXAMPLES.glob("*.py")) if EXAMPLES.is_dir() else []


@pytest.mark.skipif(not _scripts(), reason="examples are not shipped beside these tests")
@pytest.mark.parametrize("script", _scripts(), ids=lambda path: path.name)
def test_example_starts(script):
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True, timeout=60)
    missing = next((name for name in OPTIONAL if f"No module named '{name}'" in result.stderr), None)
    if missing:
        pytest.skip(f"{missing} is not installed")
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
