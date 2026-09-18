"""Read client for registry's REST API.
"""
import os

import requests
import structlog

log = structlog.get_logger()


class RegistryClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {api_key}"
        self._timeout = timeout

    def _get(self, path: str, **params):
        resp = self._session.get(f"{self.base_url}{path}", params=params or None, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    def devices(self, **filters) -> list[dict]:
        """Superuser key -> every owner's devices"""
        return self._get("/devices", **filters)

    def blueprint(self, blueprint_id: str) -> dict:
        return self._get(f"/postprocessing-blueprints/{blueprint_id}")

    def telemetry_variants(self) -> list[dict]:
        """Used for the default_reading_interval_seconds fallback when a device has
        no interval"""
        return self._get("/telemetry-variants")

    def device_measurements(self, device_uuid: str) -> list[dict]:
        return self._get(f"/devices/{device_uuid}/measurements")

    def measurement_types(self) -> list[dict]:
        return self._get("/measurements")


_client: RegistryClient | None = None


def get_registry_client() -> RegistryClient:
    global _client
    if _client is None:
        _client = RegistryClient(
            base_url=os.environ.get("QUALITY_WORKER__REGISTRY_URL", "http://registry-api:8090"),
            api_key=os.environ["QUALITY_WORKER__REGISTRY_API_KEY"],
            timeout=float(os.environ.get("QUALITY_WORKER__REGISTRY_TIMEOUT", "10")),
        )
    return _client
