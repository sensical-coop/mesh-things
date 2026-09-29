"""The EMQX REST calls behind a source. The shapes were verified against EMQX 6.3.1."""
import types
import uuid
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from registry.emqx_client import EmqxClient

SOURCE_ID = uuid.UUID("5b1f3c1e-8a55-4a8e-9a0f-1d2b3c4d5e6f")
NAME = f"mt-sources-src-{SOURCE_ID}"


def _response(status_code=200, body=None):
    resp = MagicMock(status_code=status_code)
    resp.json.return_value = body if body is not None else {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = RuntimeError(status_code)
    return resp


def _source(**fields):
    defaults = dict(
        id=SOURCE_ID, server="r.example.org:8883", ssl=True, username="u", password="p", topic="msh/#", qos=1
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

    def test_apply_updates_connector_then_source_then_rule(self):
        self.client.apply_source(_source())

        self.assertEqual(
            [(m, p) for m, p, _ in self.calls],
            [("PUT", f"/connectors/mqtt:{NAME}"), ("PUT", f"/sources/mqtt:{NAME}"), ("PUT", f"/rules/{NAME}")],
        )
        connector, bridge, rule = (body for _, _, body in self.calls)
        self.assertEqual(connector["server"], "r.example.org:8883")
        self.assertEqual(connector["pool_size"], 1)
        self.assertEqual(connector["ssl"], {"enable": True})
        # EMQX refuses name and type on an update.
        self.assertNotIn("name", connector)
        self.assertEqual(bridge, {"connector": NAME, "parameters": {"topic": "msh/#", "qos": 1}})
        self.assertEqual(rule["sql"], f'SELECT * FROM "$bridges/mqtt:{NAME}"')
        self.assertEqual(rule["actions"][0]["args"]["topic"], f"mt-sources/{SOURCE_ID}/${{topic}}")
        self.assertEqual(rule["actions"][0]["args"]["payload"], "${payload}")

    def test_apply_creates_what_emqx_does_not_know(self):
        self.responses[("PUT", f"/connectors/mqtt:{NAME}")] = _response(404)
        self.responses[("PUT", f"/rules/{NAME}")] = _response(404)

        self.client.apply_source(_source())

        posts = {path: body for method, path, body in self.calls if method == "POST"}
        self.assertEqual(set(posts), {"/connectors", "/rules"})
        self.assertEqual((posts["/connectors"]["type"], posts["/connectors"]["name"]), ("mqtt", NAME))
        self.assertEqual(posts["/rules"]["id"], NAME)

    def test_apply_raises_on_an_emqx_error(self):
        self.responses[("PUT", f"/sources/mqtt:{NAME}")] = _response(400)

        with self.assertRaises(RuntimeError):
            self.client.apply_source(_source())

    def test_delete_goes_rule_then_source_then_connector_and_tolerates_missing(self):
        self.responses[("DELETE", f"/rules/{NAME}")] = _response(404)

        self.client.delete_source(str(SOURCE_ID))

        self.assertEqual(
            [(m, p) for m, p, _ in self.calls],
            [("DELETE", f"/rules/{NAME}"), ("DELETE", f"/sources/mqtt:{NAME}"), ("DELETE", f"/connectors/mqtt:{NAME}")],
        )

    def test_status_is_missing_when_emqx_has_no_source(self):
        self.responses[("GET", f"/sources/mqtt:{NAME}")] = _response(404)

        self.assertEqual(self.client.source_status(str(SOURCE_ID)), "missing")

    def test_managed_ids_ignore_other_namespaces_and_foreign_resources(self):
        other = uuid.uuid4()
        self.responses[("GET", "/connectors")] = _response(body=[{"name": NAME}, {"name": "someone-elses"}])
        self.responses[("GET", "/sources")] = _response(body=[{"name": f"mt-sources-dev-src-{other}"}])
        self.responses[("GET", "/rules?limit=10000")] = _response(body={"data": [{"id": f"mt-sources-src-{other}"}]})

        self.assertEqual(self.client.managed_source_ids(), {str(SOURCE_ID), str(other)})

    def test_credentials_are_sent_when_set(self):
        self.client.apply_source(_source())

        connector = self.calls[0][2]
        self.assertEqual((connector["username"], connector["password"]), ("u", "p"))

    def test_a_removed_password_is_left_out_rather_than_sent_empty(self):
        self.client.apply_source(_source(username=None, password=None))

        connector = self.calls[0][2]
        self.assertNotIn("username", connector)
        self.assertNotIn("password", connector)

    def test_statuses_come_from_one_call_and_skip_other_namespaces(self):
        other = uuid.uuid4()
        self.responses[("GET", "/sources")] = _response(
            body=[
                {"name": NAME, "status": "connected"},
                {"name": f"mt-sources-dev-src-{other}", "status": "disconnected"},
            ]
        )

        self.assertEqual(self.client.source_statuses(), {str(SOURCE_ID): "connected"})
        self.assertEqual(len(self.calls), 1)
