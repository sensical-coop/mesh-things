import json
from importlib import resources

import mesh_things


def _snapshot() -> dict:
    return json.loads(resources.files("mesh_things.client").joinpath("openapi.json").read_text())


def test_snapshot_matches_the_package_version():
    # A version bump without rerunning scripts/regen-client-schema.sh leaves these apart.
    assert _snapshot()["info"]["version"] == mesh_things.__version__


def test_snapshot_names_no_server():
    assert "servers" not in _snapshot()


def test_every_operation_has_an_id():
    methods = {"get", "post", "put", "patch", "delete"}
    for path, item in _snapshot()["paths"].items():
        for method, operation in item.items():
            if method in methods:
                assert operation.get("operationId"), f"{method.upper()} {path}"
