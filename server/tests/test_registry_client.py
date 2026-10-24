import json

import httpx

from mesh_things.client import MeshThings
from quality_worker.registry_client import RegistryClient


def _registry(handler) -> tuple[RegistryClient, list[httpx.Request]]:
    seen = []

    def record(request):
        seen.append(request)
        return handler(request)

    registry = RegistryClient("http://registry.test", "key")
    registry._api = MeshThings("http://registry.test", "key", http=httpx.Client(transport=httpx.MockTransport(record)))
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
