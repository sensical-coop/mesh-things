"""The monitor's own HTTP API, for Uptime Robot and similar probes."""
import hmac

from aiohttp import web

from monitor.checks import CheckResult, iso
from monitor.service import Monitor

MONITOR_KEY = web.AppKey("monitor", Monitor)


def _body(monitor: Monitor, results: dict[str, CheckResult | None], cached: bool | None = None) -> dict:
    ok = bool(results) and all(r is not None and r.ok for r in results.values())
    checked = [r.checked_at for r in results.values() if r is not None]
    checks = {}
    for name, result in results.items():
        entry = result.as_dict() if result else {"ok": False, "detail": "not run yet", "latency_s": None, "checked_at": None}
        entry["consecutive_failures"] = monitor.alerts.consecutive.get(name, 0)
        checks[name] = entry
    body = {
        "ok": ok,
        "checked_at": iso(max(checked)) if checked else None,
        "alerting": monitor.alerting,
        "checks": checks,
    }
    if cached is not None:
        body["cached"] = cached
    return body


def _respond(body: dict) -> web.Response:
    return web.json_response(body, status=200 if body["ok"] else 503)


def _check_name(monitor: Monitor, request: web.Request) -> str | None:
    name = request.match_info.get("check")
    if name is not None and name not in monitor.names:
        raise web.HTTPNotFound(text=f"Unknown check {name!r}")
    return name


async def health(request: web.Request) -> web.Response:
    if request.app[MONITOR_KEY].is_alive():
        return web.json_response({"status": "ok"})
    return web.json_response({"status": "stalled"}, status=503)


async def status(request: web.Request) -> web.Response:
    monitor = request.app[MONITOR_KEY]
    name = _check_name(monitor, request)
    names = monitor.names if name is None else (name,)
    return _respond(_body(monitor, {n: monitor.latest.get(n) for n in names}))


def _authorize(request: web.Request, token: str) -> None:
    # Unset token: the routes do not exist, rather than being open.
    if not token:
        raise web.HTTPNotFound()
    header = request.headers.get("Authorization", "")
    given = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else request.query.get("token", "")
    if not hmac.compare_digest(given.encode(), token.encode()):
        raise web.HTTPUnauthorized(text="Missing or wrong token")


def _timeout(request: web.Request, cap: float) -> float | None:
    raw = request.query.get("timeout")
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        raise web.HTTPBadRequest(text="timeout must be a number of seconds")
    if value <= 0:
        raise web.HTTPBadRequest(text="timeout must be positive")
    return min(value, cap)


async def run(request: web.Request) -> web.Response:
    monitor = request.app[MONITOR_KEY]
    _authorize(request, monitor.config.run_token)
    name = _check_name(monitor, request)
    results, cached = await monitor.run(only=name, timeout_s=_timeout(request, monitor.config.ingest_timeout_s))
    return _respond(_body(monitor, {r.name: r for r in results}, cached=cached))


def build_app(monitor: Monitor) -> web.Application:
    app = web.Application()
    app[MONITOR_KEY] = monitor
    app.router.add_get("/health", health)
    app.router.add_get("/status", status)
    app.router.add_get("/status/{check}", status)
    for path in ("/run", "/run/{check}"):
        # GET too: Uptime Robot's free plan only sends GET and HEAD.
        app.router.add_get(path, run, allow_head=False)
        app.router.add_post(path, run)
    return app
