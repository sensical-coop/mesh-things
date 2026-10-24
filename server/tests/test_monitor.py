"""The server monitor: the probe packet, alerting and its HTTP API."""
import asyncio
import base64
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer
from paho.mqtt.client import topic_matches_sub

from mesh_things import codec
from monitor import alerts
from monitor.alerts import ALERT, RECOVERED, REMINDER, AlertState
from monitor.checks import CheckResult, marker_in_latest, marker_in_sink_message
from monitor.config import Config
from monitor.packets import build_probe
from monitor.server import build_app
from monitor.service import Monitor

PSK = base64.b64encode(bytes(range(16))).decode()
GATEWAY = 0x1A2B3C4D


def _config(**overrides) -> Config:
    values = dict(
        api_url="http://api", api_key="k", mesh_id="m", gateway_uuid="u", gateway_node_id=GATEWAY,
        psk_b64=PSK, mqtt_broker="b", mqtt_topic_prefix="msh/EU_868/2/e",
        interval_s=60, ingest_timeout_s=120, run_token="secret", run_min_interval_s=30,
    )
    values.update(overrides)
    return Config(**values)


def _result(name: str, ok: bool) -> CheckResult:
    return CheckResult(name, ok, "ok" if ok else f"{name} broke", 0.1, 1_700_000_000)


# --- The probe ---

def test_probe_decodes_with_the_mesh_key_and_carries_the_marker():
    topic, payload = build_probe(GATEWAY, "LongFast", PSK, "msh/EU_868/2/e", 1_700_000_123)

    decoded = codec.decode_message(payload, codec.decode_psk(PSK))

    assert decoded["node_id"] == GATEWAY
    assert decoded["gateway_id"] == GATEWAY
    assert decoded["channel_id"] == "LongFast"
    assert decoded["payload_kind"] == "telemetry:device_metrics"
    assert decoded["payload"]["device_metrics"]["uptime_seconds"] == 1_700_000_123


def test_probe_does_not_decode_with_another_key():
    _, payload = build_probe(GATEWAY, "LongFast", PSK, "msh/EU_868/2/e", 1)
    assert codec.decode_message(payload, bytes(16)) is None


def test_probe_topic_ends_in_the_gateway_and_sits_under_the_bridge_filter():
    topic, _ = build_probe(GATEWAY, "LongFast", PSK, "msh/EU_868/2/e", 1)
    assert topic == "msh/EU_868/2/e/LongFast/!1a2b3c4d"
    assert topic_matches_sub("msh/#", topic)


def test_encrypt_packet_is_the_inverse_of_decrypt_packet():
    from meshtastic.protobuf import mesh_pb2

    data = mesh_pb2.Data(portnum=67, payload=b"hello")
    packet = mesh_pb2.MeshPacket(id=7)
    setattr(packet, "from", GATEWAY)
    packet.encrypted = codec.encrypt_packet(data.SerializeToString(), 7, GATEWAY, bytes(range(16)))

    assert codec.decrypt_packet(packet, bytes(range(16))) == data


def test_marker_is_read_from_latest_and_from_sink_messages():
    body = {"series": [{"channel": "device_metrics.uptime_seconds", "points": [{"time": "t", "value": 42}]}]}
    assert marker_in_latest(body) == 42
    assert marker_in_latest({"series": []}) is None

    message = json.dumps({"node_id": GATEWAY, "payload": {"device_metrics": {"uptime_seconds": 42}}}).encode()
    assert marker_in_sink_message(message, GATEWAY) == 42
    assert marker_in_sink_message(message, 1) is None
    assert marker_in_sink_message(b"not json", GATEWAY) is None


# --- Alerting ---

def test_a_single_failure_stays_quiet_and_the_second_alerts():
    state = AlertState(threshold=2, reminder_s=3600)
    assert state.record([_result("ingestion", False)], now=0) is None
    alert = state.record([_result("ingestion", False)], now=60)
    assert alert == alerts.Alert(ALERT, ("ingestion",))


def test_no_repeat_within_the_reminder_window_then_a_reminder():
    state = AlertState(threshold=1, reminder_s=3600)
    assert state.record([_result("ingestion", False)], now=0).kind == ALERT
    assert state.record([_result("ingestion", False)], now=1800) is None
    assert state.record([_result("ingestion", False)], now=3600).kind == REMINDER


def test_a_newly_failing_check_alerts_even_inside_the_window():
    state = AlertState(threshold=1, reminder_s=3600)
    state.record([_result("ingestion", False)], now=0)
    alert = state.record([_result("ingestion", False), _result("api_health", False)], now=60)
    assert alert == alerts.Alert(ALERT, ("api_health", "ingestion"))


def test_recovery_is_emailed_exactly_once():
    state = AlertState(threshold=1, reminder_s=3600)
    state.record([_result("ingestion", False)], now=0)
    assert state.record([_result("ingestion", True)], now=60).kind == RECOVERED
    assert state.record([_result("ingestion", True)], now=120) is None


