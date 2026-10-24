from pathlib import Path

import pytest

PACKAGE_LICENSE = Path(__file__).parents[1] / "LICENSE"
# The repository's, which the package's copy must match. Absent outside a checkout.
REPO_LICENSE = Path(__file__).parents[3] / "LICENSE"


@pytest.mark.skipif(not REPO_LICENSE.exists(), reason="not in a repository checkout")
def test_the_package_ships_the_repository_licence():
    assert PACKAGE_LICENSE.read_bytes() == REPO_LICENSE.read_bytes()
