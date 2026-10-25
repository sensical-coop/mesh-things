"""The individual checks, run against the stack from outside: its public HTTP API and MQTT."""
import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import aiomqtt
import httpx
import structlog
from mesh_things.client import ApiError, AsyncMeshThings, Forbidden

from monitor import packets
from monitor.config import Config

log = structlog.get_logger()

EMAIL = "email"
HTTP_CHECKS = ("api_root", "api_health", "api_schema", "readings_api", EMAIL)
INGESTION = "ingestion"
REGISTRY_SIGHTING = "registry_sighting"
SINK = "sink"
PROBE_CHECKS = (INGESTION, REGISTRY_SIGHTING, SINK)

LATEST_KIND = "telemetry:device_metrics"
MARKER_CHANNEL = "device_metrics.uptime_seconds"


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    latency_s: float | None
    checked_at: float

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "detail": self.detail,
            "latency_s": None if self.latency_s is None else round(self.latency_s, 3),
            "checked_at": iso(self.checked_at),
        }


def iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(timespec="seconds")


def check_names(config: Config) -> tuple[str, ...]:
    """Every check this configuration runs, in report order."""
    probe = (INGESTION, REGISTRY_SIGHTING, SINK) if config.sink_enabled else (INGESTION, REGISTRY_SIGHTING)
    http = HTTP_CHECKS if config.email_check else tuple(name for name in HTTP_CHECKS if name != EMAIL)
    return http + probe


def _result(name: str, ok: bool, detail: str, started: float | None = None) -> CheckResult:
    latency = None if started is None else time.monotonic() - started
    return CheckResult(name, ok, detail, latency, time.time())


def marker_in_latest(body: dict) -> int | None:
    """The marker value in a readings `latest` response, if the channel is there."""
    for series in body.get("series") or []:
        if series.get("channel") == MARKER_CHANNEL and series.get("points"):
            return series["points"][-1].get("value")
    return None


def marker_in_sink_message(payload: bytes, node_id: int) -> int | None:
    try:
        event = json.loads(payload)
    except ValueError:
        return None
    if event.get("node_id") != node_id:
        return None
    return ((event.get("payload") or {}).get("device_metrics") or {}).get("uptime_seconds")


