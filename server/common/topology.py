"""Radio links between nodes, from traceroutes, neighbor info and direct receptions.

A link is directional: `from_node` transmitted and `to_node` heard it at `snr`
dB, since SNR is measured by the receiver.
"""
import math

TRACEROUTE_PORTNUM = 70
NEIGHBORINFO_PORTNUM = 71

TRACEROUTE = "traceroute"
NEIGHBORINFO = "neighborinfo"
DIRECT = "direct"
SOURCES = (TRACEROUTE, NEIGHBORINFO, DIRECT)

# Firmware placeholders: a hop it could not identify, and an SNR it did not measure.
UNKNOWN_NODE = 0xFFFFFFFF
UNKNOWN_SNR = -128


def snr_db(scaled: list) -> list[float | None]:
    """Traceroute SNRs are sent in quarter-dB steps, with -128 for unknown."""
    return [None if v == UNKNOWN_SNR else v / 4 for v in scaled]


def traceroute_paths(decoded: dict) -> dict:
    """The path a traceroute took, as complete as this reception of it shows.

    A request travels from its origin towards its target, each relay adding
    itself to `route`. The target answers with a reply (it carries
    `request_id`) holding the full route towards it, and relays add themselves
    to `route_back` on the way home. A gateway hearing either part way sees
    only the hops taken so far.

    Returns:
        {"origin", "target", "towards", "snr_towards", "back", "snr_back"}, where
        `towards` and `back` list node numbers in travel order and each SNR is
        the one measured on arriving at the next node in the list.
    """
    payload = decoded.get("payload") or {}
    route, route_back = payload.get("route") or [], payload.get("route_back") or []
    snr_towards, snr_back = snr_db(payload.get("snr_towards") or []), snr_db(payload.get("snr_back") or [])
    sender, receiver = decoded["node_id"], decoded.get("to")
    if decoded.get("request_id"):
        origin, target = receiver, sender
        towards = [origin, *route, target]
        back = [target, *route_back]
        # The last SNR of a complete return path is the origin's own reception.
        if len(snr_back) > len(route_back):
            back.append(origin)
    else:
        origin, target = sender, receiver
        towards = [origin, *route]
        back = []
    return {
        "origin": origin,
        "target": target,
        "towards": towards,
        "snr_towards": snr_towards,
        "back": back,
        "snr_back": snr_back,
    }


def _path_links(nodes: list[int], snrs: list[float | None]) -> list[tuple[int, int, float]]:
    links = []
    for a, b, snr in zip(nodes, nodes[1:], snrs):
        if snr is None or UNKNOWN_NODE in (a, b) or a == b:
            continue
        links.append((a, b, snr))
    return links


def traceroute_links(paths: dict) -> list[tuple[int, int, float]]:
    """(from_node, to_node, snr) for every hop of a traceroute with a measured SNR."""
    return _path_links(paths["towards"], paths["snr_towards"]) + _path_links(paths["back"], paths["snr_back"])


def neighborinfo_links(decoded: dict) -> list[tuple[int, int, float]]:
    """A node's report of the neighbors it hears, as links into that node."""
    payload = decoded.get("payload") or {}
    reporter = payload.get("node_id") or decoded["node_id"]
    links = []
    for neighbor in payload.get("neighbors") or []:
        node = neighbor.get("node_id")
        if node and node != reporter and node != UNKNOWN_NODE:
            links.append((node, reporter, float(neighbor.get("snr", 0.0))))
    return links


def distance_km(a: tuple[float, float] | None, b: tuple[float, float] | None) -> float | None:
    """Great-circle distance between two (latitude, longitude) points."""
    if a is None or b is None:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))
