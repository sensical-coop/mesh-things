# Done

Work that is finished, kept for the reasoning rather than the result. Each entry
keeps the number it had while it was open, so older references to
`#N` still resolve here.

`plans/` holds only what is still open, a numbered file per entry, and `plans/known-gaps.md`
holds findings from investigations, which is a
different thing: a gap was something that turned out to be wrong, an entry here
was something planned and then built.

| # | Summary |
|---|---|
| 0 | Two build targets, `lite` and `full`, from one codebase |
| 1 | CI now runs the root test suite |
| 2 | S3 writer small-file explosion |
| 2b | Archive stored partition keys as columns too |
| 8 | Merge vs. separate vs. Postgres replication, settled |
| 9 | API surface: summary and metrics endpoints |
| 10c | A failed batch was dropped rather than retried |
| 10d | readings required a registration row, not just mesh ownership |
| 11 | Timeseries `start`/`stop` window |
| 12 | Gateway ID and node ID had different formats in InfluxDB |
| 13 | Not all MQTT messages reached the bridge |
| 15 | The published OpenAPI schema carried no parameters or response shapes |
| 15b | Alarms became opt-in, per detector, per measurement |
| 16 | Postprocessing was not related to devices |
| 3 | A jobmanager restart dropped every Flink job |
| 4 | Redeploying a job with state was a manual savepoint dance |
| 5 | The `alarms` topic had no retention policy |
| 20 | The Flink image was 2.9 GB and ran on Java 11 |
| 10 | Superusers could not see `psk_b64` and `admin_keys_b64` |
| 5b | Pattern detection raised an alarm on every reading |
| 21 | Alarms fired too quickly |
| 22 | Alarms were stored forever, one point each |
| 23 | Gateways had to be registered by hand |
| 6 | Derived catalog types outlived the devices producing them |
| 14 | `/docs` "Try it out" failed cross-origin |
| 19 | Owners could not export their readings |
| 1a | Every packet came from one broker and one topic |
| 25 | Mesh network metrics needed Malla, which is slow |
| — | [Evaluated and deliberately not doing](#evaluated-and-deliberately-not-doing) |
| — | [Accepted, no action](#accepted-no-action) |

---

## 0. Two build targets: `lite` and `full` — Resolved

Shipped, decision #3 aside (see below). Ship the stack as two products from one codebase: a
`lite` build small enough for demos and small deployments, and a `full` build
with stream processing, archiving and headroom. Both get built and tested; the
goal is that the difference is *configuration and one runtime*, not a fork.

### What each tier is for

- **lite** — MQTT in, decode, store in InfluxDB, manage meshes/devices over the
  API. A single small VPS. The thing you hand someone to try.
- **full** — everything above plus the Flink stream tier (calibration,
  flat-value/plausibility, absence detection), the S3/Parquet archive, and the
  capacity to scale the decode step.

### Measured basis

Traced by following the Kafka topics, not assumed: `mqtt_kafka_bridge` → raw →
decode (needs `mesh.keys.v1` + `mesh.node_rejections.v1`, both published by
registry) → decoded → `influxdb_writer` → InfluxDB. Everything else is optional to
that path.

| | lite | full (today) |
|---|---|---|
| Containers | ~9-13 | 22 |
| Memory | **~1.3-1.8 GB** | **~6.2 GB** |
| Fits | 2-4 GB VPS (CX22, ~€4/mo) | 8-16 GB VPS (CX32/CX42) |

The gap is almost entirely Flink. Measured with **only** the decode job running,
so this is the honest floor for keeping it:

```
taskmanager: 1.67 GiB   (1138 MB JVM + 480 MB one PyFlink worker)
jobmanager : 1.02 GiB
```

**2.7 GB of a 4.0 GB minimal deployment — 67% — to decode roughly one message
per second.** That is the entire case for a second decode runtime.

### The key finding: batch quality does not need Flink

`quality_worker` depends only on InfluxDB, Kafka, registry and Redis (the two
Flink mentions in its source are comments). So **postprocessing blueprints and
completeness/gap analysis work in `lite`** — only the per-point stream checks
need Flink. That makes the split far more attractive than "lite loses the
interesting features".

> Superseded by [#16](#16-postprocessing-was-not-related-to-devices--resolved):
> postprocessing moved into the Flink tier, so `lite` keeps completeness but no
> longer derives channels.

### Proposed shape

| Component | lite | full |
|---|---|---|
| Kafka, Postgres, Redis, InfluxDB | ✅ | ✅ |
| `mqtt_kafka_bridge`, `influxdb_writer`, `registry_api`, Caddy | ✅ | ✅ |
| Decode | plain Kafka consumer | Flink (`decode_job.py`) |
| Delivery guarantee | at-least-once | exactly-once |
| `readings_api` (read API) | ✅ recommended (+148 MB) | ✅ |
| registry device/discovery consumers | ✅ (+120 MB) | ✅ |
| `quality_worker` + beat (blueprints, completeness) | ✅ optional (+185 MB) | ✅ |
| Flink stream tier (calibration, pattern, absence) | ❌ | ✅ |
| S3/MinIO Parquet archive | ❌ | ✅ |
| `kafbat-ui` | opt-in (`--profile kafka-ui`) | opt-in (`--profile kafka-ui`) |

### How to keep the reuse high

**Done.** The decision logic — `DecodeWithBroadcastKey.process_element`'s
gateway/reject checks, decrypt/decode, and the device-sighting/
sensor-discovery side-output derivation — is now one pure function,
`decode_packet(raw, gateway_state, rejected_nodes) -> dict | None`, in
[`common/decode.py`](../server/common/decode.py). Both runtimes
are thin callers:

- `flink/decode_job.py` — sources, sinks, broadcast state (adapted to
  `decode_packet`'s dict/set-like params via two small adapter classes),
  calls the shared function.
- `pipeline/decode_consumer.py` — two plain `KafkaConsumer`s (raw packets,
  and the same `mesh.keys.v1`/`mesh.node_rejections.v1` config topics kept
  as two in-memory dicts instead of broadcast state) plus one
  `KafkaProducer`, calling the same function. At-least-once (commit after a
  batch's decoded/sighting/discovery events are all produced), vs. Flink's
  exactly-once.

The decryption path stays single-implementation — it is the most
security-sensitive code in the repo. `tests/test_decode.py` exercises the
shared function directly (registered/unregistered gateway, rejected node,
encrypted/plaintext, position/nodeinfo sighting enrichment, telemetry
discovery); both call sites are thin enough (wiring only, no decision logic)
that they don't need their own tests — matches how `flink/calibration_job.py`
already has no dedicated test since its logic lives in `common/calibration.py`.
(Both were later removed by [#16](#16-postprocessing-was-not-related-to-devices--resolved);
`flink/postprocessing_job.py` follows the same rule, its logic living in
`common/postprocessing/`.)

No new image — the lite decoder is a new `decode_consumer` service in the
existing `mesh-things/pipeline` image, alongside the MQTT bridge and
the writers (`compose/pipeline.yml`).

### Selecting a tier

**Done.** Compose profiles, not a second compose file — one service
inventory, no drift risk. Decode is now genuinely tier-exclusive:
`jobmanager`/`taskmanager`/`flink-job` carry `profiles: ["full"]`, the new
`decode_consumer` carries `profiles: ["lite"]`
(`test_decode_runtimes_are_mutually_exclusive_per_tier` in
`test_deploy_ports.py` guards against them ever sharing a profile — that
would double-decode every packet). Base infra, registry, `readings_api`, the
bridge/writer, and Caddy still carry no tag — always-on regardless of tier.

```bash
docker compose --profile full up -d                    # today's full stack: Flink decode + stream tier + S3 archive
docker compose --profile lite up -d                     # pure-python decode, no Flink/S3
docker compose --profile lite --profile quality up -d   # lite + batch quality (blueprints, completeness)
```

`env.example` ships `COMPOSE_PROFILES=lite` so a fresh `cp env.example .env
&& docker compose up -d` (no `--profile` flag) runs lite by default —
without it, once decode became tier-tagged, a bare `up -d` would start infra
with no decode step at all. Production deployments should set it to `full`
(or delete it and pass `--profile` explicitly) — noted as a `REQUIRES USER
ACTION` line in `env.example`, same treatment as the `COMPOSE_FILE` line
above it. This only affects fresh setups; existing `.env` files (gitignored)
don't get the line automatically.

`docker-compose.dev.yml` stays orthogonal — it constrains bindings and settings
regardless of tier (it's the one that opens things up for local dev; the base
file is prod-safe by default now, see `known-gaps.md`).

### Open decisions

1. ~~**Does `lite` include `readings_api`?**~~ **Resolved: yes.** It already
   carried no profile tag before this split (no change needed) — 148 MB, and
   it's what makes a demo demoable without querying InfluxDB directly.
2. ~~**Does `lite` include the batch quality tier?**~~ **Resolved: yes, off
   by default.** `quality_worker`/`quality_worker_beat` are dual-tagged
   `profiles: ["full", "quality"]` — `--profile lite --profile quality` opts
   in (Compose profiles OR, so `--profile full` is unaffected).
3. **Should `registry` advertise features the running tier can't deliver?**
   A `lite` deployment still exposes `/postprocessing-blueprints` and the alarm
   endpoints; alarms from the stream detectors simply never fire. Either gate
   the routes on a tier flag, or document that they are inert. Gating is
   honest but adds a config axis. Still open — an API-surface question, not
   a deployment one, out of scope for this pass.
4. ~~**Keep Kafka in `lite`?**~~ **Resolved: yes.** Considered dropping it
   (−684 MB) for a direct MQTT→decode→InfluxDB path, but it is the spine: the
   buffer, the replay mechanism, and how registry distributes gateway keys and
   reject lists to the decoder. Removing it would need a different
   key-distribution channel and a much larger divergence. Enforced
   structurally now, not just recommended - `compose/base.yml`'s services
   (including Kafka) carry no profile tag, so they can't be accidentally
   excluded from either tier.

### Risks to manage

- **Two decode runtimes drifting.** Mitigated by the shared pure function;
  `tests/test_decode.py` runs the fixtures through it directly (both runtimes
  are thin enough not to need their own).
- **CI must build and test both tiers.** This makes item 1 (CI doesn't run the
  root suite) a blocker rather than a nice-to-have.
- **Profile hygiene.** Addressed —
  `test_profiles_are_known_values`/`test_decode_runtimes_are_mutually_exclusive_per_tier`
  in `test_deploy_ports.py` catch a typo'd profile name or a service missing
  a tier tag.

## 1. CI doesn't run the root test suite — Resolved

`.github/workflows/pr-checks.yml` ran only the Django suites, so a PR could
break the S3 partitioning, the unit resolution, the loopback-only port bindings
or the shared-image wiring and still go green.

Fixed by the `root-tests` job, which runs `pytest -q --ignore=api` with no
services. Current counts across the three suites: **297 root, 273 registry, 39
readings**.

## 2. S3 writer small-file explosion — Resolved

`flush()` wrote one Parquet file per `(mesh_id, node_id)` per flush. Measured on
the live archive: **2986 objects for 11.7 MiB**, a mean object of 4 KB and 149
objects per device per day. At 4 KB a file is mostly Parquet footer, because a
sparse device contributes a row or two per flush. At 300 devices that is tens of
thousands of files a day, and it degrades into inode pressure, request cost and
slow scans.

**Fixed by dropping `node_id=` from the path and rolling each partition into one
object.** The key layout is now
`{prefix}/mesh_id=.../dt=.../hour=.../data.parquet`; `flush()` reads that hour's
object back, appends, deduplicates on
`(node_id, packet_id, rx_time, payload_kind)` and rewrites it. File count is
bounded at 24 per *mesh* per day instead of scaling with devices and flushes.

Measured on a synthetic mesh of 50 devices over a day (14 400 rows), the two
layouts compared as:

| | objects | on disk | one node, whole day | whole mesh |
|---|---|---|---|---|
| `node_id=` in the path | 1200 | 3544 KiB | 38.6 ms | 73.5 ms |
| `node_id` as a column | 24 | **87 KiB** | **3.4 ms** | **2.8 ms** |

Per-partition pruning does not pay for itself when the partitions are 4 KB: the
reader spends its time opening footers. Bigger files also let dictionary and RLE
encoding work on `channel_id`/`payload_kind`, which is where the 40x size drop
comes from. `node_id` stays a column, so DuckDB and pandas filter on it as an
ordinary predicate.

**What this gives up:** per-device credential scoping. `node_id` is no longer a
key prefix, so S3 policies can scope to a mesh and no further. Per-device access
has to be enforced above the archive, as the readings role already does.

Parquet cannot be appended to and S3 objects are immutable, so the rollup is a
rewrite, and it is per *hour* rather than per day so the rewrite stays bounded to
tens of KB. Because each flush is now a GET plus a full-object PUT,
`S3_WRITER__FLUSH_INTERVAL_S` defaults to 300 rather than 60. Older objects keep
their names and layout; nothing is rewritten.

## 2b. Archive stored partition keys as columns too — Resolved

`_flatten()` wrote `mesh_id` and `node_id` into every row while the same values
were already Hive path segments. A reader then has to merge the path's inferred
type with the column's, and they disagree:

```
pd.read_parquet(archive)   -> ArrowTypeError: Unable to merge: Field mesh_id
                              has incompatible types: string vs dictionary<string>
ds.dataset(partitioning="hive") -> ... Field node_id: int64 vs string
```

So **pandas and `pyarrow.dataset` could not read the archive at all**. DuckDB
resolves the duplication on its own, which is why this went unnoticed - every
worked example in [s3-access.md](s3-access.md) was DuckDB.

Fixed by keeping partition keys only in the path: `SCHEMA` no longer carries
`mesh_id`. `node_id` is now a plain column rather than a path key, so it does not
collide either. Objects from the older layout still carry both and still need
DuckDB or an explicit partitioning schema.

## 8. Decision pending: merge vs. separate vs. Postgres replication — Resolved

Settled as **one project, one image, two container roles**: `registry` owns the
catalog and writes, `readings` answers queries as a read-only Postgres role.
Neither full merge nor two services.

The requirement that decided it: read traffic must never occupy the processes
that answer registration. A single process fails that (one gunicorn pool);
two projects satisfied it but only by asking each other questions over HTTP.
Two roles from one codebase keep the process boundary and delete the HTTP.

Options weighed and rejected: merging into one process (fails the requirement);
keeping two services with a shared database (concedes schema independence,
which was the thing being protected, without collecting the simplification);
signed tokens (revocation becomes TTL-bound, reintroducing the staleness this
removes, and adds a token-exchange step for clients); logical replication and
pushing auth state over Kafka (both give the read tier a full local copy of
every owner, a worse blast radius than column grants, for more infrastructure).

What went with it: `mesh.owner_auth_revocations.v1`, its consumer container,
`publish_key_revoked`, the 60-second introspection cache and its `503` failure
mode, the cross-service schema fetch and merge, and one Dockerfile, settings
package and requirements file. The read tier now holds no mesh keys at all, and
a rotated key stops working on the next request rather than when a TTL expires.

See [architecture.md#roles-registry-and-readings](architecture.md#roles-registry-and-readings).

## 9. API surface: summary and metrics endpoints — Resolved

The three open items from the old `TODO.md`, all delivered:

- **Root summary endpoint.** `GET /` dropped the top-level `schema`/`docs`
  keys (the per-service entries already carry their own) and added a
  `metrics` link on the `management` entry. The root itself stays a static
  Caddyfile literal — it can't compute counts, so it links to the endpoint
  below instead of embedding data.
- **`GET /metrics`** (registry): `{devices, owners, meshes, active_gateways}` —
  plain `Device`/`Owner`/`Mesh` counts, public, no auth. See
  [api-reference.md#metrics](api-reference.md#metrics).
- **Per-device metrics** (readings): `GET /devices/{uuid}/metrics` and the
  mesh+node equivalent — `points_ingested`, `plausibility_ratio`,
  `alarms_by_detector`, and per-channel completeness, over a `start`/`stop`
  window. See [api-reference.md#per-device-metrics](api-reference.md#per-device-metrics).

Confirmed while building this: it's exactly the aggregation layer expected,
not new computation — `points_ingested` is `sum(observed)` from the existing
`quality` measurement and `plausibility_ratio` is derived from the existing
`alarms` measurement's `plausibility`-detector count. Both are consequently
empty/zero for a device the batch quality tier hasn't evaluated yet (no
blueprint, or `quality_worker` not running — e.g. `lite` without `--profile
quality`) — an accepted trade-off, not a bug.

## 10c. A failed batch is dropped, not retried — Resolved

Handling a sink failure by logging and "retrying next poll" without committing
the offset only helps across a restart or a rebalance. kafka-python advances the
*fetch position* on `poll()`, so within one process lifetime the next poll
returns new records and the failed batch is simply gone.

Confirmed directly against a live broker: poll one returns offsets 0-2, and
without a commit poll two returns 3-5. The batch is not redelivered.

**Fixed in `writer/influx_writer.py`.** The write and the commit are now
separate: on failure `_rewind()` seeks each partition back to the first offset
of the batch, so the next poll re-reads it. A batch that produced no points also
commits now, because those records *were* read and deliberately not persisted
(`point_builders.SKIP_PAYLOAD_KINDS`); previously the `if points:` guard held
their offsets back forever. Covered by
`server/tests/test_influx_writer_offsets.py`.

**Also fixed in `pipeline/decode_consumer.py`.** That one publishes per record
rather than per batch, so the rewind point is the record that failed, not the
start of the batch - rewinding further would republish records already on the
decoded topic. It also stops reading the partition at the failure, so a later
record cannot overtake the one being retried. Verified against a live broker:
six packets, one forced publish failure, all six delivered in order and none
duplicated. Covered by `server/tests/test_decode_consumer_offsets.py`.

`decode_consumer.py` also lost its module-level `from dotenv import load_dotenv`
(moved into the `--local` branch of `main()`, where it is the only user). That
matches the split `writer/influx_writer.py` and `writer/kafka_influx_writer.py`
already have, and is what makes the module importable in a test.

**Also fixed in all three registry consumers** (`consume_device_sightings`,
`consume_sensor_discovery`, `consume_quality_alarms`). These were the worst
variant: a catch-all per record followed by an unconditional commit, so a failed
record was never retried at all. A Postgres blip meant every sighting in that
window was silently lost and those devices never appeared in the registry.

All three ran byte-identical loops, so the loop now lives once in
`registry/consumer_loop.py` and each command supplies a `_handle_record`. The
fix needs a distinction the other two did not: only `OperationalError` and
`InterfaceError` rewind. `IntegrityError` is a `DatabaseError` too but a
permanent one, and rewinding onto it would block the partition forever, so it is
skipped like bad data. Covered by `registry/tests/test_consumer_loop.py`.

**Also fixed in `writer/s3_writer.py`**, which had both problems: its buffer was
cleared inside the `try`, so a failed flush re-accumulated on top of unflushed
records and grew unbounded while S3 was down. It now treats Kafka as the source
of truth - a failed flush drops the buffer and seeks every partition back to its
last commit, so nothing is held across retries and nothing is lost. The partition
rewrite is idempotent, so the replay that follows cannot duplicate rows.

Found while designing the forwarder in
[#1b](../plans/done/01b-federated-lite-sites.md#federated-deployment-lite-sites-forwarding-to-a-full-instance), which must not copy the idiom.

## 10d. readings required a registration row, not just mesh ownership — Resolved

`readings._require_owned_device` checks `(mesh_id, node_id) in request.user.devices`,
and `Owner.devices` comes from `Device` rows. So it needs a *registration row*,
not merely a mesh the caller owns. Verified: an owner querying an unregistered
node on **their own mesh** gets `404`. Only superusers get through.

[architecture.md](architecture.md) describes that same address as "the escape
hatch: it reaches devices with telemetry but no registration row", and
`examples/readings.py` repeats it. Both are wrong for every non-superuser.

It matters because everything else in the system scopes per mesh: `Mesh.owner` is
the only ownership FK, every registry write goes through
`_require_mesh_ownership`, and the S3 archive is partitioned by `mesh_id`.
Non-gateway devices are never registered by a human at all - sightings create
them - so there is a real window where telemetry exists on your mesh and you
cannot read it.

**Resolved by scoping per mesh.** `_require_owned_device` became
`_require_owned_mesh`, an indexed `Mesh.owner_id` check rather than a membership
test against every device the owner has. An owner now reads any node on a mesh
they own, registered or not, which is what the docs always claimed.

`Owner.devices` had exactly one caller and is gone. `Owner.devices_by_uuid`
stays: the `/readings/devices/{uuid}` form is addressed *by* a registration, so
it needs the row by definition.

known-gaps #11 is unaffected. That leak was a node number reused across
*different* meshes, and a mesh-level check still refuses the other mesh.

## 11. Add timeseries start_date and end_date — Resolved

Delivered by widening the existing `start`/`stop` rather than adding a second
pair of parameters. They now accept a relative duration (`-24h`), `now()`, a
date (`2026-09-01`) or a timestamp (`2026-09-01T13:45:00Z`), and the forms mix
freely, so `start=2026-09-01&stop=now()` is valid.

Separate `start_date`/`end_date` parameters were considered and dropped: they
would have needed a documented precedence rule for requests that sent both
pairs, for no gain over one pair that accepts both forms. Widening the shared
validator also gave `/metrics` and `latest`'s `lookback` absolute ranges at no
extra cost.

A date is read as midnight and a timestamp without an offset as UTC; offsets
are applied rather than ignored, so `2026-09-01T13:45:00+02:00` is 11:45 UTC.
Bounds are rebuilt from the parsed value instead of being passed through, which
keeps the Flux-injection guarantee that made the old validator duration-only.
Invalid calendar dates such as `2026-02-30` are rejected by the parse, not just
by the pattern.

## 12. Gateway ID and NodeID have different formats in Influx — Resolved

Gateway ID was stored in string format (!XXXX) while node ID is stored in numerical format
in influx tags.

Both are the same thing, a Meshtastic node number, so the decoded message now
carries the number and `!aabbccdd` stays on the wire. `common/node_ids.py`
holds the conversion and `common/codec.py::build_decoded_message` applies it,
which puts the change at the one boundary every sink reads from, so the Influx
tag and the S3 column moved together.

The cost of the old split was not cosmetic: gateway `!19ba4462` and node
`431637602` are one device, and no query could tell. `r.node_id ==
r.gateway_id` now identifies self-relayed readings, verified against live data.

Converting `node_id` to the string form was the other option and was rejected.
`node_id` is what the readings API filters on and what `Device.device_id`
stores as an integer, so it would have rippled through the scoping rule, the
Flux queries and the registry for the same result.

Parsing only accepts the `!`-prefixed form. A bare `"431637602"` is valid hex
*and* valid decimal, 17 bytes apart in value, so it returns None rather than
resolving the ambiguity by assumption.

Deploying it needed the Flink cluster recreated, not just the job resubmitted:
the taskmanager container still held the image it was created from, so the new
job graph ran against an old `common/` and failed on a signature that had
changed since (`decode_packet() got an unexpected keyword argument 'on_drop'`).
Decoded output stopped while the job sat in RUNNING. Worth remembering that a
job restart alone does not pick up changes to `common/`.

The resubmit also replayed history. `decode_job.py` reads from
`KafkaOffsetsInitializer.earliest()`, so a job with no savepoint re-decodes the
whole raw topic. Because `gateway_id` is a tag and its value had just changed,
the replayed points landed in new series instead of overwriting, leaving every
historical reading stored twice - once per spelling. The readings API filters
on `mesh_id`/`node_id` and never on `gateway_id`, so those queries returned
each point twice, and windowed aggregation computed per series returned two
results. The old-spelling points were deleted after checking they were pure
duplicates: the numeric series starts a day earlier than the string one, and
every sampled old point had a twin at the same timestamp with the same value.

This was a one-off caused by the tag value changing under a replay. A future
replay rewrites the same series keys and is an idempotent overwrite.

Parquet files written before the change keep the old spelling. The S3 schema is
inferred per batch, so a scan crossing the change has to cast the column.

## 13. Not all MQTT messages reach the bridge — Resolved

**Cause: the MQTT client id was derived from the container hostname**, which
under Docker is the container id and therefore changed on every recreate:

```python
self.client_id = f'{client_id_prefix}-{socket.gethostname()}'   # bridge/mqtt_handler.py
```

With `MQTT_BRIDGE__CLEAN_SESSION=false` the broker keeps a *persistent*
session per client id indefinitely, and `$share/kafka-bridge/test/#` splits
each message across every member of the group. So every `docker compose up -d`
that recreated the bridge left one more permanently-offline member in the
group, each taking its round-robin share and queueing it for a client that
never came back. Confirmed broker-side: 11+ stale subscribers.

Measured rather than inferred. In one three-minute window a plain
(non-shared) subscriber received 2 messages and the bridge received **0**; in
a five-minute window a fresh single-member shared group received 7 while the
bridge captured 4. The share fluctuates, but the loss is continuous, and
nothing logged anything - the bridge was healthy the whole time.

**Fix**: `_client_id()` in `bridge/mqtt_handler.py` no longer touches the
hostname. It uses `MQTT_BRIDGE__CLIENT_ID` when set, otherwise the bare
prefix, so a reconnect resumes the one existing session instead of stranding
another. `clean_session=false` is kept deliberately: with a stable id it now
does what it was meant to, queueing messages while the bridge restarts rather
than dropping them.

One fixed id is only correct for a single replica, since MQTT permits one
connection per id - two replicas sharing one would disconnect each other in a
loop. A process cannot see its siblings, so that invariant is asserted against
the compose files by `test_deploy_ports.py` rather than guessed at runtime.
`tests/test_mqtt_client_id.py` pins all of it, including that a blank
`MQTT_BRIDGE__CLIENT_ID=` counts as unset.

**Still losing messages until the broker is cleaned up.** The code fix stops
new sessions being stranded; it cannot reclaim the ones already registered.
Measured right after deploying it: the broker published 8 in five minutes and
the bridge captured 4, the same ~50% as before. That is the expected result -
the 11+ stale members are still in the group taking their share - and it is
the reason this entry is not closed. Ingestion recovers when those sessions
are deleted broker-side.

Renaming `MQTT_BRIDGE__SHARED_GROUP` restores full delivery immediately
(verified: a fresh single-member group received 7 in the window the bridge
got 4) but leaves the stale sessions accumulating queued QoS-1 messages
forever, so it is a stopgap rather than a fix. The stale sessions were
deleted broker-side.

### Scaling the group

The behaviour that caused this is also the behaviour worth keeping, and it was
verified directly against the broker: a member that disconnects has its share
of the messages **queued and redelivered on reconnect**. That is what makes a
restart lossless, so each member owns a fixed client id for good.

The dangerous half of it is now bounded. The bridge speaks **MQTT 5** with
`clean_start=False` and a **session expiry interval**
(`MQTT_BRIDGE__SESSION_EXPIRY`, default 3600s), rather than 3.1.1's
`clean_session=False`, under which a session simply never expired. Both halves
were verified against the broker:

| | Result |
|---|---|
| Reconnect within the interval | 5/5 queued messages delivered |
| Reconnect after it | 0/3 - session and queue discarded |

So a member that never returns now costs at most one interval of its share
instead of swallowing it forever, and the group redistributes to whoever is
left. Tuning it trades restart-resilience against how long a dead member keeps
taking a share. One caveat worth knowing: when the *only* member expires the
group has no subscribers at all and messages are dropped rather than queued,
so a single-member deployment wants this generous.

Pool members are named services, not `deploy.replicas`: Compose gives replicas
no stable per-replica identity, which is exactly what a session needs.
`mqtt_kafka_bridge` runs by default as `mesh-bridge-1`; `mqtt_kafka_bridge_2`
and `_3` come up with `--profile bridge-pool`.

**Scaling down still wants a deliberate step**, though it is no longer
permanent damage: an abandoned session takes its share until the expiry
interval passes. Retire it immediately instead of waiting:

```bash
docker compose exec mqtt_kafka_bridge mqtt_kafka_bridge --retire-session mesh-bridge-3
```

**A local stack is a member of the group too**, if it points at the same
broker. A distinct client id is not enough on its own: that only stops the two
disconnecting each other, and the group is what decides who gets which message,
so a dev bridge left on `kafka-bridge` takes a share of production's traffic
rather than duplicating it. `docker-compose.dev.yml` sets
`MQTT_BRIDGE__INSTANCE_SUFFIX=dev`, which is appended to both the client id and
the group, so the two can never be separated by halves. Renaming the group does
not retire the session that held the old subscription, so the same deliberate
step above applies when a dev stack moves off a group it was sharing.

`test_deploy_ports.py` guards the rest: every member declares a client id, no
two share one, none uses `deploy.replicas`, and the dev overlay sets the
suffix on every member.

---

## 15. The published OpenAPI schema carried no parameters or response shapes — Resolved

`GET :8090/schema` listed every route and its prose description, but nothing
else: `components` held only `securitySchemes`, every operation reported
`"200": {"description": "No response body"}`, and the only parameters declared
were the ones drf-spectacular reads off the URL pattern. The query parameters the
view docstrings describe in their `Args:` sections did not exist as far as a
generated client or the Swagger "Try it out" form was concerned.

The cause was that these are plain `APIView`s reading `request.query_params`
directly, with no serializer for drf-spectacular to introspect.

Fixed by declaring every operation explicitly with `@extend_schema` in
`registry/views.py` and `readings/views.py` - `parameters` for the query
parameters, `request` for the input serializer, `responses` for the output. The
bodies the views build by hand gained schema-only serializers in
`registry/serializers.py` (`OwnerProfileSerializer`, `OwnerDevicesSerializer`,
`DetailSerializer`, `AlgorithmSerializer`).

The document went from 27.8 KB to 72.9 KB, `components.schemas` from 0 to 40, and
`manage.py spectacular` now reports 0 warnings and 0 errors - the one remaining
warning, an `operationId` collision between `GET /owners` and `GET /owners/{id}`,
was fixed by naming the list operation `owners_list`.

This is a declaration kept in parallel with the code, so a query parameter added
to a view without a matching `parameters` entry will silently not appear.

## Evaluated and deliberately not doing

Recorded so they don't get re-litigated from scratch.

**Merging the four Flink job graphs into one.** Would save ~800 MB (four
PyFlink Python workers collapse to one) and reduce slots 4 → 1. Costs
independent redeploy: any change would restart all four pipelines, and
savepoints become all-or-nothing. At ~1 msg/s the memory is not worth losing
per-job deployment. Reconsider if item 7 turns out to be a real leak.

**Merging the three registry consumers into one process.** Would remove two
containers and ~115 MiB. They currently fail independently; merged, one crash
stops all three and a poison message in one topic stalls the others. 115 MiB out
of ~6 GB is a poor price for that.

**Dropping `mailhog` from production entirely.** Originally evaluated and
rejected in favor of just rebinding its ports to loopback (defense in depth,
since the override model couldn't *remove* a service, only patch it) - since
superseded: the base/dev flip (see `known-gaps.md`) made the base file
prod-safe by default, and `mailhog` doesn't exist in it at all anymore, only
in `docker-compose.dev.yml`. `settings.prod` still independently refuses to
use it as a mail transport even if it were somehow running, unchanged.

**Dropping `kafbat-ui` from production.** Done 2026-10-03: it moved to its own
`kafka-ui` profile. The first production host has 7.6 GB of RAM and no swap, and
the UI held about 360 MB while idle, so it now runs only when someone starts it. (`docker-compose.dev.yml`
republishes its port to `0.0.0.0` for local dev convenience; the base file
keeps it loopback-bound like every other admin UI.)

**Streaming CSV exports from readings.** Evaluated 2026-09-28 against the archive zip,
which streams fine: copying Parquet costs nothing, and gthread workers with the DB
connection released keep a slow download from blocking anything. CSV is different
work, querying InfluxDB, pivoting and deflating, CPU-bound under the GIL in a
web worker, and a failure halfway wastes it all. Exports become background jobs
instead, and the zip stream is folded into them. See
[#19](../plans/done/19-exports.md#exports-csv-and-parquet-downloads-as-background-jobs).

**Removing the `/management` and `/data` gateway prefixes.** ~~Rejected~~ —
**done**, as part of #8. The rejection rested on `/health`, `/docs` and
`/schema` colliding between two services, and on the proxy needing readings'
route table. Merging into one project removed both: there is one `/schema` and
one `/docs`, per-role health probes are internal to their containers, and the
read half owns a single `/readings/` segment, so the proxy routes on one line
rather than a route table. Paths are now forwarded unchanged, which also
deleted the schema path-rewriting and the per-request `servers` ordering. See
[architecture.md#reverse-proxy](architecture.md#reverse-proxy).

---

## Accepted, no action

**Devices with telemetry but no registration row are not listable** —
known-gaps #13. They remain addressable via
`/readings/meshes/{mesh_id}/nodes/{node_id}/...` if you know the pair. Of 24
`(mesh_id, node_id)` pairs observed, 21 were old test data or deleted
registrations. If a real need reappears, the honest fix is a registry
"unregistered devices" report reconciling the registry against observed
telemetry — not a second device list in readings.

## 15b. Alarms fired on channels that are meant to be flat — Resolved

Barometric pressure is meant to be stable and wind is often calm, so both tripped
`flat_value` continuously. The only lever was deleting the catalog's
`valid_min`/`valid_max`, which turns off a different detector.

Investigating first changed the shape of the work: three of the four detectors
were already opt-in by accident, and only `flat_value` fired unconditionally.
`plausibility` needed curated bounds, `absence` needed a publish interval and
`completeness` a reading interval - three accidental switches and one missing one.

Replaced with one explicit rule. `payload_kind`-style resolution, mirroring how a
device's `reading_interval_seconds` already overrides the variant default:

    enabled = measurement.enabled_detectors        # null inherits, [] silences
              if not None else
              variant_measurement.default_enabled_detectors

`TelemetryVariantMeasurement.default_enabled_detectors` is the shared,
superuser-curated default; `Measurement.enabled_detectors` is the mesh owner's
per-device override, set through the new `PUT /devices/{uuid}/measurements/{id}`.
`absence` has no channel, so it hangs off `Device.alarms_enabled` instead of
silently switching on when someone sets an interval for an unrelated reason.

The stream jobs learn about it through a third key shape on
`mesh.quality_config.v1`, `<mesh_id>:<device_id>:<channel>`, which cannot be
confused with the channel key (a dot, no colon) or the device key (one colon).

Migration `0003_alarm_opt_in` is additive and every existing row resolves to no
detectors, so **all alarms went quiet until enabled** - the behaviour the request
asked for. Verified live: nothing alarmed, then enabling `flat_value` on one
wind-speed channel produced six alarms for that channel alone while the equally
flat temperature, humidity, pressure and wind-direction channels stayed silent.

`completeness` metrics are still computed and written whichever way the switch is
set; only the alarm is suppressed, so the figures stay on `/readings/.../quality`.

## 16. Postprocessing was not related to devices — Resolved

A review of the blueprint work found the gap was in the model, not in any one
bug. The only link between a blueprint and a device was a nullable
`Device.postprocessing_blueprint` FK, so everything a device actually needs had
nowhere to live:

- **Calibration sat on the shared recipe.** `ec_sensor_ppb`'s `sensitivity` and
  zero offsets belong to one physical electrode, but lived in the blueprint's
  step `params`. Sharing a blueprint gave every device the same calibration;
  not sharing it meant one blueprint per device.
- **Inputs were bound to channel names on the recipe,** unchecked against the
  device, so a mismatch surfaced only as a `no_data` Celery result nobody read,
  and two devices wired differently could not share a blueprint.
- **One blueprint per device,** and derived `Measurement` rows with no link to
  what produced them, left behind after detaching.
- **Detectors on derived channels were accepted and silently ignored:** derived
  values were written straight to InfluxDB and never reached the stream tier.
- **The existing Flink `calibration_job.py` was dead code** - nothing published
  to its config topic, and it overwrote raw values on a topic only pattern
  detection read, so the stored data and the checked data disagreed.

The requirement was postprocessing that reads from Kafka and writes back to
Kafka, with the same features as every other measurement, and a place to add
calibration parameters for any algorithm.

### What was built

Delivered in five commits, each stageable on its own:

1. **Algorithms declare their parameters** with `Param`, `calibration=True`
   marking the per-sensor ones. Defaults come from the signature and the
   declaration is checked against it at import time. `offset_scale` and
   `lookup_table` became ordinary algorithms, and `common/calibration.py` went.
   A pure engine, `common/postprocessing/` (resolved plans, a streaming join,
   `apply`), is shared by the stream job and backfills.
2. **Registry models the device relationship:** immutable `BlueprintVersion`s
   with input slots and keyed steps; `DevicePostprocessing` with input bindings
   to the device's own measurements, `output_prefix`, tolerance and an enable
   switch; append-only `StepCalibration` history with `valid_from`; and
   `Measurement.produced_by`, so derived channels are created, owned and
   removed with their postprocessing. Plans are published per device on the
   compacted `mesh.postprocessing_config.v1`, rolling the API change back if
   that fails.
3. **`postprocessing_job.py` replaced `calibration_job.py`,** writing to
   `mesh.telemetry.derived.v1` in the decoded envelope shape. Pattern detection
   reads decoded and derived together.
4. **Writers, the archive and completeness** handle derived channels, a derived
   channel being held to its slowest input's reading interval.
5. **Backfills** replaced the scheduled `run_blueprint`: requested through the
   API, claimed by the worker, run through the same engine with the calibration
   in force at each reading, and published to the derived topic.

### Decisions taken along the way

- **Blueprint versions are immutable** rather than edited live and revalidated.
  Devices stay on their version until moved; calibration carries over for steps
  with the same key and algorithm.
- **Postprocessings may read each other's output,** with registry refusing
  cycles and publishing a device's plans in dependency order.
- **Blueprints can be public.** Deleting an owner always succeeds: blueprints
  other owners' devices still use are kept with a null owner, editable by
  superusers only.
- **Raw values are never modified.** Calibration always produces a new derived
  channel, so raw data stays auditable and can be reprocessed.
- **Backfilled events carry `"backfill": true` and pattern detection skips
  them,** since alarming now on long-past values would report them as new faults.
- **The live sources of both jobs start at the end of a topic they have never
  read.** Replaying retained history on first start would have emailed alarms
  for all of it.

### What the implementation turned up

- **The first streaming join dropped the start of batched history.** Pruning
  relative to the newest sample discarded a batch's early readings whenever one
  channel's history arrived ahead of the others. It now assumes only that each
  channel's own samples arrive in order, with a test skewing channels by 10 hours.
- **PyFlink's `committed_offsets()` fails at submit time** in this Flink
  version: the Python side passes the Kafka `OffsetResetStrategy` shaded into
  the SQL connector jar, which the connector's Java method does not accept.
  `common/flink_kafka.py` builds the initializer through the JVM gateway with
  the unshaded class.
- **Derived events have no `packet_id`,** which the Influx point builder
  required and the S3 archive used to deduplicate rows. Derived events got
  their own point builder, and the archive a `postprocessing_id` column in its
  row key.
- **A reading heard through two gateways is two series in InfluxDB,** so the
  backfill's reader merges them and keeps each timestamp once.

Verified live at each step against Kafka, InfluxDB, the archive and the readings
API, using throwaway meshes: a decoded reading became a calibrated derived value
and a `range` alarm on it; three hours of stored history (twelve readings) were
backfilled with the calibration applied and no alarms raised.

This also settles half of [#6](../plans/06-derived-catalog-types.md): derived channels now get their unit
when the blueprint is attached, so they are no longer catalogued unlabelled.
Their `MeasurementType` rows still outlive the last device producing them.

## 17. Both API containers received every secret in `.env` — Resolved

`readings_api` loaded the whole `.env`, so the read tier, meant to hold only a read-only
Postgres role, also held the MinIO root credential, `INFLUX__TOKEN`,
`POSTGRES_PASSWORD`, `REGISTRY__SECRET_KEY` and the EMQX keys. It now gets an explicit
`environment:` list in `compose/api.yml`: its own `READINGS__*`, the InfluxDB
connection, `GATEWAY__PUBLIC_URL` and the archive's read-only identity.
`test_deploy_ports.py` fails if it gets `env_file` back or any `S3_WRITER__`,
`REGISTRY__`, `POSTGRES_` or `MQTT_` variable. Done with the archive sink (pending #2c),
which gives readings an S3 credential on purpose. The registry services still load the
whole file: they use most of it.

## 18. `s3-access.md` described the archive schema before derived rows — Resolved

It listed the columns and dedupe key from before `postprocessing_id`. Rewritten with the
archive sink: opt-in devices, the current schema and key, who holds which credential,
reading through the API, and bundled MinIO versus external S3.

## 3. A jobmanager restart dropped every Flink job — Resolved

Real high availability (ZooKeeper or Kubernetes) is out of proportion for one host,
so the goal became recovering on its own instead. Two changes: checkpoints are kept
on a volume shared by every Flink container and `submit-job.sh` resumes from the
newest one (the checkpoint storage fix), and a `flink-watchdog` service runs that
same idempotent script for every job each minute. The one-shot submitters stay
one-shot, since restarting them is what used to produce duplicate jobs; the
watchdog starts only after they have finished and restarts with the host, which
also covers reboots, where the exited submitters never ran again.

Tested by restarting `jobmanager`: all four jobs were back within 90 seconds,
each from its newest checkpoint. The first attempt also killed the taskmanager
with `OutOfMemoryError: Cannot reserve ... direct buffer memory`. PyFlink's gRPC
channel to the Python workers allocates direct memory, and the taskmanager had
none budgeted for tasks, so restoring every job at once exceeded the limit.
`taskmanager.memory.task.off-heap.size: 128m` fixed it, with the process size
raised from 1280m to 1536m so heap and managed memory kept their sizes. The same
restart on the previous Java 11 image and memory settings failed the same way, so
this was not caused by the Java 17 change in #20.

## 4. Redeploying a job with state was a manual savepoint dance — Resolved

`scripts/redeploy-flink.sh` rebuilds the image, stops the watchdog, stops each
job with a savepoint, resubmits it so it resumes from that savepoint, checks for
exactly one live copy, and starts the watchdog again. With no arguments it also
recreates jobmanager and taskmanager, which a `common/` change needs. Submissions
now prune older savepoints as well as old checkpoint runs.

## 5. The `alarms` topic had no retention policy — Resolved

`kafka-topics-init` sets `retention.ms` to 3 days and `retention.bytes` to 512 MB
on `mesh.telemetry.alarms.v1`, applied with `kafka-configs --alter` so existing
topics pick it up. Alarms are persisted to InfluxDB, so the topic is only a
transport buffer. The volume itself comes from the detector raising an alarm on
every reading, which is #5b.

## 20. The Flink image was 2.9 GB and ran on Java 11 — Resolved

`flink/Dockerfile` installed `default-jdk` (OpenJDK 11 with its GUI dependencies)
and `python3-dev` (gcc), and pointed `JAVA_HOME` at that JDK, so the cluster ran
on 11 despite the `java17` base tag. Nothing in the image is compiled: `pemja`
and every other dependency ship as wheels. Both are gone, and the base image's
Java 17 runs Flink. The requirements are now installed before `COPY . .` and
without pip's cache, so a code change no longer reinstalls PyFlink and leaves a
3 GB image behind. The image is 1.59 GB with identical Python packages, a rebuild
after a source change takes about 5 seconds, and every job restored its Java 11
checkpoints on Java 17.


## 10. Superusers could not see `psk_b64` and `admin_keys_b64` — Resolved

Both fields were hidden from every caller except the resource's owner, superusers
included. The values are stored in plain text in Postgres and, for the PSK, on
`mesh.keys.v1`, so hiding them from superusers protected nothing. The mesh and
device serializers now show them to superusers as well, and the Django admin shows
both read-only instead of excluding them, since a key changed there would not reach
the pipeline.

## 5b. Pattern detection raised an alarm on every reading — Resolved

`flat_value` and `range` re-evaluated each observation and yielded an alarm
whenever the condition held, so one device with a flat wind vane and a
temperature above its range put about 1.9M alarms on the topic locally. The job
now keeps the reading time of each detector's last alarm in keyed state and
raises one alarm at onset, then at most one per
`PATTERN_DETECTION__ALARM_REPEAT_HOURS` (default 1) while the condition holds.
The cap is hard, so values flapping at a bound do not re-alarm, and it follows
reading time, so a backlog replay no longer bursts. There is no "cleared" event.
Consumers are unchanged; a summary's count now means roughly hours active. On
the local stack the device went from two alarms a minute to one of each at
onset.

## 21. Alarms fired too quickly — Resolved

`range` fired on one reading out of bounds, `flat_value` after as few as 5 identical
readings, `absence` every 3 publish intervals while a device stayed silent, and
`completeness` re-alarmed one gap 24 times. Each detector now alarms on a sustained
condition, once:

- `range` needs `PATTERN_DETECTION__RANGE_READINGS` (default 3, 2 on devices reading
  every 30 min or slower) consecutive readings out of bounds.
- `flat_value` needs the same value for `PATTERN_DETECTION__FLAT_VALUE_HOURS`
  (default 12), across at least 3 readings.
- `absence` alarms once per silence, and a later silence only after 3X publish
  intervals. Timers due while Flink was down restart their countdown instead of firing.
- `completeness` alarms each gap once, remembered in Redis, and a low ratio at most
  once per 24 h.

Hourly re-raises are marked `repeat` and replayed bursts `replay`; neither is emailed on
its own. `absence` is emailed straight away, at most once per device per day. Plan in
[plans/done/21-alarm-triggers.md](../plans/done/21-alarm-triggers.md).

## 22. Alarms were stored forever, one point each — Resolved

Every alarm was a point in the readings bucket, kept as long as the readings, and
`range_ratio` assumed one `range` alarm per bad reading, which #21 broke. Raw alarms
now go to their own `alarms` bucket with a 30-day retention, created by the one-shot
`influx_init` service. A daily quality-worker task keeps long-term counts per device,
channel and detector: hours the condition was active and how many new conditions
started. `range_ratio` is now 1 minus the share of reported hours with a `range` alarm.
The readings API answers ranges within the last 30 days from the raw alarms and older
ones from the daily counts. A one-off command turned existing alarms into daily counts
and removed them from the readings bucket. Plan in
[plans/done/22-alarm-storage.md](../plans/done/22-alarm-storage.md).

## 23. Gateways had to be registered by hand — Resolved

A mesh only ingested once its owner registered a gateway by its node number. A mesh with
`discover_gateways` on now registers its own: the bridge sends paced samples of
unregistered gateways' packets to `mesh.gateway_candidates.v1`, and
`registry_gateway_discovery` registers the gateway, with `discovered_at` set, once a
sample fully decodes with exactly one mesh's source, channel and PSK. Ambiguous matches,
gateways already allowed elsewhere and rejected rows are skipped, and only an operator
may use discovery with a well-known PSK. Merged in PR #48 on 2026-10-03; how it works is
in [architecture.md#gateway-discovery](architecture.md#gateway-discovery). Plan in
[plans/done/23-gateway-discovery.md](../plans/done/23-gateway-discovery.md).

## 6. Derived catalog types outlived the devices producing them — Resolved

A `computed:derived` `MeasurementType` stayed after the last device producing it was
detached or deleted, and kept its unit, so a later attach declaring another unit under
the same field name was refused. A `post_delete` handler on `Measurement` now drops the
type with its last channel, so cascades from device, mesh and owner deletion are covered
as well as a detach. A type a telemetry variant declares in the catalog is kept. Plan in
[plans/done/06-derived-catalog-types.md](../plans/done/06-derived-catalog-types.md).

## 14. `/docs` "Try it out" failed cross-origin — Resolved

The last open item of the API inconsistencies (#14), "can't auth for the readings API
through the docs", was not an auth bug. `/docs` on registry's published port sends its
requests to the schema's server, the gateway URL, and neither `*__CORS_ORIGINS` listed
`:8090`, so the browser blocked the preflight before auth was reached. The dev overlay
now appends `http://localhost:$REGISTRY__PORT` to both allowlists; through the gateway
the form was already same-origin. Plans in
[plans/done/14-api-inconsistencies.md](../plans/done/14-api-inconsistencies.md) and
[plans/done/14-api-docs-try-it-out.md](../plans/done/14-api-docs-try-it-out.md).

## 19. Owners could not export their readings — Resolved

Deleting a mesh or moving it off a source told owners to export their readings first,
but only operators could reach the archive, through a streamed zip. Exports are now
background jobs on readings: CSV from InfluxDB for every device (a file per measurement
and day, plus units), or the archive's Parquet for operators. A worker builds the zip
into a multipart upload under the bucket's `exports/` prefix with its own write-only
identity, emails the owner, and the file and its presigned link last a day. One export
per owner runs at a time, jobs live in Redis so readings keeps its read-only Postgres
role, and a heartbeat lets any worker fail a dead one. The streamed `/zip` route was
retired, and readings went back to sync workers. Plan in
[plans/done/19-exports.md](../plans/done/19-exports.md).

## 1b. Federation between instances — Dropped

Designed 2026-09-28 as a lite site forwarding raw `ServiceEnvelope` bytes to a full
instance, with a `Site` model, a `site_id` tag through the pipeline and an HTTP
handshake that registered the mesh's PSK and gateways remotely. A second pass the
next day forwarded decoded JSON instead, so the receiver would hold no key, but that
needed a new ingest path on the receiver, a mesh without a PSK, a way to stop derived
readings and alarms being counted twice, and loop protection between instances.

Neither was worth it. A full instance already bridges any reachable broker as a
[source](../plans/done/01a-mqtt-sources.md), and third parties get readings through pull
MQTT [sinks](../plans/02c-sinks.md#decisions-2026-09-29). The one case left, a lite
site whose broker is not reachable from the internet, is solved by that broker
bridging its Meshtastic topics out to the full instance's default broker, with the
mesh and gateways registered there like any owner's. The per-mesh device uniqueness
it required landed with #1a and stays. The design is kept in
[plans/done/01b](../plans/done/01b-federated-lite-sites.md).

## 1a. Every packet came from one broker and one topic — Resolved

A source is a remote MQTT broker and topic filter that registry bridges into this
instance through an EMQX connector, source and republish rule. A mesh attached to a
source works like one on the default broker, and the bridge drops a gateway arriving
through any other source. It brought the `operator` role and operator requests, terms
per account, mesh and source with `REGISTRY__TERMS_ENFORCED` to turn them off, and the
data lifecycle (lapses, grace period, deletion from InfluxDB and the archive). Merged
in PR #17, with status alerts in PR #38 and the terms schema fix in #37. Bandwidth
filtering was shelved on 2026-10-08: production's only source averages about 0.5 msg/s.
Sinks continued as #2c. How it works is in
[architecture.md#mqtt-sources](architecture.md#mqtt-sources). Plan in
[plans/done/01a-mqtt-sources.md](../plans/done/01a-mqtt-sources.md).

## 25. Mesh network metrics needed Malla, which is slow — Resolved

Malla stores every raw packet in SQLite and computes every view on read. Here the
figures are aggregated while packets stream through Kafka: every packet a registered
gateway hears goes to `mesh.traffic.v1`, `mesh_stats_writer` counts it into a
`mesh_stats` bucket kept 30 days, and every read touches pre-aggregated rows only.
Traceroutes and RF links live in Postgres (`registry_topology_consumer`), kept 30
days. Readings serves traffic, busiest nodes, gateway share and overlap, hops, signal,
relays and packet types per node; registry serves links and traceroutes. The console
shows them on a mesh's Traffic and Topology tabs. Merged in PR #63 on 2026-10-11, with
a traceroute fix in PR #64. Line of sight is left as #28. Plan in
[plans/done/25-mesh-network-metrics.md](../plans/done/25-mesh-network-metrics.md).
