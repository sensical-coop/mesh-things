# Mesh things package examples

These are small scripts that show the [mesh-things package](../README.md) at work with the API: from reading your meshes and their readings, to setting up a mesh, sharing data with others and working with the archive. Each script is independent, so you can copy whichever one you need and adapt it to your own project. They are also included in the package's source distribution.

For a description of every operation, its parameters and its responses, you can open the interactive API documentation at `/docs` on your instance, for example `http://localhost/docs`.

## Before you start

You will need Python 3.10 or newer. To install the package with everything the examples use:

```bash
pip install "mesh-things[pandas,archive]" duckdb
# or, from this repository:
pip install -e "..[pandas,archive]" duckdb
```

The scripts read their settings from these environment variables, so you only need to set them once:

| Variable | Description |
|---|---|
| `MESH_THINGS_URL` | The address of your instance. Defaults to `http://localhost`, a local stack started with `docker compose`. |
| `MESH_THINGS_API_KEY` | Your API key. You receive it when you sign up with `registry_create_owner.py`. |
| `SUPERUSER_API_KEY` | A superuser's key, only needed for the few scripts that manage the instance. |

## Reading data

These scripts only read from the API, so they are a safe way to explore. We suggest starting with `get_started.py`, which gives you an overview of your account.

```bash
# Your account, your meshes, their devices and the latest reading of each device
python3 get_started.py

# The latest value of every channel on a mesh, with units, optionally as a DataFrame
python3 get_latest_readings.py --mesh-id <mesh id>
python3 get_latest_readings.py --mesh-id <mesh id> --dataframe

# Data quality of one device: completeness, gaps, alarms and radio traffic
python3 get_device_health.py --device-uuid <device uuid> --start=-7d --range 7d

# The instance's catalog: telemetry types, measurements and units, detectors, algorithms
python3 get_catalog.py

# Public meshes, read without an API key
python3 get_public_meshes.py
```

To look at readings over time, `readings.py` walks through the devices you have registered, the channels they report, their values over a range of time and their latest values. Add `--dataframe` to see the values as a pandas DataFrame:

```bash
python3 readings.py --lookback=-7d
python3 readings.py --lookback=-7d --dataframe
python3 readings.py --lookback=-7d --mesh-id <mesh id> --node-id 111222333
```

> **Note**
> Please write `--lookback=-7d` with the `=` sign. Without it, `-7d` is read as a separate option instead of as a value.

The last example addresses a device by its mesh and node number rather than by its registration. This reaches devices that report readings but have never been registered.

Computed channels can be read in exactly the same way. These include the outputs of postprocessing (`derived`), data quality (`quality`) and the alarms that were raised (`alarms`):

```python
from mesh_things.client import MeshThings

api = MeshThings()
dew_point = api.readings.devices_get(device_uuid, channel="derived.dew_point", start="-7d", window="1h", agg="mean")
completeness = api.readings.devices_get(device_uuid, channel="quality.completeness_ratio", start="-7d")
alarms = api.readings.devices_get(device_uuid, channel="alarms.message", start="-7d")
```

Individual alarms are kept for 30 days. Totals per detector for longer periods come from `get_device_health.py`.

### Mesh traffic and topology

`mesh_stats.py` summarises a mesh's radio traffic: totals, packets by type, the busiest nodes, each gateway's share and signal, and how many hops packets took. `registry_mesh_topology.py` shows the radio links between nodes, longest first, followed by the newest traceroutes. A public mesh can be read without an API key.

```bash
python3 mesh_stats.py --mesh-id <mesh id> --range 7d
python3 registry_mesh_topology.py --mesh-id <mesh id> --since 7d
python3 registry_mesh_topology.py --mesh-id <mesh id> --node-id '!334af480'
```

## Setting up a mesh

A mesh holds the channel name and key that every device on your Meshtastic network shares. Each device on it is either a gateway, a node that relays traffic to the broker, or a regular node. The instance decodes a mesh's traffic once its gateway is registered. The other nodes appear on their own the first time one of their packets is decoded.

The channel key (`psk_b64`) and the devices' admin keys (`admin_keys_b64`) are only shown to the mesh's owner and to superusers.

