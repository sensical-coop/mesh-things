"""Which MQTT messages the bridge lets through to Kafka.

The broker lets any gateway publish Meshtastic traffic with a shared login, so that
unregistered gateways can be discovered. The bridge decides what counts: a
registered gateway's envelopes, on the source its mesh is on, at a sane rate.
"""
import os
import time

from mesh_things import codec

# Why a message stays out of Kafka, as counted on the bridge's /health.
NOT_ENVELOPE = "not_envelope"
UNPARSEABLE = "unparseable"
GATEWAY_MISMATCH = "gateway_mismatch"
UNREGISTERED = "unregistered"
WRONG_SOURCE = "wrong_source"
RATE_LIMITED = "rate_limited"

ENCRYPTED = "e"
MAP = "map"


def topic_kind(topic: str) -> str | None:
    """`e` for `.../2/e/<channel>/!<gateway>`, `map` for `.../2/map/`, else None.

    Only those carry a ServiceEnvelope; Meshtastic's json and stat topics do not.
    """
    levels = topic.split("/")
    if len(levels) >= 4 and levels[-4:-2] == ["2", ENCRYPTED] and levels[-1].startswith("!"):
        return ENCRYPTED
    if levels[-3:] == ["2", MAP, ""] or levels[-2:] == ["2", MAP]:
        return MAP
    return None


def envelope_gateway(payload: bytes) -> str | None:
    """The gateway a ServiceEnvelope names, or None when it does not parse or names none."""
    try:
        return codec.parse_envelope(payload).gateway_id or None
    except Exception:
        return None


class GatewayRate:
    """A token bucket per gateway: `rate` messages a second on average, in bursts of up to `burst`.

    Each bridge member keeps its own buckets, and a shared subscription splits a
    gateway's messages between members, so the cap applies per member.
    """

    def __init__(self, rate: float, burst: int, clock=time.monotonic):
        self.rate = rate
        self.burst = burst
        self.clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}

    @classmethod
    def from_env(cls) -> "GatewayRate":
        return cls(
            rate=float(os.environ.get("MQTT_BRIDGE__GATEWAY_RATE", 5)),
            burst=int(os.environ.get("MQTT_BRIDGE__GATEWAY_BURST", 300)),
        )

    def allow(self, gateway: str) -> bool:
        """Whether one more message from `gateway` fits. A rate of 0 lets everything through."""
        if self.rate <= 0:
            return True
        now = self.clock()
        tokens, last = self._buckets.get(gateway, (float(self.burst), now))
        tokens = min(float(self.burst), tokens + (now - last) * self.rate)
        if tokens < 1:
            self._buckets[gateway] = (tokens, now)
            return False
        self._buckets[gateway] = (tokens - 1, now)
        return True

    def forget(self, gateway: str) -> None:
        self._buckets.pop(gateway, None)
