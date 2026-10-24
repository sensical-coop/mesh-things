# Debugging

## Logs

```bash
docker logs <container-name> --tail 50
docker logs -f <container-name>            # follow
```

Container names (not always the same as the compose service name — check
[architecture.md](architecture.md#services-and-ports)): `mqtt-kafka-bridge` isn't fixed
when scaled (use `docker ps` to find the generated names), `influxdb-writer`,
`s3-writer`, `registry-api`, `readings-api`, `kafka`, `jobmanager`, `taskmanager`,
`flink-job`, `postgres`, `minio`.

## Health endpoints

Every long-running Python service exposes `GET /health`:

```bash
curl http://localhost:19090/health   # influxdb_writer
curl http://localhost:19091/health   # s3_writer
curl http://localhost:8090/health    # registry_api
curl http://localhost:8091/health    # readings_api
```

`mqtt_kafka_bridge`'s health port isn't published to the host when scaled (see
`docker-compose.yml` — it uses `expose:` not `ports:` so multiple replicas don't
conflict on the same host port); check it via `docker exec <container> curl -f
http://localhost:9090/health` instead.

## Kafka topics

See [architecture.md#kafka-topics](architecture.md#kafka-topics) for what each topic
carries and who produces/consumes it. To look at raw messages, `kafka`'s image ships
the standard CLI tools — always `docker exec` into the `kafka` container itself and use
`kafka:29092`, not `localhost:29092`:

```bash
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:29092 --list

docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka:29092 --topic mesh.telemetry.decoded.v1 \
  --from-beginning --timeout-ms 8000
```

**Always pass `--timeout-ms`** on a `--from-beginning` read — without it the consumer
just blocks forever waiting for new messages instead of exiting once it hits the end,
which looks like a hang in a script or an agent shell. It exits with a
`TimeoutException` and a "Processed a total of N messages" line once the timeout
fires; that's the expected way to stop, not an error to chase.

**`--bootstrap-server localhost:29092` fails, even run from inside the `kafka`
container itself** — confirmed via `Connection to node -1 (localhost/127.0.0.1:29092)
could not be established`. The `PLAINTEXT` listener (`KAFKA_LISTENERS`) is bound to the
hostname `kafka`, not `0.0.0.0` or `127.0.0.1`, so nothing is actually listening on
`localhost:29092` inside the container even though the port is mapped — only the
`kafka:29092` address (resolved via the compose network's DNS) reaches it. The
`PLAINTEXT_HOST` listener on `9092` is the one meant for host-side tools.

**Filtering for one gateway/device while eyeballing JSON** — pipe through `grep` or
`python3 -m json.tool` per line; there's no server-side filter in the console consumer:

```bash
docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka:29092 --topic mesh.telemetry.decoded.v1 \
  --from-beginning --timeout-ms 8000 | grep '"gateway_id": "!0f8625c7"'
```

**Checking the actual registered-gateway state Flink is broadcasting** — `mesh.keys.v1`
is compacted, so a full `--from-beginning` read (add `--property print.key=true` to see
the `gateway_id` key alongside each record) reconstructs the current key-by-key state:
the *last* record per key is what's live in `GATEWAY_KEY_STATE`, an `"op": "delete"`
record means that `gateway_id` currently decodes nothing (see
[architecture.md#registered-gateways-only-gate](architecture.md#registered-gateways-only-gate)
and the "mesh goes dark" gotcha below — this is the most direct way to confirm what
Flink believes is registered, independent of what Postgres/the API currently say).

**Checking which nodes are currently rejected** — same idea, against the other
compacted topic: `mesh.node_rejections.v1` reconstructs `NODE_REJECTED_STATE` the same
way, keyed by `"mesh_id:device_id"` rather than `gateway_id`. A key with no record at
all (or whose last record is `"op": "delete"`) means that node is currently allowed —
absence means allowed, matching the default-open model (see
[architecture.md#device-registration-and-the-is_allowed-gate](architecture.md#device-registration-and-the-is_allowed-gate)):

```bash
docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka:29092 --topic mesh.node_rejections.v1 \
  --from-beginning --timeout-ms 8000 --property print.key=true
```

**Consumer lag, to check whether Flink is actually keeping up** (group IDs are set via
`.set_group_id()` in each job file — `flink-decode-group`/`flink-decode-keys-group` for
`decode_job.py`, `flink-postprocessing-group`/`flink-postprocessing-config-group` for
`postprocessing_job.py`, `flink-pattern-detection-group`/`flink-pattern-detection-quality-config-group`
for `pattern_detection_job.py`):

```bash
docker exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka:29092 --describe --group flink-decode-group
```

`LAG` should be near zero for a healthy job. **"Consumer group has no active members"
in the output does not mean the job is dead** — Flink's Kafka source manages partition
assignment itself (via checkpointed state) rather than through the standard
group-coordinator rebalance protocol, so it never shows up as an "active member" even
while healthy; it still commits offsets to the group for this command to read. Trust
`LAG`/`CURRENT-OFFSET` moving forward over time, not the active-member count.

## Flink jobs

**Dashboard**: http://localhost:8081 — job graph, running/failed tasks, exceptions,
checkpoint history.

**REST API** (useful for scripting/checking status without the UI):

```bash
curl -s http://localhost:8081/jobs/overview | python3 -m json.tool          # all jobs
curl -s http://localhost:8081/jobs/<jid> | python3 -m json.tool             # one job, per-vertex detail
curl -s http://localhost:8081/jobs/<jid>/exceptions | python3 -m json.tool  # failure history, no log-digging needed
```

**A job silently isn't processing anything**: check `state` is `RUNNING` and
`tasks.running` equals `tasks.total` in the overview above. If it's stuck at
`CREATED`/`SCHEDULED`, check `taskmanager` logs — it likely can't register with
`jobmanager` (see the DNS/networking gotcha below).

**Logs are split across three containers, and it's easy to grep the wrong one**:

- `docker logs flink-job` — only the *submission* client's output (config loading, "Job
  has been submitted with JobID ..."). Confirms the job was accepted, nothing more. A
  stale, long-past-startup snapshot is normal here even while the job is actively
  running - this container doesn't execute anything after submitting.
- `docker logs jobmanager` — scheduling, checkpointing, task deployment/failure
  events, restart strategy activity. Start here for "why did the job restart".
- `docker logs taskmanager` — where the pipeline actually executes, including every
  UDF `print()`/`_udf_log()` call (see `decode_job.py`'s `process_element` and the
  `structlog`-in-a-UDF gotcha below) - this is the **only** place the
  `Dropping packet from unregistered gateway: gateway_id=...` line (or any other UDF
  log output) appears. If you're debugging pipeline *behavior* rather than job
  *scheduling*, `taskmanager` is almost always the right log to tail:

```bash
docker logs -f taskmanager | grep -i "dropping\|error\|exception"
```

**Redeploying a job after a code change**: see
[flink.md](flink.md#redeploying-after-a-code-change) for the full procedure
(savepoints, cold restarts). The old
"submitting-container-auto-resubmits-a-duplicate" trap is gone - submitters are
now one-shot and idempotent - but one trap remains, and it's easy to get
backwards:

- The old job keeps running until you cancel/stop it — resubmitting without
  doing that first gives you a *second* job with the same consumer group
  (rebalancing/duplicate-consumption), not a clean replace.
- **Correction to an earlier version of this doc**: this used to also claim
  "rebuilding `flink-job` alone is not enough — `taskmanager` executes the
  Python UDF from its own baked-in copy of the file, so you must rebuild
  `jobmanager`+`taskmanager` too." Directly re-tested while building the
  `mesh_id` tagging change and found this **false**: `taskmanager`'s own
  `/opt/flink/usrlib/decode_job.py` had zero rebuilds and no trace of the new
  code, while the live pipeline correctly ran it. A *fresh* `flink run -py
  <file>` submission (new JobID, not a restart of the same one) ships the
  Python file as part of that submission — only the submitting container's
  copy matters. If you ever see genuinely stale UDF behavior after a proper
  fresh resubmit, the far more likely explanation is the first bullet (the
  old job wasn't actually replaced) — check `flink list` for a duplicate
  before suspecting `taskmanager`'s own files. Sanity-check either way with:

```bash
docker exec taskmanager grep -n "<something only in your new code>" /opt/flink/usrlib/decode_job.py
# absence here is fine as long as `flink list` shows exactly one job and it's
# the new JobID - see flink.md for confirming which container submitted it.
```

## InfluxDB

Query via the CLI-friendly HTTP API (avoid the InfluxDB UI's default 1h window hiding
older test data — see the gotcha below):

```bash
TOKEN=$(grep '^INFLUX__TOKEN=' .env | cut -d= -f2-)
ORG=$(grep '^INFLUX__ORG=' .env | cut -d= -f2-)
curl -s -X POST "http://localhost:8086/api/v2/query?org=${ORG}" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Accept: application/csv" \
  -H "Content-type: application/vnd.flux" \
  -d 'from(bucket:"telemetry") |> range(start: -1h) |> filter(fn: (r) => r.node_id == "123456789")'
```

Or use the [readings API](api-reference.md) instead of raw Flux for anything routine.

## MinIO / S3

Console UI: http://localhost:9001 (login with `S3_WRITER__ACCESS_KEY`/`SECRET_KEY` from
`.env`). Or via `boto3`:

```python
import boto3, io
import pyarrow.parquet as pq

s3 = boto3.client("s3", endpoint_url="http://localhost:9000",
                   aws_access_key_id="...", aws_secret_access_key="...")
for obj in s3.list_objects_v2(Bucket="meshtastic-telemetry", Prefix="telemetry/").get("Contents", []):
    print(obj["Key"], obj["Size"])

body = s3.get_object(Bucket="meshtastic-telemetry", Key="telemetry/dt=.../hour=.../part-....parquet")["Body"].read()
print(pq.read_table(io.BytesIO(body)).to_pandas())
```

The credential above is MinIO's **root** account (`S3_WRITER__ACCESS_KEY`/`SECRET_KEY`
double as `MINIO_ROOT_USER`/`PASSWORD`) — fine for local debugging, but don't hand it to
an external consumer. See [s3-access.md](s3-access.md) for a scoped read-only
credential, DuckDB/presigned-URL access patterns, and moving to real AWS S3.

## Email verification (mailhog)

Web UI: http://localhost:8025 — every email `registry_api` sends (currently just
signup/resend/email-change verification links, see
[architecture.md#registry-email-verification](architecture.md#registry-email-verification))
lands here instead of a real inbox, as long as `REGISTRY__EMAIL_BACKEND` is set to the
SMTP backend pointed at `mailhog:1025` (the console backend, the default, just prints
to `docker logs registry-api` instead — also fine for debugging, no UI needed).
`mailhog` isn't in `registry_api`'s `depends_on` — the API starts and serves
traffic regardless of whether `mailhog` is up, matching how email failures are
non-fatal everywhere in that flow.

## Gotchas found while building this pipeline

These are real bugs hit and fixed during development — worth knowing about since the
underlying constraints don't go away.

### A source reads `connected` but nothing arrives from it

EMQX can keep a source's connection to the remote broker after the subscription on it
has stopped delivering. The connector and the source both report `connected`, while the
source's `received` counter stops moving. Its meshes go quiet, and the bridge health
check can turn unhealthy too, because fewer messages arrive to mark MQTT as connected.
Production's Mesh Hub UK source stalled this way in October 2026 and carried nothing for a day.

Compare the counter twice a minute apart, then restart the source:

```bash
./scripts/restart-source.sh                 # status and message count of every source
./scripts/restart-source.sh <source id>
```

The console's Sources page has the same Restart action. If the count still does not
move, check the remote broker with its own credentials (`mosquitto_sub -V mqttv5 -d`
shows the SUBACK code; 128 or more means it refused the topic). The silent-source alert
(`REGISTRY__SOURCE_SILENT_ALERT_HOURS`, see [deploy.md](deploy.md)) emails superusers when
this happens.

### A mesh "goes dark" after deploying the ownership gate, with no error anywhere

Since the registered-gateways-only gate landed (see
[architecture.md#registered-gateways-only-gate](architecture.md#registered-gateways-only-gate)),
a packet relayed by an unregistered gateway - encrypted **or plaintext** - is dropped in
`decode_job.py`'s `process_element` before decode is ever attempted, logged only at
debug level (`docker logs flink-job` won't show anything by default; the drop line
only appears if you're tailing `taskmanager`'s logs directly, and it logs the
`gateway_id`, not a device_id). There is no error, no alarm, nothing in
`mesh.telemetry.decoded.v1`. Before assuming decode/decryption is broken, check whether
that gateway is registered (`Device.is_gateway=true`) and still allowed
(`is_allowed=true`) - a rejected gateway drops the same way as one that was never
registered. `GET /devices` is owner-scoped (see
[api-reference.md](api-reference.md#authentication-for-mesh-and-device-mutations)) — if
you don't hold the registering owner's API key, `curl
"http://localhost:8090/devices?mesh_id=<id>&is_gateway=true" -H "Authorization: Bearer
$OWNER_API_KEY"` won't help. For cross-owner operational debugging, query Postgres
directly instead:

```bash
docker compose exec -T postgres psql -U meshtastic -d meshtastic_keys \
  -c "SELECT device_id, mesh_id, is_allowed FROM devices WHERE device_id = <device_id> AND is_gateway;"
```

If it's missing (or `is_allowed` is `false`), that's the entire explanation. Register it
via `POST /owners`, then `POST /meshes`, then `POST /devices` with `is_gateway: true`
(see [api-reference.md](api-reference.md)). Note that registering a *node* on the same
mesh never helps here - only its mesh's gateway registration matters. If a node's own
data is the thing missing instead (the gateway itself is fine), check that node's own
`is_allowed` the same way - a rejected node is dropped before decrypt too, see
[architecture.md#device-registration-and-the-is_allowed-gate](architecture.md#device-registration-and-the-is_allowed-gate).

### A mesh with gateway discovery on registers nothing

Discovery is skipped silently on purpose (see
[architecture.md#gateway-discovery](architecture.md#gateway-discovery)). Check, in order:

1. **The bridge is sampling.** `docker exec <bridge container> curl -s
   localhost:9090/health` shows `discovery_candidates_sent` and
   `discovery_gateways_tracked`. Samples land on `mesh.gateway_candidates.v1`:

   ```bash
   docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
     --topic mesh.gateway_candidates.v1 --property print.key=true --timeout-ms 10000
   ```

   No sample for the gateway yet usually means the immediate budget was spent: it is
   sent once it has been known for `MQTT_BRIDGE__DISCOVERY__DELAY_SECONDS` (a minute
   by default). Only `.../2/e/<channel>/!<gateway>` topics are sampled.
2. **The consumer saw it.** `docker logs registry-gateway-discovery` logs
   `Gateway discovered` on success and `ambiguous match` when several meshes decode it.
3. **Nothing blocks it.** Another mesh on the same source and channel with the same PSK
   (with discovery on or off) makes every match ambiguous; an allowed gateway with
   that node number on any mesh, or a rejected row on this one, skips it:

   ```bash
   docker compose exec -T postgres psql -U meshtastic -d meshtastic_keys -c \
     "SELECT id, channel_id, source_id, discover_gateways FROM meshes WHERE channel_id = '<channel>';" -c \
     "SELECT mesh_id, is_gateway, is_allowed, discovered_at FROM devices WHERE device_id = <node number>;"
   ```

4. **The packet proves it.** A sample only counts when it fully decodes with the mesh
   PSK. Text messages and other portnums without a protobuf schema don't, so a gateway
   relaying only those waits for its next retry. A plain packet never matches a mesh
   with a PSK.

Packets relayed before the gateway was registered are not recovered.

### Kafka tombstones crash SimpleStringSchema

A native Kafka tombstone (a record with a `null` value) makes PyFlink's
`SimpleStringSchema.deserialize()` throw a `NullPointerException` in the *Java* layer,
which kills the whole job (`NoRestartBackoffTimeStrategy` — no automatic recovery).
Confirmed by producing a real tombstone to a test topic and watching the job die.

**Consequence**: `mesh.keys.v1`, `mesh.quality_config.v1`, and `mesh.postprocessing_config.v1` never use
real Kafka tombstones for deletes. Every delete is a normal JSON record with
`"op": "delete"` instead — see `registry/kafka_publisher.py`. The topics are still
`cleanup.policy=compact`, so they stay bounded (one record per key, including delete
markers), just not zero-byte-per-deleted-key like a "real" compacted delete.

### `flink run` from a separate container needs `rest.address` set explicitly

`jobmanager.rpc.address` (set via `JOB_MANAGER_RPC_ADDRESS`) does **not** make
`flink run`'s REST client submission target follow it — `rest.address` is an
independent config key that defaults to `localhost`, which is wrong when the CLI runs
in a different container than the JobManager. Symptom: `Connection refused:
/0.0.0.0:8081` in the client's log, even though the JobManager is healthy. Fix: set
`rest.address: jobmanager` via `FLINK_PROPERTIES` on the client container (see the
`&flink-client-properties` anchor in `docker-compose.yml`).

### Don't `COPY` a custom `flink-conf.yaml` over the base image's default

The official Flink Docker image's default `flink-conf.yaml` includes required memory
settings (`jobmanager.memory.process.size` etc.). Overwriting the whole file at build
time with a minimal custom one strips those out, causing
`IllegalConfigurationException: ... jobmanager.memory.heap.size ... need to be
configured explicitly` at container startup. Use the `FLINK_PROPERTIES` env var instead
(processed by the base image's entrypoint, which *appends*/updates specific keys rather
than replacing the file) — see `docker-compose.yml`'s `x-flink-state-properties`
anchor.

### Don't call `env.add_jars()` for jars already on `/opt/flink/lib/`

Connector jars placed in `/opt/flink/lib/` (via the Dockerfile's `wget`) are
automatically on the classpath for every job — no `env.add_jars()` needed. Calling it
anyway in this PyFlink version corrupted the internal `pipeline.jars` config, rendering
`flink-python-*.jar`'s path as the literal string `"['file:...jar']"` (Python list
`repr()` leaking into a Java config value) and crashing with
`MalformedURLException: no protocol`. Only call `add_jars()` in `--local` mode, where
the jars aren't preinstalled on any classpath.

### Raw Kafka bytes through `SimpleStringSchema` need Latin-1, not UTF-8

Meshtastic's raw MQTT payload is protobuf, not text. `SimpleStringSchema`'s default
UTF-8 charset corrupts arbitrary binary on decode. Fix: `SimpleStringSchema("ISO-8859-1")`
on the Flink side, `.encode("ISO-8859-1")` on the Python UDF side — Latin-1 maps every
byte 0-255 to exactly one code point, so it round-trips losslessly without needing a
custom Java `DeserializationSchema` class. See `flink/decode_job.py`'s
`RAW_BYTES_CHARSET`.

### Flux `group()` + `last()` across mixed measurement types

`group(columns: [...])` followed by `last()` fails with `schema collision: cannot
group float and string types together` when the regrouped rows' `_value` column has
different types across measurements (e.g. a float `battery_level` and a string
`timestamp_quality` both flow through the same query). Fix: either `keep()` down to a
uniform schema before grouping, or overwrite `_value` with something type-stable (this
codebase uses `map(fn: (r) => ({r with _value: r._time}))` in
`readings/influx_client.py`'s `list_devices()`, grouped by `["mesh_id", "node_id"]` -
since `last()` needs *a* `_value` column to exist even if you don't care about its
content).

### PyFlink UDF subprocess doesn't inherit your shell's Python

`--local` mode spawns a Python worker subprocess that resolves the `python` command via
`PATH` — not the interpreter you launched the script with. If your venv's `bin/` isn't
first on `PATH`, you get `ModuleNotFoundError: No module named 'pyflink'` from deep
inside a Java stack trace, which looks like a Flink bug but isn't. See
[testing.md](testing.md#running-a-flink-job-locally-no-cluster-needed).

### `structlog` inside a UDF crashes with `CustomPrint.print() got an unexpected keyword argument 'flush'`

Any `log.debug()`/`log.info()`/`log.exception()` call made from *inside* a UDF method
(`open`, `process_element`, `process_broadcast_element`, `flat_map`, ...) crashes the
whole task the first time it actually executes. Root cause: on the real cluster (not
`--local` mode - see the next gotcha), PyFlink runs Python UDF code in a separate
subprocess managed by Apache Beam's Fn API, which replaces the `print` builtin inside
that subprocess with a `CustomPrint` shim so UDF output gets routed into Flink's own
log files. `structlog`'s default `PrintLogger` calls `print(message, file=f,
flush=True)` — and `CustomPrint.print()`'s signature has no `flush` parameter at all,
so passing that keyword (with *any* value, `True` or `False`) raises `TypeError:
CustomPrint.print() got an unexpected keyword argument 'flush'`, which propagates up as
a fatal `BeamPythonFunctionRunner` failure and restarts the whole job from the last
checkpoint - repeatedly, since the same log call fires again on every retry.

**Consequence**: driver-side code (`main()`, `build_pipeline()`) can use `structlog`
normally - it runs outside the UDF subprocess sandbox. Anything called from inside a UDF
method must use a plain `print(message)` instead (no `flush` kwarg, not even
`flush=False` - the keyword's mere *presence* is what breaks it, not its value). See
`_udf_log`/`_udf_log_exception` in `flink/decode_job.py`, `postprocessing_job.py`, and
`pattern_detection_job.py` for the pattern.

**Why `--local` testing didn't catch this**: PyFlink's embedded mini-cluster
(`--local` mode) runs the UDF in-process, without the Beam-based subprocess isolation
that installs the `CustomPrint` shim - so `structlog` calls work fine locally and only
fail once deployed to the real `jobmanager`/`taskmanager` cluster. There is currently no
way to catch this class of bug before a real cluster deploy; when adding any new
`log.*()` call inside a UDF method, either use the `_udf_log` pattern from the start or
budget for a real-cluster smoke test before trusting it.

### Changing `common/` requires rebuilding `taskmanager`, and the error doesn't say so

The redeploy sequence in [flink.md](flink.md#redeploying-after-a-code-change) is right
that `jobmanager`/`taskmanager` need no rebuild for a change to a *job file* — `flink
run -py <file>` ships that file with the submission. **That does not extend to
`common/`.** `flink/Dockerfile` does `RUN pip install .`, so `common` lives in the
taskmanager's site-packages, and a UDF's `from common import <module>` resolves there,
not against anything the client submitted.

Adding `mesh_things.channels` and rebuilding only `pattern-detection-job` therefore
produced a job that submitted fine and then failed at runtime with:

```
java.io.IOException: Failed to deserialize consumer record due to
  ...
  Caused by: ... ImportError: cannot import name 'channels' from 'common'
                  (/opt/venv/lib/python3.10/site-packages/common/__init__.py)
```

The outer message is actively misleading — nothing is wrong with the Kafka record; the
import failure happens inside the Beam UDF harness while processing it, and surfaces
wrapped in the deserialization error. **When a Flink job fails with "Failed to
deserialize consumer record", read all the way down the `Caused by` chain before
suspecting the data.** Fix:

```bash
docker compose build taskmanager jobmanager && docker compose up -d taskmanager
```

### `docker compose up -d <job-container>` creates duplicate Flink jobs — fixed

**No longer reproducible**, but the shape is worth knowing since a manual
`flink run` still behaves this way.

Each job container used to resubmit its job on start, and `up -d` also starts
everything in that container's `depends_on` chain. Bringing up
`pattern-detection-job` therefore restarted `flink-job` and `calibration-job`
too, each submitting a *second* copy of its job. The duplicates competed for
slots and everything ended in `RESTARTING` with:

```
org.apache.flink.runtime.jobmanager.scheduler.NoResourceAvailableException:
  Could not acquire the minimum required resources.
```

The documented workaround was to bring containers up one at a time, checking
`flink list` between each.

The submitters are now one-shot (`restart: "no"`) and idempotent: each runs
`flink/submit-job.sh`, which asks the cluster whether a job of that name is
already live and exits without submitting if it is. So this is now correct, and
safe to repeat:

```bash
docker compose up -d flink-job postprocessing-job pattern-detection-job absence-detection-job
```

A second run just prints `submit-job: 'mesh-decode-decrypt' is already running -
nothing to do.` A job that genuinely died *is* resubmitted, so the same command
doubles as recovery. `flink-watchdog` runs the same check every minute, so after a
jobmanager restart or a reboot, which drop every job since the cluster has no HA,
the jobs come back from their checkpoints without running anything.

If you do end up with duplicates from a manual `flink run`, cancel the extras by
JobID:

```bash
curl -s localhost:8081/jobs/overview | python3 -m json.tool | grep -E '"jid"|"name"|"state"'
curl -X PATCH "localhost:8081/jobs/<jid>?mode=cancel"
```

### Django's test runner prompts when a stale test database exists

If a `manage.py test` run is interrupted (timeout, Ctrl-C), the `test_<db>` database
survives and the next run blocks on an interactive prompt — which, under
`docker compose exec -T`, fails as `EOFError: EOF when reading a line` rather than
anything self-explanatory. Pass `--noinput` to drop and recreate it:

```bash
docker compose exec -T registry_api python manage.py test registry --noinput
```

### Services sharing a Dockerfile are NOT rebuilt together — fixed, but know the shape

**This no longer happens**, and the fix is worth understanding because the
symptom was so quiet.

Seventeen services build from five Dockerfiles. Compose derives an image tag
per *service* unless you name the image explicitly, so those five images used to
exist as seventeen separate tags — and `docker compose build registry_api`
rebuilt exactly one of them.

It bit hard during the `SensorType` → `TelemetryVariant` rename: the web
container was rebuilt many times and looked perfectly healthy, while the
discovery consumer kept running yesterday's image and failed on **every**
message with:

```
[warning] Failed to upsert sensor discovery error=relation "sensor_types" does not exist
```

Because that consumer logs-and-continues per message (deliberately — one bad
event shouldn't stop the stream), nothing crashed, no health check went red,
and sensor discovery was simply dead for a day.

`docker-compose.yml` now pins a shared `image:` per Dockerfile via the
`x-*-image` anchors, so every service built from `registry/Dockerfile` *is* the
same image ID. Building any one of them updates all of them. Verified by
changing a source file, rebuilding only `registry_api`, and confirming
the sensor-discovery consumer picked up the change.

```bash
docker images mesh-things/*    # pipeline, api, flink, quality-worker, and monitor once built
```

The one thing still worth remembering: **`common/` is `pip install`ed into the
Flink image**, so changing it means rebuilding that image too — see
[flink.md](flink.md#redeploying-after-a-code-change). A bare
`docker compose build` rebuilds all five and sidesteps the question.

If you ever suspect a stale container anyway, compare the image ID a service is
running against the shared tag:

```bash
docker inspect -f '{{.Image}}' "$(docker compose ps -q registry_sensor_discovery_consumer)"
docker image inspect mesh-things/api:latest -f '{{.Id}}'
```

Different IDs mean the container predates the last build — `docker compose up -d`
that service.

