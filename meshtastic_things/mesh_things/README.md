# mesh-things

Python access to the meshtastic-things API, plus the vocabulary and Meshtastic protocol
helpers the API itself is built on.

```bash
pip install mesh-things              # the API client and the vocabulary
pip install mesh-things[protobuf]    # telemetry catalog and portnum names, from the Meshtastic protobufs
pip install mesh-things[codec]       # MQTT envelope parsing and channel decryption
```

## The client

Every API operation is a method, generated from the OpenAPI document this release was
built against. There is one namespace per API tag, and methods are named after their
operation, so `GET /meshes/{mesh_id}/traceroutes` is `meshes.traceroutes_list`.
Responses are plain dicts and lists.

```python
from mesh_things.client import MeshThings

api = MeshThings("https://api.example.org", api_key="...")  # or MESH_THINGS_URL / MESH_THINGS_API_KEY
for mesh in api.meshes.list():
    print(mesh["id"], mesh["label"])
api.readings.meshes_nodes_latest_get(mesh_id, "!19ba4462")
api.meshes.create(body={"channel_id": "LongFast", "psk_b64": "..."})
```

- **Arguments.** Path parameters are positional, in path order. Query parameters and
  `body` are keywords.
- **Errors.** An unknown or missing argument raises `TypeError` before anything is sent.
- **Docs.** `help()` on a method shows the API's own documentation for it.
- **Async.** `AsyncMeshThings` offers the same methods as coroutines.

| Exception | Raised for |
|---|---|
| `ValidationFailed` | 400. `errors` maps each field to its messages. |
| `Unauthorized` | 401 |
| `Forbidden` | 403 |
| `NotFound` | 404 |
| `Conflict` | 409 |
| `Throttled` | 429 rate limits. `retry_after` gives the wait, and `retries=` retries automatically. |
| `ExportInProgress` | An export is already running. |
| `ServerError` | 5xx |

All of them subclass `ApiError`.

The API sends its version on every response. A `MeshThingsVersionWarning` means it no
longer matches this release, so upgrade mesh-things to get the current set of methods.
