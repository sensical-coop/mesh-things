"""Links and paths from traceroutes and neighbor info."""
import pytest

from common.topology import (
    UNKNOWN_NODE,
    distance_km,
    neighborinfo_links,
    traceroute_links,
    traceroute_paths,
)

A, R1, R2, B = 1, 11, 12, 2


def _traceroute(**fields) -> dict:
    return {"node_id": fields.pop("node_id"), "to": fields.pop("to"), "request_id": fields.pop("request_id", None), "payload": fields}


def test_a_complete_reply_holds_both_directions():
    reply = _traceroute(
        node_id=B, to=A, request_id=99,
        route=[R1, R2], snr_towards=[24, 20, 16],
        route_back=[R2, R1], snr_back=[12, 8, 4],
    )

    paths = traceroute_paths(reply)

    assert (paths["origin"], paths["target"]) == (A, B)
    assert paths["towards"] == [A, R1, R2, B]
    assert paths["back"] == [B, R2, R1, A]
    assert traceroute_links(paths) == [
        (A, R1, 6.0), (R1, R2, 5.0), (R2, B, 4.0),
        (B, R2, 3.0), (R2, R1, 2.0), (R1, A, 1.0),
    ]


def test_a_reply_heard_part_way_home_stops_at_the_last_relay():
    reply = _traceroute(node_id=B, to=A, request_id=99, route=[R1], snr_towards=[8, 8], route_back=[R1], snr_back=[4])

    paths = traceroute_paths(reply)

    assert paths["back"] == [B, R1]
    assert traceroute_links(paths)[-1] == (B, R1, 1.0)


def test_a_request_only_shows_the_hops_taken_so_far():
    request = _traceroute(node_id=A, to=B, route=[R1], snr_towards=[8])

    paths = traceroute_paths(request)

    assert paths["towards"] == [A, R1]
    assert traceroute_links(paths) == [(A, R1, 2.0)]


def test_return_snrs_without_a_return_path_make_no_link():
    request = _traceroute(node_id=A, to=B, route=[R1], snr_towards=[8], route_back=[R1], snr_back=[4])

    assert traceroute_links(traceroute_paths(request)) == [(A, R1, 2.0)]


def test_unknown_snrs_and_unknown_hops_make_no_link():
    reply = _traceroute(node_id=B, to=A, request_id=1, route=[UNKNOWN_NODE], snr_towards=[-128, 8])

    assert traceroute_links(traceroute_paths(reply)) == []


def test_neighbors_are_links_into_the_reporting_node():
    info = {"node_id": 7, "payload": {"node_id": 7, "neighbors": [{"node_id": 9, "snr": 6.5}, {"node_id": 7, "snr": 1}]}}

    assert neighborinfo_links(info) == [(9, 7, 6.5)]


def test_distance():
    assert distance_km((41.3874, 2.1686), (40.4168, -3.7038)) == pytest.approx(505, abs=2)
    assert distance_km(None, (0, 0)) is None
