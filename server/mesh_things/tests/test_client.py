import asyncio
import json
import warnings

import httpx
import pytest

import mesh_things
from mesh_things.client import (
    AsyncMeshThings,
    ExportInProgress,
    MeshThings,
    MeshThingsVersionWarning,
    NotFound,
    Throttled,
    ValidationFailed,
)

BASE = "http://api.test"
MESH = "5703a8ba-10ee-4a0b-81ea-f7ae04d04d2a"


def _client(handler, **kwargs) -> tuple[MeshThings, list[httpx.Request]]:
    seen = []

    def record(request):
        seen.append(request)
        return handler(request)

    api = MeshThings(BASE, "secret", http=httpx.Client(transport=httpx.MockTransport(record)), allow_insecure_http=True, **kwargs)
    return api, seen


def _json(body, status=200, headers=None):
    return httpx.Response(status, json=body, headers={"API-Version": mesh_things.__version__, **(headers or {})})


def test_path_and_query_parameters_build_the_request():
    api, seen = _client(lambda r: _json([]))
    assert api.meshes.traceroutes_list(MESH, limit=10, before=None) == []
    request = seen[0]
    assert request.method == "GET"
    assert str(request.url) == f"{BASE}/meshes/{MESH}/traceroutes?limit=10"
    assert request.headers["authorization"] == "Bearer secret"


def test_node_ids_accept_the_wire_form():
    api, seen = _client(lambda r: _json({"readings": []}))
    api.readings.meshes_nodes_latest_get(MESH, "!0000002a")
    assert seen[0].url.path == f"/readings/meshes/{MESH}/nodes/42/latest"
    with pytest.raises(ValueError):
        api.readings.meshes_nodes_latest_get(MESH, "node-42")


def test_body_is_sent_as_json():
    api, seen = _client(lambda r: _json({"id": MESH}, status=201))
    assert api.meshes.create(body={"channel_id": "LongFast"}) == {"id": MESH}
    assert json.loads(seen[0].content) == {"channel_id": "LongFast"}


def test_wrong_arguments_fail_before_any_request():
    api, seen = _client(lambda r: _json({}))
    with pytest.raises(TypeError):
        api.meshes.get()
    with pytest.raises(TypeError):
        api.meshes.traceroutes_list(MESH, no_such_parameter=1)
    with pytest.raises(TypeError):
        api.meshes.create()
    assert seen == []


def test_readings_paths_can_use_their_own_root():
    api, seen = _client(lambda r: _json({}), readings_url="http://readings.test/")
    api.readings.meshes_stats_get(MESH)
    api.meshes.get(MESH)
    assert [str(r.url).split("/")[2] for r in seen] == ["readings.test", "api.test"]


def test_no_content_and_redirects():
    api, _ = _client(lambda r: httpx.Response(204))
    assert api.meshes.delete(MESH) is None
    api, _ = _client(lambda r: httpx.Response(302, headers={"Location": "https://s3.test/part.parquet"}))
    assert api.readings.archive_meshes_partitions_get(MESH, "2026-10-24", 13) == "https://s3.test/part.parquet"


def test_error_statuses_map_to_exceptions():
    api, _ = _client(lambda r: _json({"detail": "Mesh not found"}, status=404))
    with pytest.raises(NotFound, match="Mesh not found"):
        api.meshes.get(MESH)
    api, _ = _client(lambda r: _json({"label": ["Too long."]}, status=400))
    with pytest.raises(ValidationFailed) as caught:
        api.meshes.update(MESH, body={"label": "x" * 999})
    assert caught.value.errors == {"label": ["Too long."]}


def test_export_in_progress_is_not_a_rate_limit():
    api, _ = _client(lambda r: _json({"detail": "You already have an export queued"}, status=429))
    with pytest.raises(ExportInProgress):
        api.readings.meshes_exports_create(MESH, body={"format": "csv"})
    api, _ = _client(lambda r: _json({"detail": "Request was throttled."}, status=429, headers={"Retry-After": "3"}))
    with pytest.raises(Throttled) as caught:
        api.readings.meshes_exports_create(MESH, body={"format": "csv"})
    assert caught.value.retry_after == 3


def test_throttled_requests_are_retried_when_asked(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    responses = iter([
        _json({"detail": "throttled"}, status=429, headers={"Retry-After": "1"}),
        _json({"id": MESH}),
    ])
    api, seen = _client(lambda r: next(responses), retries=1)
    assert api.meshes.get(MESH) == {"id": MESH}
    assert len(seen) == 2


def test_a_different_api_version_warns_once():
    api, _ = _client(lambda r: httpx.Response(200, json={}, headers={"API-Version": "99.0.0"}))
    with pytest.warns(MeshThingsVersionWarning):
        api.metrics.get()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        api.metrics.get()


def test_the_url_comes_from_the_environment(monkeypatch):
    monkeypatch.delenv("MESH_THINGS_URL", raising=False)
    with pytest.raises(ValueError, match="MESH_THINGS_URL"):
        MeshThings()
    monkeypatch.setenv("MESH_THINGS_URL", "https://env.test/")
    monkeypatch.setenv("MESH_THINGS_API_KEY", "from-env")
    api = MeshThings()
    assert api.base_url == "https://env.test"
    assert api._headers == {"Authorization": "Bearer from-env"}
    assert MeshThings(api_key="")._headers == {}


def test_methods_carry_the_operation_docs():
    api = MeshThings(BASE)
    assert api.meshes.traceroutes_list.__doc__.startswith("List the traceroutes")


def test_async_client():
    async def run():
        transport = httpx.MockTransport(lambda r: _json({"id": MESH}))
        async with AsyncMeshThings(BASE, http=httpx.AsyncClient(transport=transport)) as api:
            return await api.meshes.get(MESH)

    assert asyncio.run(run()) == {"id": MESH}


def test_deprecated_operations_warn():
    from dataclasses import replace

    from mesh_things.client import _core
    from mesh_things.client.schema import operations

    with pytest.warns(DeprecationWarning, match="/metrics"):
        _core.warn_if_deprecated(replace(operations()["metrics_retrieve"], deprecated=True))


@pytest.mark.parametrize("url", ["http://localhost:8090", "http://127.0.0.1", "http://[::1]:8000", "https://api.test"])
def test_a_key_may_go_to_this_machine_or_over_https(url, monkeypatch):
    monkeypatch.delenv("MESH_THINGS_ALLOW_HTTP", raising=False)
    MeshThings(url, "secret")


def test_a_key_is_not_sent_over_plain_http_to_another_host(monkeypatch):
    from mesh_things.client import InsecureTransport

    monkeypatch.delenv("MESH_THINGS_ALLOW_HTTP", raising=False)
    with pytest.raises(InsecureTransport, match="registry-api"):
        MeshThings("http://registry-api:8090", "secret")
    with pytest.raises(InsecureTransport):
        MeshThings("https://api.test", "secret", readings_url="http://readings.test")
    MeshThings("http://registry-api:8090", api_key="")  # no key, nothing to protect
    MeshThings("http://registry-api:8090", "secret", allow_insecure_http=True)
    monkeypatch.setenv("MESH_THINGS_ALLOW_HTTP", "1")
    MeshThings("http://registry-api:8090", "secret")
