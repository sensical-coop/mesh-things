"""Client for the EMQX REST API, which realises each Source as a bridge.

A source is three EMQX resources sharing one name: an MQTT connector to the remote
broker, an MQTT source subscribing to the remote topic, and a rule republishing
what arrives under the source's local topic prefix.
"""
import requests
import structlog

from common import sources
from common.env import env_str

log = structlog.get_logger()

# One connection per source. With a pool or an EMQX cluster the remote filter would
# need a $share group, or every member would receive every message.
POOL_SIZE = 1


class EmqxClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.auth = (api_key, api_secret)
        self._timeout = timeout

    def _request(self, method: str, path: str, json=None) -> requests.Response:
        return self._session.request(method, f"{self.base_url}{path}", json=json, timeout=self._timeout)

    def _upsert(self, path: str, collection: str, body: dict, create_extra: dict) -> None:
        """PUT the resource, creating it with POST when EMQX does not know it."""
        resp = self._request("PUT", path, json=body)
        if resp.status_code == 404:
            resp = self._request("POST", collection, json={**create_extra, **body})
        resp.raise_for_status()

    def _delete(self, path: str) -> None:
        resp = self._request("DELETE", path)
        if resp.status_code != 404:
            resp.raise_for_status()

    def apply_source(self, source) -> None:
        """Create or update a source's connector, source and rule, in dependency order."""
        name = sources.resource_name(str(source.id))
        connector = {
            "server": source.server,
            "proto_ver": "v5",
            "pool_size": POOL_SIZE,
            "ssl": {"enable": source.ssl},
        }
        # Left out rather than sent empty, so EMQX connects without credentials.
        if source.username:
            connector["username"] = source.username
        if source.password:
            connector["password"] = source.password
        self._upsert(f"/connectors/mqtt:{name}", "/connectors", connector, {"type": "mqtt", "name": name})
        bridge = {"connector": name, "parameters": {"topic": source.topic, "qos": source.qos}}
        self._upsert(f"/sources/mqtt:{name}", "/sources", bridge, {"type": "mqtt", "name": name})
        rule = {
            "sql": f'SELECT * FROM "$bridges/mqtt:{name}"',
            "actions": [
                {
                    "function": "republish",
                    "args": {
                        "topic": f"{sources.local_topic_prefix(str(source.id))}/${{topic}}",
                        "qos": "${qos}",
                        "payload": "${payload}",
                        "retain": False,
                    },
                }
            ],
        }
        self._upsert(f"/rules/{name}", "/rules", rule, {"id": name})
        log.info("Applied EMQX source", source_id=str(source.id))

    def delete_source(self, source_id: str) -> None:
        """Remove a source's resources. EMQX refuses to delete one still referenced, hence the order."""
        name = sources.resource_name(source_id)
        self._delete(f"/rules/{name}")
        self._delete(f"/sources/mqtt:{name}")
        self._delete(f"/connectors/mqtt:{name}")
        log.info("Deleted EMQX source", source_id=source_id)

    def source_status(self, source_id: str) -> str:
        """EMQX's connection status for the source, such as `connected` or `disconnected`."""
        resp = self._request("GET", f"/sources/mqtt:{sources.resource_name(source_id)}")
        if resp.status_code == 404:
            return "missing"
        resp.raise_for_status()
        return resp.json().get("status", "unknown")

    def source_statuses(self) -> dict[str, str]:
        """Connection status of every source in this instance's namespace, in one call."""
        resp = self._request("GET", "/sources")
        resp.raise_for_status()
        statuses = {}
        for item in resp.json():
            source_id = sources.source_id_from_resource_name(item.get("name", ""))
            if source_id:
                statuses[source_id] = item.get("status", "unknown")
        return statuses

    def managed_source_ids(self) -> set[str]:
        """Ids of every source with any resource in this instance's namespace."""
        found = set()
        for path, id_field in (("/connectors", "name"), ("/sources", "name")):
            resp = self._request("GET", path)
            resp.raise_for_status()
            found.update(item.get(id_field, "") for item in resp.json())
        resp = self._request("GET", "/rules?limit=10000")
        resp.raise_for_status()
        found.update(item.get("id", "") for item in resp.json().get("data", []))
        return {sid for sid in map(sources.source_id_from_resource_name, found) if sid}


_client: EmqxClient | None = None


def get_emqx_client() -> EmqxClient:
    global _client
    if _client is None:
        _client = EmqxClient(
            base_url=env_str("REGISTRY__EMQX_API_URL"),
            api_key=env_str("REGISTRY__EMQX_API_KEY"),
            api_secret=env_str("REGISTRY__EMQX_API_SECRET"),
            timeout=float(env_str("REGISTRY__EMQX_TIMEOUT", "10")),
        )
    return _client
