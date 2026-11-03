"""Runs rounds of checks, on a schedule or on request, and keeps their latest results."""
import asyncio
import time

import structlog

from monitor import alerts
from monitor.checks import HTTP_CHECKS, PROBE_CHECKS, Checker, CheckResult, check_names
from monitor.config import Config

log = structlog.get_logger()


class Monitor:
    def __init__(self, config: Config, checker: Checker, send=alerts.send_email, clock=time.time):
        self.config = config
        self.checker = checker
        self.send = send
        self.clock = clock
        self.names = check_names(config)
        self.alerts = alerts.AlertState(config.failures_before_alert, config.reminder_hours * 3600)
        self.latest: dict[str, CheckResult] = {}
        self.alerting = True
        self.started_at: float | None = None
        self.last_round_at: float | None = None
        self._probe_task: asyncio.Task | None = None
        self._probe_results: list[CheckResult] = []
        self._probe_finished_at = 0.0

    async def _probe(self, timeout_s: float | None, reuse_recent: bool) -> tuple[list[CheckResult], bool]:
        """Results of a probe, and whether this call started it.

        A call made while a probe is in flight shares that probe, and an on-demand
        call shortly after one finished gets its results, so requests never publish
        more than one probe at a time or in quick succession.
        """
        if self._probe_task and not self._probe_task.done():
            return await asyncio.shield(self._probe_task), False
        recent = self.clock() - self._probe_finished_at < self.config.run_min_interval_s
        if reuse_recent and self._probe_results and recent:
            return self._probe_results, False
        self._probe_task = asyncio.create_task(self._run_probe(timeout_s))
        return await asyncio.shield(self._probe_task), True

    async def _run_probe(self, timeout_s: float | None) -> list[CheckResult]:
        results = await self.checker.probe(timeout_s)
        self._probe_results = results
        self._probe_finished_at = self.clock()
        return results

    async def run(self, only: str | None = None, timeout_s: float | None = None, on_demand: bool = True):
        """Run every check, or only one, and return (results, cached).

        `cached` is true when the probe results come from a probe this call did not
        start. Those are recorded once, by the call that started it.
        """
        names = self.names if only is None else (only,)
        http = [name for name in names if name in HTTP_CHECKS]
        results = list(await asyncio.gather(*(self.checker.http_check(name) for name in http)))
        to_record = list(results)
        cached = False
        if any(name in PROBE_CHECKS for name in names):
            probe_results, fresh = await self._probe(timeout_s, reuse_recent=on_demand)
            cached = not fresh
            if fresh:
                to_record += probe_results
            results += [r for r in probe_results if r.name in names]
        await self._record(to_record)
        return results, cached

    async def _record(self, results: list[CheckResult]) -> None:
        for result in results:
            self.latest[result.name] = result
        alert = self.alerts.record(results, self.clock())
        if alert is None:
            return
        subject, body = alerts.compose(alert, self.latest, self.config)
        log.warning("alert", kind=alert.kind, failing=alert.failing)
        self.alerting = await self.send(self.config, subject, body)

    async def loop(self) -> None:
        self.started_at = self.clock()
        while True:
            try:
                results, _ = await self.run(on_demand=False)
                log.info("round", failing=[r.name for r in results if not r.ok])
            except Exception:
                log.exception("round_failed")
            self.last_round_at = self.clock()
            await asyncio.sleep(self.config.interval_s)

    def is_alive(self) -> bool:
        """The loop is running and has completed a round recently, or is still on its first."""
        since = self.last_round_at or self.started_at
        if since is None:
            return False
        limit = 2 * self.config.interval_s + self.config.ingest_timeout_s
        return self.clock() - since <= limit
