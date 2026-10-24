"""Background worker: emails a device's owner when a quality alarm is triggered.

  python manage.py consume_quality_alarms

Consumes mesh.telemetry.alarms.v1:
- Flink stream jobs (flat_value/range/absence)
- quality_worker's batch checks (completeness).

The first alarm on a device is emailed and opens a window of
REGISTRY__ALARM_EMAIL_COOLDOWN_SECONDS (or the owner's own
`alarm_email_cooldown_seconds`). Every later alarm on that device, from any
detector or channel, is held in Redis and sent as one summary when the window
closes. A cooldown of 0 emails every alarm.

Exceptions:
- `absence` is emailed straight away, even during an open window, since a
  device going silent alarms only once. At most one is emailed per device per
  ABSENCE_EMAIL_INTERVAL_SECONDS; later ones are treated like `repeat`, so a
  device publishing slower than configured does not email all day.
- Alarms marked `repeat` re-raise a condition already emailed when it started.
  They are counted in an open window's summary. Outside a window, one is emailed
  as a reminder once REGISTRY__ALARM_REMINDER_HOURS (default 24, 0 for never)
  have passed since the condition was last emailed, so a long silence means the
  device is fine rather than that alarms stopped.
- Alarms marked `replay` come from history being reprocessed, not from a
  device reporting now, and are never emailed.
"""
import json
import os
import time
from datetime import datetime, timezone

import redis
import structlog
from django.conf import settings
from django.core.management.base import BaseCommand

from kafka import KafkaConsumer

from mesh_things.detectors import ABSENCE
from registry.consumer_loop import consume_forever
from registry.emailing import console_url, default_alarm_email_cooldown_seconds, send_templated_email
from registry.models import Device

log = structlog.get_logger()

# Server-wide default; an owner's own `alarm_email_cooldown_seconds` overrides this.
ALARM_EMAIL_COOLDOWN_SECONDS = default_alarm_email_cooldown_seconds()

# Sorted set of open windows ("<mesh_id>:<device_id>"), scored by when each closes.
WINDOWS_KEY = "registry:alarm-windows"
HELD_KEY_PREFIX = "registry:alarm-held:"
ABSENCE_EMAILED_KEY_PREFIX = "registry:absence-emailed:"
ABSENCE_EMAIL_INTERVAL_SECONDS = 24 * 3600
# When each ongoing condition ("<window>|<detector>|<channel>") was last emailed, and
# since when it holds. Refreshed by its hourly re-raises, so it lapses once they stop.
CONDITION_KEY_PREFIX = "registry:alarm-condition:"
CONDITION_TTL_SECONDS = 2 * 24 * 3600
ALARM_REMINDER_SECONDS = int(float(os.environ.get("REGISTRY__ALARM_REMINDER_HOURS", "24")) * 3600)

_redis = None


def redis_client() -> redis.Redis:
    """Raw client on the cache's Redis, for the sorted set and hashes the cache API lacks."""
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(settings.CACHES["default"]["LOCATION"], decode_responses=True)
    return _redis

DETECTOR_SUBJECTS = {
    "absence": "Device has stopped publishing",
    "completeness": "Device readings have gaps",
    "flat_value": "Sensor value is flat",
    "range": "Sensor value is out of range",
}


