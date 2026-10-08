"""Client for the EMQX REST API, which realises each Source as a bridge and each Sink
as a user its consumer connects with.

A source is three EMQX resources sharing one name: an MQTT connector to the remote
broker, an MQTT source subscribing to the remote topic, and a rule republishing
what arrives under the source's local topic prefix.

A sink is a user in the built-in authentication database and that user's rules in the
built-in authorization database, which must be checked before any other source.
"""
from urllib.parse import quote

import requests
import structlog

from common import sinks, sources
from common.env import env_str

log = structlog.get_logger()

AUTHN_USERS = f"/authentication/{quote('password_based:built_in_database', safe='')}/users"
AUTHZ_SOURCES = "/authorization/sources"
AUTHZ_DB = f"{AUTHZ_SOURCES}/built_in_database"
AUTHZ_USERS = f"{AUTHZ_DB}/rules/users"
AUTHZ_ALL = f"{AUTHZ_DB}/rules/all"
LIST_LIMIT = 10000

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

    def source_message_count(self, source_id: str) -> int | None:
        """Messages the source's rule has handled since EMQX started, or None when it has no rule."""
        resp = self._request("GET", f"/rules/{sources.resource_name(source_id)}/metrics")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("metrics", {}).get("matched")

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


    def _put_user_rules(self, username: str, rules: list[dict]) -> None:
        body = {"username": username, "rules": rules}
        resp = self._request("PUT", f"{AUTHZ_USERS}/{quote(username, safe='')}", json=body)
        if resp.status_code == 404:
            resp = self._request("POST", AUTHZ_USERS, json=[body])
        resp.raise_for_status()

    def apply_sink(self, sink_id: str, password: str | None = None) -> None:
        """Create or update a sink's user and rules. The password is set only when given."""
        username = sinks.username(sink_id)
        if password is not None:
            resp = self._request("POST", AUTHN_USERS, json={"user_id": username, "password": password})
            if resp.status_code == 409:
                resp = self._request("PUT", f"{AUTHN_USERS}/{quote(username, safe='')}", json={"password": password})
            resp.raise_for_status()
        self._put_user_rules(
            username,
            [
                {"topic": sinks.topic_filter(sink_id), "permission": "allow", "action": "subscribe"},
                {"topic": "#", "permission": "deny", "action": "all"},
            ],
        )
        log.info("Applied EMQX sink", sink_id=sink_id)

    def pause_sink(self, sink_id: str) -> None:
        """Refuse everything to a sink's user and disconnect it, keeping the password for a renewal."""
        self._put_user_rules(sinks.username(sink_id), [{"topic": "#", "permission": "deny", "action": "all"}])
        self.kick_sink_clients(sink_id)
        log.info("Paused EMQX sink", sink_id=sink_id)

    def set_sink_password(self, sink_id: str, password: str) -> None:
        resp = self._request(
            "PUT", f"{AUTHN_USERS}/{quote(sinks.username(sink_id), safe='')}", json={"password": password}
        )
        resp.raise_for_status()

    def delete_sink(self, sink_id: str) -> None:
        """Remove a sink's user and rules, then disconnect whoever is still using them."""
        username = quote(sinks.username(sink_id), safe="")
        self._delete(f"{AUTHN_USERS}/{username}")
        self._delete(f"{AUTHZ_USERS}/{username}")
        self.kick_sink_clients(sink_id)
        log.info("Deleted EMQX sink", sink_id=sink_id)

    def _sink_clients(self, username_like: str) -> list[dict]:
        resp = self._request("GET", f"/clients?like_username={quote(username_like, safe='')}&limit={LIST_LIMIT}")
        resp.raise_for_status()
        return resp.json().get("data", [])

    def kick_sink_clients(self, sink_id: str) -> None:
        """EMQX checks rules on subscribe, not on delivery, so a revoked consumer must be disconnected."""
        username = sinks.username(sink_id)
        for client in self._sink_clients(username):
            if client.get("username") == username:
                self._delete(f"/clients/{quote(client['clientid'], safe='')}")

    def sink_sessions(self) -> list[dict]:
        """Every session, connected or not, of a sink consumer in this instance's namespace."""
        return [
            client for client in self._sink_clients(sinks.username(""))
            if sinks.id_from_username(client.get("username") or "")
        ]

    def discard_session(self, clientid: str) -> None:
        """Disconnect a client if connected, and drop its session and queued messages."""
        self._delete(f"/clients/{quote(clientid, safe='')}")

    def sink_connections(self) -> dict[str, int]:
        """Connected clients per sink in this instance's namespace, in one call."""
        counts: dict[str, int] = {}
        for client in self._sink_clients(sinks.username("")):
            sink_id = sinks.id_from_username(client.get("username") or "")
            if sink_id and client.get("connected", True):
                counts[sink_id] = counts.get(sink_id, 0) + 1
        return counts

    def managed_sink_ids(self) -> tuple[set[str], set[str]]:
        """Ids of the sinks with a user, and of those with rules, in this instance's namespace."""
        prefix = quote(sinks.username(""), safe="")
        resp = self._request("GET", f"{AUTHN_USERS}?like_user_id={prefix}&limit={LIST_LIMIT}")
        resp.raise_for_status()
        users = {sinks.id_from_username(item.get("user_id", "")) for item in resp.json().get("data", [])}
        resp = self._request("GET", f"{AUTHZ_USERS}?like_username={prefix}&limit={LIST_LIMIT}")
        # 404 until the built-in authorization database is installed.
        if resp.status_code == 404:
            rules = set()
        else:
            resp.raise_for_status()
            rules = {sinks.id_from_username(item.get("username", "")) for item in resp.json().get("data", [])}
        return users - {None}, rules - {None}

    def _get_rules(self, path: str) -> list[dict]:
        """A rule set, empty when it or the built-in authorization database does not exist yet."""
        resp = self._request("GET", path)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json().get("rules", [])

    def apply_sink_namespace(self) -> None:
        """Let the dispatcher publish sink topics and stop every other client using them.

        The dispatcher's user and the rules for everyone may be shared with other namespaces
        on the broker, such as a dev stack's, so this one's rules are added rather than
        replacing theirs.
        """
        root = f"{sinks.topic_root()}/#"
        username = sinks.dispatcher_username()
        rules = self._get_rules(f"{AUTHZ_USERS}/{quote(username, safe='')}")
        if not any(rule.get("topic") == root and rule.get("permission") == "allow" for rule in rules):
            self._put_user_rules(username, [*rules, {"topic": root, "permission": "allow", "action": "publish"}])
        rules = self._get_rules(AUTHZ_ALL)
        if not any(rule.get("topic") == root and rule.get("permission") == "deny" for rule in rules):
            resp = self._request("POST", AUTHZ_ALL, json={"rules": [*rules, {"topic": root, "permission": "deny", "action": "all"}]})
            resp.raise_for_status()

    def sink_authorization_problem(self) -> str | None:
        """Why sinks would not be protected, or None when the built-in database is checked first."""
        resp = self._request("GET", AUTHZ_SOURCES)
        resp.raise_for_status()
        found = resp.json().get("sources", [])
        if not found or found[0].get("type") != "built_in_database":
            return "the built_in_database authorization source is missing or not first"
        if not found[0].get("enable", False):
            return "the built_in_database authorization source is disabled"
        return None

    def install_sink_authorization(self) -> None:
        """Create the built-in authorization database if missing and check it before any other source."""
        resp = self._request("GET", AUTHZ_SOURCES)
        resp.raise_for_status()
        if not any(item.get("type") == "built_in_database" for item in resp.json().get("sources", [])):
            resp = self._request("POST", AUTHZ_SOURCES, json={"type": "built_in_database", "enable": True})
            resp.raise_for_status()
        resp = self._request("POST", f"{AUTHZ_DB}/move", json={"position": "front"})
        resp.raise_for_status()


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
