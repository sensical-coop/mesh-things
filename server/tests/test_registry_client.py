import json

import httpx

from mesh_things.client import MeshThings
from quality_worker.registry_client import RegistryClient


def _registry(handler) -> tuple[RegistryClient, list[httpx.Request]]:
    seen = []

    def record(request):
        seen.append(request)
        return handler(request)

    registry = RegistryClient("http://registry-api:8090", "key")
    registry._api = MeshThings(
        "http://registry.test", "key", http=httpx.Client(transport=httpx.MockTransport(record)), allow_insecure_http=True,
    )
    return registry, seen


def test_a_deleted_device_and_a_held_backfill_are_none():
    registry, _ = _registry(lambda r: httpx.Response(404, json={"detail": "Not found."}))
    assert registry.device("d") is None
    registry, _ = _registry(lambda r: httpx.Response(409, json={"detail": "Already claimed."}))
    assert registry.claim_backfill("b") is None


def test_requests_the_worker_sends():
    registry, seen = _registry(lambda r: httpx.Response(200, json=[]))
    registry.devices(is_allowed=True)
    registry.pending_backfills()
    registry.finish_backfill("b", "done", 12)
    assert [(r.method, r.url.path, str(r.url.params)) for r in seen] == [
        ("GET", "/devices", "is_allowed=true"),
        ("GET", "/postprocessing-backfills", "status=pending"),
        ("PUT", "/postprocessing-backfills/b", ""),
    ]
    assert json.loads(seen[2].content) == {"status": "done", "points_published": 12, "error": None}


def test_plain_http_is_allowed_only_to_a_compose_service(monkeypatch):
    import pytest

    from mesh_things.client import InsecureTransport

    monkeypatch.delenv("MESH_THINGS_ALLOW_HTTP", raising=False)
    RegistryClient("http://registry-api:8090", "key")
    RegistryClient("https://api.example.org", "key")
    for url in ("http://api.example.org", "http://10.0.0.5:8090", "http://[fd00::1]:8090"):
        with pytest.raises(InsecureTransport):
            RegistryClient(url, "key")
    monkeypatch.setenv("MESH_THINGS_ALLOW_HTTP", "1")
    RegistryClient("http://api.example.org", "key")