class Command(BaseCommand):
    help = "Consume mesh.telemetry.alarms.v1 and email the device owner - see module docstring."

    def handle(self, *args, **options):
        bootstrap_servers = os.environ["KAFKA_BOOTSTRAP"]
        topic = os.environ.get("PATTERN_DETECTION__ALARMS_TOPIC", "mesh.telemetry.alarms.v1")
        consumer = KafkaConsumer(
            bootstrap_servers=bootstrap_servers,
            group_id="registry-quality-alarms-group",
            enable_auto_commit=False,
            auto_offset_reset="latest", # avoid bursting
        )
        consumer.subscribe([topic])
        log.info("Starting quality-alarms consumer", topic=topic)
        consume_forever(consumer, self._handle_record, "handle quality alarm", tick=self.flush_due_windows)

    @staticmethod
    def _handle_record(value: bytes) -> None:
        Command._handle(json.loads(value))

    @staticmethod
    def _handle(event: dict, now: float | None = None) -> None:
        now = time.time() if now is None else now
        detector = event.get("detector")
        if event.get("replay"):
            log.debug("Skipping replayed alarm", detector=detector)
            return
        mesh_id, device_id = event.get("mesh_id"), event.get("device_id")
        if not detector or not mesh_id or device_id is None:
            log.debug("Skipping unroutable alarm", detector=detector)
            return

        device = (
            Device.objects.select_related("mesh__owner")
            .filter(mesh_id=mesh_id, device_id=int(device_id))
            .first()
        )
        if device is None:
            # Deleted between the alarm trigger and now?
            log.info("Alarm for unknown device, skipping", mesh_id=mesh_id, device_id=device_id)
            return
        owner = device.mesh.owner
        if not owner.email or not owner.is_active:
            log.info("Owner has no verified email, skipping", owner_id=str(owner.id))
            return

        cooldown_seconds = owner.alarm_email_cooldown_seconds
        if cooldown_seconds is None:
            cooldown_seconds = ALARM_EMAIL_COOLDOWN_SECONDS

        window = f"{device.mesh_id}:{device.device_id}"
        repeat = bool(event.get("repeat"))
        if detector == ABSENCE and not repeat:
            last_emailed = redis_client().get(ABSENCE_EMAILED_KEY_PREFIX + window)
            repeat = last_emailed is not None and now - float(last_emailed) < ABSENCE_EMAIL_INTERVAL_SECONDS
            if not repeat:
                redis_client().set(ABSENCE_EMAILED_KEY_PREFIX + window, now, ex=ABSENCE_EMAIL_INTERVAL_SECONDS)
        opened = False
        if cooldown_seconds > 0:
            r = redis_client()
            closes_at = r.zscore(WINDOWS_KEY, window)
            if closes_at is not None and closes_at <= now:
                # The tick hasn't closed it yet, so close it before opening a new one.
                Command._flush_window(window, now)
                closes_at = None
            if closes_at is not None and (repeat or detector != ABSENCE):
                Command._hold(window, event)
                log.debug("Alarm held for the summary", window=window, detector=detector)
                return
            if closes_at is None and not repeat:
                r.zadd(WINDOWS_KEY, {window: now + cooldown_seconds})
                opened = True
        if repeat:
            if detector != ABSENCE and Command._reminder_due(window, event, now):
                Command._send_alarm_email(device, event, cooldown_seconds, since=Command._since(window, event), reminder=True)
                Command._remember(window, event, now)
                return
            log.debug("Repeat of an alarm already emailed, not sent", detector=detector)
            return

        try:
            Command._send_alarm_email(device, event, cooldown_seconds)
            Command._remember(window, event, now)
        except Exception:
            if opened:
                # Without the first email, later alarms must not be held silently.
                redis_client().zrem(WINDOWS_KEY, window)
            if detector == ABSENCE:
                redis_client().delete(ABSENCE_EMAILED_KEY_PREFIX + window)
            raise

    @staticmethod
    def _condition_key(window: str, detector: str | None, channel: str | None) -> str:
        return f"{CONDITION_KEY_PREFIX}{window}|{detector}|{channel or ''}"

    @staticmethod
    def _since(window: str, event: dict) -> str | None:
        raw = redis_client().get(Command._condition_key(window, event.get("detector"), event.get("channel")))
        return json.loads(raw).get("since") if raw else None

    @staticmethod
    def _remember(window: str, event: dict, now: float) -> None:
        """Note that the condition was just emailed, keeping when it started."""
        since = Command._since(window, event) or event.get("triggered_at")
        redis_client().set(
            Command._condition_key(window, event.get("detector"), event.get("channel")),
            json.dumps({"emailed_at": now, "since": since}),
            ex=CONDITION_TTL_SECONDS,
        )

    @staticmethod
    def _reminder_due(window: str, event: dict, now: float) -> bool:
        """Whether a re-raise should be emailed as a reminder.

        A condition with no record started before this was tracked, as after an
        upgrade, so it is reminded at once.
        """
        if ALARM_REMINDER_SECONDS <= 0:
            return False
        key = Command._condition_key(window, event.get("detector"), event.get("channel"))
        raw = redis_client().get(key)
        if raw is None:
            return True
        if now - json.loads(raw)["emailed_at"] >= ALARM_REMINDER_SECONDS:
            return True
        redis_client().expire(key, CONDITION_TTL_SECONDS)
        return False

    @staticmethod
    def _hold(window: str, event: dict) -> None:
        key = HELD_KEY_PREFIX + window
        field = f"{event.get('detector')}|{event.get('channel') or ''}"
        r = redis_client()
        entry = json.loads(r.hget(key, field) or "null") or {
            "count": 0,
            "first_triggered_at": event.get("triggered_at"),
        }
        entry["count"] += 1
        entry["last_triggered_at"] = event.get("triggered_at")
        entry["last_value"] = event.get("value")
        entry["last_message"] = event.get("message")
        r.hset(key, field, json.dumps(entry))

    @staticmethod
    def flush_due_windows(now: float | None = None) -> None:
        """Close every window that has ended, emailing a summary where alarms were held."""
        now = time.time() if now is None else now
        for window in redis_client().zrangebyscore(WINDOWS_KEY, "-inf", now):
            try:
                Command._flush_window(window, now)
            except Exception as e:
                # Left open, so the next tick retries it.
                log.warning("Failed to send alarm summary", window=window, error=str(e))

    @staticmethod
    def _flush_window(window: str, now: float | None = None) -> None:
        r = redis_client()
        key = HELD_KEY_PREFIX + window
        held = r.hgetall(key)
        if held:
            Command._send_summary_email(window, held, now)
        pipe = r.pipeline()
        pipe.delete(key)
        pipe.zrem(WINDOWS_KEY, window)
        pipe.execute()

    @staticmethod
    def _send_alarm_email(device: Device, event: dict, cooldown_seconds: int, since: str | None = None, reminder: bool = False) -> None:
        """Email one alarm; with `reminder`, as a condition still holding since `since`."""
        owner = device.mesh.owner
        detector = event.get("detector")
        prefix = "Still active: " if reminder else ""
        send_templated_email(
            to_email=owner.email,
            subject=f"[Mesh Things] {prefix}{DETECTOR_SUBJECTS.get(detector, 'Data quality alarm')}"
            f" - {_device_label(device)}",
            template_name="quality_alarm",
            context={
                **_device_context(device),
                "channel": event.get("channel"),
                "detector": detector,
                "detector_summary": DETECTOR_SUBJECTS.get(detector, "Data quality alarm"),
                "message": event.get("message"),
                "value": event.get("value"),
                "source": event.get("source"),
                "triggered_at": event.get("triggered_at"),
                "cooldown_hours": round(cooldown_seconds / 3600, 1) if cooldown_seconds else 0,
                "details": _device_details(device)
                + ([{"label": "Channel", "value": event["channel"], "mono": True}] if event.get("channel") else [])
                + ([{"label": "Ongoing since", "value": _when(since)}] if reminder and since else [])
                + [{"label": "Last detected" if reminder else "Detected", "value": _when(event.get("triggered_at"))}],
                "reminder": reminder,
                "since": _when(since),
                "reminder_hours": round(ALARM_REMINDER_SECONDS / 3600, 1),
            },
        )
        log.info("Sent quality alarm email", detector=detector, device_id=device.device_id)

    @staticmethod
    def _send_summary_email(window: str, held: dict, now: float | None = None) -> None:
        mesh_id, device_id = window.rsplit(":", 1)
        device = (
            Device.objects.select_related("mesh__owner")
            .filter(mesh_id=mesh_id, device_id=int(device_id))
            .first()
        )
        if device is None:
            log.info("Summary for a deleted device, dropping", window=window)
            return
        owner = device.mesh.owner
        if not owner.email or not owner.is_active:
            log.info("Owner has no verified email, dropping summary", owner_id=str(owner.id))
            return

        alarms = []
        for field, raw in held.items():
            detector, channel = field.split("|", 1)
            alarms.append({
                **json.loads(raw),
                "detector": detector,
                "detector_summary": DETECTOR_SUBJECTS.get(detector, "Data quality alarm"),
                "channel": channel or None,
            })
        alarms.sort(key=lambda a: a["first_triggered_at"] or "")
        for alarm in alarms:
            alarm["first_triggered_at"] = _when(alarm.get("first_triggered_at"))
            alarm["last_triggered_at"] = _when(alarm.get("last_triggered_at"))

        send_templated_email(
            to_email=owner.email,
            subject=f"[Mesh Things] Alarm summary - {_device_label(device)}",
            template_name="quality_alarm_summary",
            context={
                **_device_context(device),
                "alarms": alarms,
                "total": sum(a["count"] for a in alarms),
                "details": _device_details(device),
            },
        )
        log.info("Sent quality alarm summary", device_id=device.device_id, kinds=len(alarms))
        # A summary counts as emailing each of its conditions, so no reminder follows straight away.
        for alarm in alarms:
            Command._remember(
                window,
                {"detector": alarm["detector"], "channel": alarm["channel"], "triggered_at": alarm["first_triggered_at"]},
                time.time() if now is None else now,
            )


def _device_label(device: Device) -> str:
    return device.label or device.name or str(device.device_id)


def _device_context(device: Device) -> dict:
    return {
        "name": device.mesh.owner.name,
        "device_label": _device_label(device),
        "device_id": device.device_id,
        "device_link": console_url("devices", device.id),
        "mesh_label": device.mesh.label or device.mesh.channel_id,
        "mesh_link": console_url("meshes", device.mesh_id),
    }


def _device_details(device: Device) -> list[dict]:
    """The device and mesh rows of an alarm email's summary table, linked to the console."""
    context = _device_context(device)
    return [
        {"label": "Device", "value": f"{context['device_label']} (node {context['device_id']})", "href": context["device_link"]},
        {"label": "Mesh", "value": context["mesh_label"], "href": context["mesh_link"]},
    ]


def _when(value: str | None) -> str | None:
    """An event's ISO timestamp as `2026-09-06 12:00 UTC`, or as given when it is not one."""
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError):
        return value
