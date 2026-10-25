"""One-off provisioning of the monitor's mesh, gateway and optional sink."""
import base64
import os
import secrets
import sys

from mesh_things.client import Conflict, MeshThings, terms_fields

LABEL = "server monitor"
# Keeps clear of the broadcast address and of the low numbers used in examples.
NODE_ID_RANGE = (0x10000000, 0xFFFFFFFE)


def _terms(api: MeshThings, kind: str, accept: bool) -> dict:
    """Terms fields to send, or {} when the instance does not enforce terms."""
    terms = api.get_terms(kind, locale="en")
    if terms is None:
        return {}
    if not accept:
        print(f"{terms['title']} ({terms['version']})\n\n{terms['description']}\n")
        for statement in terms["statements"]:
            print(f"  [{statement['id']}] {statement['text']}")
        sys.exit(f"\nRead the {kind} terms above, then rerun with --accept-terms.")
    return terms_fields(terms)


def _register_gateway(api: MeshThings, mesh_id: str) -> dict:
    for _ in range(5):
        node_id = secrets.randbelow(NODE_ID_RANGE[1] - NODE_ID_RANGE[0]) + NODE_ID_RANGE[0]
        body = {"node_id": node_id, "mesh_id": mesh_id, "is_gateway": True, "label": f"{LABEL} gateway"}
        try:
            return api.devices.create(body=body)
        except Conflict:
            # Another allowed gateway already has that number.
            continue
    sys.exit("Could not find a free gateway node number")


def setup(api_url: str, api_key: str, channel_id: str, accept_terms: bool, with_sink: bool) -> None:
    api = MeshThings(api_url, api_key)
    mesh_terms = _terms(api, "meshes", accept_terms)
    sink_terms = _terms(api, "sinks", accept_terms) if with_sink else {}

    psk_b64 = base64.b64encode(os.urandom(16)).decode()
    mesh = api.meshes.create(body={"channel_id": channel_id, "psk_b64": psk_b64, "label": LABEL, **mesh_terms})
    gateway = _register_gateway(api, mesh["id"])

    lines = [
        f"MONITOR__CHANNEL_ID={channel_id}",
        f"MONITOR__MESH_ID={mesh['id']}",
        f"MONITOR__PSK_B64={psk_b64}",
        f"MONITOR__GATEWAY_NODE_ID={gateway['node_id']}",
        f"MONITOR__GATEWAY_UUID={gateway['uuid']}",
    ]
    if with_sink:
        sink = api.sinks.create(
            body={"label": LABEL, "streams": ["decoded"], "mesh_ids": [mesh["id"]], **sink_terms},
        )
        lines += [
            f"MONITOR__SINK_BROKER={sink['broker']}",
            f"MONITOR__SINK_USER={sink['username']}",
            f"MONITOR__SINK_PASS={sink['password']}",
            f"MONITOR__SINK_TOPIC={sink['topic_filter']}",
        ]
    print("Created the monitor's mesh and gateway. Add these to monitor.env:\n")
    print("\n".join(lines))
    if with_sink:
        print("\nThe sink password is shown only once.")