class Checker:
    """Runs checks against one configured instance."""

    def __init__(self, config: Config):
        self.config = config

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.config.http_timeout_s)

    def _api(self, http: httpx.AsyncClient, authenticated: bool = True) -> AsyncMeshThings:
        return AsyncMeshThings(self.config.api_url, self.config.api_key if authenticated else None, http=http)

    def _path(self, name: str) -> str:
        if name == "readings_api":
            return f"readings/devices/{self.config.gateway_uuid}/latest"
        return {"api_root": "", "api_health": "health", "api_schema": "schema"}[name]

    async def _get(self, name: str, http: httpx.AsyncClient):
        """One HTTP check's request. Public routes are called without credentials, as any visitor would."""
        if name == "api_health":
            return await self._api(http, authenticated=False).health.get()
        if name == "readings_api":
            return await self._latest(self._api(http))
        # The root and the schema are not API operations, so they are plain GETs.
        # Followed as aiohttp did before, so a redirect to the right place still passes.
        resp = await http.get(f"{self.config.api_url}/{self._path(name)}", follow_redirects=True)
        if resp.status_code != 200:
            raise ApiError(resp.status_code, f"HTTP {resp.status_code}")
        return None

    async def _latest(self, api: AsyncMeshThings) -> dict:
        return await api.readings.devices_latest_get(self.config.gateway_uuid, payload_kind=LATEST_KIND, lookback="-1d")

    async def http_check(self, name: str) -> CheckResult:
        """One HTTP route answers 200 within the timeout."""
        if name == EMAIL:
            return await self.email_check()
        path = self._path(name)
        started = time.monotonic()
        try:
            async with self._http() as http:
                await self._get(name, http)
        except ApiError as e:
            return _result(name, False, f"HTTP {e.status} from /{path}", started)
        except httpx.TimeoutException:
            return _result(name, False, f"/{path} timed out after {self.config.http_timeout_s}s", started)
        except httpx.HTTPError as e:
            return _result(name, False, f"/{path} unreachable: {type(e).__name__}", started)
        return _result(name, True, "ok", started)

    async def email_check(self) -> CheckResult:
        """Registry's emails are being accepted by its mail server: the latest send did not fail.

        Reads the superuser-only status route, so the monitor's key must be a superuser's.
        """
        started = time.monotonic()
        try:
            async with self._http() as http:
                body = await self._api(http).status.email_get()
        except Forbidden:
            return _result(EMAIL, False, "the monitor's API key is not a superuser's, so /status/email is refused", started)
        except ApiError as e:
            return _result(EMAIL, False, f"HTTP {e.status} from /status/email", started)
        except httpx.TimeoutException:
            return _result(EMAIL, False, f"/status/email timed out after {self.config.http_timeout_s}s", started)
        except httpx.HTTPError as e:
            return _result(EMAIL, False, f"/status/email unreachable: {type(e).__name__}", started)
        if not body.get("ok"):
            return _result(
                EMAIL,
                False,
                f"the last email ({body.get('last_failed_template')}, {body.get('last_failed_at')}) failed: "
                f"{body.get('last_error')}; {body.get('failed_24h')} failed in 24h",
                started,
            )
        return _result(EMAIL, True, f"{body.get('sent_24h')} sent in 24h, none failing", started)

    async def _last_seen(self, api: AsyncMeshThings) -> str | None:
        device = await api.devices.get(self.config.gateway_uuid)
        return device.get("last_seen")

    async def _publish(self, topic: str, payload: bytes) -> None:
        c = self.config
        async with aiomqtt.Client(
            c.mqtt_broker,
            port=c.mqtt_port,
            username=c.mqtt_user or None,
            password=c.mqtt_pass or None,
            tls_params=aiomqtt.TLSParameters() if c.mqtt_ssl else None,
            timeout=c.http_timeout_s,
        ) as client:
            await client.publish(topic, payload=payload, qos=1)

    async def _await_reading(self, api: AsyncMeshThings, marker: int, started: float, deadline: float) -> CheckResult:
        last = "no reading yet"
        while True:
            try:
                value = marker_in_latest(await self._latest(api))
                if value == marker:
                    return _result(INGESTION, True, "probe reached the readings API", started)
                last = f"latest {MARKER_CHANNEL} is {value}"
            except (httpx.HTTPError, ApiError) as e:
                last = str(e) or type(e).__name__
            if time.monotonic() >= deadline:
                return _result(INGESTION, False, f"probe {marker} not in the readings API in time ({last})", started)
            await asyncio.sleep(self.config.poll_s)

    async def _await_sighting(self, api: AsyncMeshThings, baseline: str | None, started: float,
                              deadline: float) -> CheckResult:
        last = "last_seen unchanged"
        while True:
            try:
                seen = await self._last_seen(api)
                if seen and seen != baseline:
                    return _result(REGISTRY_SIGHTING, True, "gateway last_seen advanced", started)
            except (httpx.HTTPError, ApiError) as e:
                last = str(e) or type(e).__name__
            if time.monotonic() >= deadline:
                return _result(REGISTRY_SIGHTING, False, f"gateway not sighted by the registry in time ({last})", started)
            await asyncio.sleep(self.config.poll_s)

    async def _await_sink(self, marker: int, subscribed: asyncio.Event, deadline_s: float) -> CheckResult:
        c = self.config
        started = time.monotonic()

        async def delivered() -> CheckResult:
            async with aiomqtt.Client(
                c.sink_broker,
                port=c.sink_port,
                username=c.sink_user or None,
                password=c.sink_pass or None,
                tls_params=aiomqtt.TLSParameters() if c.sink_ssl else None,
            ) as client:
                await client.subscribe(c.sink_topic, qos=1)
                subscribed.set()
                async for message in client.messages:
                    if marker_in_sink_message(message.payload, c.gateway_node_id) == marker:
                        return _result(SINK, True, "probe delivered on the sink", started)
            return _result(SINK, False, "sink subscription ended", started)

        # wait_for rather than asyncio.timeout(), which needs Python 3.11; the package supports 3.10.
        try:
            return await asyncio.wait_for(delivered(), deadline_s)
        except asyncio.TimeoutError:
            return _result(SINK, False, f"probe {marker} not delivered on the sink in time", started)
        except aiomqtt.MqttError as e:
            return _result(SINK, False, f"sink broker: {e}", started)
        finally:
            subscribed.set()

    async def probe(self, timeout_s: float | None = None) -> list[CheckResult]:
        """Publish one probe and follow it to the readings API, the registry and the sink."""
        c = self.config
        timeout_s = timeout_s or c.ingest_timeout_s
        marker = int(time.time())
        topic, payload = packets.build_probe(c.gateway_node_id, c.channel_id, c.psk_b64, c.mqtt_topic_prefix, marker)

        async with self._http() as http:
            api = self._api(http)
            try:
                baseline = await self._last_seen(api)
            except (httpx.HTTPError, ApiError):
                baseline = None

            sink_task = None
            if c.sink_enabled:
                subscribed = asyncio.Event()
                sink_task = asyncio.create_task(self._await_sink(marker, subscribed, timeout_s + c.http_timeout_s))
                await subscribed.wait()

            started = time.monotonic()
            try:
                await self._publish(topic, payload)
            except (aiomqtt.MqttError, OSError) as e:
                if sink_task:
                    sink_task.cancel()
                log.warning("probe_publish_failed", error=str(e))
                failed = [_result(INGESTION, False, f"publish failed: {e}", started)]
                failed.append(_result(REGISTRY_SIGHTING, False, "not run: publish failed"))
                if c.sink_enabled:
                    failed.append(_result(SINK, False, "not run: publish failed"))
                return failed

            deadline = started + timeout_s
            waits = [
                self._await_reading(api, marker, started, deadline),
                self._await_sighting(api, baseline, started, deadline),
            ]
            if sink_task:
                waits.append(sink_task)
            return list(await asyncio.gather(*waits))
