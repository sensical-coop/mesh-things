# Mesh things python package

`mesh-things` is the Python package for the [mesh-things](https://github.com/sensical-coop/mesh-things) API. It lets you read your Meshtastic meshes, their devices and their readings, and manage them, without writing any HTTP code. It also contains the vocabulary and Meshtastic protocol helpers that the API itself is built on, so your scripts and the server always speak the same language.

## Installation

The package works with Python 3.10 or newer. The base install includes the API client. Optional extras add support for pandas, the Parquet archive and the Meshtastic protobufs:

```bash
pip install mesh-things              # the API client and the shared vocabulary
pip install mesh-things[pandas]      # readings and exports as pandas DataFrames
pip install mesh-things[archive]     # the Parquet archive, read straight from S3 (adds pyarrow)
pip install mesh-things[protobuf]    # the telemetry catalog and portnum names, from the Meshtastic protobufs
pip install mesh-things[codec]       # MQTT envelope parsing and channel decryption
```

## Getting started

To connect, you need the address of your instance and, for anything that is not public, an API key. You receive the key when you sign up (see `registry_create_owner.py` in the [examples](examples/README.md)). You can pass both directly, or set `MESH_THINGS_URL` and `MESH_THINGS_API_KEY` once in your environment:

```python
from mesh_things.client import MeshThings

api = MeshThings("https://api.example.org", api_key="...")

me = api.owners.me_get()
print(f"Hello, {me['name']}")
for mesh in api.meshes.list():
    print(mesh["id"], mesh["label"])
```

Every operation of the API is available as a method. Methods are grouped by topic, such as `meshes`, `devices` or `readings`, and named after the operation they call: for example, `GET /meshes/{mesh_id}/traceroutes` becomes `api.meshes.traceroutes_list(mesh_id)`. Responses are plain Python dictionaries and lists. Calling `help()` on a method shows the API's own documentation for it, including its arguments.

## Reading your data

Most of the time you will want to read data. The calls below cover the most common cases:

```python
# The devices on a mesh, and the latest readings of each one
for device in api.meshes.devices_list(mesh_id):
    latest = api.readings.devices_latest_get(device["uuid"])
    for reading in latest["readings"]:
        print(device["name"], reading["channel"], reading["value"], reading["unit"])

# One channel over the last day, averaged every hour
temperature = api.readings.devices_get(
    device_uuid, channel="environment_metrics.temperature", start="-1d", window="1h", agg="mean",
)

# Data completeness, radio traffic and mesh statistics
quality = api.readings.devices_quality_get(device_uuid, start="-7d")
traffic = api.readings.devices_traffic_get(device_uuid, range="7d")
stats = api.readings.meshes_stats_get(mesh_id, range="24h")

# Radio links between the nodes of a mesh
links = api.meshes.links_list(mesh_id, since="7d")

# The measurements of one kind of telemetry, with their units
measurements = api.measurements.list(payload_kind="telemetry:environment_metrics")
```

A node can be given either as its number or in its Meshtastic form, such as `"!19ba4462"`. Dates and times can be given as `date` or `datetime` objects, which are sent in UTC. A public mesh can be read without an API key.

The [examples](examples/README.md) include several short scripts that only read data, all starting with `get_`. They are a good place to see these calls in context.

## Making changes

Calls that create or change something take their content as `body`. Path parameters are given in order, and query parameters by name:

```python
mesh = api.meshes.create(body={"channel_id": "LongFast", "psk_b64": "..."})
api.meshes.update(mesh["id"], body={"label": "Rooftop mesh"})
```

The client checks your arguments before sending anything. An unknown or missing argument raises `TypeError`. A value the API would reject raises `ValueError`, for example a value outside a list of allowed options, a malformed `start`, `stop` or `window`, or a `channel` that is not written as `<measurement>.<field>`.

## Helpers

Some tasks take more than one call, so the client takes care of them for you:

```python
from mesh_things.client import terms_fields

# Accept the terms an instance asks for when creating a mesh, if any
terms = api.get_terms("meshes")
mesh = api.meshes.create(body={"channel_id": "LongFast", "psk_b64": "...", **terms_fields(terms)})

# Request an export, wait until it is ready and download it
export = api.readings.meshes_exports_create(mesh["id"], body={"format": "csv", "start": "2026-10-01", "stop": "2026-10-07"})
export = api.wait_for_export(mesh["id"], export["id"], timeout=600)
api.download(export["url"], "readings.zip")

# Download one hour of the Parquet archive
api.download_partition(mesh["id"], "2026-10-24", 13, "13.parquet")

# Go through every traceroute, page after page
for traceroute in api.traceroutes(mesh["id"], node_id="!19ba4462"):
    print(traceroute["heard_at"])
```

Download links are signed on their own, so your API key is never sent with them.

## Working with pandas

With the `[pandas]` extra, you can turn readings, exports and archive rows into DataFrames:

```python
from mesh_things.pandas import channel_units, read_export, to_dataframe

readings = api.readings.devices_get(device_uuid, payload_kind="telemetry:environment_metrics", start="-1d")
df = to_dataframe(readings, units=channel_units(api.measurements.list()))
frames = read_export(api.download(export["url"]))
```

By default, a DataFrame has one row per time, in UTC, and one column per channel, such as `environment_metrics.temperature`. If you prefer one row per reading, pass `long=True`. The DataFrame's `attrs` keep the context: the mesh, the node, the kind of payload, its origin and, when you pass them, the units. Latest readings and quality results become one row per channel.

## The Parquet archive

With the `[archive]` extra, an operator can read a mesh's whole archive straight from S3, using temporary credentials that the API issues:

```python
from mesh_things import archive
from mesh_things.pandas import archive_frame

rows = archive.open_dataset(api, mesh_id).to_table().to_pandas()
df = archive_frame(rows)  # one column per channel, indexed by node and time
```

## Meshtastic messages

With the `[protobuf]` extra, `mesh_things.protobuf` turns readings back into Meshtastic protobuf messages. `latest_messages()` builds one `Telemetry` message per kind of telemetry from a device's latest readings, `series_messages()` builds one message per time from raw readings, and `payload_message()` converts an archived payload of any kind. Positions and node details are stored in the API's own format, so they stay as dictionaries.

## Async

`AsyncMeshThings` offers exactly the same methods as coroutines, for use with `asyncio`:

```python
from mesh_things.client import AsyncMeshThings

async with AsyncMeshThings("https://api.example.org", api_key="...") as api:
    meshes = await api.meshes.list()
```

## Errors

When the API answers with an error, the client raises one of the following exceptions:

| Exception | When |
|---|---|
| `ValidationFailed` | The request was rejected (400). `errors` lists the messages for each field. |
| `Unauthorized` | The API key is missing or not valid (401). |
| `Forbidden` | You do not have access to this resource (403). |
| `NotFound` | The resource does not exist, or you cannot see it (404). |
| `Conflict` | The change clashes with existing data (409). |
| `Throttled` | You are sending requests too quickly (429). `retry_after` gives the waiting time in seconds, and `retries=` makes the client wait and retry for you. |
| `ExportInProgress` | One of your exports is already running. |
| `ServerError` | Something went wrong on the server (5xx). |
| `InsecureTransport` | Your API key, or archive credentials, would travel over plain HTTP to another computer. |

All of them are subclasses of `ApiError`. `wait_for_export` also raises `ExportFailed` when an export cannot be completed, and `TimeoutError` when it takes longer than you allowed.

> **Note**
> To protect your credentials, the client only sends an API key over plain `http://` to your own machine (`localhost`, `127.0.0.1` or `::1`). For any other address, please use `https://`. If you work on a network you trust, you can allow it with `allow_insecure_http=True` or by setting `MESH_THINGS_ALLOW_HTTP=1`.

## Versions

Each release of `mesh-things` matches a version of the API, and the API reports its version on every response. If you see a `MeshThingsVersionWarning`, the API has changed since your release was published. Upgrading `mesh-things` gives you its current set of methods.

## Examples

The [examples](examples/README.md) cover every part of the API, from signing up to reading the archive. They are included in the source distribution, and each one can be run on its own.
