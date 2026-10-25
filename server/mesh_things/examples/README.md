# mesh-things examples

Small, standalone scripts against the running API (`docker compose up`, or point
`MESH_THINGS_URL` at wherever it is actually deployed). Each script is independent -
copy-paste whichever one you need. They all go through the
[mesh-things client](../README.md), so none of them builds a URL or a header by hand,
and they are shipped with the package's source distribution. For the full endpoint
reference (every route, status code, and curl equivalent) see
[../../../docs/api-reference.md](../../../docs/api-reference.md).

```bash
pip install "mesh-things[pandas,archive]" duckdb   # or, from this repository:
pip install -e "..[pandas,archive]" duckdb
```

Env vars:
- `MESH_THINGS_URL` (default `http://localhost`, the gateway that serves both roles).
- `MESH_THINGS_API_KEY`, read by every script that needs auth, so you only have to
  export it once.
- `SUPERUSER_API_KEY`, for the superuser-only scripts.

The MQTT tools some walkthroughs below pair with (a fake gateway, a sink consumer) are
not API clients, so they live in the repository's
[server/examples/](../../examples/README.md).

## Registry role

A Mesh holds the shared channel_id + psk_b64 for a physical Meshtastic network. A
Device is always exactly one role: a gateway (a specific node registered against
the mesh that actually relays MQTT traffic - registering one is what starts
decoding, the rest of that mesh's devices need no registration of their own) or a
node (auto-discovered on first successful decode, or pre-registerable to set admin
keys in advance). See
[../../../docs/architecture.md#registered-gateways-only-gate](../../../docs/architecture.md#registered-gateways-only-gate)
and
[../../../docs/architecture.md#device-registration-and-the-is_allowed-gate](../../../docs/architecture.md#device-registration-and-the-is_allowed-gate).

`psk_b64` and `admin_keys_b64` are "password fields": only the resource's owner and
superusers see them in a response (see
[../../../docs/architecture.md#password-fields-psk_b64-admin_keys_b64-and-the-superuser-role](../../../docs/architecture.md#password-fields-psk_b64-admin_keys_b64-and-the-superuser-role)).

```bash
# 1. Create an owner ("sign up") - prints a MESH_THINGS_API_KEY to export
# On an instance with REGISTRY__TERMS_ENFORCED=false there are no terms: skip
# --show-terms and --accept-terms.
python3 registry_create_owner.py --show-terms      # signing up accepts these
python3 registry_create_owner.py --accept-terms --name "Alice" --email alice@example.com
export MESH_THINGS_API_KEY=...  # from the output above

# 2. Register a mesh under that owner (the shared channel_id + psk_b64) - prints a
#    MESH_ID to export
python3 registry_create_mesh.py --show-terms          # a mesh has its own terms
python3 registry_create_mesh.py --accept-terms --channel-id LongFast
export MESH_ID=...  # from the output above

# 3. Register a gateway against that mesh ("this node relays traffic for this mesh") -
#    this is the step that actually authorizes decoding
python3 registry_create_gateway.py --node-id 111222333 --label "office gateway"
#    ... or let the mesh find its gateways: any gateway whose packets decode with
#    its channel and PSK is registered automatically (operator-only on a default or
#    blank PSK). --wait keeps polling and prints each one as it appears.
python3 registry_discover_gateways.py $MESH_ID --on --wait 300
#    ... or promote a node that is already registered (and --node to demote it again)
python3 registry_device_role.py --device-uuid <device_uuid>

# 4. Edit the mesh (partial update - only what you pass changes; rotating the PSK
#    republishes every gateway on this mesh with the new key)
python3 registry_update_mesh.py $MESH_ID --label "home mesh"

# 5. Give the gateway node an admin key too (Meshtastic's Config.SecurityConfig.admin_key,
#    for remote node control - unrelated to the gateway decode gate).
#    --admin-key-b64 sets the node's *full* key list, not an addition -
#    admin_keys_b64 is write-only, so there's nothing to read back and append to.
#    Repeat the flag for more than one key.
python3 registry_add_admin_key.py --node-id 111222333 --admin-key-b64 QUFBQQ==

# 6. List owners (public) and this owner's meshes and gateways
python3 registry_list_owners_meshes_and_gateways.py

# 7. Make this mesh public, then private again. Publishing widens reads only -
#    anyone, with or without an API key, can read the mesh, its devices and
#    their latest readings, but never edit them or see psk_b64. Pass
#    --reader-api-key to watch another owner's write get refused.
python3 registry_publish_mesh.py --reader-api-key <other owner's key>
```

### Sources (remote MQTT brokers)

A source bridges a remote broker's topic into this instance, so a mesh whose
gateways publish elsewhere is ingested like any other. Every source route needs an
operator key, and operators only see and attach meshes to the sources they created. See
[../../../docs/api-reference.md#sources](../../../docs/api-reference.md#sources).

```bash
# 0. Become an operator: file a request, a superuser approves it
python3 registry_request_operator.py --reason 'I run the regional broker'
python3 registry_decide_operator_request.py --list            # superuser key
python3 registry_decide_operator_request.py --approve <request id>
python3 registry_request_operator.py --status                 # now approved

# 1. As an operator (--grant-operator promotes an owner first, with a superuser key)
python3 registry_create_source.py --show-terms          # read the terms first
python3 registry_create_source.py --accept-terms --server mqtt.meshtastic.org:1883 --no-ssl \
  --username meshdev --password large4cats --topic 'msh/EU_868/2/e/LongFast/#' \
  --grant-operator <owner uuid> --superuser-api-key $SUPERUSER_API_KEY
export SOURCE_ID=...  # from the output above

# 2. As the mesh owner: point the mesh at it, then register gateways as usual
python3 registry_attach_mesh_to_source.py
```

To test a source in development, publish fake readings to its broker as one of the
mesh's gateways. The packets are real Meshtastic protobufs, encrypted with the mesh's
key (`AQ==`, Meshtastic's default, unless `--psk-b64` says otherwise), carrying
`environment_metrics`. Use a test broker, never a public one. The topic must sit under
the source's topic filter, and the gateway must be registered on a mesh attached to it,
or the instance drops the packets as it would a stranger's.

```bash
# Register the fake gateway on the attached mesh (created with --psk-b64 AQ==)
python3 registry_create_gateway.py --node-id 439041101      # !1a2b3c4d

# Then publish as it: 10 readings, one every 5 seconds, to msh/EU_868/2/e/LongFast/!1a2b3c4d
python3 ../../examples/source_publish_fake.py --broker test-broker.example.org:8883 \
  --username dev --password ... --topic-prefix msh/EU_868/2/e --channel LongFast \
  --gateway-id '!1a2b3c4d' --count 10 --interval 5

# Another node relayed by that gateway, around 30 C; --count 0 runs until Ctrl-C
python3 ../../examples/source_publish_fake.py --broker localhost:1883 --no-ssl \
  --gateway-id '!1a2b3c4d' --node-id 123456789 --temperature 30 --count 0
```

They show up as any reading does:
`python3 readings.py --device-uuid <device uuid> --payload-kind telemetry:environment_metrics`.

### Sinks (third parties subscribing to readings)

A sink lets a service you choose subscribe to the readings of your meshes and devices on
this instance's broker, as JSON, with credentials only it holds. Every sink route needs
an operator key, and only meshes owned by an operator can be attached. The credentials
are shown once, on creation and on rotation. See
[../../../docs/api-reference.md#sinks](../../../docs/api-reference.md#sinks).

```bash
# 1. As an operator: read the terms, then create a sink on a whole mesh
python3 registry_create_sink.py --show-terms
python3 registry_create_sink.py --accept-terms --label "Partner" \
  --stream decoded --stream alarms --mesh-id $MESH_ID
export SINK_ID=...  # and hand the printed broker, username, password and topic filter over

# Narrow it to one device, or change what it carries (lists replace the current ones)
python3 registry_create_sink.py --update $SINK_ID --mesh-id "" --device-uuid <device_uuid>
python3 registry_create_sink.py --rotate $SINK_ID        # new password, consumer disconnected

# 2. As the third party: subscribe with the credentials, no API key needed
SINK_BROKER=mqtt.example.org:8883 SINK_USERNAME=... SINK_PASSWORD=... \
SINK_TOPIC_FILTER='mt-sources-sinks/<sink id>/#' python3 ../../examples/sink_consume.py
```

To test a sink, count what it delivers instead. It prints a running total and a summary
per stream, node and payload kind; `--expect` exits 1 if fewer arrive in `--duration`.
Give it its own `--client-id`: the broker disconnects any other client using the same one.

```bash
SINK_BROKER=mqtt.example.org:8883 SINK_USERNAME=... SINK_PASSWORD=... \
SINK_TOPIC_FILTER='mt-sources-sinks/<sink id>/#' python3 ../../examples/sink_count.py --duration 300

# Paired with source_publish_fake.py: 10 readings published, 10 expected within 2 minutes
python3 ../../examples/sink_count.py --expect 10 --duration 120
```

`--mesh-id ""` sends an empty list, which detaches every mesh; `--device-uuid ""` does the same for devices.

### Sensor / measurement catalog

`TelemetryVariant`/`MeasurementType` (what a device *can* report) are global,
shared catalogs pre-seeded from the Meshtastic protobuf schema whenever the
`registry_api` container starts (not from these scripts - they only edit rows that
already exist).
`TelemetryVariant` is keyed by wire-format message type (e.g.
`telemetry:environment_metrics`), **not** verified physical hardware - one
variant can be produced by several different chips, so `name`/`model`/
`datasheet_url` are only an optional curated "commonly this chip" hint. A
third table, `TelemetryVariantMeasurement`, links the two and carries which
detectors default on per field. Catalog writes below require a superuser
key - see
[../../../docs/architecture.md#device-telemetry-variant--measurement-catalog](../../../docs/architecture.md#device-telemetry-variant--measurement-catalog).

```bash
# List every field linked to a telemetry variant, and its catalog defaults
python3 registry_curate_telemetry_catalog.py --api-key $SUPERUSER_API_KEY \
  --payload-kind telemetry:environment_metrics --list

# Set the telemetry variant's expected reporting interval (seconds) - a firmware
# ModuleConfig fact, not derivable from the protobuf schema, so seeding always
# leaves it null
python3 registry_curate_telemetry_catalog.py --api-key $SUPERUSER_API_KEY \
  --payload-kind telemetry:environment_metrics --default-reading-interval-seconds 900

# Set the range bounds for one field on one device. Unlike the two above this is
# per-device, not catalog-wide, so it's the mesh owner's key rather than a
# superuser's - one device's plausible range can differ from another's on the
# same field.
python3 registry_curate_telemetry_catalog.py --api-key $MESH_THINGS_API_KEY \
  --payload-kind telemetry:environment_metrics --device-uuid <device uuid> \
  --field-name temperature --range-min -40 --range-max 85
```

These bounds and intervals aren't just documentation: editing them publishes to
`mesh.quality_config.v1`, which is what tunes the live data-quality checks - see
[../../../docs/architecture.md#data-quality-checks](../../../docs/architecture.md#data-quality-checks).

### Postprocessing

A **blueprint** is a reusable recipe: the input slots it reads and ordered steps,
each running an algorithm from `common/algorithms/`. A step takes its inputs from
a slot or from an earlier step's output, so `ADC -> ppb -> ug/m3` is two chained
steps. **Attaching** it to a device binds the slots to that device's channels and
gives it the device's own **calibration**, because two sensors of the same build
never share their sensitivity. It then runs on live telemetry in the Flink tier,
and a **backfill** recomputes stored history. See
[../../../docs/data-quality.md#postprocessing](../../../docs/data-quality.md#postprocessing).

```bash
# What's available, and which parameters are per-device calibration
python3 registry_manage_blueprint.py --list-algorithms

# Create the built-in NO2 example, or supply your own JSON
python3 registry_manage_blueprint.py
python3 registry_manage_blueprint.py --blueprint-file my_blueprint.json

# Attach it, calibrate the ppb step, enable, and recompute history
python3 registry_device_postprocessing.py attach --device-uuid <device uuid> --blueprint-id <blueprint id>
python3 registry_device_postprocessing.py calibrate --device-uuid <device uuid> --postprocessing-id <id> \
    --step ppb --params '{"sensitivity": 0.42, "working_zero": 220.0}'
python3 registry_device_postprocessing.py enable --device-uuid <device uuid> --postprocessing-id <id>
python3 registry_device_postprocessing.py backfill --device-uuid <device uuid> --postprocessing-id <id> --start 2026-09-01
python3 registry_device_postprocessing.py show --device-uuid <device uuid>
```

To add your own algorithm, drop a decorated function into a module under
`server/common/algorithms/`, declaring its parameters with `Param`
and marking the per-sensor ones `calibration=True`. Registry imports the same
registry, so a step naming an unknown function, mis-binding an input or setting
a calibration parameter is rejected with a `400` when written.

Derived channels are registered on the device when the blueprint is attached,
under the flat `derived` payload_kind, so they can be given units and range
bounds exactly like real sensor fields:

```bash
# Everything this device produces - measured, derived and quality channels,
# each tagged with an `origin` so you can tell them apart
curl -s -H "Authorization: Bearer $MESH_THINGS_API_KEY" \
  http://localhost:8090/devices/<device id>/measurements

# Just the computed ones
curl -s -H "Authorization: Bearer $MESH_THINGS_API_KEY" \
  "http://localhost:8090/measurements?kind=computed"
curl -s -H "Authorization: Bearer $MESH_THINGS_API_KEY" \
  "http://localhost:8090/measurements?payload_kind=computed:quality"
```

### Superuser

Not an example script - superuser is granted via a CLI command run inside the
`registry_api` container, not through the API (there's no route for it,
deliberately):

```bash
docker compose exec registry_api python manage.py createsuperuser \
  --email you@example.com --name "You"
```

A superuser sees and manages every owner's meshes/devices, `psk_b64` and
`admin_keys_b64` included - see
[../../../docs/api-reference.md#superuser](../../../docs/api-reference.md#superuser).

### Browsing GET routes in a browser

A browser address bar can't send an `Authorization` header, so authenticated `GET`
routes also accept the key as an `?access_token=` query param (checked only when no
header is present). Paste a URL like this straight into a browser tab:

```
http://localhost:8090/owners/me?access_token=<your MESH_THINGS_API_KEY>
http://localhost:8090/meshes?access_token=<your MESH_THINGS_API_KEY>
http://localhost:8090/devices?access_token=<your MESH_THINGS_API_KEY>
```

Prefer the `Authorization` header (as every script above does) for anything scripted -
query-string tokens end up in browser history and server access logs. See
[../../../docs/api-reference.md#browsing-get-routes-directly-from-a-browser-address-bar](../../../docs/api-reference.md#browsing-get-routes-directly-from-a-browser-address-bar).

## Readings role

Requires `MESH_THINGS_API_KEY` - readings checks the key is valid with registry and scopes
results to that owner's own devices (a superuser key sees every device); see
[../../../docs/api-reference.md#authentication](../../../docs/api-reference.md#authentication).

```bash
# registry: which devices exist -> which channels they report
#   -> readings: the values (timeseries + latest)
# Use --lookback=-7d (with the =) - argparse otherwise reads -7d as a flag, not a value.
python3 readings.py --lookback=-7d

# The same values addressed the store-native way. No registry lookup at all,
# which is the point: this reaches devices registry has never heard of.
python3 readings.py --lookback=-7d --mesh-id <mesh_id> --node-id 111222333
```

Note the split the script demonstrates: **what exists** comes from registry
(`GET /devices`, `GET /devices/{uuid}/measurements`), **what the values were**
from readings. readings has no device or channel listing of its own - see
[../../../docs/api-reference.md#which-address-to-use](../../../docs/api-reference.md#which-address-to-use).

Derived channels and quality metrics are readable through the same routes with no
special handling - they're ordinary InfluxDB measurements, tagged with the same
`mesh_id`/`node_id` and so subject to the same per-owner scoping:

```bash
# A postprocessing's output (measurement "derived", field = the derived field name)
curl -s -H "Authorization: Bearer $MESH_THINGS_API_KEY" \
  "http://localhost:8091/readings/devices/<device_uuid>?channel=derived.dew_point&start=-7d&stop=now()&window=1h&agg=mean"

# Completeness over time (measurement "quality"), and fired alarms (measurement "alarms")
curl -s -H "Authorization: Bearer $MESH_THINGS_API_KEY" \
  "http://localhost:8091/readings/devices/<device_uuid>?channel=quality.completeness_ratio&start=-7d&stop=now()"
curl -s -H "Authorization: Bearer $MESH_THINGS_API_KEY" \
  "http://localhost:8091/readings/devices/<device_uuid>?channel=alarms.message&start=-7d&stop=now()"
```

Alarms are kept one by one for 30 days (`INFLUX__ALARMS_RETENTION_DAYS`), so `alarms.*`
returns nothing further back. Longer-term totals per detector come from the device's
quality figures, `GET /readings/devices/<device_uuid>/quality`.

## Mesh traffic stats

Totals, packets by portnum, the busiest nodes, each gateway's share and SNR, and the
hop distribution for one mesh over `1h`, `24h`, `7d` or `30d`. Names are joined from the registry's device list.
A public mesh needs no key.

```bash
python3 mesh_stats.py --mesh-id <mesh_id> --range 7d
```

## Mesh topology

Who hears whom: radio links from traceroutes, neighbor reports and direct receptions,
longest first, then the newest traceroutes with both directions of their route.

```bash
python3 registry_mesh_topology.py --mesh-id <mesh_id> --since 7d
python3 registry_mesh_topology.py --mesh-id <mesh_id> --node-id '!334af480'
```

## Exports

A mesh's readings over a range of days as one zip, for its owner (and superusers). CSV
reads every device from InfluxDB, a file per measurement and day plus `channels.csv` with
units; `--node-id` narrows it. Parquet holds the archive's hourly files and needs the
operator role. The zip is built in the background, the owner is emailed when it is ready,
and the link works for 24 hours. Full profile only. See
[../../../docs/api-reference.md#exports](../../../docs/api-reference.md#exports).

```bash
python3 export_download.py --mesh-id <mesh_id> --start 2026-09-27 --stop 2026-09-28
python3 export_download.py --mesh-id <mesh_id> --start 2026-09-27 --stop 2026-09-27 --node-id 431637602
python3 export_download.py --mesh-id <mesh_id> --start 2026-09-27 --stop 2026-09-28 --format parquet
```

## Parquet archive (operators)

The archive keeps decoded and derived readings as Parquet, for analysis at a scale the
readings routes are not built for. It is opt-in **per device**, only on meshes owned by
an operator or a superuser, and only on instances that run it (the full profile). Only
the mesh's owner, while an operator, and superusers can read it. See
[../../../docs/api-reference.md#parquet-archive](../../../docs/api-reference.md#parquet-archive).

Layout is one object per mesh per hour (UTC), holding only the devices that opted in:

```
{prefix}/mesh_id={mesh_id}/dt=YYYY-MM-DD/hour=HH/data.parquet
```

```bash
pip install -r requirements.txt      # adds duckdb, pandas, pyarrow

# 1. As the mesh owner (an operator): archive a device from now on
python3 registry_device_archive.py --device-uuid <device_uuid>
python3 registry_device_archive.py --device-uuid <device_uuid> --off   # stop; stored rows stay

# 2. Query the mesh with temporary S3 credentials from readings, scoped to its prefix
python3 archive_duckdb.py --mesh-id <mesh_id>
python3 archive_duckdb.py --mesh-id <mesh_id> --node-id 111222333

# The same, as a DataFrame
python3 archive_pandas.py --mesh-id <mesh_id>

# 3. Or fetch one hour as a file, with no S3 client (defaults to the latest hour)
python3 archive_download.py --mesh-id <mesh_id>
python3 archive_download.py --mesh-id <mesh_id> --day 2026-09-27 --hour 13
```

The queries print rows per device and day and the most recent `environment_metrics`,
pulling values out of the `payload_json` column - the payload shape varies by
`payload_kind`, so it is stored as JSON rather than exploded into columns.

Credentials last `READINGS__ARCHIVE_CREDENTIAL_TTL_S` (an hour by default) and cannot be
revoked early. On a storage provider without STS the credentials route answers `404`;
`archive_download.py` still works there.
