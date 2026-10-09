"""Per-mesh traffic statistics, aggregated from `mesh.traffic.v1` reception events.

A packet heard by several gateways arrives once per gateway. The first reception
counts the packet; every reception counts as a reception. Rows are keyed by the
start of their bucket and rewritten whole on every flush, so a bucket written
while still filling is simply overwritten later.

Measurements, all tagged with mesh_id:
  - mesh_traffic, per minute and portnum ("unknown" when undecoded): packets,
    receptions, bytes, and rejected_packets/rejected_receptions, the share of
    those from nodes the owner rejected.
  - mesh_node_traffic, per hour and node_id: packets, receptions. Rejected nodes
    are left out.
  - mesh_gateway_traffic, per hour and gateway_id: receptions, direct_receptions
    (heard with no hop), signal_receptions, rx_snr_sum, rx_rssi_sum.
  - mesh_hops, per hour and hops ("unknown" on firmware without hop_start): packets.
  - mesh_signal, per hour, metric ("snr" or "rssi") and bucket (its lower bound): receptions.

Direct links, a node heard by a gateway with no hop in between, are summed per
hour too, and handed back by close() once their hour is over rather than stored
in InfluxDB.
"""
import os
from collections import defaultdict
from datetime import datetime, timezone

from common.topology import DIRECT

MESH_STATS_BUCKET = os.environ.get("INFLUX__MESH_STATS_BUCKET") or "mesh_stats"

MESH_TRAFFIC = "mesh_traffic"
MESH_NODE_TRAFFIC = "mesh_node_traffic"
MESH_GATEWAY_TRAFFIC = "mesh_gateway_traffic"
MESH_HOPS = "mesh_hops"
MESH_SIGNAL = "mesh_signal"
# Not a measurement: direct links leave through close() for the registry.
DIRECT_LINKS = "direct_links"

UNKNOWN = "unknown"
MINUTE_MS = 60_000
HOUR_MS = 3_600_000
GRAINS = {
    MESH_TRAFFIC: MINUTE_MS,
    MESH_NODE_TRAFFIC: HOUR_MS,
    MESH_GATEWAY_TRAFFIC: HOUR_MS,
    MESH_HOPS: HOUR_MS,
    MESH_SIGNAL: HOUR_MS,
    DIRECT_LINKS: HOUR_MS,
}
# Histogram steps: SNR in dB, RSSI in dBm.
SIGNAL_STEPS = {"snr": 2.5, "rssi": 10}
# Every other field is a count. InfluxDB fixes a field's type on its first write.
FLOAT_FIELDS = frozenset({"rx_snr_sum", "rx_rssi_sum"})
# A packet relayed back to a gateway is still the same packet well within this.
DEDUP_TTL_MS = 10 * MINUTE_MS


def hops_of(event: dict) -> str:
    hop_start, hop_limit = event.get("hop_start") or 0, event.get("hop_limit") or 0
    if hop_start <= 0 or hop_limit > hop_start:
        return UNKNOWN
    return str(hop_start - hop_limit)


