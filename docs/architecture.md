# Architecture

```
Remote MQTT brokers (sources) --EMQX bridge + republish rule--+
                                                               v
External MQTT Broker (EMQX, TLS)   own topic + {namespace}/{source_id}/...
     |  $share/{group}/{topic}, QoS 1, clean_session=False, stable client_id per replica
     v
mqtt_kafka_bridge (N replicas)  -- source gate, from mesh.keys.v1
     |
     v
Kafka: mesh.telemetry.raw.v1
     |                                            registry role (Django + DRF + Postgres)
     v                                            :8090
PyFlink decode_job.py <----------------------------- broadcast: mesh.keys.v1 +
     |                                                          mesh.node_rejections.v1 (both compacted)
     |
     v
Kafka: mesh.telemetry.decoded.v1 ---------------------------------------+
     |                                                                   v
     |                                         postprocessing_job.py  <-- broadcast:
     |                                         (device plans)            mesh.postprocessing_config.v1
     |                                                  |                (compacted, from registry)
     |                                                  v
     |                                  Kafka: mesh.telemetry.derived.v1
     |                                                  |
     |------------------------|-------------------------+--------------|
     v                        v                                        v
influxdb_writer          s3_writer                  pattern_detection_job.py  <-- broadcast:
(decoded + derived)      (decoded + derived)        (flat_value, range;        mesh.quality_config.v1
     |                        |                      decoded + derived)
     v                        v
InfluxDB :8086           MinIO/S3 :9000
     ^                   (Parquet, dt=/hour=)
     |
readings role :8091
(reads InfluxDB)
                                                                  |                    ^  (compacted)
                                                                  |                    |
                                        absence_detection_job.py  |            registry role
                                        (timers; reads            |            (catalog + device
                                         mesh.sensor_discovery.v1)|             interval edits)
                                                     |            |
                                                     v            v
                                                  Kafka: mesh.telemetry.alarms.v1
                                                     |                  |
                                                     v                  v
                                      influxdb_writer          registry alarm consumer
                                      (measurement "alarms")   (resolves owner -> email)

InfluxDB :8086 --> quality_worker (Celery) --> Kafka: mesh.telemetry.alarms.v1
                   - completeness/gap analysis        --> InfluxDB "quality"
                   - postprocessing backfills         --> Kafka: mesh.telemetry.derived.v1

decoded + derived + alarms --> sink_dispatcher --> EMQX {namespace}-sinks/{sink_id}/...
                               (mesh.sink_config.v1)   --> third-party consumers, one user per sink
```

