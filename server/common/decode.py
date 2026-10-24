from meshtastic.protobuf import portnums_pb2

from mesh_things import codec, node_ids
from mesh_things.channels import NODEINFO_KIND, POSITION_KIND, TELEMETRY


def _discovered_fields(payload_kind: str, payload: dict) -> list[str]:
    """telemetry:<variant> only, numeric leaf fields only."""
    if not payload_kind.startswith(f"{TELEMETRY}:"):
        return []
    variant = payload_kind.split(":", 1)[1]
    sub = payload.get(variant)
    if not isinstance(sub, dict):
        return []
    return [k for k, v in sub.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]


def _build_sighting(mesh_id: str, decoded: dict) -> dict:
    sighting = {
        "key": f"{mesh_id}:{decoded['node_id']}",
        "mesh_id": mesh_id,
        "device_id": decoded["node_id"],
        "op": "upsert",
    }
    payload = decoded["payload"]
    if decoded["payload_kind"] == POSITION_KIND:
        lat_i, lon_i = payload.get("latitude_i"), payload.get("longitude_i")
        if lat_i is not None and lon_i is not None:
            sighting["latitude"] = lat_i / 1e7
            sighting["longitude"] = lon_i / 1e7
    elif decoded["payload_kind"] == NODEINFO_KIND:
        for src_field, sighting_key in (
            ("long_name", "name"),
            ("short_name", "short_name"),
            ("hw_model", "hardware_type"),
            ("role", "role"),
        ):
            if payload.get(src_field):
                sighting[sighting_key] = payload[src_field]
    return sighting


def _build_discovery(mesh_id: str, decoded: dict, fields: list[str]) -> dict:
    return {
        "mesh_id": mesh_id,
        "device_id": decoded["node_id"],
        "payload_kind": decoded["payload_kind"],
        "fields": fields,
        "op": "upsert",
    }


def _drop(on_drop, reason: str) -> None:
    if on_drop is not None:
        on_drop(reason)
    return None


_KNOWN_PORTNUMS = frozenset(portnums_pb2.PortNum.values())


def _build_traffic(mesh_id: str, se, rejected: bool, received_at: int | None) -> dict:
    """One reception of a packet, whether or not it can be decoded.

    Carries no payload. `portnum` is None for a packet still encrypted, and
    for one whose portnum is unknown, which is also what a wrong key that
    happens to parse looks like.
    """
    mp = se.packet
    plain = mp.HasField("decoded")
    known = plain and mp.decoded.portnum in _KNOWN_PORTNUMS
    return {
        "mesh_id": mesh_id,
        "gateway_id": node_ids.to_num(se.gateway_id),
        "node_id": getattr(mp, "from"),
        "to": mp.to,
        "packet_id": mp.id,
        "portnum": mp.decoded.portnum if known else None,
        "size": len(mp.decoded.payload) if plain else len(mp.encrypted),
        "rx_time": mp.rx_time,
        "received_at": received_at,
        **codec.routing_fields(mp),
        "rejected": rejected,
    }


def decode_packet(raw: bytes, gateway_state, rejected_nodes, on_drop=None, received_at: int | None = None) -> dict | None:
    """Decrypt/decode one raw ServiceEnvelope.

    Returns None only for a packet from an unregistered gateway, which belongs
    to no mesh. Otherwise a dict of events: "traffic" for every packet of a
    gateway whose mesh is known, and "decoded", plus "sighting" and possibly
    "discovery", when the packet decodes and its node is not rejected.

    Args:
        on_drop: Called with the reason whenever a packet yields no decoded
            event. A wrong mesh key and an unsupported portnum are otherwise
            indistinguishable from no traffic at all. The two runtimes log
            differently, so each supplies its own.
    """
    se = codec.parse_envelope(raw)
    gateway_id = se.gateway_id or "unparseable"
    state = gateway_state.get(gateway_id)
    if state is None:
        return _drop(on_drop, f"unregistered gateway {gateway_id}")

    key_b64 = state.get("psk_b64")
    mesh_id = state.get("mesh_id")
    key_bytes = codec.decode_psk(key_b64) if key_b64 else None
    events = {}

    node_id = getattr(se.packet, "from")
    if mesh_id and f"{mesh_id}:{node_id}" in rejected_nodes:
        events["traffic"] = _build_traffic(mesh_id, se, rejected=True, received_at=received_at)
        _drop(on_drop, f"rejected node {mesh_id}:{node_id}")
        return events

    mp = se.packet
    if mp.HasField("encrypted") and not mp.HasField("decoded"):
        decrypted = codec.decrypt_packet(mp, key_bytes)
        if decrypted is not None:
            mp.decoded.CopyFrom(decrypted)
    if mesh_id:
        events["traffic"] = _build_traffic(mesh_id, se, rejected=False, received_at=received_at)
    if not mp.HasField("decoded"):
        _drop(
            on_drop,
            f"could not decrypt packet from node {node_id} via gateway {gateway_id}; "
            f"the mesh key does not match what the channel is transmitting with",
        )
        return events

    result = codec.decode_payload(mp)
    if result is None:
        _drop(on_drop, f"portnum {mp.decoded.portnum} has no protobuf schema, nothing to store")
        return events
    portnum, pb_dict, payload_kind = result
    decoded = codec.build_decoded_message(se, portnum, pb_dict, payload_kind)
    if mesh_id:
        decoded["mesh_id"] = mesh_id

    events["decoded"] = decoded
    if mesh_id:
        events["sighting"] = _build_sighting(mesh_id, decoded)
        fields = _discovered_fields(decoded["payload_kind"], decoded["payload"])
        if fields:
            events["discovery"] = _build_discovery(mesh_id, decoded, fields)
    return events
