import asyncio
from datetime import date, datetime, timezone

import httpx
import pytest

from mesh_things.client import AsyncMeshThings, ExportFailed, MeshThings, terms_fields

BASE = "http://api.test"
MESH = "5703a8ba-10ee-4a0b-81ea-f7ae04d04d2a"
EXPORT = "0b7c64b4-4b8e-4a0e-9d29-0c1a3c2f9e11"


def _client(handler, cls=MeshThings):
    seen = []

    def record(request):
        seen.append(request)
        return handler(request)

    transport = httpx.MockTransport(record)
    http = httpx.Client(transport=transport) if cls is MeshThings else httpx.AsyncClient(transport=transport)
    return cls(BASE, "secret", http=http), seen


def _export(status, **extra):
    return {"id": EXPORT, "status": status, "url": None, "error": None, **extra}


def test_enum_parameters_are_checked_against_the_schema():
    api, seen = _client(lambda r: httpx.Response(200, json={}))
    with pytest.raises(ValueError, match="allowed: 1h, 24h, 30d, 7d"):
        api.readings.meshes_stats_get(MESH, range="2h")
    with pytest.raises(ValueError, match="agg"):
        api.readings.devices_get("d", channel="device_metrics.voltage", agg="median")
    assert seen == []


def test_range_bounds_use_the_readings_validators():
    api, seen = _client(lambda r: httpx.Response(200, json={}))
    for bad in ({"start": "yesterday"}, {"window": "5 minutes"}, {"channel": "voltage"}):
        with pytest.raises(ValueError):
            api.readings.devices_get("d", **{"channel": "device_metrics.voltage", **bad})
    assert seen == []
    api.readings.devices_get(
        "d", channel="device_metrics.voltage", start=datetime(2026, 10, 1, 12, tzinfo=timezone.utc), window="5m",
    )
    assert seen[0].url.params["start"] == "2026-10-01T12:00:00Z"


def test_archive_dates_are_plain_dates():
    api, seen = _client(lambda r: httpx.Response(200, json={"partitions": []}))
    api.readings.archive_meshes_get(MESH, start=date(2026, 10, 1))
    assert seen[0].url.params["start"] == "2026-10-01"


def test_terms_and_their_fields():
    terms = {"version": "2026-09", "locale": "en", "statements": []}
    api, seen = _client(lambda r: httpx.Response(200, json=terms))
    assert api.get_terms("meshes", locale="es") == terms
    assert seen[0].url.path == "/meshes/terms" and seen[0].url.params["locale"] == "es"
    assert terms_fields(terms) == {"terms_version": "2026-09", "terms_locale": "en"}

    api, _ = _client(lambda r: httpx.Response(404, json={"detail": "Not found."}))
    assert api.get_terms() is None
    assert terms_fields(None) == {}
    with pytest.raises(ValueError):
        api.get_terms("gateways")


def test_wait_for_export(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    states = iter([_export("queued"), _export("running"), _export("ready", url="https://s3.test/e.zip")])
    api, seen = _client(lambda r: httpx.Response(200, json=next(states)))
    assert api.wait_for_export(MESH, EXPORT)["url"] == "https://s3.test/e.zip"
    assert len(seen) == 3

    api, _ = _client(lambda r: httpx.Response(200, json=_export("failed", error="No data")))
    with pytest.raises(ExportFailed, match="No data"):
        api.wait_for_export(MESH, EXPORT)

    api, _ = _client(lambda r: httpx.Response(200, json=_export("running")))
    with pytest.raises(TimeoutError):
        api.wait_for_export(MESH, EXPORT, interval=0, timeout=0)


def test_download_sends_no_credentials(tmp_path):
    api, seen = _client(lambda r: httpx.Response(200, content=b"zip-bytes"))
    assert api.download("https://s3.test/e.zip") == b"zip-bytes"
    assert "authorization" not in seen[0].headers
    target = api.download("https://s3.test/e.zip", tmp_path / "e.zip")
    assert target.read_bytes() == b"zip-bytes"


def test_download_partition_follows_the_redirect():
    def handler(request):
        if request.url.host == "api.test":
            return httpx.Response(302, headers={"Location": "https://s3.test/13.parquet"})
        return httpx.Response(200, content=b"parquet")

    api, seen = _client(handler)
    assert api.download_partition(MESH, date(2026, 10, 24), 13) == b"parquet"
    assert seen[0].url.path == f"/readings/archive/meshes/{MESH}/partitions/2026-10-24/13"
    assert "authorization" not in seen[1].headers


def _traceroute_pages(request):
    heard = [f"2026-10-24T10:00:0{i}Z" for i in range(5, 0, -1)]
    before = request.url.params.get("before")
    remaining = [h for h in heard if before is None or h < before]
    limit = int(request.url.params["limit"])
    return httpx.Response(200, json=[{"heard_at": h} for h in remaining[:limit]])


def test_traceroutes_follow_the_cursor():
    api, seen = _client(_traceroute_pages)
    assert [t["heard_at"][-3:] for t in api.traceroutes(MESH, page_size=2)] == ["05Z", "04Z", "03Z", "02Z", "01Z"]
    assert len(seen) == 3
    with pytest.raises(ValueError):
        list(api.traceroutes(MESH, page_size=501))


def test_async_helpers():
    async def run():
        api, _ = _client(_traceroute_pages, cls=AsyncMeshThings)
        return [t async for t in api.traceroutes(MESH, page_size=2)]

    assert len(asyncio.run(run())) == 5