def test_a_check_that_recovers_and_fails_again_alerts_again():
    state = AlertState(threshold=1, reminder_s=3600)
    state.record([_result("ingestion", False), _result("sink", False)], now=0)
    assert state.record([_result("ingestion", True), _result("sink", False)], now=60) is None
    assert state.record([_result("ingestion", False)], now=120).kind == ALERT


def test_the_alert_email_lists_each_failing_check_with_its_detail():
    latest = {"ingestion": _result("ingestion", False)}
    subject, body = alerts.compose(alerts.Alert(ALERT, ("ingestion",)), latest, _config())
    assert "ingestion" in subject and "http://api" in subject
    assert "- ingestion: ingestion broke" in body


# --- The service and its API ---

class FakeChecker:
    def __init__(self, ok=True, delay=0.0):
        self.ok = ok
        self.delay = delay
        self.probes = 0
        self.timeouts = []

    async def http_check(self, name):
        return _result(name, self.ok)

    async def probe(self, timeout_s=None):
        self.probes += 1
        self.timeouts.append(timeout_s)
        await asyncio.sleep(self.delay)
        return [_result("ingestion", self.ok), _result("registry_sighting", self.ok)]


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _monitor(checker, clock=None, sent=None, **overrides):
    async def send(config, subject, body):
        if sent is not None:
            sent.append(subject)
        return True

    return Monitor(_config(**overrides), checker, send=send, clock=clock or Clock())


def _serve(monitor, scenario):
    async def go():
        async with TestClient(TestServer(build_app(monitor))) as client:
            await scenario(client)

    asyncio.run(go())


AUTH = {"Authorization": "Bearer secret"}


def test_status_is_503_before_any_round_and_200_after_a_passing_one():
    monitor = _monitor(FakeChecker())

    async def scenario(client):
        resp = await client.get("/status")
        assert resp.status == 503
        assert (await resp.json())["checks"]["ingestion"]["detail"] == "not run yet"
        await monitor.run(on_demand=False)
        resp = await client.get("/status")
        body = await resp.json()
        assert resp.status == 200 and body["ok"] is True
        assert set(body["checks"]) == set(monitor.names)

    _serve(monitor, scenario)


def test_status_is_503_when_any_check_fails_and_404_for_an_unknown_check():
    monitor = _monitor(FakeChecker(ok=False))

    async def scenario(client):
        await monitor.run(on_demand=False)
        assert (await client.get("/status")).status == 503
        resp = await client.get("/status/ingestion")
        assert resp.status == 503
        assert list((await resp.json())["checks"]) == ["ingestion"]
        assert (await client.get("/status/nope")).status == 404

    _serve(monitor, scenario)


def test_health_is_ok_on_the_first_round_and_stale_after_two_intervals():
    clock = Clock()
    monitor = _monitor(FakeChecker(), clock=clock)
    assert not monitor.is_alive()
    monitor.started_at = clock.now
    assert monitor.is_alive()
    monitor.last_round_at = clock.now
    clock.now += 2 * 60 + 120 + 1
    assert not monitor.is_alive()


def test_run_needs_the_token_and_does_not_exist_without_one():
    async def with_token(client):
        assert (await client.post("/run")).status == 401
        assert (await client.post("/run", headers={"Authorization": "Bearer wrong"})).status == 401
        assert (await client.get("/run?token=secret")).status == 200

    _serve(_monitor(FakeChecker()), with_token)

    async def without_token(client):
        assert (await client.post("/run", headers=AUTH)).status == 404

    _serve(_monitor(FakeChecker(), run_token=""), without_token)


def test_running_one_probe_check_runs_the_probe_once_and_reports_only_it():
    checker = FakeChecker()
    monitor = _monitor(checker)

    async def scenario(client):
        resp = await client.post("/run/registry_sighting", headers=AUTH)
        body = await resp.json()
        assert resp.status == 200
        assert list(body["checks"]) == ["registry_sighting"]
        assert body["cached"] is False
        assert checker.probes == 1
        # The whole probe is recorded, not only the check asked for.
        assert "ingestion" in monitor.latest

    _serve(monitor, scenario)


def test_an_http_check_on_demand_does_not_publish():
    checker = FakeChecker()
    monitor = _monitor(checker)

    async def scenario(client):
        resp = await client.post("/run/api_health", headers=AUTH)
        assert list((await resp.json())["checks"]) == ["api_health"]
        assert checker.probes == 0

    _serve(monitor, scenario)


def test_concurrent_runs_share_one_probe():
    checker = FakeChecker(delay=0.05)
    monitor = _monitor(checker)

    async def scenario(client):
        first, second = await asyncio.gather(client.post("/run", headers=AUTH), client.post("/run", headers=AUTH))
        bodies = [await first.json(), await second.json()]
        assert checker.probes == 1
        assert sorted(b["cached"] for b in bodies) == [False, True]

    _serve(monitor, scenario)


