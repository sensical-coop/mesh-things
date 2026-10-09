"""Aggregation of mesh.traffic.v1 into the mesh_* measurements."""
from datetime import datetime, timezone

from common.mesh_stats import (
    HOUR_MS,
    MESH_GATEWAY_TRAFFIC,
    MESH_HOPS,
    MESH_NODE_TRAFFIC,
    MESH_SIGNAL,
    MESH_TRAFFIC,
    MINUTE_MS,
    MeshStatsAggregator,
    hops_of,
    signal_bucket,
)

T0 = 1_760_000_400_000  # a whole hour, so minute and hour buckets share a start
assert T0 % HOUR_MS == 0


def _event(**overrides) -> dict:
    event = {
        "mesh_id": "m1",
        "gateway_id": 100,
        "node_id": 7,
        "packet_id": 1,
        "portnum": 67,
        "size": 20,
        "hop_start": 3,
        "hop_limit": 3,
        "rx_snr": 6.0,
        "rx_rssi": -95,
        "rejected": False,
    }
    event.update(overrides)
    return event


def _rows(agg, measurement):
    return {tuple(sorted(r["tags"].items())): r["fields"] for r in agg.rows() if r["measurement"] == measurement}


def test_a_packet_heard_by_two_gateways_is_one_packet_and_two_receptions():
    agg = MeshStatsAggregator()
    agg.add(_event(gateway_id=100), T0)
    agg.add(_event(gateway_id=200, hop_limit=2), T0 + 500)

    traffic = _rows(agg, MESH_TRAFFIC)[(("mesh_id", "m1"), ("portnum", "67"))]
    assert traffic["packets"] == 1 and traffic["receptions"] == 2 and traffic["bytes"] == 20
    assert _rows(agg, MESH_NODE_TRAFFIC)[(("mesh_id", "m1"), ("node_id", "7"))] == {"packets": 1, "receptions": 2}
    gateways = _rows(agg, MESH_GATEWAY_TRAFFIC)
    assert gateways[(("gateway_id", "100"), ("mesh_id", "m1"))]["direct_receptions"] == 1
    assert gateways[(("gateway_id", "200"), ("mesh_id", "m1"))]["direct_receptions"] == 0
    # Hops come from the first reception only.
    assert _rows(agg, MESH_HOPS) == {(("hops", "0"), ("mesh_id", "m1")): {"packets": 1}}


def test_the_same_packet_id_after_the_dedup_window_is_a_new_packet():
    agg = MeshStatsAggregator()
    agg.add(_event(), T0)
    agg.add(_event(), T0 + 11 * MINUTE_MS)

    assert sum(r["fields"]["packets"] for r in agg.rows() if r["measurement"] == MESH_TRAFFIC) == 2


def test_rejected_nodes_count_as_traffic_but_not_as_nodes():
    agg = MeshStatsAggregator()
    agg.add(_event(rejected=True, portnum=None), T0)

    traffic = _rows(agg, MESH_TRAFFIC)[(("mesh_id", "m1"), ("portnum", "unknown"))]
    assert traffic["rejected_packets"] == 1 and traffic["rejected_receptions"] == 1 and traffic["packets"] == 1
    assert _rows(agg, MESH_NODE_TRAFFIC) == {}


def test_signal_is_only_counted_when_heard_over_the_air():
    agg = MeshStatsAggregator()
    agg.add(_event(rx_snr=None, rx_rssi=None), T0)

    assert _rows(agg, MESH_SIGNAL) == {}
    gateway = _rows(agg, MESH_GATEWAY_TRAFFIC)[(("gateway_id", "100"), ("mesh_id", "m1"))]
    assert gateway["signal_receptions"] == 0 and gateway["receptions"] == 1


