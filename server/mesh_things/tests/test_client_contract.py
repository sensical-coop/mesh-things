"""The client's binding to the OpenAPI snapshot: every operation reachable, under a usable name."""
import keyword
from collections import Counter
from importlib import resources

from mesh_things.client import MeshThings, _helpers
from mesh_things.client._stubgen import render
from mesh_things.client.schema import operations

def test_every_operation_gets_a_unique_valid_method():
    names = Counter((op.namespace, op.name) for op in operations().values())
    assert [key for key, count in names.items() if count > 1] == []
    for namespace, name in names:
        for identifier in (namespace, name):
            assert identifier.isidentifier() and not keyword.iskeyword(identifier), identifier


def test_namespaces_do_not_shadow_the_client():
    own = {name for name in dir(MeshThings) if not name.startswith("_")} | {"base_url", "readings_url", "retries"}
    assert own.isdisjoint({op.namespace for op in operations().values()})


def test_parameters_do_not_collide_with_body():
    for op in operations().values():
        names = [p.name for p in op.path_params + op.query_params]
        assert len(names) == len(set(names)), op.operation_id
        assert "body" not in names, op.operation_id


def test_every_operation_is_bound_on_the_client():
    api = MeshThings("http://api.test")
    for op in operations().values():
        assert callable(getattr(getattr(api, op.namespace), op.name)), op.operation_id


def test_referenced_operations_exist():
    assert _helpers.REFERENCED <= set(operations())


def test_type_stub_is_up_to_date():
    # Rerun scripts/regen-client-schema.sh after the snapshot changes.
    committed = resources.files("mesh_things.client").joinpath("_namespaces.pyi").read_text()
    assert committed == render()
