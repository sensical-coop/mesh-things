"""The EMQX REST calls behind a source. The shapes were verified against EMQX 6.3.1."""
import hashlib
import types
import uuid
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from registry.emqx_client import EmqxClient

SOURCE_ID = uuid.UUID("5b1f3c1e-8a55-4a8e-9a0f-1d2b3c4d5e6f")
NAME = f"mt-sources-src-{SOURCE_ID}"
LONGFAST = f"{NAME}-{hashlib.sha1(b'LongFast').hexdigest()[:12]}"
PRIVATE = f"{NAME}-{hashlib.sha1(b'Private').hexdigest()[:12]}"


def _response(status_code=200, body=None):
    resp = MagicMock(status_code=status_code)
    resp.json.return_value = body if body is not None else {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = RuntimeError(status_code)
    return resp


def _source(**fields):
    defaults = dict(
        id=SOURCE_ID, server="r.example.org:8883", ssl=True, username="u", password="p", root="msh/EU_868", qos=1
    )
    return types.SimpleNamespace(**{**defaults, **fields})


@patch.dict("os.environ", {"MQTT_CONNECTORS__NAMESPACE": ""})
class EmqxClientTests(SimpleTestCase):
    def setUp(self):
        self.client = EmqxClient("https://emqx.example.org:18084/api/v5/", "key", "secret")
        self.calls = []
        self.responses = {}

        def request(method, url, json=None, timeout=None):
            path = url.removeprefix("https://emqx.example.org:18084/api/v5")
            self.calls.append((method, path, json))
            return self.responses.get((method, path), _response())

        self.client._session.request = request

    def test_authenticates_with_the_key_and_secret(self):
        self.assertEqual(EmqxClient("https://x", "key", "secret")._session.auth, ("key", "secret"))

    def test_apply_updates_the_connector_then_each_channel_source_and_rule(self):
        self.client.apply_source(_source(), {"LongFast": ["!aabbccdd"]})

        self.assertEqual(
            [(m, p) for m, p, _ in self.calls],
            [
                ("PUT", f"/connectors/mqtt:{NAME}"),
                ("PUT", f"/sources/mqtt:{LONGFAST}"),
                ("PUT", f"/rules/{LONGFAST}"),
                ("GET", "/sources"),
                ("GET", "/rules?limit=10000"),
            ],
        )
        connector, bridge, rule = (body for _, _, body in self.calls[:3])
        self.assertEqual(connector["server"], "r.example.org:8883")
        self.assertEqual(connector["pool_size"], 1)
        self.assertEqual(connector["ssl"], {"enable": True})
        # EMQX refuses name and type on an update.
        self.assertNotIn("name", connector)
        self.assertEqual(bridge, {"connector": NAME, "parameters": {"topic": "msh/EU_868/2/e/LongFast/+", "qos": 1}})
        self.assertEqual(
            rule["sql"], f'SELECT * FROM "$bridges/mqtt:{LONGFAST}" WHERE regex_match(topic, \'/(!aabbccdd)$\')'
        )
        self.assertEqual(rule["actions"][0]["args"]["topic"], f"mt-sources/{SOURCE_ID}/${{topic}}")
        self.assertEqual(rule["actions"][0]["args"]["payload"], "${payload}")

    def test_a_rule_lists_every_gateway_of_its_channel(self):
        self.client.apply_source(_source(), {"LongFast": ["!22222222", "!11111111"]})

        rule = self.calls[2][2]
        self.assertTrue(rule["sql"].endswith("WHERE regex_match(topic, '/(!11111111|!22222222)$')"))

    def test_a_discovering_channel_passes_every_gateway(self):
        self.client.apply_source(_source(), {"Private": None})

        self.assertEqual(self.calls[2][2]["sql"], f'SELECT * FROM "$bridges/mqtt:{PRIVATE}"')

    def test_channels_no_longer_used_are_removed_and_others_kept(self):
        other = f"mt-sources-src-{uuid.uuid4()}-abc"
        self.responses[("GET", "/sources")] = _response(body=[{"name": LONGFAST}, {"name": PRIVATE}, {"name": other}])
        self.responses[("GET", "/rules?limit=10000")] = _response(body={"data": [{"id": LONGFAST}, {"id": NAME}]})

        self.client.apply_source(_source(), {"LongFast": ["!aabbccdd"]})

        deletes = [p for m, p, _ in self.calls if m == "DELETE"]
        self.assertCountEqual(
            deletes, [f"/rules/{PRIVATE}", f"/sources/mqtt:{PRIVATE}", f"/rules/{NAME}", f"/sources/mqtt:{NAME}"]
        )

    def test_a_source_with_no_channels_keeps_only_its_connector(self):
        self.responses[("GET", "/sources")] = _response(body=[{"name": LONGFAST}])

        self.client.apply_source(_source(), {})

        self.assertEqual(self.calls[0][:2], ("PUT", f"/connectors/mqtt:{NAME}"))
        self.assertEqual(
            [p for m, p, _ in self.calls if m == "DELETE"], [f"/rules/{LONGFAST}", f"/sources/mqtt:{LONGFAST}"]
        )

    def test_apply_creates_what_emqx_does_not_know(self):
        self.responses[("PUT", f"/connectors/mqtt:{NAME}")] = _response(404)
        self.responses[("PUT", f"/rules/{LONGFAST}")] = _response(404)

        self.client.apply_source(_source(), {"LongFast": ["!aabbccdd"]})

        posts = {path: body for method, path, body in self.calls if method == "POST"}
        self.assertEqual(set(posts), {"/connectors", "/rules"})
        self.assertEqual((posts["/connectors"]["type"], posts["/connectors"]["name"]), ("mqtt", NAME))
        self.assertEqual(posts["/rules"]["id"], LONGFAST)

    def test_apply_raises_on_an_emqx_error(self):
        self.responses[("PUT", f"/sources/mqtt:{LONGFAST}")] = _response(400)

        with self.assertRaises(RuntimeError):
            self.client.apply_source(_source(), {"LongFast": ["!aabbccdd"]})

    def test_delete_goes_rules_then_sources_then_connector_and_tolerates_missing(self):
        self.responses[("GET", "/sources")] = _response(body=[{"name": LONGFAST}])
        self.responses[("DELETE", f"/rules/{LONGFAST}")] = _response(404)

        self.client.delete_source(str(SOURCE_ID))

        self.assertEqual(
            [(m, p) for m, p, _ in self.calls if m == "DELETE"],
            [
                ("DELETE", f"/rules/{LONGFAST}"),
                ("DELETE", f"/sources/mqtt:{LONGFAST}"),
                ("DELETE", f"/connectors/mqtt:{NAME}"),
            ],
        )

    def test_status_is_missing_when_emqx_has_no_connector(self):
        self.responses[("GET", f"/connectors/mqtt:{NAME}")] = _response(404)

        self.assertEqual(self.client.source_status(str(SOURCE_ID)), "missing")

    def test_the_message_count_is_the_rule_matched_counter(self):
        self.responses[("GET", f"/rules/{NAME}/metrics")] = _response(body={"metrics": {"matched": 1234}})

        self.assertEqual(self.client.source_message_count(str(SOURCE_ID)), 1234)

    def test_a_source_without_a_rule_has_no_count(self):
        self.responses[("GET", f"/rules/{NAME}/metrics")] = _response(404)

        self.assertIsNone(self.client.source_message_count(str(SOURCE_ID)))

    def test_managed_ids_ignore_other_namespaces_and_foreign_resources(self):
        other = uuid.uuid4()
        self.responses[("GET", "/connectors")] = _response(body=[{"name": NAME}, {"name": "someone-elses"}])
        self.responses[("GET", "/sources")] = _response(body=[{"name": f"mt-sources-dev-src-{other}"}])
        self.responses[("GET", "/rules?limit=10000")] = _response(body={"data": [{"id": f"mt-sources-src-{other}"}]})

        self.assertEqual(self.client.managed_source_ids(), {str(SOURCE_ID), str(other)})

    def test_credentials_are_sent_when_set(self):
        self.client.apply_source(_source(), {})

        connector = self.calls[0][2]
        self.assertEqual((connector["username"], connector["password"]), ("u", "p"))

    def test_a_removed_password_is_left_out_rather_than_sent_empty(self):
        self.client.apply_source(_source(username=None, password=None), {})

        connector = self.calls[0][2]
        self.assertNotIn("username", connector)
        self.assertNotIn("password", connector)

    def test_statuses_come_from_the_connectors_in_one_call_and_skip_other_namespaces(self):
        other = uuid.uuid4()
        self.responses[("GET", "/connectors")] = _response(
            body=[
                {"name": NAME, "status": "connected"},
                {"name": f"mt-sources-dev-src-{other}", "status": "disconnected"},
            ]
        )

        self.assertEqual(self.client.source_statuses(), {str(SOURCE_ID): "connected"})
        self.assertEqual(len(self.calls), 1)


SINK_ID = "0c9d8e7f-6a5b-4c3d-2e1f-0a9b8c7d6e5f"
SINK_USER = f"mt-sources-sink-{SINK_ID}"
AUTHN_USERS = "/authentication/password_based%3Abuilt_in_database/users"
AUTHZ_USERS = "/authorization/sources/built_in_database/rules/users"
AUTHZ_ALL = "/authorization/sources/built_in_database/rules/all"


@patch.dict("os.environ", {"MQTT_CONNECTORS__NAMESPACE": "", "MQTT_SINKS__USER": "dispatcher"})
class EmqxSinkTests(SimpleTestCase):
    """The EMQX REST calls behind a sink. The shapes are EMQX 5.8's."""

    setUp = EmqxClientTests.setUp

    def test_a_new_sink_gets_a_user_and_rules_limited_to_its_topics(self):
        self.responses[("PUT", f"{AUTHZ_USERS}/{SINK_USER}")] = _response(404)

        self.client.apply_sink(SINK_ID, "pw")

        self.assertEqual(
            [(m, p) for m, p, _ in self.calls],
            [("POST", AUTHN_USERS), ("PUT", f"{AUTHZ_USERS}/{SINK_USER}"), ("POST", AUTHZ_USERS)],
        )
        self.assertEqual(self.calls[0][2], {"user_id": SINK_USER, "password": "pw"})
        rules = self.calls[2][2][0]["rules"]
        self.assertEqual(
            rules,
            [
                {"topic": f"mt-sources-sinks/{SINK_ID}/#", "permission": "allow", "action": "subscribe"},
                {"topic": "#", "permission": "deny", "action": "all"},
            ],
        )

    def test_an_existing_user_gets_its_password_replaced(self):
        self.responses[("POST", AUTHN_USERS)] = _response(409)

        self.client.apply_sink(SINK_ID, "pw")

        self.assertIn(("PUT", f"{AUTHN_USERS}/{SINK_USER}", {"password": "pw"}), self.calls)

    def test_reapplying_without_a_password_leaves_the_user_alone(self):
        self.client.apply_sink(SINK_ID)

        self.assertEqual([p for _, p, _ in self.calls], [f"{AUTHZ_USERS}/{SINK_USER}"])

    def test_deleting_removes_user_and_rules_then_kicks_only_that_user(self):
        self.responses[("GET", f"/clients?like_username={SINK_USER}&limit=10000")] = _response(
            body={"data": [{"clientid": "c/1", "username": SINK_USER}, {"clientid": "c2", "username": f"{SINK_USER}x"}]}
        )

        self.client.delete_sink(SINK_ID)

        self.assertEqual(
            [(m, p) for m, p, _ in self.calls if m == "DELETE"],
            [("DELETE", f"{AUTHN_USERS}/{SINK_USER}"), ("DELETE", f"{AUTHZ_USERS}/{SINK_USER}"), ("DELETE", "/clients/c%2F1")],
        )

    def test_pausing_denies_everything_and_kicks(self):
        self.client.pause_sink(SINK_ID)

        self.assertEqual(
            self.calls[0][2], {"username": SINK_USER, "rules": [{"topic": "#", "permission": "deny", "action": "all"}]}
        )
        self.assertEqual(self.calls[1][0:2], ("GET", f"/clients?like_username={SINK_USER}&limit=10000"))

    def test_the_namespace_rules_are_added_to_shared_ones_once(self):
        dev_publish = {"topic": "mt-sources-dev-sinks/#", "permission": "allow", "action": "publish"}
        dev_deny = {"topic": "mt-sources-dev-sinks/#", "permission": "deny", "action": "all"}
        self.responses[("GET", f"{AUTHZ_USERS}/dispatcher")] = _response(body={"rules": [dev_publish]})
        self.responses[("GET", AUTHZ_ALL)] = _response(body={"rules": [dev_deny]})

        self.client.apply_sink_namespace()

        publish = {"topic": "mt-sources-sinks/#", "permission": "allow", "action": "publish"}
        deny = {"topic": "mt-sources-sinks/#", "permission": "deny", "action": "all"}
        self.assertIn(("PUT", f"{AUTHZ_USERS}/dispatcher", {"username": "dispatcher", "rules": [dev_publish, publish]}), self.calls)
        self.assertIn(("POST", AUTHZ_ALL, {"rules": [dev_deny, deny]}), self.calls)

        self.calls.clear()
        self.responses[("GET", f"{AUTHZ_USERS}/dispatcher")] = _response(body={"rules": [dev_publish, publish]})
        self.responses[("GET", AUTHZ_ALL)] = _response(body={"rules": [dev_deny, deny]})
        self.client.apply_sink_namespace()
        self.assertEqual([m for m, _, _ in self.calls], ["GET", "GET"])

    def test_authorization_is_a_problem_unless_the_database_is_first(self):
        file_first = {"sources": [{"type": "file", "enable": True}, {"type": "built_in_database", "enable": True}]}
        db_first = {"sources": [{"type": "built_in_database", "enable": True}, {"type": "file", "enable": True}]}

        self.responses[("GET", "/authorization/sources")] = _response(body=file_first)
        self.assertIn("not first", self.client.sink_authorization_problem())
        self.responses[("GET", "/authorization/sources")] = _response(body=db_first)
        self.assertIsNone(self.client.sink_authorization_problem())

    def test_installing_creates_the_database_and_moves_it_first(self):
        self.responses[("GET", "/authorization/sources")] = _response(body={"sources": [{"type": "file"}]})

        self.client.install_sink_authorization()

        self.assertEqual(
            [(m, p) for m, p, _ in self.calls],
            [
                ("GET", "/authorization/sources"),
                ("POST", "/authorization/sources"),
                ("POST", "/authorization/sources/built_in_database/move"),
            ],
        )
        self.assertEqual(self.calls[2][2], {"position": "front"})

    def test_connections_are_counted_per_sink_of_this_namespace(self):
        self.responses[("GET", "/clients?like_username=mt-sources-sink-&limit=10000")] = _response(
            body={"data": [{"username": SINK_USER}, {"username": SINK_USER}, {"username": "mt-sources-dev-sink-x"}]}
        )

        self.assertEqual(self.client.sink_connections(), {SINK_ID: 2})

    def test_before_installation_there_are_no_rules(self):
        self.responses[("GET", f"{AUTHN_USERS}?like_user_id=mt-sources-sink-&limit=10000")] = _response(
            body={"data": [{"user_id": SINK_USER}]}
        )
        self.responses[("GET", f"{AUTHZ_USERS}?like_username=mt-sources-sink-&limit=10000")] = _response(404)

        self.assertEqual(self.client.managed_sink_ids(), ({SINK_ID}, set()))

    def test_sessions_are_listed_only_for_this_namespaces_sinks(self):
        self.responses[("GET", "/clients?like_username=mt-sources-sink-&limit=10000")] = _response(
            body={"data": [{"clientid": "a", "username": SINK_USER}, {"clientid": "b", "username": "mt-sources-dev-sink-x"}]}
        )

        self.assertEqual([s["clientid"] for s in self.client.sink_sessions()], ["a"])

    def test_discarding_a_session_deletes_the_client(self):
        self.client.discard_session("c/1")

        self.assertEqual(self.calls, [("DELETE", "/clients/c%2F1", None)])
