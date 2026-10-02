"""One-off provisioning of the monitor's mesh, gateway and optional sink."""
import base64
import json
import os
import secrets
import sys
import urllib.error
import urllib.request

LABEL = "server monitor"
# Keeps clear of the broadcast address and of the low numbers used in examples.
NODE_ID_RANGE = (0x10000000, 0xFFFFFFFE)


class ApiError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body}")
        self.status = status


def _call(api_url: str, api_key: str, method: str, path: str, body: dict | None = None, params: str = "") -> dict | None:
    """JSON request against the registry; None on 404."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{api_url}/{path}{params}",
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise ApiError(e.code, e.read().decode(errors="replace")) from None


def _terms(api_url: str, api_key: str, kind: str, accept: bool) -> dict:
    """Terms fields to send, or {} when the instance does not enforce terms."""
    terms = _call(api_url, api_key, "GET", f"{kind}/terms", params="?locale=en")
    if terms is None:
        return {}
    if not accept:
        print(f"{terms['title']} ({terms['version']})\n\n{terms['description']}\n")
        for statement in terms["statements"]:
            print(f"  [{statement['id']}] {statement['text']}")
        sys.exit(f"\nRead the {kind} terms above, then rerun with --accept-terms.")
    return {"terms_version": terms["version"], "terms_locale": terms["locale"]}


def _register_gateway(api_url: str, api_key: str, mesh_id: str) -> dict:
    for _ in range(5):
        node_id = secrets.randbelow(NODE_ID_RANGE[1] - NODE_ID_RANGE[0]) + NODE_ID_RANGE[0]
        body = {"node_id": node_id, "mesh_id": mesh_id, "is_gateway": True, "label": f"{LABEL} gateway"}
        try:
            return _call(api_url, api_key, "POST", "devices", body)
        except ApiError as e:
            # Another allowed gateway already has that number.
            if e.status != 409:
                raise
    sys.exit("Could not find a free gateway node number")


def setup(api_url: str, api_key: str, channel_id: str, accept_terms: bool, with_sink: bool) -> None:
    api_url = api_url.rstrip("/")
    mesh_terms = _terms(api_url, api_key, "meshes", accept_terms)
    sink_terms = _terms(api_url, api_key, "sinks", accept_terms) if with_sink else {}

    psk_b64 = base64.b64encode(os.urandom(16)).decode()
    mesh = _call(
        api_url, api_key, "POST", "meshes",
        {"channel_id": channel_id, "psk_b64": psk_b64, "label": LABEL, **mesh_terms},
    )
    gateway = _register_gateway(api_url, api_key, mesh["id"])

    lines = [
        f"MONITOR__CHANNEL_ID={channel_id}",
        f"MONITOR__MESH_ID={mesh['id']}",
        f"MONITOR__PSK_B64={psk_b64}",
        f"MONITOR__GATEWAY_NODE_ID={gateway['node_id']}",
        f"MONITOR__GATEWAY_UUID={gateway['uuid']}",
    ]
    if with_sink:
        sink = _call(
            api_url, api_key, "POST", "sinks",
            {"label": LABEL, "streams": ["decoded"], "mesh_ids": [mesh["id"]], **sink_terms},
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
