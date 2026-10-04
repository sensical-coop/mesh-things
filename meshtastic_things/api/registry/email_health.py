"""Whether registry's emails are reaching the mail server, for the status route and the monitor.

Every send records its outcome in Redis: the last success and the last failure, and
one entry per send in a sorted set trimmed to a day, so a count needs no scan.
"""
import time
import uuid

import redis
from django.conf import settings

HEALTH_KEY = "registry:email-health"
SENT_KEY = "registry:email-sent"
FAILED_KEY = "registry:email-failed"
WINDOW_S = 24 * 3600
# An SMTP error can carry the whole server reply; the status route needs the gist.
ERROR_MAX_CHARS = 300

_redis = None


def _client() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(settings.CACHES["default"]["LOCATION"], decode_responses=True)
    return _redis


def _record(key: str, fields: dict, now: float) -> None:
    pipe = _client().pipeline()
    pipe.hset(HEALTH_KEY, mapping=fields)
    pipe.zadd(key, {f"{now}:{uuid.uuid4().hex[:8]}": now})
    pipe.zremrangebyscore(key, "-inf", now - WINDOW_S)
    pipe.expire(key, WINDOW_S)
    pipe.execute()


def record_sent(template: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    _record(SENT_KEY, {"last_sent_at": now, "last_sent_template": template}, now)


def record_failed(template: str, error: Exception, now: float | None = None) -> None:
    now = time.time() if now is None else now
    message = f"{type(error).__name__}: {error}"[:ERROR_MAX_CHARS]
    _record(FAILED_KEY, {"last_failed_at": now, "last_failed_template": template, "last_error": message}, now)


def summary(now: float | None = None) -> dict:
    """Last success and failure, how many of each in the last day, and whether sending works.

    `ok` is false while the most recent send failed: one success afterwards clears it.
    """
    now = time.time() if now is None else now
    r = _client()
    health = r.hgetall(HEALTH_KEY)
    last_sent = float(health["last_sent_at"]) if health.get("last_sent_at") else None
    last_failed = float(health["last_failed_at"]) if health.get("last_failed_at") else None
    return {
        "ok": last_failed is None or (last_sent is not None and last_sent > last_failed),
        "last_sent_at": last_sent,
        "last_sent_template": health.get("last_sent_template"),
        "last_failed_at": last_failed,
        "last_failed_template": health.get("last_failed_template"),
        "last_error": health.get("last_error"),
        "sent_24h": r.zcount(SENT_KEY, now - WINDOW_S, "+inf"),
        "failed_24h": r.zcount(FAILED_KEY, now - WINDOW_S, "+inf"),
    }
