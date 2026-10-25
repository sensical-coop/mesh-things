"""Email alerts: the conditions for sending them, and delivery through the monitor's own SMTP settings."""
import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

import structlog

from monitor.checks import CheckResult
from monitor.config import Config

log = structlog.get_logger()

ALERT = "alert"
REMINDER = "reminder"
RECOVERED = "recovered"


@dataclass(frozen=True)
class Alert:
    kind: str
    failing: tuple[str, ...]


class AlertState:
    """Tracks consecutive failures per check and decides which email, if any, is due.

    A check is failing once it has failed `threshold` times in a row. An alert goes
    out when a check starts failing, a reminder every `reminder_s` while any still
    fails, and one recovery email when none does.
    """

    def __init__(self, threshold: int, reminder_s: float):
        self.threshold = threshold
        self.reminder_s = reminder_s
        self.consecutive: dict[str, int] = {}
        self.alerted: set[str] = set()
        self.last_sent_at: float | None = None

    def failing(self) -> set[str]:
        return {name for name, count in self.consecutive.items() if count >= self.threshold}

    def record(self, results: list[CheckResult], now: float) -> Alert | None:
        for result in results:
            self.consecutive[result.name] = 0 if result.ok else self.consecutive.get(result.name, 0) + 1
        failing = self.failing()

        kind = None
        if failing - self.alerted:
            kind = ALERT
        elif failing and self.reminder_s and now - (self.last_sent_at or 0) >= self.reminder_s:
            kind = REMINDER
        elif not failing and self.alerted:
            kind = RECOVERED
        # Forget recovered checks, so failing again alerts again.
        self.alerted = failing
        if kind is None:
            return None
        self.last_sent_at = now
        return Alert(kind, tuple(sorted(failing)))


def compose(alert: Alert, latest: dict[str, CheckResult], config: Config) -> tuple[str, str]:
    """Subject and plain-text body of an alert email."""
    if alert.kind == RECOVERED:
        return f"Recovered: every check passes - {config.name}", f"Every server check on {config.name} passes again.\n"
    prefix = "Still failing" if alert.kind == REMINDER else "Failing"
    subject = f"{prefix}: {', '.join(alert.failing)} - {config.name}"
    lines = [f"Server checks failing on {config.name}:", ""]
    for name in alert.failing:
        result = latest.get(name)
        lines.append(f"- {name}: {result.detail if result else 'no result'}")
    lines += ["", f"Checks run every {config.interval_s}s from the server monitor."]
    return subject, "\n".join(lines) + "\n"


def _send_sync(config: Config, subject: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.email_from
    message["To"] = ", ".join(config.alert_emails)
    message.set_content(body)
    smtp_class = smtplib.SMTP_SSL if config.email_use_ssl else smtplib.SMTP
    with smtp_class(config.email_host, config.email_port, timeout=30) as smtp:
        if config.email_use_tls and not config.email_use_ssl:
            smtp.starttls()
        if config.email_user:
            smtp.login(config.email_user, config.email_password)
        smtp.send_message(message)


async def send_email(config: Config, subject: str, body: str) -> bool:
    """Email every alert recipient; False when there are none or sending failed."""
    if not config.alert_emails or not config.email_host:
        log.warning("alert_not_emailed", reason="no recipients or SMTP host", subject=subject)
        return False
    try:
        await asyncio.to_thread(_send_sync, config, subject, body)
    except (smtplib.SMTPException, OSError) as e:
        log.error("alert_email_failed", error=str(e), subject=subject)
        return False
    log.info("alert_emailed", subject=subject, recipients=len(config.alert_emails))
    return True
