"""The registry calls the quality worker makes, through the mesh-things client."""
import os
from urllib.parse import urlsplit

from mesh_things.client import Conflict, MeshThings, NotFound


def _is_compose_service(url: str) -> bool:
    """Whether the URL names a single-label host, such as `registry-api`, which only the compose network resolves."""
    host = urlsplit(url).hostname or ""
    return bool(host) and "." not in host and ":" not in host


class RegistryClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0):
        # Plain HTTP is by design on the compose network; any other host follows MESH_THINGS_ALLOW_HTTP.
        allow = True if _is_compose_service(base_url) else None
        self._api = MeshThings(base_url, api_key, timeout=timeout, allow_insecure_http=allow)

    def devices(self, **filters) -> list[dict]:
        """Superuser key -> every owner's devices"""
        return self._api.devices.list(**filters)

    def device(self, device_uuid: str) -> dict | None:
        """One device, or None once it has been deleted."""
        try:
            return self._api.devices.get(device_uuid)
        except NotFound:
            return None

    def pending_backfills(self) -> list[dict]:
        return self._api.postprocessing_backfills.list(status="pending")

    def claim_backfill(self, backfill_id: str) -> dict | None:
        """The backfill with its plans, or None when another worker holds it."""
        try:
            return self._api.postprocessing_backfills.claim_create(backfill_id)
        except Conflict:
            return None

    def finish_backfill(self, backfill_id: str, status: str, points_published: int, error: str | None = None) -> None:
        self._api.postprocessing_backfills.update(
            backfill_id, body={"status": status, "points_published": points_published, "error": error},
        )

    def telemetry_variants(self) -> list[dict]:
        """Used for the default_reading_interval_seconds fallback when a device has
        no interval"""
        return self._api.telemetry_variants.list()

    def device_measurements(self, device_uuid: str) -> list[dict]:
        return self._api.devices.measurements_list(device_uuid)

    def device_postprocessings(self, device_uuid: str) -> list[dict]:
        return self._api.devices.postprocessings_list(device_uuid)

    def measurement_types(self) -> list[dict]:
        return self._api.measurements.list()


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