def test_field_types_never_change():
    agg = MeshStatsAggregator()
    agg.add(_event(rx_snr=6.0, rx_rssi=-95), T0)

    fields = _rows(agg, MESH_GATEWAY_TRAFFIC)[(("gateway_id", "100"), ("mesh_id", "m1"))]
    assert isinstance(fields["rx_snr_sum"], float) and isinstance(fields["rx_rssi_sum"], float)
    assert isinstance(fields["receptions"], int)


def test_rows_are_stamped_at_their_bucket_start():
    agg = MeshStatsAggregator()
    agg.add(_event(), T0 + 90_000)

    times = {r["measurement"]: r["time"] for r in agg.rows()}
    assert times[MESH_TRAFFIC] == datetime.fromtimestamp((T0 + MINUTE_MS) / 1000, tz=timezone.utc)
    assert times[MESH_NODE_TRAFFIC] == datetime.fromtimestamp(T0 / 1000, tz=timezone.utc)


def test_offsets_are_held_back_until_every_bucket_holding_them_closes():
    agg = MeshStatsAggregator(grace_ms=MINUTE_MS)
    agg.add(_event(packet_id=1), T0, partition=0, offset=10)
    agg.add(_event(packet_id=2), T0 + 5 * MINUTE_MS, partition=0, offset=11)

    agg.close()
    # The minute buckets have closed, the hour has not: offset 10 is still needed.
    assert len(_rows(agg, MESH_TRAFFIC)) == 1
    assert agg.committable() == {0: 10}

    agg.close(watermark=T0 + HOUR_MS + 2 * MINUTE_MS)
    assert agg.rows() == []
    assert agg.committable() == {0: 12}


def test_a_late_reception_joins_the_oldest_open_bucket():
    agg = MeshStatsAggregator(grace_ms=MINUTE_MS)
    agg.add(_event(packet_id=1), T0 + 10 * MINUTE_MS)
    agg.close()
    agg.add(_event(packet_id=2), T0)

    starts = sorted(r["time"] for r in agg.rows() if r["measurement"] == MESH_TRAFFIC)
    assert starts[0] >= datetime.fromtimestamp((T0 + 8 * MINUTE_MS) / 1000, tz=timezone.utc)


def test_events_without_a_mesh_are_ignored():
    agg = MeshStatsAggregator()
    agg.add(_event(mesh_id=None), T0)

    assert agg.rows() == []


def test_hops_and_signal_buckets():
    assert hops_of({"hop_start": 3, "hop_limit": 1}) == "2"
    assert hops_of({"hop_start": 0, "hop_limit": 3}) == "unknown"
    assert signal_bucket("snr", -7.25) == "-7.5"
    assert signal_bucket("rssi", -95) == "-100"


def test_direct_receptions_become_links_once_their_hour_closes():
    agg = MeshStatsAggregator(grace_ms=MINUTE_MS)
    agg.add(_event(packet_id=1, rx_snr=6.0), T0 + 1000)
    agg.add(_event(packet_id=2, rx_snr=4.0), T0 + 2000)
    agg.add(_event(packet_id=3, hop_limit=2), T0 + 3000)  # relayed, not direct
    agg.add(_event(packet_id=4, via_mqtt=True), T0 + 4000)

    assert agg.close() == []
    links = agg.close(watermark=T0 + HOUR_MS + 2 * MINUTE_MS)

    assert links == [
        {
            "mesh_id": "m1", "from_node": 7, "to_node": 100, "source": "direct",
            "samples": 2, "snr_sum": 10.0, "first_seen": T0 + 1000, "last_seen": T0 + 2000,
        }
    ]
    assert agg.close(watermark=T0 + 2 * HOUR_MS + 2 * MINUTE_MS) == []


def test_rejected_nodes_and_a_gateway_hearing_itself_make_no_link():
    agg = MeshStatsAggregator(grace_ms=MINUTE_MS)
    agg.add(_event(rejected=True), T0)
    agg.add(_event(packet_id=2, node_id=100), T0)

    assert agg.close(watermark=T0 + HOUR_MS + 2 * MINUTE_MS) == []
