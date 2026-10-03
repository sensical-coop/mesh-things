"""Samples of unregistered gateways' traffic, for the registry to match against meshes with discovery on."""
import base64
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

from common import sources

# A gateway is forgotten after this many quiet windows. Kept well above one, or a
# gateway sending less often than the delay would be seen as new on every packet and
# never be sent once the immediate budget is spent.
IDLE_WINDOWS = 4


def candidate_topic() -> str:
    return os.environ.get("REGISTRY__GATEWAY_CANDIDATES_KAFKA_TOPIC", "mesh.gateway_candidates.v1")


def parse_candidate(topic: str) -> tuple[str | None, str, str] | None:
    """Return (source_id, channel_id, gateway_id) for an encrypted-feed topic, else None.

    Only `.../2/e/<channel>/!<gateway>` carries a ServiceEnvelope; json and map topics don't.
    """
    source_id = sources.source_id_from_topic(topic)
    remote = topic
    if source_id is not None:
        remote = topic[len(sources.local_topic_prefix(source_id)) + 1:]
    levels = remote.split("/")
    if len(levels) < 3 or levels[-3] != "e" or not levels[-2] or not levels[-1].startswith("!"):
        return None
    return source_id, levels[-2], levels[-1]


def candidate_event(source_id: str | None, channel_id: str, gateway_id: str, payload: bytes) -> tuple[str, dict]:
    """The Kafka key and value of one sample."""
    key = f"{source_id or 'own'}:{gateway_id}"
    return key, {
        "source_id": source_id,
        "channel_id": channel_id,
        "gateway_id": gateway_id,
        "seen_at": datetime.now(timezone.utc).isoformat(),
        "sample_b64": base64.b64encode(payload).decode("ascii"),
    }


@dataclass
class _Seen:
    first_seen: float
    last_packet: float
    last_sent: float | None = None


class DiscoveryPacer:
    """Decides which unregistered gateways' packets are sent to the registry.

    The first `immediate_gateways` new gateways in any `delay_seconds` window are sent
    at once, so a quiet private mesh is found straight away. Once that budget is
    spent, a new gateway waits `delay_seconds` from when it was first seen, so a
    busy public broker can't flood the registry. Every gateway is retried at most
    once per `delay_seconds` after that, in case its packet didn't decode or its
    mesh switched discovery on later.
    """

    def __init__(self, immediate_gateways: int, delay_seconds: float, clock=time.monotonic):
        self.immediate_gateways = immediate_gateways
        self.delay_seconds = delay_seconds
        self._clock = clock
        self._immediate_grants: deque[float] = deque()
        self._seen: dict[tuple, _Seen] = {}
        self._last_prune = clock()

    @classmethod
    def from_env(cls) -> "DiscoveryPacer":
        return cls(
            immediate_gateways=int(os.environ.get("MQTT_BRIDGE__DISCOVERY__IMMEDIATE_GATEWAYS", 5)),
            delay_seconds=float(os.environ.get("MQTT_BRIDGE__DISCOVERY__DELAY_SECONDS", 900)),
        )

    def should_send(self, key: tuple) -> bool:
        now = self._clock()
        self._prune(now)
        seen = self._seen.get(key)
        if seen is None:
            seen = self._seen[key] = _Seen(first_seen=now, last_packet=now)
            if len(self._immediate_grants) < self.immediate_gateways:
                self._immediate_grants.append(now)
                seen.last_sent = now
                return True
            return False
        seen.last_packet = now
        since = seen.first_seen if seen.last_sent is None else seen.last_sent
        if now - since < self.delay_seconds:
            return False
        seen.last_sent = now
        return True

    def __len__(self) -> int:
        return len(self._seen)

    def _prune(self, now: float) -> None:
        while self._immediate_grants and now - self._immediate_grants[0] >= self.delay_seconds:
            self._immediate_grants.popleft()
        # Pruning every entry is linear, so it runs at most once per window.
        if now - self._last_prune < self.delay_seconds:
            return
        self._last_prune = now
        idle_after = IDLE_WINDOWS * self.delay_seconds
        idle = [key for key, seen in self._seen.items() if now - seen.last_packet >= idle_after]
        for key in idle:
            del self._seen[key]