```bash
# 1. Create your account. This prints an API key to export.
#    If your instance does not ask for terms, you can leave out --show-terms and --accept-terms.
python3 registry_create_owner.py --show-terms
python3 registry_create_owner.py --accept-terms --name "Alice" --email alice@example.com
export MESH_THINGS_API_KEY=...

# 2. Create a mesh with your channel name and key. This prints a mesh id to export.
python3 registry_create_mesh.py --show-terms
python3 registry_create_mesh.py --accept-terms --channel-id LongFast
export MESH_ID=...

# 3. Register the gateway that relays this mesh's traffic. Decoding starts from then on.
python3 registry_create_gateway.py --node-id 111222333 --label "office gateway"

#    Alternatively, let the mesh find its gateways on its own. Any gateway whose packets
#    decode with the mesh's key is registered automatically. --wait keeps listening and
#    prints each gateway as it appears.
python3 registry_discover_gateways.py $MESH_ID --on --wait 300

#    You can also turn a registered node into a gateway, or back into a node with --node.
python3 registry_device_role.py --device-uuid <device uuid>

# 4. Change the mesh. Only the values you pass are changed. A new key is sent to every
#    gateway on the mesh.
python3 registry_update_mesh.py $MESH_ID --label "home mesh"

# 5. Give a node its admin keys, for remote administration in Meshtastic. The keys you
#    pass replace the node's whole list, so repeat --admin-key-b64 for each key it needs.
python3 registry_add_admin_key.py --node-id 111222333 --admin-key-b64 QUFBQQ==

# 6. List the owners on the instance, and your own meshes and gateways
python3 registry_list_owners_meshes_and_gateways.py

# 7. Make the mesh public, then private again. Anyone can then read the mesh, its devices
#    and their latest readings, but nobody else can change them or see the channel key.
#    Pass --reader-api-key to see another owner's change being refused.
python3 registry_publish_mesh.py --reader-api-key <another owner's key>
```

## Bringing in a remote broker (sources)

A source brings the traffic of a topic on another MQTT broker into this instance. This is useful when a mesh's gateways already publish to a broker of their own. Creating a source needs the operator role, and you can only attach your meshes to the sources you created.

```bash
# 1. Ask for the operator role. A superuser approves the request.
python3 registry_request_operator.py --reason "I run the regional broker"
python3 registry_decide_operator_request.py --list            # with a superuser key
python3 registry_decide_operator_request.py --approve <request id>
python3 registry_request_operator.py --status

# 2. Create the source, after reading its terms. A superuser can grant the role in the same step.
python3 registry_create_source.py --show-terms
# The public Meshtastic broker shares these credentials openly. For your own broker, please keep TLS on.
python3 registry_create_source.py --accept-terms --server mqtt.meshtastic.org:1883 --no-ssl \
  --username meshdev --password large4cats --topic 'msh/EU_868/2/e/LongFast/#' \
  --grant-operator <owner id> --superuser-api-key $SUPERUSER_API_KEY
export SOURCE_ID=...

# 3. Attach your mesh to the source, then register its gateways as usual
python3 registry_attach_mesh_to_source.py
```

## Sharing data with others (sinks)

A sink lets a service of your choice subscribe to the readings of your meshes and devices, as JSON, on this instance's broker. The service receives its own credentials, which are shown only once, when the sink is created or its password is renewed. Creating a sink needs the operator role.

```bash
# 1. Create a sink for a whole mesh, after reading its terms
python3 registry_create_sink.py --show-terms
python3 registry_create_sink.py --accept-terms --label "Partner" \
  --stream decoded --stream alarms --mesh-id $MESH_ID
export SINK_ID=...   # then share the broker, username, password and topic filter it printed

# Limit it to one device, or renew its password (which disconnects the current consumer)
python3 registry_create_sink.py --update $SINK_ID --mesh-id "" --device-uuid <device uuid>
python3 registry_create_sink.py --rotate $SINK_ID

# 2. The service subscribes with those credentials, using any MQTT client. It needs no API key.
mosquitto_sub -h mqtt.example.org -p 8883 --capath /etc/ssl/certs \
  -u ... -P ... -t 'mt-sources-sinks/<sink id>/#'
```

## The measurement catalog

The catalog describes the data devices can report: the kinds of telemetry and the measurements in each, with their units. It is shared by every owner, and the instance fills it in from the Meshtastic definitions when it starts. Superusers can complete it, for example with a telemetry type's usual reporting interval. Owners can set the plausible range of a measurement on each of their devices.

```bash
# The measurements of a telemetry type, and their defaults
python3 registry_curate_telemetry_catalog.py --api-key $SUPERUSER_API_KEY \
  --payload-kind telemetry:environment_metrics --list

# The usual reporting interval of this kind of telemetry, in seconds (superusers)
python3 registry_curate_telemetry_catalog.py --api-key $SUPERUSER_API_KEY \
  --payload-kind telemetry:environment_metrics --default-reading-interval-seconds 900

# The plausible range of one measurement on one of your devices
python3 registry_curate_telemetry_catalog.py \
  --payload-kind telemetry:environment_metrics --device-uuid <device uuid> \
  --field-name temperature --range-min -40 --range-max 85
```