The data-quality half of that diagram is covered in
[data quality checks](#data-quality-checks) and
[device fault detection](#device-fault-detection); the operational guide is
[data-quality.md](data-quality.md).

## Services and ports

| Service | Container name | Port(s) | Purpose |
|---|---|---|---|
| `mqtt_kafka_bridge` | (scaled, no fixed name) | health: `MQTT_BRIDGE__HEALTH__PORT` (9090, internal) | MQTT -> Kafka raw |
| `kafka` | `kafka` | 9092 (external), 9093/29092 (controller) | KRaft, single broker |
| `kafka-topics-init` | `kafka-topics-init` | - (runs once, then exits) | Pre-creates every topic before anything subscribes — consumers can't auto-create topics (KIP-361), so a new topic added in code but not here silently never exists. Two loops: plain event topics, and `cleanup.policy=compact` changelogs |
| `kafbat-ui` | `kafbat-ui` | 8080 | Kafka topic browser. Opt-in through the `kafka-ui` profile |
| `jobmanager` / `taskmanager` | `jobmanager` / `taskmanager` | 8081 (Flink dashboard) | Flink session cluster; runs all four jobs. JVM sizes are pinned in `x-flink-state-properties` - see [flink.md](flink.md) |
| `flink-job` | `flink-job` | - | One-shot: submits `decode_job.py` detached, then exits |
| `registry_api` | `registry-api` | `REGISTRY__PORT` (8090) | `APP_ROLE=registry`: mesh, device and owner CRUD, plus `/schema` and `/docs` for the whole API |
| `registry_device_consumer` | `registry-device-consumer` | - (internal) | `manage.py consume_device_sightings`; separate process from the web container |
| `registry_gateway_discovery` | `registry-gateway-discovery` | - (internal) | `manage.py consume_gateway_candidates`; registers gateways for meshes with discovery on - see [gateway discovery](#gateway-discovery) |
| `registry_sensor_discovery_consumer` | `registry-sensor-discovery-consumer` | - (internal) | `manage.py consume_sensor_discovery`; populates the device telemetry-variant/Measurement catalog |
| `postgres` | `postgres` | - (internal) | Backs the registry; the readings role reads it as `readings_ro` |
| `influxdb_writer` | `influxdb-writer` | `INFLUXDB_WRITER__HEALTHCHECK_PORT` (19090) | decoded and derived -> InfluxDB; alarms -> their own 30-day bucket |
| `s3_writer` | `s3-writer` | `S3_WRITER__HEALTHCHECK_PORT` (19091) | decoded and derived readings of archived devices -> Parquet on S3/MinIO - see [sinks](#sinks-and-the-parquet-archive) |
| `mesh_stats_writer` | `mesh-stats-writer` | `MESH_STATS_WRITER__HEALTHCHECK_PORT` (19094) | `mesh.traffic.v1` -> per-mesh traffic statistics in the `mesh_stats` bucket, and hourly direct links -> `mesh.links.v1` - see [mesh traffic stats](#mesh-traffic-stats-readings) |
| `registry_topology_consumer` | `registry-topology-consumer` | - (internal) | `manage.py consume_topology`; traceroutes and RF links into Postgres - see [mesh topology](#mesh-topology-registry) |
| `sink_dispatcher` | `sink-dispatcher` | `SINK_DISPATCHER__HEALTHCHECK_PORT` (19093) | decoded, derived and alarms of devices with an MQTT sink -> this instance's EMQX, `full` or `sinks` profile - see [MQTT sinks](#mqtt-sinks) |
| `minio` | `minio` | 9000 (API), 9001 (console) | Bundled S3-compatible storage, `minio` profile; left out when the archive is on an external S3 |
| `minio_init` | `minio-init` | - (runs once, then exits) | `minio` profile: creates the bucket and the read-only `archive-reader` user readings issues credentials from |
| `influxdb` | `influxdb` | 8086 | Time-series store |
| `readings_api` | `readings-api` | `READINGS__PORT` (8091) | `APP_ROLE=readings`: `/readings/*` over InfluxDB. Same image, read-only Postgres role - see [roles](#roles-registry-and-readings) |
| `readings_export_worker` | `readings-export-worker` | - (internal) | `manage.py run_export_worker`; builds [exports](#exports) into the archive bucket. Full profile |
| `redis` | `mesh-things-redis` | - (internal) | Shared cache for both APIs - see [roles](#roles-registry-and-readings) |
| `caddy` | `caddy` | 80, 443 | Reverse proxy fronting both roles - see [reverse proxy](#reverse-proxy) |
| `registry_quality_alarms_consumer` | `registry-quality-alarms-consumer` | - (internal) | `manage.py consume_quality_alarms`; emails a device's owner when a quality alarm fires |
| `quality_worker` | `quality-worker` | - (internal) | Celery worker: completeness checks, postprocessing backfills and the daily alarm counts - see [data quality checks](#data-quality-checks) |
| `influx_init` | `influx-init` | - (one-shot) | Creates the `alarms` (30-day) and `alarm_counts` buckets on every `up` |
| `quality_worker_beat` | `quality-worker-beat` | - (internal) | Celery beat; one scheduler regardless of worker count |
| `postprocessing-job` | `postprocessing-job` | - | One-shot submitter; runs every enabled device postprocessing on live telemetry - see [postprocessing](#postprocessing) |
| `pattern-detection-job` | `pattern-detection-job` | - | One-shot submitter; `flat_value` + `range` stream checks |
| `absence-detection-job` | `absence-detection-job` | - | One-shot submitter; "device stopped publishing", the only job using Flink timers |
| `flink-watchdog` | `flink-watchdog` | - | Resubmits any job that is no longer live, from its newest checkpoint |
| `server_monitor` | `server-monitor` | 8095 (loopback unless `compose/monitor.public.yml`) | `monitor` profile, meant for another machine: probes the stack end to end from outside and emails superusers - see [server monitor](#server-monitor) |
| `monitor_caddy` | `monitor-caddy` | 80, 443 | Only with `compose/monitor.caddy.yml`, on the monitor's machine: serves its status API on `MONITOR__DOMAIN` over HTTPS |

The four `*-job` services are **one-shot submitters**, not long-running
processes: each runs `flink/submit-job.sh`, which submits its job detached and
exits, skipping submission entirely if that job is already live. They show as
`Exited (0)` in `docker compose ps`, which is the healthy steady state - the
jobs themselves run inside `taskmanager`. This replaced four permanently
attached `flink run` clients that held ~550 MB of JVM each, and removed the
duplicate-job trap that made bringing the stack up a careful, one-at-a-time
ritual.

`flink-watchdog` covers what the one-shot submitters cannot. The cluster has no
high availability, so a jobmanager restart or a host reboot drops every job,
and the submitters, having exited, never run again. The watchdog restarts with
the host, starts only after the submitters have finished, and every minute runs
the same idempotent `submit-job.sh` for each job, so a lost job resumes from its
newest checkpoint. See [flink.md](flink.md).

### One image per Dockerfile, not one per service

Seventeen services build from five Dockerfiles. Compose derives an image tag per
*service* unless you name the image, which meant those five images existed as
seventeen tags and `docker compose build <one>` left the siblings on old code -
how a stale sensor-discovery consumer once ran a day behind the API beside it.

The `x-*-image` anchors at the top of `docker-compose.yml` pin a shared
`image:` per Dockerfile (`mesh-things/api:latest` and so on), so every
service built from the same Dockerfile resolves to the same image ID and they
cannot drift. The names match what `.github/workflows/deploy.yml` publishes to
ghcr.io, so a registry-based deployment reads identically.
`server_monitor` has its own anchor and image, `mesh-things/monitor:latest`,
built from `monitor/Dockerfile` with only `mesh_things`, `common/` and `monitor/`, so the
machine it runs on never pulls Kafka, InfluxDB or Parquet libraries.

### Shared code: the `mesh-things` package and `common/`

Code used by more than one service lives in two places:

- **`server/mesh_things/`** is the `mesh-things` distribution (import
  `mesh_things`), the one that is published to PyPI ([plan #31](../plans/31-mesh-things-package.md)).
  It holds what both the server and API clients need:
  - the channel and `payload_kind` vocabulary (`channels`);
  - node ids, units, query validation, timestamps and env parsing;
  - detector names, sink stream names (`streams`), export formats and statuses (`exports`);
  - the `Telemetry` catalog walk (`catalog`), which the catalog seed command uses;
  - portnum names (`portnums`);
  - the MQTT envelope codec (`codec`).

  The bare install needs only `httpx`, for the client. The `[protobuf]` extra adds the
  pinned `meshtastic` package, and `[codec]` adds `cryptography` on top of it.
- **`server/common/`** holds the server-only modules, which import from
  `mesh_things`.

The package also ships a snapshot of the OpenAPI document,
`mesh_things/client/openapi.json`, which the client binds its methods to. Three things
keep it in step with the API:

- `scripts/regen-client-schema.sh` regenerates it from the `registry_api` image, with a
  fixed environment and with `servers` removed.
- The `client-schema` job in `pr-checks.yml` regenerates it and fails when the committed
  copy differs.
- `scripts/check-client-version.sh` fails when the snapshot differs from the base branch
  but `mesh_things.__version__` was not raised.

That version is also the schema's `info.version` and the `API-Version` header on every
response (`api_project/middleware.py`), so one number names an API shape.

The client (`mesh_things.client`, httpx, sync and async) declares no endpoint itself:
- **Methods.** At construction it reads the snapshot and adds one namespace per tag and
  one method per operation. The name is the operationId without its tag prefix, with
  `retrieve` read as `get` and `destroy` as `delete`.
- **Arguments.** Each method's signature is built from the operation's parameters, and
  its docstring is the operation's description.
- **Types.** `_namespaces.pyi`, generated alongside the snapshot, lists the same methods
  for type checkers.

A new endpoint therefore reaches the client with nothing more than a regenerated
snapshot. Releasing the package to PyPI is in [client.md](client.md#releasing).

Every image installs the package from the repository before copying its own code:
`api`, `monitor` and the pipeline and Flink images with `[codec]`, `quality_worker`
bare. A change to it therefore needs every image rebuilt, not only the service you
are working on.

### Django settings, per environment

Both APIs load a settings *package*, not a module:
`base.py` holds everything true everywhere, `dev.py` adds local conveniences
(MailHog, `DEBUG`, a permissive `ALLOWED_HOSTS`), and `prod.py` carries none of
that and validates at import time. `docker-compose.yml` (the base file) selects
`.prod` by default - it's the production invocation now, see
`docs/known-gaps.md`; `docker-compose.dev.yml` overrides it to `.dev`.

The point is that production never *references* development-only
infrastructure - MailHog appears in `dev.py` and nowhere else - and that a
leftover dev value stops the container at boot with a specific message rather
than surfacing at the first signup, or never surfacing at all in the case of
`DEBUG`. See [deploy.md](deploy.md#django-settings).

Environment parsing goes through `mesh_things.env`, which treats a set-but-empty
variable as unset. `REGISTRY__BEHIND_TLS=` previously read as "false" and quietly
disabled HSTS and secure cookies while looking configured.

## Kafka topics

| Topic | Producer | Consumer(s) | Notes |
|---|---|---|---|
| `mesh.telemetry.raw.v1` | `mqtt_kafka_bridge` | `flink-job` | Raw protobuf `ServiceEnvelope` bytes |
| `mesh.telemetry.rawhealth.v1` | `mqtt_kafka_bridge` | - | Bridge health pings |
| `mesh.keys.v1` | `registry_api` | `flink-job`, `mqtt_kafka_bridge` | Compacted; gateway device key changelog, broadcast state. The bridge reads only `source_id`, for the [source gate](#mqtt-sources) |
| `mesh.node_rejections.v1` | `registry_api` | `flink-job` | Compacted; node reject-list changelog, broadcast state |
| `mesh.telemetry.decoded.v1` | `flink-job` | `influxdb_writer`, `s3_writer`, `postprocessing-job`, `pattern-detection-job`, `sink_dispatcher` | Decoded JSON, one per packet |
| `mesh.links.v1` | `mesh_stats_writer` | `registry_topology_consumer` | One-day retention; one summary per mesh, node and gateway for each closed hour of direct receptions |
| `mesh.traffic.v1` | `flink-job` (`decode_consumer` in lite) | `mesh_stats_writer` | One-day retention; one event per reception of every packet from a registered gateway, decoded or not, with routing and signal fields and no payload |
| `mesh.sink_config.v1` | `registry_api` | `s3_writer`, `sink_dispatcher` | Compacted; effective state in three key shapes: the sinks a device's readings go to (`archive`, `sink:<uuid>`), keyed `<mesh_id>:<device_id>`; the MQTT sinks every node of a mesh goes to, keyed `mesh:<mesh_id>`; and each MQTT sink's streams, keyed `sink:<uuid>` - see [sinks](#sinks-and-the-parquet-archive) |
| `mesh.postprocessing_config.v1` | `registry_api` | `postprocessing-job` | Compacted; every enabled postprocessing plan of a device, keyed `<mesh_id>:<device_id>`, broadcast state - see [postprocessing](#postprocessing) |
| `mesh.telemetry.derived.v1` | `postprocessing-job`, `quality_worker` (backfills) | `influxdb_writer`, `s3_writer`, `pattern-detection-job`, `sink_dispatcher` | Derived channels in the decoded envelope shape; backfilled events carry `"backfill": true` and are ignored by detection |
| `mesh.rules.v1` | (Key API, extend for this) | - | Compacted; **superseded** by `mesh.quality_config.v1` - retained but no longer consumed |
| `mesh.quality_config.v1` | `registry_api` | `pattern-detection-job`, `absence-detection-job` | Compacted; catalog detector defaults per channel, a device's own range bounds, and reading/publish intervals per device, broadcast state - see [data quality checks](#data-quality-checks) |
| `mesh.telemetry.alarms.v1` | `pattern-detection-job`, `absence-detection-job`, `quality_worker` | `influxdb_writer`, `registry_quality_alarms_consumer`, `sink_dispatcher` | Alarm events; one shape from both tiers, `source` distinguishes stream vs batch |
| `mesh.devices.v1` | `flink-job` | `registry_api` | Not compacted; device-sighted events auto-creating/refreshing node Device rows |
| `mesh.gateway_candidates.v1` | `mqtt_kafka_bridge` | `registry_gateway_discovery` | Not compacted, one-day retention; paced samples of unregistered gateways' traffic, keyed `<source_id or own>:<gateway_id>` - see [gateway discovery](#gateway-discovery) |
| `mesh.sensor_discovery.v1` | `flink-job`, `quality_worker` | `registry_api` | Not compacted; field-name-only discovery events populating the device telemetry-variant/Measurement catalog. The worker reuses it to register a device's `quality` channels through the same path. Derived channels are registered by registry itself, when a blueprint is attached |

Topics that delete old data keep the broker's default week, capped at 1 GB each
(`KAFKA_LOG_RETENTION_BYTES` in `compose/base.yml`), so a busy source or a loop cannot
fill the disk; the overrides above are tighter. Compacted topics are never trimmed by size.

## Decoded message shape

```json
{
  "node_id": 123456789,
  "to": 4294967295,
  "packet_id": 42,
  "portnum": 67,
  "request_id": null,
  "rx_time": 1700000000,
  "hop_start": 3,
  "hop_limit": 1,
  "rx_snr": 6.25,
  "rx_rssi": -97,
  "relay_node": 77,
  "next_hop": null,
  "via_mqtt": false,
  "channel_id": "LongFast",
  "gateway_id": 2864434397,
  "mesh_id": "11111111-2222-3333-4444-555555555555",
  "payload_kind": "telemetry:device_metrics",
  "payload": {"device_metrics": {"battery_level": 87, "voltage": 3.98}}
}
```

The routing fields say how the packet reached the gateway that heard it.
`hop_start - hop_limit` is the hops taken; `hop_start` is 0 on firmware that predates
it. `rx_snr` and `rx_rssi` are null when the gateway did not hear the packet over the
air (relayed through MQTT, or from its own node), since the firmware reports 0 there.
`relay_node` and `next_hop` hold only the last byte of a node number, as the firmware
sends them, and are null when unset.

`payload_kind` is what every sink (`writer/point_builders.py`, `postprocessing_job.py`,
`pattern_detection_job.py`) dispatches on. New portnums get a name in
`mesh_things.portnum_registry` and everything downstream picks them up automatically.
`mesh_id` (the registry `Mesh` UUID, added by `decode_job.py` from the gateway's
broadcast state) is only present from this point forward — see
[roles](#roles-registry-and-readings) for why it's there and why
older, pre-existing messages won't have it.

`gateway_id` is a number here, not the `!aabbccdd` the wire carries. Both name
the same Meshtastic node: the hex is its unsigned 32-bit rendering, and
`mesh_things.node_ids` converts between them. The wire form survives where it
has to match what the firmware sends - the MQTT topic, `ServiceEnvelope`, and
the `mesh.keys.v1` key - and the decode boundary is where it becomes a number,
so a gateway's relaying and its own telemetry share one identity. They did not
before: the same device appeared as `!19ba4462` in `gateway_id` and
`431637602` in `node_id`, and nothing could join the two. Points written
before this change keep the old spelling.

## Registered-gateways-only gate

**This is a breaking behavioral change.** Registration works at the mesh level, not
the device level: a Meshtastic mesh network is just a set of devices that share one
channel PSK, so the PSK only needs to be entered once, against a **Mesh** — not once
per device. What still needs individually registering is a **gateway Device**: the
specific node(s) that actually relay MQTT traffic for that mesh. A mesh can have any
number of gateways simultaneously - the uniqueness constraint is per `device_id`
(while allowed), never per mesh. Everything else on the mesh gets decoded
automatically, purely by virtue of arriving through a registered gateway - subject to
the node-level `is_allowed` gate described below.

`decode_job.py`'s `DecodeWithBroadcastKey.process_element` checks
`GATEWAY_KEY_STATE.contains(gateway_id)` — keyed off `ServiceEnvelope.gateway_id`, the
relaying node, **not** the originating device — *before* calling
`mesh_things.codec.decode_message` at all. If a packet arrived via an unregistered gateway,
it's dropped outright — encrypted **or already-plaintext** — logged only at debug
level. There is no global fallback key (`MESH_CH0_ENCRYPTION_KEY` has been removed).

Registration is three steps via the registry role:

1. An `Owner` must exist (`POST /owners`, which returns a one-time API key).
2. That owner registers a `Mesh` (`POST /meshes` with `channel_id` + `psk_b64`).
3. That owner registers a gateway `Device` for it (`POST /devices` with
   `is_gateway: true`, the relaying node's `device_id`, and the mesh's `mesh_id`) —
   this is the step that actually starts decoding, since it's what gets published to
   `mesh.keys.v1`. A mesh with `discover_gateways` on skips it: see
   [gateway discovery](#gateway-discovery).

Only the mesh's owner can do any of this — see
[api-reference.md#authentication-for-mesh-and-device-mutations](api-reference.md#authentication-for-mesh-and-device-mutations).
A `Device` has no owner field of its own; `Mesh.owner` is the one ownership
relationship in the schema, and it's what gates adding/editing/deleting the mesh and
every device on it (including flipping `is_allowed` — see below).
A mesh's traffic only starts appearing in InfluxDB/S3 once it has at least one
registered gateway — any mesh that was visible before this gate landed goes silent,
with no error anywhere, until someone registers a gateway for it. See
[api-reference.md](api-reference.md#owners) for the exact calls and
[debugging.md#a-mesh-goes-dark-after-deploying-the-ownership-gate-with-no-error-anywhere](debugging.md#a-mesh-goes-dark-after-deploying-the-ownership-gate-with-no-error-anywhere)
if you're troubleshooting a mesh that stopped showing up.

Rotating a mesh's `psk_b64` (`PUT /meshes/{id}`) automatically republishes every
allowed gateway device already registered on that mesh with the new key, since the
broadcast state stores the PSK denormalized per `gateway_id` rather than looking it up
from the mesh at decode time.

A gateway can be moved to a different mesh without losing its registration history.
An allowed gateway's `device_id` is unique among *allowed* gateways
(`uq_devices_gateway_device_id_allowed`), because `mesh.keys.v1` is keyed by the
gateway number alone. Plain nodes are only unique per mesh
(`uq_devices_mesh_device_id_allowed`), so two sources may each report the same node
number. `PUT /devices/{id}` with
`{"is_allowed": false}` publishes the same Kafka delete event `DELETE /devices/{id}`
would — dropping it from `GATEWAY_KEY_STATE` and stopping decode for that `gateway_id`
immediately — but keeps the Postgres row for audit history instead of removing it.
`POST /devices` with the same `device_id` on a different mesh then succeeds and starts
decoding on the new mesh right away. Re-allowing the old row later
(`PUT .../is_allowed: true`) republishes an upsert and fails with `409` if another
allowed gateway has that `device_id` — reject it first, there's no automatic
takeover. None of this requires any change to `decode_job.py`: rejecting/re-allowing
are just the existing delete/upsert events applied to a row instead of to a
`DELETE`/`POST`.

## Gateway discovery

A mesh with `discover_gateways: true` registers its gateways itself. The mesh already
pins down the source (or the own topic), the channel and the PSK, so a gateway whose
packets decode with them is registered as an ordinary gateway `Device`, with
`discovered_at` set, the moment one of its packets proves it. There is no manual
acceptance step and no candidate state.

```
mqtt_kafka_bridge --(unregistered gateways, paced)--> mesh.gateway_candidates.v1
    --> registry_gateway_discovery: same source + channel, trial decrypt
    --> Device(is_gateway, discovered_at) --> mesh.keys.v1 (as POST /devices)
```

**Bridge.** The decode gate drops unregistered gateways before decrypting, and only
the bridge knows the source, so the bridge samples them (`bridge/discovery.py`). For
every accepted packet on an `.../2/e/<channel>/!<gateway>` topic whose gateway is not
in its gateway sources, it may publish `{source_id, channel_id, gateway_id, seen_at,
sample_b64}`. Pacing is bridge-wide, so a busy public broker can't flood the registry
while a quiet private mesh is still found at once:

- The first `MQTT_BRIDGE__DISCOVERY__IMMEDIATE_GATEWAYS` (default 50) new gateways in
  any rolling `MQTT_BRIDGE__DISCOVERY__DELAY_SECONDS` (default 60) window are sent
  with their first packet.
- Once that budget is spent, a new gateway's first packet after it has been known
  for a full window is sent.
- Each gateway is retried at most once per window, for a packet that didn't decode
  or a mesh that switched discovery on later. A gateway quiet for four windows is
  forgotten.

The state is per bridge member and resets on restart. `/health` reports
`discovery_candidates_sent` and `discovery_gateways_tracked`.

**Registry.** `registry/gateways.py` handles each sample:

1. Discard it unless a mesh with discovery on has the same source and channel.
2. Try every mesh on that source and channel, with discovery on or not. A match is
   a full decode (`codec.decodes_with`): an encrypted packet must decrypt to a known
   portnum whose payload parses, since a wrong key yields random bytes that sometimes
   parse as `Data`. A plain packet only matches a mesh without encryption.
3. Skip unless exactly one mesh matches and it has discovery on. Two owners sharing a
   channel and PSK would otherwise race for the gateway, and the loser would get
   `409` on registering it by hand.
4. Skip if an allowed gateway with that node number exists anywhere (it can feed
   only one mesh), or if the matching mesh holds a rejected row for it. Rejecting a
   gateway therefore keeps it out; deleting it lets discovery find it again.
5. Otherwise create the gateway, or promote an allowed node row already on the mesh,
   and publish it through `save_gateway`, the same path `POST /devices` uses. A
   failed publish rolls the row back. A paused mesh gets the row but stays
   deregistered, as for any gateway.

**Well-known keys.** The default `AQ==`, any other one-byte index key and a blank
PSK prove nothing, since every gateway on that channel decrypts them. Only an
operator may switch discovery on for such a mesh, or move a mesh with discovery on to
such a key (`403` otherwise). Apart from that they are treated like any other key.

**Costs.** Packets a gateway relays before it is registered are lost, up to one
window once the immediate budget is spent. Switching discovery off keeps the
gateways already found.

## MQTT sources

A **source** is a remote MQTT broker and a topic filter whose traffic this instance
ingests as if it arrived on its own broker. It is realised on the instance's own EMQX,
the broker `mqtt_kafka_bridge` already reads, by three resources sharing the name
`{namespace}-src-{source_id}`:

| EMQX resource | Does |
|---|---|
| MQTT connector | Holds one connection (`pool_size: 1`) to the remote broker |
| MQTT source | Subscribes to the remote topic filter |
| Rule, `republish` action | Republishes each message, payload untouched, on `{namespace}/{source_id}/{remote topic}` |

The remote topic is kept as a suffix, so the last segment is still the gateway id the
bridge uses as the Kafka key. The bridge subscribes to `{namespace}/#` alongside
`MQTT_BRIDGE__TOPIC`, on the same client, and refuses to start if its own filter would
also match the source topics. From Kafka onwards nothing knows about sources: decode,
sightings, discovery, the writers and alarms are unchanged.

`registry_api` drives EMQX through its REST API (`registry/emqx_client.py`), with the
same failure policies as the Kafka publishes: creating or updating a source rolls the
row back if EMQX refuses, and deleting one removes the bridge first and keeps the row
if that fails. A source with meshes attached cannot be deleted (`409`). `manage.py
sync_sources` reconciles EMQX with Postgres after an EMQX redeploy or a lost write, and
only ever touches resources in its own namespace. `POST /sources/<id>/restart`, `manage.py
restart_source` and `scripts/restart-source.sh` re-apply one source's bridge and turn the
EMQX source off and on, which makes it subscribe again; EMQX 5.8 has no restart operation
for sources.

`MQTT_CONNECTORS__NAMESPACE` (default `mt-sources`) separates stacks sharing one EMQX. It
prefixes everything registry creates there: source bridges and their republished topics,
and [sinks'](#mqtt-sinks) users and topics. The dev overlay sets `mt-sources-dev` on every
registry service, every bridge member and `sink_dispatcher` (the lifecycle pass removes
and recreates bridges and sinks when terms lapse or are renewed), so a local stack neither
reads production's source traffic nor edits its bridges and sinks. `tests/test_deploy_ports.py` fails if a service
is left out. The value is part
of every name on the broker, so changing it on a running instance orphans what exists.

**Internal hosts.** `registry/broker_hosts.py` refuses sources that would make EMQX
connect into this deployment (SSRF): every loopback spelling, including the legacy IPv4
forms `inet_aton` accepts, `0.0.0.0`, link-local, multicast and reserved ranges, bare
hostnames (Docker service names), and names that resolve to any of them at save time.
Private ranges are refused unless `REGISTRY__SOURCES_ALLOW_PRIVATE_BROKERS` is set.

**No loops.** A source pointing back at this instance's broker would republish its own
traffic into itself. Its host is refused when it matches, by name or by any resolved
address, the hosts of the EMQX API, the bridge's broker or the sinks' broker; and,
wherever the broker is, its topic filter is refused when it could match a stack's
republished or sinked topics (`common/sources.py`, `reaches_reserved_topics`).

**Attaching a mesh.** `Mesh.source` is a nullable FK; null means the instance's own
topic. Only an operator creates sources, because each one is a persistent connection
from shared infrastructure. Sources are scoped like private data: an operator sees,
edits and attaches meshes only to the sources they created (`Owner.visible_sources`), a
superuser to all, and anyone else to none. `source_id` on a mesh is shown only to the
mesh's owner. The
workflow is otherwise unchanged: create the mesh with `source_id`, then register its
gateways. Changing a mesh's source republishes every allowed gateway, rolled back on
failure like a PSK change.

**The source gate.** Each gateway upsert on `mesh.keys.v1` carries its mesh's
`source_id`. The bridge replays that topic to its end before subscribing to MQTT, then
follows it, and drops a message from a registered gateway that arrives through anything
other than its mesh's source. A gateway uplinking both directly and to a bridged public
broker is therefore ingested once. Unregistered gateways pass, and decode drops them as
before. The gate lives in the bridge rather than in decode because PyFlink's Kafka source
here reads values only, so a record's topic or headers never reach `decode_job.py`. Drops
are counted in the bridge's `/health` body as `source_mismatch_drops`.

Operational requirements: `MQTT_BRIDGE__BROKER` must be the EMQX that
`REGISTRY__EMQX_API_URL` controls, and the bridge's MQTT user needs permission to
subscribe to `{namespace}/#`. See [deploy.md](deploy.md#mqtt-sources).

## Device registration and the is_allowed gate

A `Device` is always exactly one role, and always belongs to a `Mesh`. There's a
single `is_gateway` boolean, not a separate `is_node` field - a Device that isn't a
gateway is a node, by definition, so there's no invalid third state to guard against
with a constraint. Unlike a gateway (always explicitly `POST`ed by the mesh owner, see
above), a **node** is normally never `POST`ed into existence by a device operator at
all: it's auto-discovered the first time one of its packets decrypts successfully
against its mesh's PSK, which is the only thing that actually proves it shares that
mesh (a gateway can relay other meshes' encrypted traffic too — the `gateway_id` gate
above only checks *who's relaying*, not *whose mesh the payload belongs to*). A node
can also be pre-registered directly by the mesh owner via `POST /devices` with
`is_gateway: false`, e.g. to set `admin_keys_b64` in advance of ever seeing the
device.

**`is_allowed` is default-open, not a pending-approval flag.** A gateway is allowed
the instant it's registered; a node is allowed the instant it's first seen (or
pre-registered). The mesh owner's lever is *rejection* — flipping `is_allowed` to
`false` via `PUT /devices/{id}` — not approval. Rejecting a gateway cascades: nothing
from any node relayed through it gets through either, regardless of that node's own
flag (see the gate above). Rejecting a node stops just that node's data.

Unlike the gateway gate, a rejected node's future packets are meant to be dropped
*before* decrypt is even attempted, not decrypted and then discarded — decode_job.py
enforces this with a second broadcast state, `NODE_REJECTED_STATE`, fed by the
compacted `mesh.node_rejections.v1` topic (`KeyEventPublisher.publish_node_reject`/
`publish_node_unreject` in `registry/kafka_publisher.py`, keyed by `"mesh_id:device_id"`
— absence means allowed, matching the default-open model). This works because the
originating node id (`ServiceEnvelope.packet.from`) sits on the unencrypted part of a
`MeshPacket` — it's literally read to build the AES nonce in `mesh_things.codec`'s
`decrypt_packet` — so `process_element` can check it against `NODE_REJECTED_STATE`
before calling `mesh_things.codec.decode_message` at all, the same "check before decode"
shape as the gateway gate. Both `mesh.keys.v1` and `mesh.node_rejections.v1` feed one
`.union()`ed broadcast connection, tagged by a `"kind"` field per event
(`"gateway_key"` vs `"node_rejection"`) so `process_broadcast_element` can route each
one to the right state map.

Deleting a device (`DELETE /devices/{id}`) that's currently a rejected node also
publishes the unreject event first, to clear its `NODE_REJECTED_STATE` entry —
otherwise a stale rejection would block a future registration of the same
`device_id` elsewhere forever, since the broadcast state has no way to know the row
that rejected it is gone.

## Device catalog

Every registered gateway and every discovered/registered node is just a `Device` row
— `GET /meshes/{id}/devices` returns them directly, no synthesis needed. `decode_job.py`
publishes a `{mesh_id, device_id}` record to `mesh.devices.v1` on every successful
decode (using the `mesh_id` carried in `GATEWAY_KEY_STATE`'s broadcast-state value
alongside the PSK, not looked up separately) — this is what auto-creates a node
`Device` the first time it's seen, or bumps `last_seen` if a row already exists (a
pre-registered node, or a gateway's own telemetry — `Device.objects.get_or_create(mesh,
device_id, ...)` finds the existing row either way, never touching its role or
`is_allowed`). Rather than running as a background task inside the web process (Django
has no lifespan-style hook for that), the consumer runs as its own
`registry_device_consumer` container, executing
`python manage.py consume_device_sightings`
(`registry/management/commands/consume_device_sightings.py`) — a synchronous
`KafkaConsumer` polling loop.

`mesh.devices.v1` is **not compacted**, unlike `mesh.keys.v1`/`mesh.node_rejections.v1`
- Flink's `KafkaSink` here doesn't set a record key (PyFlink's
`KeyedBroadcastProcessFunction` has no working `ctx.output()` for real side outputs in
this PyFlink version; the main decoded stream and the sighting stream are both
produced from the same `process_element` call, tagged by a `"kind"` field, and split
back apart with plain `filter()`/`map()` before their respective sinks - see
`flink/decode_job.py`), and Kafka rejects unkeyed writes to a compacted topic. Dedup
happens in Postgres on upsert instead.

## Auto-filled location and NodeInfo fields

Beyond the bare `{mesh_id, device_id}` sighting, `decode_job.py` opportunistically
enriches the `mesh.devices.v1` event with two independent field groups, each sourced
from a different packet kind (`payload_kind`, see [Decoded message
shape](#decoded-message-shape)):

| Group | Source packet | `Device` fields | Override flag |
|---|---|---|---|
| Location | `position` (`Position.latitude_i`/`longitude_i`, ÷ 1e7 - same conversion `writer/point_builders.py` already does) | `latitude`, `longitude` | `location_overridden` |
| NodeInfo | `nodeinfo` (`User.long_name`/`short_name`/`hw_model`/`role`) | `name`, `short_name`, `hardware_type`, `role` | `nodeinfo_overridden` |

Each group is **default-open, sticky-override** - the same shape as `is_allowed`, but
per field-group instead of per device: `consume_device_sightings.py` applies a
group's values from every sighting **unless** the mesh owner has already pinned it via
`PUT`/`POST /devices` (`*_overridden = True`). A `PUT` that supplies any non-null value
in a group pins the whole group - e.g. setting just `name` also freezes
`hardware_type`/`short_name`/`role` against future telemetry, since they all arrive
together in one NodeInfo packet anyway. To release a group back to auto-fill, `PUT`
every field in that group as explicit `null` in the same request - a partial `null`
(e.g. just `{"name": null}`) is treated as an ordinary field update, not a group reset.
`POST /devices` behaves the same way: supplying a group at registration time pins it
immediately, so the device's first telemetry sighting doesn't clobber it.

`latitude`/`longitude` are always read/written as a pair - the API rejects one without
the other with `400`. There's no such pairing constraint across the NodeInfo group;
each of `name`/`short_name`/`hardware_type`/`role` is independently settable, only the
*override flag* is shared.

Deliberately excluded from `User`: `macaddr`/`public_key` (binary/security-sensitive,
no clear use here), `is_licensed`/`is_unmessagable` (niche ham-radio flags), and `id`
(redundant with `Device.device_id`).

## Device telemetry-variant / Measurement catalog

Beyond registration, a `Device` now has a real catalog of what it actually reports -
`DeviceTelemetryVariant` and `Measurement` (per-device instances, auto-discovered) plus
`TelemetryVariant` and `MeasurementType` (global, shared catalogs the instances point
to). `DeviceTelemetryVariant` isn't a physical sensor model - it's the fact that a given
`Device` has been seen reporting a given `TelemetryVariant`, and since when; a real
per-chip hardware catalog, if ever added, is a separate concern (see below). A third
global table, `TelemetryVariantMeasurement`, declares which `MeasurementType`s a given
`TelemetryVariant` carries, plus which detectors default on for that pairing - see
[data quality checks](#data-quality-checks). The range detector's bounds are not part
of this catalog at all: they're set per device, directly on `Measurement`, since one
device's plausible range for a channel can differ from another's:

```
Device --has many--> DeviceTelemetryVariant --FK--> TelemetryVariant   (one row per Telemetry protobuf "variant" - see below;
                        |                |               name/model/datasheet_url/default_reading_interval_seconds)
                        |                `--has many--> TelemetryVariantMeasurement --FK--> MeasurementType
                        |                                 (default_enabled_detectors)
                        `--has many--> Measurement --FK--> MeasurementType  (unit/quantity_kind/vocabulary_uri)
                                         (enabled_detectors, valid_min/valid_max)
```

**`TelemetryVariant` is keyed by wire-format message type, not verified physical
hardware** - despite the name a `SensorType` model had in an earlier pass, it was
never really "which chip produced this," since one Telemetry protobuf variant
(e.g. `environment_metrics`) can be produced by several different physical chips
(a BME280 or a BMP180 both report into it) and protobuf alone can't tell you
which. `name`/`model`/`datasheet_url` are an optional curated "commonly this
chip" hint on the row, not verified identity. A real per-chip hardware catalog,
if ever needed, would be a separate model keyed some other way (e.g. curated
per-`Device`, since only a human who's opened the enclosure actually knows) -
not this one.

**Scope: `telemetry:<variant>` payload kinds only, for now.** `position`/`nodeinfo`
are deliberately skipped - `Device.latitude`/`longitude` and `Device.name`/
`short_name`/`hardware_type`/`role` (see above) already cover their current-value
case. This isn't a permanent wall: a future "historic position" concept (a mobile
node's position over time, as its own timeseries rather than a single current
lat/lon) could add a `"position"` case to `decode_job.py`'s `_discovered_fields`
later without any model/migration rework.

**Discovery rides the same cadence as the sighting event** - once per successful
decode, not once per field - no new Flink keyed state, no re-partitioning. Right
after building the `sighting` event, `process_element` also builds a `discovery`
event whenever the decoded payload has a `telemetry:<variant>` `payload_kind` with
at least one numeric leaf field (matching exactly what
`writer/point_builders.py`'s `build_telemetry_points` ends up persisting to
InfluxDB - the catalog never describes a field that isn't actually queryable):

```json
{"mesh_id": "<mesh_id>", "device_id": 111222333, "payload_kind": "telemetry:environment_metrics", "fields": ["temperature", "relative_humidity"], "op": "upsert"}
```

Published to `mesh.sensor_discovery.v1` (not compacted, same reasoning as
`mesh.devices.v1`), carrying **field names only, never values** - registry never
ingests raw telemetry payloads. `registry/management/commands/
consume_sensor_discovery.py` (running as its own `registry_sensor_discovery_
consumer` container) does the actual upsert: `get_or_create`s a `TelemetryVariant`
for the `payload_kind`, a `DeviceTelemetryVariant` linking the `Device` to it, and a `MeasurementType` +
`Measurement` per field. Dedup happens for free via `get_or_create`'s unique
constraints - the event isn't deduplicated in Flink (packets from one device can be
relayed by different gateways over time, and gateway-keyed Flink state can't
cleanly dedupe per-device without a real re-keying operator), so re-discovery of an
already-known field is just a cheap indexed lookup plus a `last_seen` bump.

**`MeasurementType` carries a curated `native_unit`/`quantity_kind`/`description`**
for every field known from the vendored `telemetry.proto` (101 rows across all 8
`telemetry:*` variants) - e.g. `telemetry:environment_metrics:temperature` →
`native_unit: "degC"`, `quantity_kind: "physical_property"`. That table lives in
`registry/measurement_catalog_seed.py` and is irreducibly manual: the compiled
protobuf carries no `source_code_info` and no field options, so neither the unit
nor the proto comment can be read back at runtime. `quantity_kind` is derived from
the unit (`mesh_things.units`) rather than stored twice. **`vocabulary_uri` is deliberately left `null`
on every seeded row** - no QUDT/EIONET concept URI is fabricated; a wrong
semantic-web link is worse than an absent one. Verified hardware identity (which
physical chip actually produced a reading) genuinely can't be inferred from the
wire, so `TelemetryVariant.name`/`model`/`datasheet_url` still start `null` -
either from `get_or_create` at discovery time, or from `manage.py
seed_measurement_catalog` (below), and are curated afterward via `PUT
/telemetry-variants/{id}` as an optional best-guess hint, not verified fact.

**The catalog is seeded by `manage.py seed_measurement_catalog`**
(`registry/management/commands/seed_measurement_catalog.py`), which the registry
container runs from its `CMD` after `migrate`, alongside `provision_read_role`. It
runs on every start rather than by hand because the `TelemetryVariantMeasurement`
links it creates are what make `mesh.quality_config.v1`'s catalog-default entries
publishable at all - without them the stream-tier flat_value detector has no
default to broadcast. (Range has no catalog entry to seed - see above.) It introspects
`meshtastic.protobuf.telemetry_pb2.Telemetry`'s `variant` oneof directly (one
`TelemetryVariant` per variant, e.g. `telemetry:environment_metrics`), `get_or_create`s
a `MeasurementType` for every scalar numeric sub-field, and links each pairing with a
`TelemetryVariantMeasurement` row. String and message fields are skipped
(`host_metrics.user_string`), as are repeated numerics
(`environment_metrics.one_wire_temperature`): a repeated field arrives as a list, so
`common/decode.py` drops it from discovery and `writer/point_builders.py` cannot write
it - a catalog row for it would describe a channel that can never carry a value.
Idempotent throughout (`get_or_create`), so running
it after a `meshtastic` package upgrade adds new variants/fields without
duplicating rows or clobbering already-curated `valid_min`/`valid_max`/
`default_reading_interval_seconds`. It also **fills in blanks**: a row that sensor
discovery created from live traffic with no unit, or a `TelemetryVariant` left
nameless the same way, gets its curated values on the next start. A value that is
already set is never overwritten, so superuser curation survives. `TelemetryVariant.default_reading_interval_seconds` is a fact
about the *telemetry type* (Meshtastic firmware configures interval per
telemetry module - every field in one packet shares it), not derivable from the
`Telemetry` message itself (interval lives in firmware `ModuleConfig`, a
different message family), so seeding always leaves it `null` - curate it via
`PUT /telemetry-variants/{id}`.

**Full CRUD on both catalogs, superuser-only for writes** - `GET /measurements`
and `GET /telemetry-variants` are open to any verified owner (shared reference data
everyone benefits from reading), but `POST`/`PUT`/`DELETE` require
`request.user.is_superuser` (`registry/permissions.py`'s `IsSuperuser`, checked
inline in the view the same way `_require_mesh_ownership` already is elsewhere -
not baked into `permission_classes`, so `GET` stays reachable on the same view for
everyone). `payload_kind` (and `field_name` for `MeasurementType`) is the row's
identity and immutable after creation. A `DeviceTelemetryVariant` instance has **no
PUT route of its own at all** - it's purely auto-discovered. `Measurement` does have
one, mesh-owner-scoped rather than superuser-only: `PUT /devices/{id}/measurements/{id}`
sets `enabled_detectors` and the range detector's `valid_min`/`valid_max` - both are
per-device, not shared catalog properties. `TelemetryVariantMeasurement` follows the
read-open/write-superuser split, but has no `POST`/`DELETE` of its own - `GET
/telemetry-variants/{id}/measurements` lists a `TelemetryVariant`'s links, and `PUT
/telemetry-variants/{id}/measurements/{link_id}` curates `default_enabled_detectors`;
the pairing's existence is owned entirely by the seed command.

A device's own discovered catalog is **two read-only routes**, both mesh-owner-scoped
like every other device route: `GET /devices/{id}/telemetry-variants` (which telemetry
types it reports) and `GET /devices/{id}/measurements` (a flat list of the channels it
produces, each carrying its `"<measurement>.<field>"` `channel` name). They were one
endpoint, `/devices/{id}/sensors`, which nested the second inside the first - that
conflated two questions and made every caller pay for both.

Every device record (`GET /devices`, `GET /meshes/{id}/devices`, and the single-device
routes) also carries `telemetry_variant_ids`: the ids of the variants it has reported,
in first-seen order, taken from the same `DeviceTelemetryVariant` links. Only ids are
sent, since names come from `GET /telemetry-variants`. The list views prefetch the
links, so this costs one extra query per list rather than one per device; it exists so
a dashboard can filter loaded rows by variant without a request per device.

Both list routes also accept `telemetry_variant=<operator>:<id>|<id>` for API callers
who want the filtering done server-side: `has_any_of` (reported at least one),
`has_all_of` (reported every one) and `has_none_of` (reported none). Bare ids mean
`has_any_of`. An unknown operator or a value that is not a UUID is a 400.

**Deferred, not shipped in this pass**: unit conversion at request time (storing
`degC`, requesting `degF`) and pollutant molecular-weight-based conversions -
explicitly flagged as "nice to have, not compulsory" / "more complex, not trivial."
The model already stores `native_unit` + `quantity_kind`, so this is addable later
without a schema change. Also deferred: a Postgres-side "latest value" cache -
`readings`'s `/latest` (below) answers that live instead.

## Latest readings across every sensor (readings)

`GET /devices/{device_uuid}/latest` (readings, `:8091`, or the equivalent
`GET /meshes/{mesh_id}/nodes/{node_id}/latest`) takes an optional `?payload_kind=`:

- **Provided**: the latest point of every channel in that one family, in the same
  `payload_kind`/`series` shape the timeseries route returns.
- **Omitted**: one combined Flux query across every channel the device has ever
  reported (`InfluxQueryClient.latest_all`, grouping by
  `["_measurement", "_field"]` before `last()` - finer-grained than
  `list_devices`'s last-seen query, so unlike that one this doesn't need the
  `_value`-overwrite trick to dodge Flux's schema-collision error on `last()`
  across heterogeneous value types). Each reading is decorated with `unit`/
  `quantity_kind`/`vocabulary_uri` by cross-calling registry's `GET
  /measurements` (`readings/measurement_catalog.py`). That catalog is keyed by
  **channel** (`"<measurement>.<field>"`, via `mesh_things.channels`) rather than by
  registry's `(payload_kind, field_name)`: a reading read back out of InfluxDB
  knows its measurement, not the payload_kind that produced it, and `derived` and
  `quality` payload_kinds are flat, so no prefix can be reconstructed from the
  measurement alone. A channel with no catalog match still comes back with
  `unit: null` rather than being dropped, the reading itself is still real.

  Each reading also carries `origin` (`measured`/`device`/`computed`), derived
  from the measurement rather than the catalog row, so a consumer doesn't plot
  `completeness_ratio` next to `temperature` by accident. The per-point
  bookkeeping fields (`influx_client.METADATA_FIELDS`: `packet_id`,
  `timestamp_quality`) are excluded from this query - they are writer
  provenance, not readings, and have no catalog row to decorate them with. The
  per-family `latest` and timeseries reads leave them out too; a timeseries read
  that names one of them as its `channel` still returns it.

This still lives in readings, not registry - registry deliberately has zero InfluxDB
access (see [roles](#roles-registry-and-readings) below for why the
two services' datastores are fully independent), so values can only honestly come
from where InfluxDB access already exists. The catalog cross-call is cached
~5 minutes (`measurement_catalog.CACHE_TTL_SECONDS`) - much longer than the 60s
owner-auth cache in `authentication.py`, since this is shared reference data that
changes rarely (superuser curation, not a per-request value), and the cache key is
global, not per-token: any authenticated caller's forwarded bearer token can prime
it, every other caller reuses the same cached copy. A catalog fetch failure is
non-fatal - readings still come back, just undecorated (`unit: null`), since the
telemetry values themselves are real and useful even if registry is briefly
unreachable.

## Mesh traffic stats (readings)

`GET /readings/meshes/{mesh_id}/stats?range=` is [plan 25](../plans/done/25-mesh-network-metrics.md)'s
Malla-style view of a mesh. Malla stores every packet and aggregates on read; here
packets are counted as they stream through Kafka, and the endpoint reads only
pre-aggregated rows.

```
decode (flink-job / decode_consumer) --> mesh.traffic.v1 --> mesh_stats_writer --> InfluxDB "mesh_stats"
                                                                                       |
                                       InfluxDB readings bucket (device_metrics) --> readings /stats
```

**Traffic events.** `decode_packet` emits a `traffic` event for every packet from a
registered gateway whose mesh is known, before anything is dropped: text, routing,
packets that could not be decrypted (`portnum` null) and packets from rejected nodes
(`"rejected": true`). It carries the routing and signal fields of the decoded shape,
`size` (payload bytes) and `received_at`, the bridge's Kafka timestamp of the raw
packet. Counting by `received_at` rather than decode time keeps a decoder catching up
from bunching a backlog into one minute. Packets from unregistered gateways belong to
no mesh and are not counted.

**`mesh_stats_writer`** is a plain Kafka consumer, not a Flink job, to keep the
taskmanager's memory where it is ([#7](../plans/07-pyflink-memory.md)). It counts in
memory (`common/mesh_stats.py`) and writes every minute:

| Measurement | Grain | Tags | Fields |
|---|---|---|---|
| `mesh_traffic` | minute | `mesh_id`, `portnum` (`unknown` when undecoded) | `packets`, `receptions`, `bytes`, `rejected_packets`, `rejected_receptions` |
| `mesh_node_traffic` | hour | `mesh_id`, `node_id` | `packets`, `receptions`; rejected nodes left out |
| `mesh_gateway_traffic` | hour | `mesh_id`, `gateway_id` | `receptions`, `direct_receptions`, `signal_receptions`, `rx_snr_sum`, `rx_rssi_sum` |
| `mesh_hops` | hour | `mesh_id`, `hops` (`unknown` without `hop_start`) | `packets` |
| `mesh_signal` | hour | `mesh_id`, `metric` (`snr`/`rssi`), `bucket` (lower bound, 2.5 dB / 10 dBm) | `receptions` |
| `mesh_node_ports` | hour | `mesh_id`, `node_id`, `portnum` | `packets`; rejected nodes left out |
| `mesh_gateway_pairs` | hour | `mesh_id`, `gateway_a`, `gateway_b` (a < b) | `common_packets`, `signal_pairs`, `snr_diff_sum`, `rssi_diff_sum` (a minus b) |
| `mesh_relays` | hour | `mesh_id`, `gateway_id`, `relay` (last byte of the relaying node) | `receptions` of relayed packets |

- A packet heard by several gateways arrives once per gateway. The first reception
  within 10 minutes of the same `(mesh, node, packet_id)` counts the packet; every one
  counts a reception. Each gateway that hears a packet another already heard adds one
  to that pair's `common_packets`, which is what gateway compare reads.
- The firmware reports only the last byte of a relay's node number, so relays are
  counted by that byte; the endpoint offers the registered nodes it could be, and the
  console marks the ones the gateway also hears directly.
- Each row is stamped at the start of its bucket and rewritten whole on every flush,
  so a bucket still filling is simply overwritten later. Sums, not means, are stored,
  so any range can be combined exactly.
- Offsets are committed only once every bucket holding a record has closed (event
  time past its end plus a minute's grace). A restart therefore replays at most the
  open hour and rebuilds it in full, instead of overwriting it with a partial count.
  A reception arriving after its bucket closed joins the oldest open one.
- Tag cardinality is bounded by nodes per mesh. A 30-day view reads ~720 hourly rows
  per node regardless of traffic.

The `mesh_stats` bucket keeps 30 days (`INFLUX__MESH_STATS_RETENTION_DAYS`), the
longest range the endpoint serves; `influx_init` creates it.

**The endpoint** sums those rows over a fixed range (`1h`, `24h`, `7d`, `30d`), with
per-minute traffic bucketed to `1m`, `15m`, `1h` or `6h`. Hourly figures start at
`hourly_start`, the whole hour on or before the start of the range. Congestion is the
`channel_utilization` and `air_util_tx` nodes report in `device_metrics`, read from
the readings bucket. The body is cached in the shared Redis for 60 s per
`(mesh, range)`.

`readings_ro` holds column grants on `devices` (`id`, `device_id`, `mesh_id`,
`is_allowed`) and nothing that names a device, so the response gives each node's
`device_uuid` and the console joins names from the registry's device list. Same
visibility rule as `/latest`: a public mesh is readable anonymously.

Statistics start when `mesh_stats_writer` first runs; nothing is backfilled.

## Mesh topology (registry)

`GET /meshes/{mesh_id}/links` and `GET /meshes/{mesh_id}/traceroutes` answer who hears
whom. InfluxDB cannot hold the lists a traceroute is made of, and the volume is small,
so both live in Postgres, written by `registry_topology_consumer`
(`manage.py consume_topology`, `registry/topology.py`):

```
mesh.telemetry.decoded.v1 (portnum 70, 71) --\
                                             +--> registry_topology_consumer --> traceroutes, rf_links
mesh_stats_writer --> mesh.links.v1 ---------/
```

- **`traceroutes`**: one row per traceroute packet, unique on `(mesh, from_node,
  packet_id)`. Gateways hear a traceroute at different points of its journey, each
  copy with the hops taken so far, so the longest route seen is kept and every gateway
  is appended to `gateway_ids`. SNRs are stored in dB (the firmware sends quarter-dB
  steps, with -128 for unmeasured).
- **`rf_links`**: one row per `(mesh, from_node, to_node, source)`, directional because
  SNR is measured by the receiver. `samples` and `snr_sum` add up, `last_snr` follows the
  newest sample, `first_seen`/`last_seen` widen. Sources:
  - `traceroute`: every hop with a measured SNR, added once per hop even when several
    gateways hear the same traceroute (only hops the stored copy lacked are added).
    Placeholder hops (`0xFFFFFFFF`) are skipped.
  - `neighborinfo`: each neighbor a node reports, as a link into the reporting node.
  - `direct`: a reception with `hop_start == hop_limit`, heard over the air by a
    gateway that is not the sender, from a node that is not rejected.
    `mesh_stats_writer` sums them per hour and publishes each closed hour to
    `mesh.links.v1`, so a busy mesh costs one row update per pair per hour.
- Distances are computed on read from the positions registry already holds, so the
  links route is one query per mesh, where Malla parses up to 25,000 stored packets.
- `registry_data_lifecycle` deletes traceroutes and links not heard for 30 days.

The routes follow the mesh's visibility: anyone reads a public mesh's topology. A
rejected node's own packets are never decoded and its direct receptions are skipped,
so its only links are as a relay in someone else's traceroute; only the owner sees it
named there.

## Password fields (`psk_b64`, `admin_keys_b64`) and the superuser role

`Mesh.psk_b64` and `Device.admin_keys_b64` are treated as password fields: every
API response omits them **unless the caller owns the resource or is a superuser** -
`MeshSerializer`/`DeviceReadSerializer`'s `to_representation` in
`registry/serializers.py` pops the field whenever `context["viewer_id"]` doesn't
match `instance.owner_id` (mesh) / `instance.mesh.owner_id` (device) and
`context["viewer_is_superuser"]` is false. Every view that returns one of these
serializers passes both (or the relevant owner's, for `GET /owners/me`'s embedded
device list) so this is enforced centrally rather than per-route. Superusers see
them because the values are stored in plain retrievable form anyway (Postgres, and
in the case of `psk_b64`, the `mesh.keys.v1` Kafka message `decode_job.py`
consumes), so hiding them from someone with that access protected nothing. The
system genuinely needs them - `psk_b64` to decrypt packets, `admin_keys_b64` to
authenticate outbound `AdminMessage` traffic. "Password field" describes API
exposure, not at-rest encryption. The Django admin shows both read-only, since a
key changed there would not reach the pipeline. `admin_keys_b64` exists on every
`Device` regardless of role, though it's only ever meaningful for a node.

One practical consequence: `PUT /devices/{id}` still replaces `admin_keys_b64`
wholesale, and there's no dedicated "append" route - a caller that wants to add one
key to the existing set now reads the current list back via `GET /devices/{id}`
(as the device's owner) and `PUT`s the full list with the new key appended, instead
of reconstructing it from memory - see `mesh_things/examples/registry_add_admin_key.py`.

**Superuser**: an `Owner.is_superuser` flag that bypasses every ownership check in
`registry/views.py` - full read/write across every owner's meshes and devices, and
every list route returns all owners' rows instead of just the caller's. As above,
this includes `psk_b64`/`admin_keys_b64` on resources it doesn't own. It also allows removing any owner
outright: `DELETE /owners/{id}` (`OwnerDetailView.delete`) runs the same
gateway-deregistration-then-cascade logic as `DELETE /owners/me`
(`OwnerMeView.delete`) - both now call a shared `_delete_owner_cascading` helper -
just against an arbitrary owner instead of only the caller. Gated by
`_require_superuser`, the same helper `MeasurementTypeListCreateView`/
`MeasurementTypeDetailView` use for their superuser-only writes.

It also widens what the owner directory returns. `GET /owners` and `GET
/owners/{id}` are `AllowAny`, but DRF authenticates before it checks permissions, so
`_owner_serializer_for` in `registry/views.py` can choose between
`OwnerReadSerializer` and `OwnerPublicSerializer` on the same two routes.

The detail route passes the owner being requested, so the full record comes back for
a superuser **or for the owner themselves** - the same fields `GET /owners/me`
returns. The list route passes no owner and so only widens for a superuser: an
authenticated owner's own row stays on the public shape there deliberately, because a
list whose elements change shape per row cannot be typed by a generated client, and
`/owners/me` already answers that question.

`is_superuser` is therefore the only way to read `email`, `is_staff`, `is_active`,
`email_verified_at`, `email_verification_sent_at` and `last_login` for an owner other
than yourself, which is what makes unverified signups visible to an administrator.
There's deliberately no API route to grant it (`POST /owners` is public unauthenticated
signup, so self-escalation through the API has to be impossible); instead, it's granted
via Django's own `createsuperuser` management command, overridden in
`registry/management/commands/createsuperuser.py` to mint an API key (and set/promote
the owner) instead of only a Django admin password:

```bash
docker compose exec registry_api python manage.py createsuperuser \
  --email you@example.com --name "You"
```

See [api-reference.md#superuser](api-reference.md#superuser) for the full behavior.

**Operator**: `Owner.role`, either `member` (the default) or `operator`. An operator
may create [sources](#mqtt-sources) and read, update and delete the ones they created,
and nothing else beyond what
a member may do: no ownership bypass, no catalog writes. A superuser counts as an
operator. Only a superuser grants the role, through `PUT /owners/{id}`, the Django
admin, or by approving an operator request (`OperatorRequest`, `operator_requests`), so
it cannot be self-assigned through the public signup. An owner files a request with a
reason, every active superuser is emailed, and the decision is emailed back. One request
may be pending per owner (a partial unique constraint), and the table has no grant for
the readings role. `role` is part of the
full owner record only.

Source credentials follow a stricter rule than `psk_b64`: the remote broker `password`
is write-only and is returned to nobody, the operator who set it included. The
`sources` table has no grant for the readings role.

**Terms.** `registry/terms.py` holds three versioned documents in `en` and `es`, accepted
where data starts:

- **Account terms**, at signup (`POST /owners` requires `terms_version`). Terms of Use and
  Privacy Policy only: an account stores no mesh data. They never lapse.
- **Mesh terms**, per mesh on the default broker (`POST /meshes`, or moving a mesh off a
  source). Its owner is the controller of its traffic, Sensical the processor.
- **Source terms**, per source, accepted by the operator as the controller of the bridged
  traffic. A mesh on a source is covered by them and has no mesh terms.

`REGISTRY__TERMS_ENFORCED=false` (a self-hosted instance, with no second party to contract
with) switches all of it off at two points: `terms.terms_enforced()` makes the terms
routes answer `404` and `terms_version` optional, and `record_acceptance` writes nothing.

The mesh and source footnotes end with a retention sentence built from the settings.
`terms_acceptances` is append-only evidence for all three (`kind`): the acceptor's name
and email snapshotted, version, locale, a sha256 of the exact text served, and
`expires_at` (mesh and source terms, when a retention period is set). It outlives the
owner, mesh and source (all `SET_NULL`) and has no grant for the readings role.

## Data lifecycle

Readings are never deleted without asking their owner again first. With
`REGISTRY__DATA_RETENTION_DAYS` set, every acceptance lapses after that period unless
renewed, and a lapse stops ingestion before anything is deleted:

- **Mesh terms** pause the mesh (`Mesh.paused_at`): its gateways are deregistered from
  the decoder. `kafka_publisher.publish_gateway_state` keeps it that way, publishing a
  delete instead of an upsert for any gateway of a mesh whose `Mesh.ingest_paused` is true.
- **Source terms** pause the source (`Source.paused_at`): its EMQX bridge is removed, and
  `sync_sources` treats it as having no bridge.
- **Sink terms** pause the sink (`Sink.paused_at`): the dispatcher drops it and its
  consumer is disconnected and refused. A sink stores nothing, so nothing is scheduled.

`registry_data_lifecycle` runs `manage.py run_data_lifecycle`, a pass every
`REGISTRY__DATA_LIFECYCLE_INTERVAL_SECONDS`. Each step is idempotent:

1. **Renewal notices** to mesh owners and operators (sources and sinks) whose acceptance lapses within
   `REGISTRY__TERMS_RENEWAL_NOTICE_DAYS`, once per acceptance.
2. **Pausing** lapsed default-broker meshes, sources and sinks, scheduling a `terms_lapsed` `DataDeletion`
   for each affected mesh with `data_until` at the lapse. Renewing re-registers the
   gateways or re-applies the bridge and cancels those deletions.
3. **Purging.** A `DataDeletion` past `delete_after` deletes the mesh's InfluxDB points
   (predicate on the `mesh_id` tag, up to `data_until`) and its Parquet partitions under
   `mesh_id=<id>/` whose hour starts before `data_until`. Failures stay pending and are
   retried, with `attempts` and `last_error` recorded.

Deletions are also scheduled on mesh deletion (also through owner deletion) and on moving
a mesh off a source. They hold ids, not foreign keys, since the mesh is usually gone when
they run. A mesh or source with no acceptance at all never lapses. With terms not
enforced, steps 1 and 2 are skipped and a `resume_paused` step resumes anything a
lapse paused before the switch. Without `S3_WRITER__BUCKET` (the lite profile) only InfluxDB
is touched.

The same pass also looks after the broker, whatever the terms setting
(`registry/status_alerts.py`, and the sink session limits under [MQTT sinks](#mqtt-sinks)):

The first two email only operators who set `Owner.status_alerts_enabled` (off by default).

- **Source alerts.** A source not `connected` in EMQX's status for
  `REGISTRY__SOURCE_ALERT_HOURS` (default 2), including a bridge missing from the broker,
  emails its operator.
- **Sink alerts.** A sink with meshes or devices attached and no consumer connected for
  `REGISTRY__SINK_ALERT_HOURS` (default 24) emails its operator.
- **Busy sources.** Each pass reads the source rule's `matched` counter from EMQX and
  keeps it in the cache; the difference from the previous pass over the time between
  them is the source's average rate. Above `REGISTRY__SOURCE_RATE_ALERT_MSGS_PER_S`
  (default 20, 0 for off) it emails every superuser, and the operator only if they set
  `Owner.source_rate_alerts_enabled`. A lower count than last time means EMQX restarted,
  and that pass is skipped. EMQX has no threshold alarm of its own for this.
- **Silent sources.** The same counter, kept with the first pass that saw its current
  value. When it has not moved for `REGISTRY__SOURCE_SILENT_ALERT_HOURS` (default 6, 0
  for off) it emails every superuser, and the operator if they set
  `Owner.status_alerts_enabled`. Any change, including a lower count after an EMQX
  restart, starts the silence again. It catches a bridge that stays `connected` after
  the remote broker has stopped delivering, which EMQX's status never shows.

Each is one email per outage. The cache keeps when an outage was first seen and whether
it was reported, refreshed on every pass and expiring a week after the last one that saw
it; a recovery clears both, so the next outage alerts again. A failed email is retried
on the next pass. Paused sources and sinks are skipped.

## Sinks and the Parquet archive

A sink is somewhere a device's readings are sent besides InfluxDB: the Parquet archive,
described here, or an [MQTT sink](#mqtt-sinks) a third party subscribes to. Both are
routed by `mesh.sink_config.v1` and only on meshes owned by an operator.

**Opt-in per device.** `Device.archive_enabled`, off by default, set by the mesh's owner
through `PUT /devices/{uuid}`. It takes effect only while the mesh's owner is an operator
(a superuser counts) and the registration is allowed, and is refused on an instance
without an archive (`S3_WRITER__BUCKET` blank, the lite profile). `registry/sinks.py`
computes the effective list per node and publishes it to `mesh.sink_config.v1`, keyed
`<mesh_id>:<device_id>` like the postprocessing config, whenever an input changes: the
flag, `is_allowed`, the owner's role, or deletion of the device, its mesh or its owner.
Writes that turn archiving off publish before answering and roll back on failure, so an
opt-out is never silently lost.

**The instruction is recorded.** Under GDPR the owner is the controller and Sensical the
processor, which acts on documented instructions (Art. 28(3)(a)) and must be able to show
them (Art. 5(2)). Once the change is published, the device gets `archive_enabled_at` and
`archive_enabled_by` (cleared when switched off), and a `SinkInstruction` row is appended:
sink, on or off, mesh, node, who and when, with the person's name and email snapshotted
so it outlives the device and the account, like `terms_acceptances`. Read-only in the
admin, which also cannot edit the archive fields, and not granted to the readings role.
No separate acceptance is asked: the mesh and source terms authorise the archive for the
devices the owner chooses, and commit them to archiving only what they need. `manage.py publish_sink_config` rebuilds the topic from
Postgres, for a lost topic or a role changed in the Django admin.

**The writer.** `s3_writer` replays `mesh.sink_config.v1` to its end before its first
data poll (the bridge's pattern for `mesh.keys.v1`), then follows it. It keeps a record
only if its `<mesh_id>:<node_id>` is archived, so readings without a mesh are never
stored. Turning a device off keeps what was stored; it goes with the mesh's data under
the [data lifecycle](#data-lifecycle).

**Reading it.** Only the mesh's owner, while an operator, and superusers. readings serves
a manifest from `list_objects_v2`, temporary credentials from STS `AssumeRole` with an
inline session policy limited to the mesh's prefix (listing conditioned on it), and a
presigned redirect for one hour. The credential readings holds is a read-only identity
(`READINGS__ARCHIVE_*`, the `archive-reader` user on the bundled MinIO), never the
writer's. Readings receives an explicit list of environment variables rather than the
whole `.env`, so it holds none of registry's, the writer's or EMQX's secrets.

**Ranges are exports.** A range of the archive as one zip is a Parquet [export](#exports),
built in the background rather than streamed from a request, so readings runs plain
sync gunicorn workers.

**Backends.** The bucket is the bundled MinIO (`minio` profile, API proxied by Caddy on
`CADDY_S3_ADDRESS` with no basic auth, since every request is signed) or an external S3.
`READINGS__ARCHIVE_STS` is `minio`, `aws` (assuming `READINGS__ARCHIVE_ROLE_ARN`) or blank
for a provider without STS, which leaves the manifest and downloads. A presigned URL loses
Hive partitioning (`hive_partitioning=true` cannot find `mesh_id`), which is why scoped
credentials, not links, are the way to query the archive as a dataset.

## Exports

A mesh's readings over a range of days as one zip: CSV from InfluxDB, for every device,
or the archive's Parquet files. Requested on readings, built by `readings_export_worker`,
downloaded from the bucket through a presigned link. The routes are in
[api-reference.md#exports](api-reference.md#exports).

```
client --POST exports--> readings-api --job--> Redis <--BLMOVE-- readings-export-worker
client --GET export----> readings-api --reads the job--^                 |
                              |                          InfluxDB (CSV), archive (Parquet)
                              +-- presigned link <-- bucket exports/ <---+ multipart upload
```

**Why jobs.** A CSV export queries, pivots and compresses, which is real CPU for minutes
on a long range, and a stream cut halfway would waste all of it. The worker builds the
zip into an S3 multipart upload, part by part, so memory stays bounded whatever the
range, and the API only answers with the job.

**Access.** The mesh's owner and superusers, for both formats, even on a public mesh;
Parquet also needs the operator role, as the archive does. `node_ids` narrows a CSV
export; Parquet files hold the whole mesh, and the API image has no Parquet reader.

**Jobs in Redis.** A hash per job, plus an index per owner, kept 30 days so the console
can list past exports and ask for them again; a ready export reads as `expired` once its
file, kept 24 hours, is gone. No Postgres writes, so readings stays on its read-only role.
`exports:active:<owner>` holds the owner's one queued or running job: the same request
returns it, another answers `429`. A worker moves a job from `exports:queue` to
`exports:processing` with `BLMOVE` and beats a heartbeat after each day. Any worker
fails a job whose heartbeat is ten minutes old, so a crash or restart frees its owner,
and replicas recover each other's jobs.

**CSV.** One InfluxDB query per day, streamed, pivoted in Python into a row per time and
node: a Flux `pivot` fails when one field has different types across series. Duplicate
points from several gateways fold into one row. Descriptive tags (a node's name) are
columns; routing tags (`gateway_id`, `channel_id`, `postprocessing_id`) are not.
`quality` and alarms are left out. `channels.csv` describes each channel from the
catalog (name, unit, description, telemetry variant, derived or not), read as
`readings_ro`.

**Storage.** Files at `exports/<mesh_id>/<id>.zip` in the archive bucket, outside the
`telemetry/` prefix that archive credentials are scoped to. Only the worker holds
`READINGS__EXPORT_*`, the `export-writer` identity that can write under `exports/` and
read nothing. readings presigns downloads with the archive reader, which already reads
the whole bucket. A lifecycle rule expires `exports/` after a day (`minio_init` sets it
on the bundled MinIO; on an external S3 it is set by hand).

**Email.** The worker emails the owner when an export is ready, with the link, or has
failed, in the same HTML layout as every other email (see [email sending](#registry-email-verification)) with
a plain-text part. It is the only readings service with mail settings, mapped from
`REGISTRY__EMAIL_*`. A mail failure is logged and does not fail the export.

## MQTT sinks

A sink lets a third party subscribe, on this instance's EMQX, to the readings of the
meshes and devices an operator attaches to it, one JSON message per reading or alarm.
Nothing connects outwards: the consumer pulls, with credentials registry generates, and
the broker keeps it to its own sink's topics.

**Routing.** A `Sink` has `streams`, a subset of `decoded`, `derived` and `alarms`, and
is attached to whole meshes (`MeshSink`, every node including later ones) or single
devices (`DeviceSink`). `registry/sinks.py` publishes three kinds of record to
`mesh.sink_config.v1`: each sink's streams (`sink:<uuid>`, removed when it is paused or
deleted), each mesh's sinks (`mesh:<mesh_id>`), and each device's sinks alongside the
archive (`<mesh_id>:<device_id>`). Nothing is listed unless the mesh's owner is an
operator, so losing the role stops every sink of their meshes, as it stops the archive.
Each attach and detach is recorded as a `SinkInstruction`, with a null `node_id` for a
whole mesh.

**`sink_dispatcher`** (pipeline image, `full` profile, or `sinks` for lite) replays that
topic before its first poll and follows it. It consumes the decoded, derived and alarms
topics with its own group from the newest offset, so a new dispatcher does not replay
history, and publishes each event to the union of its mesh's and device's sinks that
chose its stream, at QoS 1 on
`{namespace}-sinks/{sink_id}/{stream}/{mesh_id}/{node_id}`. It skips backfilled derived
readings, which a consumer would read as new, and adds `"schema": 1` to every message.
Offsets are committed only after the broker acknowledges; a failed publish seeks the
partition back and reconnects, so Kafka is the buffer while the broker is down.
Once published, delivery is EMQX's: a consumer offline without a persistent session
misses messages, and one with a session gets back at most EMQX's queue per session.
EMQX's broker-wide session limits suit the bridge, not third parties, so each lifecycle
pass discards sink sessions offline longer than `REGISTRY__SINKS_MAX_OFFLINE_HOURS` or
queueing more than `REGISTRY__SINKS_MAX_QUEUED`, and disconnects a consumer that far behind.

The topic root sits outside `{namespace}/#`, the filter the bridge reads for sources, so
sinked JSON never comes back in as raw packets. The dispatcher connects as
`MQTT_SINKS__USER`, or the bridge's user when blank.

**Authorization on EMQX.** The broker's own rules are a hand-maintained file source,
which lets every authenticated client publish anywhere and only listed ones subscribe.
Registry never edits it. Sinks use EMQX's built-in authorization database, which must be
checked **before** the file (`manage.py sync_sinks --install-authz`, once per broker):

| Rules for | Rules |
|---|---|
| user `{namespace}-sink-{sink_id}` | allow subscribe `{namespace}-sinks/{sink_id}/#`, deny everything else |
| the dispatcher's user | allow publish `{namespace}-sinks/#` |
| everyone | deny publish and subscribe `{namespace}-sinks/#` |

A client matching none of them falls through to the file, so nothing else changes.
The dispatcher's user and the rules for everyone can be shared with another namespace on
the same broker, such as a dev stack's, so registry adds its rules to theirs rather than
replacing them. Creating a sink is refused (`502`) while the database is missing or not
first, since the file would then refuse the consumer and let any gateway credential
publish into sink topics. Clients the file allows everything, by IP or by subscribing to
`#`, still see sink traffic; they are the operator's own.

EMQX checks rules on subscribe, not per delivery, so revoking is also a disconnect:
deleting a sink removes its user and rules and kicks its clients, rotating replaces the
password and kicks, and a lapse replaces the rules with deny-all and kicks, keeping the
password for a renewal. The password lives only in EMQX, hashed; registry returns it
once and never stores it. `manage.py sync_sinks` reconciles users and rules with Postgres
after an EMQX redeploy; a sink whose user was lost needs its credentials rotated.

**Terms.** Like a source, a sink needs its own terms accepted, recorded and renewed
(`TermsKind.SINK`), since the operator becomes the controller of what the third party
receives. A sink stores nothing, so a lapse pauses it and schedules no deletion.

## registry rate limiting

`registry/throttling.py` defines DRF throttle classes, wired in via
`api_project/settings/base.py`'s `DEFAULT_THROTTLE_CLASSES`: `OwnerRateThrottle`
(120/min per authenticated owner), `AnonReadThrottle` (60/min per source IP, any
anonymous `GET` - in practice `GET /owners`, `GET /owners/{id}`, and `GET
/owners/verify-email`), `SignupThrottle` (20/hour per source IP, `POST /owners` only -
the one unauthenticated write on this API, and the highest-value abuse target), and
`ResendVerificationThrottle` (3/hour per authenticated owner, `POST
/owners/me/resend-verification` only - each call sends a real email, a higher-value
spam/cost target than an ordinary read). `LoginThrottle` (10/min per source IP and
email, `POST /owners/login` only) is covered under [Password login](#password-login).
`HealthView` is exempt from all of them (infra probe, not sensitive data).

DRF's dispatch runs authentication *before* throttling, so none of the four ever see a
request with an invalid bearer token - `OwnerBearerAuthentication` raises immediately on
a bad token, before `check_throttles` runs at all. `registry/authentication.py` closes
that gap directly with its own per-source-IP cap on *failed* attempts specifically (30
per minute) - deliberately not on every attempt, since a legitimate heavy user's valid
traffic is already governed separately by `OwnerRateThrottle`'s per-owner budget. Both
roles share this authentication class, so the cap applies to readings too.

**Source IP behind Caddy.** Every request reaches the API from Caddy's container
address, so `REMOTE_ADDR` is the same for all callers. `REST_FRAMEWORK["NUM_PROXIES"] = 1`
makes DRF's `get_ident()` take the last `X-Forwarded-For` entry instead, which Caddy
writes itself (it replaces any client-sent value unless `trusted_proxies` is set).
`OwnerBearerAuthentication`'s guard reads the same value through
`throttling.client_ident()`. Keying anything on `REMOTE_ADDR` directly makes it global:
the old hand-rolled login guard did, and ten mistyped passwords from anyone locked every
user out of login. If another proxy (a CDN
or load balancer) is added in front of Caddy, configure Caddy's `trusted_proxies` for it
so the forwarded chain still ends in the real client.

## registry email verification

A self-service signup (`POST /owners`) starts `is_active=False` (unverified) and gets
no access to anything but their own account until they click the link in a
verification email. Enforced by `registry/permissions.py`'s `IsVerifiedOwner`
(`is_authenticated and is_active`), set as `permission_classes` on every mesh/device/
key-rotation/device-listing view. `createsuperuser`/`seed_from_env`-minted owners
bypass this entirely (operator-initiated, not self-service) and stay fully active from
creation - only the public `POST /owners` route is gated.

**Unverified owners still sign in.** Signup itself logs the new owner in, and
`POST /owners/login` accepts an unverified owner too, so the console's verify-pending
page runs on the session cookie like every other page. Django's default
`ModelBackend` and DRF's `SessionAuthentication` both drop inactive users, so
`AUTHENTICATION_BACKENDS` is `AllowAllUsersModelBackend` and registry authenticates
sessions with `OwnerSessionAuthentication`, which keeps them; `IsVerifiedOwner` is what
gates access, for sessions and bearer keys alike. Readings keeps DRF's stock
`SessionAuthentication`, so an unverified owner's session is anonymous there. Before
this, the console held the signup `api_key` in browser storage and sent it as a bearer
on every request, and a stale key broke login. Bearer keys are for scripts only now.

**Exempted while unverified** - `OwnerMeView` (`GET`/`PUT`/`DELETE /owners/me`, so an
owner can view their status, fix a typo'd email, or delete/abandon the account) and
`POST /owners/me/resend-verification` (the unlock mechanism itself). Everything else
(meshes, devices, key rotation, `GET /owners/me/devices`) returns `403` until
verified.

**Verification link**: opens `REGISTRY__PUBLIC_FRONTEND_URL/verify-email?token=<token>`
(the frontend app), which reads the token from the query string and calls
`GET /owners/verify-email?token=<token>` itself - no bearer auth at all, the
token is the credential. The link points at the frontend rather than straight
at this API so the recipient sees a rendered result instead of the API's raw
JSON response. Expires after `REGISTRY__EMAIL_VERIFICATION_TTL_HOURS`
(default 24); `POST /owners/me/resend-verification` issues a fresh token, invalidating
the old one. Re-visiting an already-verified link is idempotent (`200`, not an error) -
deliberately, since email security scanners/link-prefetchers commonly auto-visit a
link before the real recipient clicks it, and a naive single-use token would get burned
by the scanner and lock the real user out. Invalid and expired tokens are merged into
one generic `400` rather than distinguished, to avoid an existence oracle.

**Changing email resets verification**: `PUT /owners/me` with a different `email`
flips `is_active` back to `False` and sends a fresh verification email to the new
address - same "changing the sensitive field re-triggers the side effect" pattern as
`PUT /meshes/{id}` republishing every allowed gateway device on a `psk_b64` rotation.

**Email sending** (`registry/emailing.py`) is a generic `send_templated_email(to,
subject, template_name, context)` helper on top of Django's `EMAIL_BACKEND`
(`REGISTRY__EMAIL_*` env vars, defaulting to the console backend), with
`send_verification_email` and `send_password_reset_email` as thin wrappers - this
split is deliberate: it's the reusable foundation the alarm-triggered email
(`registry_quality_alarms_consumer`, see
[Data quality checks](#data-quality-checks) above) calls directly with its own
template and context, without touching anything verification-specific.
Every email is sent as plain text (`registry/emails/<name>.txt`, not HTML-escaped) with
an HTML part (`<name>.html`) styled like the console: the shared layout and pieces are in
`registry/templates/emails/` (`base.html`, and `_chip`, `_title`, `_button`, `_quote`,
`_details` partials), all with inline styles since many mail clients drop `<style>`
blocks. A test fails if a plain-text email has no HTML version.
Local dev: a `mailhog` service in
`docker-compose.yml` catches outgoing mail at `http://localhost:8025` (`REGISTRY__EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`,
`REGISTRY__EMAIL_HOST=mailhog`) instead of needing a real SMTP provider - email delivery
failures are treated as non-fatal everywhere (signup and the `PUT /owners/me`
email-change path log and continue rather than rolling back; only
`POST /owners/me/resend-verification`, whose entire purpose is sending the email,
surfaces a failure as `502`).

## Password login

Every owner has two independent credentials: the bearer API key (scripts,
integrations, `POST /owners/me/rotate-key`) and, since password login shipped,
a real password (a future dashboard's login/sign-up forms). They don't
interact - rotating the API key doesn't touch the password and vice versa.
Before this, only superusers had a *usable* password (`createsuperuser`,
gated by `is_staff`, for `/admin/` login); every self-service owner got
`set_unusable_password()`. `POST /owners` now requires a `password` on every
signup, validated by Django's standard `AUTH_PASSWORD_VALIDATORS` (length,
not-too-similar-to-email/name, not a common password, not all-numeric).
Owners that signed up before this change still have no usable password by
definition - `POST /owners/reset-password` (below) is also how they set one
for the first time, not a separate migration path.

**Session, not a bearer key, for login.** `POST /owners/login` (email +
password) sets a Django session cookie via `django.contrib.auth.login()`,
rather than minting/returning a bearer key - the raw API key is never stored
after creation (only its hash), so login has nothing to hand back on that
path anyway, and re-minting one on every login would invalidate every other
device's session each time (the same key backs every device, unlike a
session cookie). `DEFAULT_AUTHENTICATION_CLASSES` lists
`OwnerBearerAuthentication` before `OwnerSessionAuthentication` (registry) or
DRF's `SessionAuthentication` (readings) - every permission class (`IsVerifiedOwner`,
`IsSuperuser`) only ever looks at `request.user`, so this is additive and
every existing route works unmodified over either credential.
`GET /owners/csrf-cookie` primes the CSRF cookie for a browser client's first
session-authenticated write (`django.middleware.csrf.get_token`) - nothing
else in this API causes Django to set it, since scripts write with a bearer
key instead. `POST /owners/logout` is deliberately
CSRF-exempt (`authentication_classes = []`, so `SessionAuthentication`'s CSRF
check never runs) - the worst a forged call does is log the victim out, not
act on their behalf.

Login is limited by `LoginThrottle` (`login`, 10/minute), an ordinary DRF
throttle keyed per source IP *and* email, so one person's typos lock out only
that account from that address, not everyone sharing it (an office or event
NAT). It counts every attempt, not only failures: nobody legitimately signs in
ten times a minute, and that keeps it a plain throttle rather than a cache
counter in the view. Once tripped, even the right password gets `429` until the
oldest attempt leaves the window. A password is human-chosen and guessable in a
way a bearer key isn't, which is why login has this and bearer keys only have
the coarser failed-auth guard.

**Password reset** (`POST /owners/request-password-reset` +
`POST /owners/reset-password`) mirrors the email-verification token shape
(`password_reset_token_hash`/`password_reset_sent_at` on `Owner`, same
`generate_api_key`/`hash_api_key` token, `REGISTRY__PASSWORD_RESET_TTL_HOURS`
default 1h - shorter than verification's 24h, since this token grants account
takeover, not just inbox proof). Unlike every other owner-facing flow, the
request step is reachable by someone who hasn't proven they own the address
at all, so its response is always a generic `200` regardless of whether the
email is registered - the one place in this API that's a deliberate
existence-oracle exception in the other direction from verification's
merged-400 treatment (same goal, opposite mechanism: nothing distinguishes a
registered address here either way). `RequestPasswordResetThrottle` caps it
per-IP, same shape as `SignupThrottle`.

Like email verification, the reset link points at `REGISTRY__PUBLIC_FRONTEND_URL`
(the frontend app) rather than at this API directly - but reset additionally needs
a form to collect the new password, so the frontend can't just fire the request on
page load the way it does for verification. The frontend reads the token from
the link's query string and sends it back in the body of
`POST /owners/reset-password` as `token`, next to `new_password`. The view takes
no credentials at all (`authentication_classes = []`), the same as
`GET /owners/verify-email`: the token is resolved to its owner inline, with the
TTL and single-use rules, and invalid, unknown and expired tokens all fail the same
way with `400` on `token`. This keeps the API to two credentials, a session cookie or
an API key.

`POST /owners/me/change-password` (session or bearer, requires the *current*
password even though the caller is already authenticated) exists so a
hijacked or left-open session can't silently take over the login credential
- not explicitly separate from the reset flow for any deep reason, just the
obvious authenticated-user path a login system needs.

**Cross-origin cookie caveat, deliberately unresolved**: `SESSION_COOKIE_SAMESITE`
stays Django's default (`Lax`), which works for a dashboard served same-site
(e.g. behind this same Caddy gateway). A dashboard on a genuinely different
origin would need `SameSite=None` plus `Secure` (HTTPS-only) - real topology
isn't known yet, same reasoning as the merge-vs-separate decision for
registry/readings. `REGISTRY__CORS_ORIGINS` / `READINGS__CORS_ORIGINS` being set
already turns on `CORS_ALLOW_CREDENTIALS` and mirrors the allowlist into
`CSRF_TRUSTED_ORIGINS`, since a cookie is useless cross-origin without the former
and CSRF checks need the latter - revisit `SameSite` if the dashboard ends up
cross-site. Readings has no `CsrfViewMiddleware`, but `SessionAuthentication`
still checks CSRF on its one write (`POST /readings/archive/meshes/{id}/credentials`),
validating the `csrftoken` cookie registry set.

## Roles: registry and readings

One Django project serves the whole API, shipped as one image and deployed as
two container roles. `APP_ROLE` picks which urlconf is mounted and which
database credentials are used.

| | registry role | readings role |
|---|---|---|
| serves | `/owners`, `/meshes`, `/devices`, the catalog, blueprints, `/admin/`, `/schema`, `/docs` | `/readings/*`, including the [archive](#sinks-and-the-parquet-archive) |
| database | `REGISTRY__DB_DSN`, the owning role | `READINGS__DB_DSN`, `readings_ro` |
| container | `registry-api:8090` | `readings-api:8091` |

**Why two containers rather than one process.** Reading telemetry is the
open-ended, potentially heavy half of the API; registering a gateway is not.
A single gunicorn pool would let a burst of range queries occupy the workers
that answer registration, so the two get their own pools and can be scaled
and restarted independently. Why not two *projects*: they shared no code, so
every cross-service question had to be asked over HTTP, which is what the
previous design did and what this replaces.

**Authentication is one database lookup.** Both roles use
`registry.authentication.OwnerBearerAuthentication`: the bearer token is
sha256'd and matched against `owners.api_key_hash`. `request.user` is a real
`Owner`. The mesh-keyed routes scope with an indexed `Mesh.owner_id` check;
`Owner.devices_by_uuid` gives the UUID-addressed routes their
registration-to-address map. `Owner.visible_meshes` is
the single definition of "which meshes may this owner read" - every mesh for a
superuser, otherwise their own and any with `is_public`. `Owner.visible_devices` derives from it, and
`_devices_for_owner` serves `GET /owners/me` from the same property.

**Reading widens; writing does not.** `is_public` only ever answers "may this
caller read this mesh". Both registry views and readings
resolve reads through `visible_meshes_for(user)`, which is `visible_meshes` for an
owner and only public meshes for an anonymous caller, while every mutation goes through
`Owner.can_edit_mesh`, which is still owner-or-superuser and which `is_public`
does not touch. Reads that are refused answer `404` rather than `403`, so a
private mesh does not confirm its own existence to a caller with no access; a
refused *write* keeps its `403`, since by then the caller has already proved
they can see it.

**Public meshes are public to anonymous callers too.** Mesh list/detail, the
mesh's device list and the two `latest` readings routes accept requests without
credentials and answer for public meshes only; everything else keeps its
authentication. Every non-owner, signed in or not, gets the mesh through
`MeshPublicSerializer`, an explicit allowlist that leaves out `psk_b64`,
`source_id` and the terms status, so a field added to `MeshSerializer` later is
not exposed to viewers by accident. An anonymous UUID lookup on readings resolves
only allowed devices on public meshes, from the columns `readings_ro` already has.
Anonymous traffic is throttled per IP by `AnonReadThrottle` on both roles.

This replaces an HTTP introspection call to `GET /owners/me` whose result was
cached for 60 seconds. That cache is gone, and with it three failure modes:

- a `503` on every readings request whenever the registry role was unreachable,
- a device registered in the last 60 seconds not yet being queryable,
- a rotated or deleted key still working until the entry expired, which needed
  a Kafka topic (`mesh.owner_auth_revocations.v1`) and a dedicated consumer
  container purely to invalidate it early. Both are deleted.

**The read tier cannot write, and holds no key material.** `readings_ro` is
created by `manage.py provision_read_role`, which the registry role runs after
`migrate` so grants are re-applied as tables appear:

| table | granted |
|---|---|
| `meshes` | `id`, `owner_id`, `is_public` only |
| `devices` | `id`, `device_id`, `mesh_id`, `is_allowed` only |
| `owners` | every column |
| `measurement_types` | every column |

`visible_meshes` reads `meshes.is_public`, so without that column grant readings
fails with a Postgres permission error at request time. The Django test runner
connects as the superuser role and cannot reproduce that, which is why
`test_provision_read_role.py` asserts the grant shape directly.

`meshes.psk_b64` and `devices.admin_keys_b64` are deliberately excluded, so a
compromised readings container cannot read the keys that decrypt mesh traffic.
That is a smaller blast radius than the introspection design, where the read
tier could ask the registry about any token it liked.

The split between column and whole-table grants is forced by the ORM, and is
worth understanding before narrowing it: **Django selects every field of a
model**, so a column grant on a table it instantiates refuses the query
outright - a column-restricted `owners` breaks authentication itself. Hence
`owners` and `measurement_types`, which the read tier loads as model objects,
are granted whole. `meshes` and `devices` keep column grants because the read
tier never instantiates them: `Owner._device_addresses` deliberately uses
`values_list("id", "mesh_id", "device_id")`, which selects exactly those three
columns. Changing it to return model instances would ask for `admin_keys_b64`
and fail.

Granting `owners` whole is acceptable because every sensitive column on it is
already a hash: `api_key_hash` is sha256 over 256 bits of entropy, and
`password` is PBKDF2. Neither is reversible, and neither is the asset an
attacker would be after - the mesh PSKs are, and those stay out of reach.

The role also carries `CONNECTION LIMIT` (`READINGS__DB_MAX_CONNECTIONS`,
default 10). That is the actual guarantee that read traffic cannot exhaust the
connections the registry role needs - enforced by Postgres, not by a convention
in a settings file. Being read-only also means the readings role *cannot* run
migrations, which is enforcement rather than agreement.

**Route trimming.** The readings role mounts only `readings/` and its own
`health` probe, so the registry's routes are not reachable there even if the
proxy is bypassed. `readings/views.py`'s `ReadingsAPIView` states
`IsAuthenticated` on the views themselves rather than inheriting it from
settings, so reading data needs an authenticated owner but not a verified one
regardless of which role's settings happen to be loaded.

`_require_visible_mesh` returns `404`, not `403`, for a mesh the caller may not
read. Scoping is per mesh because that is the only ownership relationship in the
schema, and because non-gateway devices are created from observed traffic rather
than registered - requiring a registration row would hide a node's telemetry
from the owner of the mesh it arrived on. The mesh still travels with every node
number: a Meshtastic node number is only unique per mesh among currently-*allowed*
registrations (`uq_devices_mesh_device_id_allowed`), not globally or over time, so
the same number can belong to two owners at once, and a number freed by one owner
and later reused by another would otherwise expose the previous owner's history, InfluxDB having no ownership boundary of its own. This
is why the store-native address is nested as
`/readings/meshes/{mesh_id}/nodes/{node_id}` rather than flat, and why
`flink/decode_job.py` tags every decoded point with `mesh_id` before it reaches
InfluxDB.

**Two addresses, one implementation.**

| Address | Notes |
|---|---|
| `/readings/devices/{device_uuid}` | The registration ID, the same UUID `/devices/{id}` uses. Globally unique, so no mesh nesting is needed. |
| `/readings/meshes/{mesh_id}/nodes/{node_id}` | The store-native address, and the escape hatch: InfluxDB is tagged this way, and scoping is by mesh, so it reaches devices with telemetry but no registration row. |

`DeviceReadingsView`/`DeviceLatestView`/`DeviceQualityView` are two-line
subclasses that resolve the UUID and delegate, so the two forms return
identical bodies. Resolution doubles as the access check: an owner's map only
holds devices they own, so an unknown UUID and an unowned one are
indistinguishable and both `404`.

**Shared cache**: Redis still backs the throttle counters and the failed-auth
guard for both roles (`REGISTRY__REDIS_URL`/`READINGS__REDIS_URL`, different
logical DBs), not Django's per-process `LocMemCache` - without a shared
backend each gunicorn worker would keep private counters and silently multiply
every throttle rate by the worker count.

Two rate limits protect different things:
- `registry.throttling.OwnerRateThrottle` caps authenticated traffic at 120
  requests/minute per owner.
- A per-source-IP cap (30/minute, IP read through Caddy's `X-Forwarded-For`) on *failed* authentication inside
  `OwnerBearerAuthentication`. DRF runs authentication before throttling, so
  the owner throttle never sees a request bearing an invalid token; this closes
  that gap for both roles.

## reverse proxy

One Caddy instance fronts the API so consumers deal with one host instead of
remembering which role serves what. **Paths are forwarded unchanged**, so an
app route is already the external route:

```caddyfile
handle /readings/* { reverse_proxy readings-api:8091 }
handle             { reverse_proxy registry-api:8090 }
```

`handle`, not `handle_path`: nothing is stripped. The readings role mounts the
`readings/` segment itself, so what the urlconf says is what callers type. A
route added to either `urls.py` becomes reachable with no Caddyfile change.

This is why the readings half owns exactly one top-level segment. The two
halves previously collided on `/devices` and `/meshes` (a registration row
versus its values) and on `/health`, `/schema` and `/docs`, which is what the
old `/management` and `/data` prefixes existed to separate. Putting the
readings routes under `/readings/` removes the collision at the source, so the
prefixes and all the machinery that compensated for them are gone:
path rewriting in the schema, the per-service `servers` blocks and their
per-request ordering, and the two Swagger UIs.

`GET /` is a small static JSON index in the Caddyfile, pointing at `/schema`,
`/docs`, `/health`, `/metrics` and `/readings`. It stays static - Caddy cannot
query Postgres, which is why it links to `/metrics` rather than embedding
counts.

**One schema, generated once.** `/schema` and `/docs` are served by the
registry role over `api_project.urls_all`, a urlconf that exists only for
generation and is never mounted. Because the two roles share no paths, that
single pass describes the whole API: nothing is merged, nothing is rewritten,
and there is no cross-service HTTP call that can fail. `SERVERS` is the bare
public origin (`GATEWAY__PUBLIC_URL`), since the paths are already external.

`server/tests/test_gateway.py` parses the Caddyfile and asserts the
routing still matches what the app mounts - that `/readings/*` reaches the
readings upstream, that everything else falls through to the registry role,
that no `handle_path` reappears, and that no registry route starts with
`readings` and would therefore be unreachable.

Unmatched paths reach the registry role and get Django's `handler404`, which
`api_project/errors.py` makes JSON rather than the default HTML page.

`CADDY_SITE_ADDRESS` controls the listen address: a bare port (`:80`, note the
leading colon) serves plain HTTP with no automatic TLS, used for local dev; a
real domain (`api.yourdomain.com`) makes Caddy obtain and renew a Let's
Encrypt certificate automatically. A production deployment stops publishing
the two container ports directly and sets
`REGISTRY__BEHIND_TLS`/`READINGS__BEHIND_TLS=true` plus
`REGISTRY__PUBLIC_BASE_URL` to the public origin - no path prefix any more, since
the API is served at the root.

## Admin keys — unrelated to the decode gate

`admin_keys_b64` — base64-encoded copies of a device's `Config.SecurityConfig.admin_key`
(up to 3, matching firmware's limit) — authenticates outbound `AdminMessage` packets
for remote node control. This is unrelated to decoding: setting or changing
`admin_keys_b64` on a `Device` (via `POST`/`PUT /devices`) never publishes to Kafka,
so admin keys never reach `mesh.keys.v1`, `mesh.node_rejections.v1`, or either of the
Flink decode job's broadcast states. See
[api-reference.md#devices](api-reference.md#devices).

## Postprocessing

Postprocessing derives new channels from a device's telemetry: calibrating a
sensor, converting two ADC electrodes and a temperature into a pollutant
concentration, computing a dew point. Derived channels are stored, archived,
catalogued, checked and served exactly like the channels a device reports.

```
PostprocessingBlueprint        owner (null once deleted while in use), name, is_public
  └─ BlueprintVersion          immutable; number 1, 2, ...
       inputs  [{"slot": "working", "default_channel": "ads1115.channel_0"}, ...]
       └─ PostprocessingStep   key (stable across versions), order, function_name
            inputs   {"working": "slot:working", "concentration_ppb": "step:ppb.concentration_ppb"}
            params   configuration only, e.g. {"molecular_weight": 46.01}
            outputs  {"concentration_ppb": "no2_ppb"}

DevicePostprocessing           a blueprint version applied to one device
  device, blueprint_version, output_prefix, tolerance_seconds, is_enabled
  ├─ PostprocessingInputBinding   slot -> one of the device's Measurement rows
  ├─ StepCalibration              append-only: step_key, function_name, params, valid_from
  └─ Measurement.produced_by      the derived channels it owns, created on attach
```

**The recipe is shared, the wiring and calibration are not.** A blueprint
says what to compute from abstract input slots. Each device binds the slots to
its own channels and supplies its own calibration, because two units of the
same build have different electrode sensitivities and may wire sensors to
different ADC channels. A slot's `default_channel` binds automatically when the
device has that channel.

**Algorithms declare their calibration parameters.** An algorithm in
`common/algorithms/` declares every keyword argument with `Param`, marking the
ones that describe one physical sensor as `calibration=True`. Those are set per
device through `StepCalibration`; the rest are set on the blueprint step.
Defaults come from the function signature and the declaration is checked
against it at import time. `GET /algorithms` exposes the metadata so a client
can build a calibration form. `offset_scale` and `lookup_table` are ordinary
single-input algorithms, so plain per-channel calibration needs nothing special.

```python
@algorithm(
    name="ec_sensor_ppb",
    inputs=("working", "auxiliary", "temperature"),
    outputs=("concentration_ppb",),
    params=(
        Param("sensitivity", calibration=True, unit="mV/ppb"),
        Param("working_zero", calibration=True, unit="mV"),
        Param("reference_temperature", unit="degC"),
    ),
    output_units={"concentration_ppb": "ppb"},
)
def ec_sensor_ppb(working, auxiliary, temperature, *, sensitivity, working_zero=0.0, reference_temperature=20.0):
```

**Calibration keeps its history.** A new calibration takes effect from its
`valid_from` and never rewrites the past: the engine applies to every sample the
calibration in force when it was taken, both live and in backfills. A
calibration is keyed by step key and algorithm, so it carries over when a device
moves to a version where that step is unchanged.

**Versions are immutable.** Changing steps means adding a version; devices keep
running theirs until moved. A move keeps bindings for slots the new version
still declares, adds and removes derived channels to match its outputs, and is
refused while it would leave an enabled postprocessing unable to run.

**Postprocessings chain.** Within a version, a step reads an earlier step's
output with `step:<key>.<output>`. Across postprocessings, a slot can be bound
to another one's derived channel. Registry refuses dependency cycles, refuses
detaching a postprocessing whose outputs another reads, and publishes a device's
plans in dependency order.

**Output units** resolve in step order from the units of the bound channels,
using each algorithm's `output_units` (a literal, or `"@<input>"` for a
unit-preserving algorithm). A derived channel's `MeasurementType` is global
(`computed:derived`, field name), so an attach whose resolved unit contradicts
the catalog is refused; `output_prefix` gives the outputs other names. It also
lets one blueprint run twice on a device. The type is dropped with the last
device channel using it, however that channel is removed (detach, device, mesh or
owner deletion), unless a telemetry variant declares it in the catalog.

### Execution

Registry resolves every enabled postprocessing of a device into a `ResolvedPlan`
(`common/postprocessing/plan.py`): concrete channels instead of slots,
configuration and the calibration history, and a join tolerance (its own, or
half the device's reading interval, or 30s). All plans of a device are
published as one compacted message on `mesh.postprocessing_config.v1`. Writes
that change plans roll back if that publish fails, since stale plans would
silently compute wrong values.

`postprocessing_job.py` keys decoded telemetry by device and runs the plans
through `common/postprocessing` (`apply`). Channels arrive in separate packets
and, for devices delivering stored history, possibly hours apart, so each step
joins its inputs with a streaming join (`joiner.py`): a sample of the step's
first input becomes a row once every other input has a sample within the
tolerance. Channels may be skewed against each other by any amount; each
channel's own samples are assumed to arrive in time order. The join state lives
in Flink keyed state and is discarded when a plan changes. Derived samples take
their base sample's timestamp, resolved the same way storage resolves it
(`mesh_things.timestamps`), so they line up with the raw points and a replay
rewrites the same points.

Results go to `mesh.telemetry.derived.v1` in the decoded envelope shape:

```json
{"mesh_id": "...", "node_id": 123, "rx_time": 1790000000, "payload_kind": "computed:derived",
 "payload": {"derived": {"no2_ppb": 12.1, "no2_ugm3": 23.0}},
 "postprocessing_id": "...", "blueprint_id": "...", "blueprint_version": 2}
```

`influxdb_writer` stores them in the `derived` measurement tagged with
`postprocessing_id`, `s3_writer` archives them for devices that opted in, and `pattern-detection-job`
reads them alongside decoded telemetry, so `flat_value` and `range` work on
derived channels without special cases. The live sources of both jobs start at
the end of a topic they have never read rather than replaying it.

**Backfills** recompute history. A request creates a `PostprocessingBackfill`
row; the worker's beat task claims pending ones through registry, reads the
inputs from InfluxDB, runs the same engine in time order and publishes to the
derived topic, so storage and archive take the live path. Backfilled events are
marked `"backfill": true` and pattern detection skips them, since alarming now
on long-past values would report them as new faults. A run abandoned by a
crashed worker can be claimed again after an hour.

Windowed algorithms can be declared but nothing runs them yet, so versions
using one are refused.

## Device fault detection

**"Not publishing" is not the same fault as "not reading."** A device has a
*publish* interval and a *reading* interval, and once telemetry is batched
they diverge: a device accumulating readings is silent for a long time by
design and then delivers a complete history. That's healthy. What isn't
healthy is delivering a *patchy* history. So there are two independent
checks:

| Fault | Question | Timed against | Where | Why there |
|---|---|---|---|---|
| **A. Absence** | "have we heard from it?" | `publish_interval_seconds` | `flink/absence_detection_job.py` | needs a timer that fires when *nothing* arrives |
| **B. Completeness** | "was what we heard complete?" | `reading_interval_seconds` | `quality_worker`'s `check_completeness` | needs history, not a single event |

Both intervals live on `Device` (nullable), falling back to
`TelemetryVariant.default_reading_interval_seconds`. They're curated via
`PUT /devices/{id}` today, and are written to be NodeInfo auto-filled later,
following the same sticky-override pattern as `latitude`/`hardware_type`.

**Check B is already future-proof for buffered telemetry.** Meshtastic
doesn't ship buffered telemetry yet, but `writer/point_builders.py`'s
`_resolve_timestamp` already prefers the payload's own `time` over `rx_time`
when it's plausible. So when batched readings do arrive, each buffered sample
lands in InfluxDB at its *true reading time*, back-filling the hole — and the
same gap query keeps working with no change. Until then, the check still
correctly catches genuinely missing readings.

Absence detection is the **first and only** user of Flink timers here, and
they're **processing-time** timers deliberately: "has anything arrived
lately" is a wall-clock question about now, not a reconstruction of the
event-time stream. Event-time timers would need a real watermark strategy
plus idle-source handling — and a device that has stopped sending produces no
events to advance a watermark with, which is exactly the case being detected.
`on_timer` re-reads the interval from broadcast state rather than reusing the
armed value, so clearing a device's intervals (published as an `op: "delete"`)
stops the alarms; a silent device produces no elements, so that delete is the
only way a config change can reach it.

## Data quality checks

Two tiers, split by what each check fundamentally needs:

| Tier | Runs | Checks | Needs |
|---|---|---|---|
| **Stream** (Flink) | per point | `flat_value`, `range`, `absence` | current value + small keyed state |
| **Batch** (`quality_worker`, Celery) | scheduled | `completeness`, including derived channels | days-to-months of history |

**Thresholds come from the registry, not a separate rules topic** - the catalog
for `flat_value`'s default and reading intervals, a device's own `Measurement`
row for `range` (it has no catalog default at all). Editing either publishes to
the compacted `mesh.quality_config.v1`, which both Flink jobs consume as
broadcast state:

```json
{"kind": "variant_config", "key": "environment_metrics.temperature",
 "default_reading_interval_seconds": 900, "default_enabled_detectors": ["flat_value"], "op": "upsert"}
{"kind": "device_intervals", "key": "<mesh_id>:<device_id>",
 "reading_interval_seconds": 300, "publish_interval_seconds": 3600, "op": "upsert"}
{"kind": "measurement_alarms", "key": "<mesh_id>:<device_id>:environment_metrics.temperature",
 "enabled_detectors": ["range"], "valid_min": -40, "valid_max": 85, "op": "upsert"}
```

A `kind` discriminator routes each to the right lookup, the same way
`decode_job.py` handles its two merged broadcast streams. This supersedes
`mesh.rules.v1`/`RULES_STATE`, which `pattern_detection_job.py` no longer
reads — the catalog is the single source of truth. (The topic still exists;
it just has no consumer.) Publishing is deliberately **best-effort**, unlike
the gateway/node publishes that roll their DB write back on failure: a stale
threshold delays a detection, it doesn't leak anything, and a compacted topic
reconciles on the next edit.

**Detectors fire on sustained conditions, once.** `range` needs several readings in
a row out of bounds, `flat_value` the same value for 12 h, and both re-raise at most
hourly (by reading time) with a `repeat` flag; `absence` fires once per silence. See
[data-quality.md](data-quality.md) for the rules and their settings.

**One alarm shape from both tiers**, on `mesh.telemetry.alarms.v1`:

```json
{"mesh_id": "...", "device_id": 111222333, "channel": "environment_metrics.temperature",
 "detector": "absence|flat_value|range|completeness", "source": "stream|batch",
 "value": 21.4, "message": "...", "triggered_at": "...", "replay": true}
```

Stream alarms are stamped with the reading's time, so reprocessing a reading
rewrites its alarm rather than adding one. They are held for a few seconds
before they are sent, and a channel arriving far faster than any device reports
marks them `replay`, which the email consumer drops.

One shape means one consumer routes every alarm to email
(`registry/management/commands/consume_quality_alarms.py`, which resolves
`(mesh_id, device_id)` → `Device` → `Mesh` → `Owner`) and one writer persists
every alarm to InfluxDB (`writer/influx_writer.py`, which keys off the
`detector` field). Carrying `mesh_id`/`device_id` is what closes known-gaps #7 — alarms used to
carry a bare `node_id`,
with nothing to resolve an owner from. Emails are grouped per device: the first
alarm is emailed and opens a window, every later alarm on that device (any
detector or channel) is held in Redis, and one summary is emailed when the
window ends. `repeat` and `replay` alarms never email on their own, and `absence`
is emailed straight away, at most once per device per day. The consumer closes ended windows from a tick in its poll loop
(`consume_forever(..., tick=...)`, every 10s), since there is no scheduler.
Redis runs with AOF on a volume so pending summaries survive a redeploy. The
window length is `REGISTRY__ALARM_EMAIL_COOLDOWN_SECONDS` server-wide by
default, but each owner can set their own `alarm_email_cooldown_seconds` (via
`PUT /owners/me`) to override it - `0` means "email on every alarm, no
summaries," `null` (the default) defers to the server value. See
[data-quality.md#alarms](data-quality.md#alarms).

`quality_worker` has no database of its own: it reads device and postprocessing
metadata from registry's REST API with a superuser key, exactly as readings does
for introspection, and queries InfluxDB directly through the same validated
Flux helpers readings uses (`mesh_things.influx_query`). Its broker is Redis
logical DB 2 — registry's cache uses 0 and readings' 1 on the same container,
so this added no infrastructure.

## Server monitor

`server_monitor` (`server/monitor/`, its own slim image) is the one service
meant to run away from the stack: on another machine, so it sees what a user sees and
still reports a dead host. It uses nothing internal - only the public HTTP API through
Caddy, and the MQTT broker the bridge reads - and a member account's API key.

Each round it calls `/`, `/health` and `/schema` without credentials, then publishes a
probe: device telemetry from a gateway registered on its own mesh, encrypted with that
mesh's PSK, carrying a unique marker in `uptime_seconds`. The probe passes through the
same path as any packet (bridge, `mesh.telemetry.raw.v1`, decode, `influxdb_writer`),
and the monitor follows it out through the readings API, the gateway's `last_seen` in
the registry (`mesh.devices.v1`, `registry_device_consumer`) and, optionally, an MQTT sink.
Failures are emailed to a list of superusers kept in the monitor's own settings, so
alerting does not depend on the API it is checking. The monitor's own API serves the
latest results (`/status`) and runs checks on request (`/run`, token-protected, sharing
one probe between concurrent requests). See [monitoring.md](monitoring.md).
