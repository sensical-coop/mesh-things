# mesh-things

Python access to the meshtastic-things API, plus the vocabulary and Meshtastic protocol
helpers the API itself is built on.

```bash
pip install mesh-things              # the API client and the vocabulary
pip install mesh-things[protobuf]    # telemetry catalog and portnum names, from the Meshtastic protobufs
pip install mesh-things[codec]       # MQTT envelope parsing and channel decryption
pip install mesh-things[pandas]      # readings and exports as DataFrames
pip install mesh-things[archive]     # the Parquet archive, read straight from S3 (adds pyarrow)
```

Runnable examples for every part of the API, from signing up to reading the archive,
are in [examples/](examples/README.md) and in the source distribution.

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
- **Local checks.** Values the API would reject raise `ValueError` without a request:
  - an enum value outside the list the API publishes;
  - a malformed `start`, `stop` or `window`;
  - a `channel` not shaped `<measurement>.<field>`.

  `date` and `datetime` objects are sent as ISO 8601, in UTC.
- **Docs.** `help()` on a method shows the API's own documentation for it.
- **Async.** `AsyncMeshThings` offers the same methods as coroutines.

### Helpers

A few tasks take more than one call, so the client covers them directly:

```python
from mesh_things.client import terms_fields

terms = api.get_terms("meshes")  # None where the instance enforces no terms
mesh = api.meshes.create(body={"channel_id": "LongFast", "psk_b64": "...", **terms_fields(terms)})

export = api.readings.meshes_exports_create(mesh["id"], body={"format": "csv", "start": "2026-10-01", "stop": "2026-10-07"})
export = api.wait_for_export(mesh["id"], export["id"], timeout=600)  # raises ExportFailed if it fails
api.download(export["url"], "readings.zip")

api.download_partition(mesh["id"], "2026-10-24", 13, "13.parquet")  # one hour of the archive

for traceroute in api.traceroutes(mesh["id"], node_id="!19ba4462"):  # pages through all of them
    print(traceroute["heard_at"])
```

Presigned links are fetched without your API key.

### DataFrames (`[pandas]`)

```python
from mesh_things.pandas import channel_units, read_export, to_dataframe

readings = api.readings.devices_get(device_uuid, payload_kind="telemetry:environment_metrics", start="-1d")
df = to_dataframe(readings, units=channel_units(api.measurements.list()))  # one column per channel
df = to_dataframe(readings, long=True)  # one row per reading: time, channel, value
frames = read_export(api.download(export["url"]))  # one frame per measurement
```

- **Wide by default.** Timeseries are indexed by time in UTC, with one column per channel
  (`environment_metrics.temperature`, ...).
- **Metadata.** `df.attrs` carries `mesh_id`, `node_id`, `payload_kind`, `origin` and,
  when given, `units`.
- **Other shapes.** Latest readings and quality become one row per channel, and any list
  becomes one row per element.

### The archive (`[archive]`)

```python
from mesh_things import archive
from mesh_things.pandas import archive_frame

rows = archive.open_dataset(api, mesh_id).to_table().to_pandas()  # operators only
df = archive_frame(rows)  # payload_json spread into channel columns, indexed by node_id and time
```

### Protobuf messages (`[protobuf]`)

`mesh_things.protobuf` turns readings back into Meshtastic messages:
- `latest_messages()` gives one `Telemetry` per variant from a device's latest readings.
- `series_messages()` gives one message per time from raw, unwindowed readings.
- `payload_message()` converts an archived payload of any kind.

Readings other than telemetry are stored in a form of the API's own, so they stay as
dicts.

### Errors

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

All of them subclass `ApiError`. `wait_for_export` raises `ExportFailed` when the export
ends `failed` or `expired`, and `TimeoutError` when the time runs out.

The API sends its version on every response. A `MeshThingsVersionWarning` means it no
longer matches this release, so upgrade mesh-things to get the current set of methods.