These values are not only descriptive: the data quality checks use them as soon as you save them.

## Postprocessing

A blueprint is a reusable recipe that turns raw readings into new values, for example a sensor's voltage into a gas concentration. It lists the channels it reads and the steps it runs, each step using one of the instance's algorithms. When you attach a blueprint to a device, you also give it that device's own calibration, since no two sensors are exactly alike. The results are computed live, and a backfill can compute them for past readings too.

```bash
# The available algorithms, and their calibration parameters
python3 registry_manage_blueprint.py --list-algorithms

# Create the built-in NO2 example, or your own from a JSON file
python3 registry_manage_blueprint.py
python3 registry_manage_blueprint.py --blueprint-file my_blueprint.json

# Attach it to a device, calibrate it, switch it on, and compute past values
python3 registry_device_postprocessing.py attach --device-uuid <device uuid> --blueprint-id <blueprint id>
python3 registry_device_postprocessing.py calibrate --device-uuid <device uuid> --postprocessing-id <id> \
    --step ppb --params '{"sensitivity": 0.42, "working_zero": 220.0}'
python3 registry_device_postprocessing.py enable --device-uuid <device uuid> --postprocessing-id <id>
python3 registry_device_postprocessing.py backfill --device-uuid <device uuid> --postprocessing-id <id> --start 2026-09-01
python3 registry_device_postprocessing.py show --device-uuid <device uuid>
```

The values a blueprint produces appear as `derived` channels on the device. They can be read, given units and checked for quality like any other channel.

## Exports

An export packs a mesh's readings over a range of days into one zip file. A CSV export contains one file per measurement and day, plus `channels.csv` with the units. A Parquet export contains the archive's hourly files and needs the operator role. The file is prepared in the background, you receive an email when it is ready, and the link works for 24 hours.

```bash
python3 export_download.py --mesh-id <mesh id> --start 2026-09-27 --stop 2026-09-28
python3 export_download.py --mesh-id <mesh id> --start 2026-09-27 --stop 2026-09-27 --node-id 431637602
python3 export_download.py --mesh-id <mesh id> --start 2026-09-27 --stop 2026-09-28 --format parquet
python3 export_download.py --mesh-id <mesh id> --start 2026-09-27 --stop 2026-09-28 --dataframe
```

## The Parquet archive

The archive keeps decoded and derived readings as Parquet files, for analysis on a larger scale. Each device joins it separately, on meshes owned by an operator, and only on instances that run it. Superusers and the mesh's owner, while an operator, can read it, with temporary credentials that the API issues.

```bash
# 1. Start archiving a device, or stop (stored data is kept)
python3 registry_device_archive.py --device-uuid <device uuid>
python3 registry_device_archive.py --device-uuid <device uuid> --off

# 2. Query the archive with DuckDB, or load it into pandas
python3 archive_duckdb.py --mesh-id <mesh id>
python3 archive_pandas.py --mesh-id <mesh id> --node-id 111222333

# 3. Or download one hour as a file, without any S3 client
python3 archive_download.py --mesh-id <mesh id>
python3 archive_download.py --mesh-id <mesh id> --day 2026-09-27 --hour 13
```

The archive is organised as one file per mesh and hour, in UTC:

```
{prefix}/mesh_id={mesh_id}/dt=YYYY-MM-DD/hour=HH/data.parquet
```

Each row keeps its decoded content in a `payload_json` column, since that content differs between kinds of payload. `mesh_things.pandas.archive_frame` spreads it into one column per channel for you.

> **Note**
> The temporary credentials last one hour by default and cannot be withdrawn early. On storage providers that cannot issue them, `archive_download.py` still works.

## Superusers

Superusers manage the whole instance. The role cannot be granted through the API: it is given with a command inside the API's container.

```bash
docker compose exec registry_api python manage.py createsuperuser --email you@example.com --name "You"
```

A superuser can see and manage every owner's meshes and devices, including their channel and admin keys.

## Opening data in a browser

A browser cannot send your API key in a header, so you can also add it to the address as `access_token`. This is handy for a quick look:

```
http://localhost/owners/me?access_token=<your API key>
http://localhost/meshes?access_token=<your API key>
```

For anything else, please use the scripts or the package, which send the key in a header. A key in an address can end up in your browser history and in server logs.