def signal_bucket(metric: str, value: float) -> str:
    step = SIGNAL_STEPS[metric]
    lower = (value // step) * step
    return f"{lower:g}"


class MeshStatsAggregator:
    """Counts receptions into time buckets and tracks which offsets are safe to commit.

    A bucket closes once the watermark passes its end by `grace_ms`. Until then
    its records' offsets are not committed, so a restart replays them and
    rebuilds the bucket in full instead of overwriting it with a partial count.
    """

    def __init__(self, grace_ms: int = MINUTE_MS):
        self.grace_ms = grace_ms
        # (measurement, tags, bucket_start) -> fields
        self._rows: dict[tuple, dict] = {}
        # (measurement, bucket_start) -> {partition: lowest offset}
        self._offsets: dict[tuple, dict] = defaultdict(dict)
        self._next_offset: dict = {}
        self._closed_until = {measurement: 0 for measurement in GRAINS}
        self._seen: dict[tuple, int] = {}
        # (mesh_id, node_id, gateway_id, bucket_start) -> samples, snr_sum, first_seen, last_seen
        self._links: dict[tuple, dict] = {}
        self.watermark = 0

    def add(self, event: dict, at_ms: int, partition=None, offset: int | None = None) -> None:
        """Count one reception, heard at `at_ms` epoch milliseconds."""
        mesh_id = event.get("mesh_id")
        if not mesh_id:
            return
        self.watermark = max(self.watermark, at_ms)
        key = (mesh_id, event.get("node_id"), event.get("packet_id"))
        first = self._seen.get(key, 0) < at_ms
        if first:
            self._seen[key] = at_ms + DEDUP_TTL_MS
        rejected = bool(event.get("rejected"))
        portnum = event.get("portnum")
        hops = hops_of(event)

        def hold(measurement, bucket):
            if partition is not None and offset is not None:
                lowest = self._offsets[(measurement, bucket)]
                lowest[partition] = min(lowest.get(partition, offset), offset)

        def count(measurement, tags, **fields):
            bucket = self._bucket(measurement, at_ms)
            row = self._rows.setdefault((measurement, tuple(sorted(tags.items())), bucket), defaultdict(float))
            for name, value in fields.items():
                row[name] += value
            hold(measurement, bucket)

        count(
            MESH_TRAFFIC,
            {"mesh_id": mesh_id, "portnum": UNKNOWN if portnum is None else str(portnum)},
            packets=int(first),
            receptions=1,
            bytes=(event.get("size") or 0) if first else 0,
            rejected_packets=int(first and rejected),
            rejected_receptions=int(rejected),
        )
        if not rejected:
            count(
                MESH_NODE_TRAFFIC,
                {"mesh_id": mesh_id, "node_id": str(event.get("node_id"))},
                packets=int(first),
                receptions=1,
            )
        if first:
            count(MESH_HOPS, {"mesh_id": mesh_id, "hops": hops}, packets=1)

        snr, rssi = event.get("rx_snr"), event.get("rx_rssi")
        heard = snr is not None and rssi is not None
        if event.get("gateway_id") is not None:
            count(
                MESH_GATEWAY_TRAFFIC,
                {"mesh_id": mesh_id, "gateway_id": str(event["gateway_id"])},
                receptions=1,
                direct_receptions=int(hops == "0"),
                signal_receptions=int(heard),
                rx_snr_sum=snr if heard else 0,
                rx_rssi_sum=rssi if heard else 0,
            )
        gateway = event.get("gateway_id")
        node = event.get("node_id")
        if heard and hops == "0" and not rejected and not event.get("via_mqtt") and gateway not in (None, node):
            bucket = self._bucket(DIRECT_LINKS, at_ms)
            link = self._links.setdefault(
                (mesh_id, node, gateway, bucket),
                {"samples": 0, "snr_sum": 0.0, "first_seen": at_ms, "last_seen": at_ms},
            )
            link["samples"] += 1
            link["snr_sum"] += snr
            link["first_seen"] = min(link["first_seen"], at_ms)
            link["last_seen"] = max(link["last_seen"], at_ms)
            hold(DIRECT_LINKS, bucket)
        if heard:
            for metric, value in (("snr", snr), ("rssi", rssi)):
                count(
                    MESH_SIGNAL,
                    {"mesh_id": mesh_id, "metric": metric, "bucket": signal_bucket(metric, value)},
                    receptions=1,
                )

        if partition is not None and offset is not None:
            self._next_offset[partition] = max(self._next_offset.get(partition, 0), offset + 1)

    def _bucket(self, measurement: str, at_ms: int) -> int:
        """A late reception joins the oldest bucket still open rather than a closed one."""
        grain = GRAINS[measurement]
        return max(at_ms - at_ms % grain, self._closed_until[measurement])

    def rows(self) -> list[dict]:
        """Every bucket held, closed or still filling, as InfluxDB point dicts."""
        return [
            {
                "measurement": measurement,
                "tags": dict(tags),
                "fields": {
                    name: float(value) if name in FLOAT_FIELDS else int(value) for name, value in fields.items()
                },
                "time": datetime.fromtimestamp(bucket / 1000, tz=timezone.utc),
            }
            for (measurement, tags, bucket), fields in self._rows.items()
        ]

    def close(self, watermark: int | None = None) -> list[dict]:
        """Forget buckets whose end the watermark has passed by the grace period.

        Call it only after rows() has been written, so a closed bucket's last
        version is the one stored.

        Args:
            watermark: Event time to close against, defaulting to the latest
                reception seen. A writer with nothing to read passes the clock,
                so the last buckets close even when traffic stops.

        Returns:
            The direct links of the hours that closed, one per mesh, node and
            gateway: {"mesh_id", "from_node", "to_node", "source", "samples",
            "snr_sum", "first_seen", "last_seen"}, times in epoch milliseconds.
        """
        watermark = max(self.watermark, watermark or 0)
        for measurement, grain in GRAINS.items():
            closed = watermark - self.grace_ms - grain
            if closed < 0:
                continue
            self._closed_until[measurement] = max(self._closed_until[measurement], closed - closed % grain + grain)
        self._rows = {
            key: fields for key, fields in self._rows.items() if key[2] >= self._closed_until[key[0]]
        }
        self._offsets = defaultdict(
            dict, {key: lowest for key, lowest in self._offsets.items() if key[1] >= self._closed_until[key[0]]}
        )
        self._seen = {key: expiry for key, expiry in self._seen.items() if expiry > watermark}
        closed_links, open_until = [], self._closed_until[DIRECT_LINKS]
        for key in [key for key in self._links if key[3] < open_until]:
            mesh_id, node, gateway, _ = key
            closed_links.append(
                {"mesh_id": mesh_id, "from_node": node, "to_node": gateway, "source": DIRECT, **self._links.pop(key)}
            )
        return closed_links

    def committable(self) -> dict:
        """Per partition, the offset up to which every record lies in a closed bucket."""
        safe = dict(self._next_offset)
        for lowest in self._offsets.values():
            for partition, offset in lowest.items():
                safe[partition] = min(safe.get(partition, offset), offset)
        return safe