def test_a_run_soon_after_a_probe_reuses_it_and_later_ones_do_not():
    clock = Clock()
    checker = FakeChecker()
    monitor = _monitor(checker, clock=clock)

    async def scenario(client):
        await client.post("/run/ingestion", headers=AUTH)
        clock.now += 10
        resp = await client.post("/run/ingestion", headers=AUTH)
        assert (await resp.json())["cached"] is True
        assert checker.probes == 1
        clock.now += 30
        await client.post("/run/ingestion", headers=AUTH)
        assert checker.probes == 2

    _serve(monitor, scenario)


def test_the_scheduled_round_ignores_the_minimum_interval():
    checker = FakeChecker()
    monitor = _monitor(checker)

    async def go():
        await monitor.run(on_demand=False)
        await monitor.run(on_demand=False)

    asyncio.run(go())
    assert checker.probes == 2


def test_the_timeout_is_capped_and_validated():
    checker = FakeChecker()
    monitor = _monitor(checker, run_min_interval_s=0)

    async def scenario(client):
        await client.post("/run/ingestion?timeout=30", headers=AUTH)
        await client.post("/run/ingestion?timeout=9999", headers=AUTH)
        assert checker.timeouts == [30.0, 120]
        assert (await client.post("/run/ingestion?timeout=abc", headers=AUTH)).status == 400
        assert (await client.post("/run/ingestion?timeout=0", headers=AUTH)).status == 400

    _serve(monitor, scenario)


def test_on_demand_results_update_status_and_drive_alerts():
    sent = []
    monitor = _monitor(FakeChecker(ok=False), sent=sent, failures_before_alert=1)

    async def scenario(client):
        resp = await client.post("/run", headers=AUTH)
        assert resp.status == 503
        assert (await client.get("/status")).status == 503
        assert len(sent) == 1 and sent[0].startswith("Failing:")

    _serve(monitor, scenario)


def test_one_round_sends_one_email_for_http_and_probe_failures_alike():
    sent = []
    monitor = _monitor(FakeChecker(ok=False), sent=sent, failures_before_alert=1)
    asyncio.run(monitor.run(on_demand=False))
    assert len(sent) == 1


@pytest.mark.parametrize("value, expected", [("", 404), ("x", 401)])
def test_a_query_token_is_checked_too(value, expected):
    monitor = _monitor(FakeChecker(), run_token=value or "")

    async def scenario(client):
        assert (await client.get("/run?token=nope")).status == expected

    _serve(monitor, scenario)


# --- The email check ---

def _email_check(status: int, body: dict | None = None, **config):
    """Run the email check against a registry answering /status/email with `status` and `body`."""
    from aiohttp import web

    from monitor.checks import Checker

    seen = {}

    async def email_status(request):
        seen["auth"] = request.headers.get("Authorization")
        return web.json_response(body or {}, status=status)

    async def go():
        app = web.Application()
        app.router.add_get("/status/email", email_status)
        server = TestServer(app)
        await server.start_server()
        try:
            checker = Checker(_config(api_url=str(server.make_url("")).rstrip("/"), **config))
            return await checker.http_check("email")
        finally:
            await server.close()

    return asyncio.run(go()), seen


def test_the_email_check_passes_while_emails_are_accepted():
    result, seen = _email_check(200, {"ok": True, "sent_24h": 4})
    assert result.ok and result.detail == "4 sent in 24h, none failing"
    assert seen["auth"] == "Bearer k"


def test_the_email_check_fails_with_the_mail_server_error():
    body = {
        "ok": False, "failed_24h": 3, "last_failed_template": "quality_alarm",
        "last_failed_at": "2026-10-04T13:00:00Z", "last_error": "SMTPAuthenticationError: (535, b'bad credentials')",
    }
    result, _ = _email_check(200, body)
    assert not result.ok
    assert "quality_alarm" in result.detail and "535" in result.detail and "3 failed in 24h" in result.detail


def test_the_email_check_says_when_the_key_is_not_a_superusers():
    result, _ = _email_check(403)
    assert not result.ok and "not a superuser" in result.detail


def test_the_email_check_can_be_switched_off():
    from monitor.checks import check_names

    assert "email" in check_names(_config())
    assert "email" not in check_names(_config(email_check=False))


# --- Setup ---

def test_setup_creates_the_mesh_and_retries_a_taken_gateway_number(monkeypatch, capsys):
    import httpx

    from mesh_things.client import MeshThings
    from monitor import setup as monitor_setup

    attempts = []

    def handler(request):
        path = request.url.path
        if path == "/meshes/terms":
            return httpx.Response(404, json={"detail": "Not found."})
        if path == "/meshes":
            return httpx.Response(201, json={"id": "mesh-1"})
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(409, json={"detail": "Node number taken."})
        return httpx.Response(201, json={"node_id": 0x10000001, "uuid": "gw-1"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        monitor_setup, "MeshThings",
        lambda url, key: MeshThings(url, key, http=httpx.Client(transport=transport)),
    )
    monitor_setup.setup("http://api.test", "k", "LongFast", accept_terms=False, with_sink=False)

    out = capsys.readouterr().out
    assert len(attempts) == 2
    assert "MONITOR__MESH_ID=mesh-1" in out and "MONITOR__GATEWAY_UUID=gw-1" in out
