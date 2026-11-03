"""Alarms already raised, so an hourly scan does not repeat them."""

import os

import redis


class AlarmMemory:
    """Remembers raised alarms in Redis, so a scan does not repeat one an earlier scan raised."""

    def __init__(self, client: redis.Redis):
        self._client = client

    def first_time(self, key: str, ttl_seconds: int) -> bool:
        """True the first time `key` is seen within `ttl_seconds`."""
        return bool(self._client.set(f"quality:alarmed:{key}", 1, nx=True, ex=max(1, int(ttl_seconds))))


_memory: AlarmMemory | None = None


def get_alarm_memory() -> AlarmMemory:
    global _memory
    if _memory is None:
        _memory = AlarmMemory(redis.Redis.from_url(os.environ.get("QUALITY_WORKER__REDIS_URL", "redis://redis:6379/2")))
    return _memory
