# Flink operations

Four long-running streaming jobs run on one Flink session cluster
(`jobmanager` + `taskmanager`, dashboard at `http://localhost:8081`):

| Job name | Submitted by (container) | Script | Notes |
|---|---|---|---|
| `mesh-decode-decrypt` | `flink-job` | `decode_job.py` | Core pipeline - always needed |
| `mesh-postprocessing` | `postprocessing-job` | `postprocessing_job.py` | Device postprocessing on live telemetry -> `mesh.telemetry.derived.v1` |
| `mesh-pattern-detection` | `pattern-detection-job` | `pattern_detection_job.py` | flat_value + range checks |
| `mesh-absence-detection` | `absence-detection-job` | `absence_detection_job.py` | "device stopped publishing" - the only job using timers |

`taskmanager.numberOfTaskSlots` is **6** (`x-flink-state-properties` in
`docker-compose.yml`) for four jobs at parallelism 1. That headroom is
deliberate: a redeploy briefly needs a slot for the new submission while the
old job still holds its own, so running at exactly four would fail the
resubmit with `NoResourceAvailableException` and leave it stuck in
`RESTARTING`. Slots also divide the taskmanager's managed (RocksDB) memory
between them - at 6 slots each gets ~55 MB, measured from the
`Free slot TaskSlot(... managedMemory=...)` line in the taskmanager log.

All four follow the identical deployment shape: a **one-shot** container that
runs `./submit-job.sh <script>.py <job-name>` and exits as soon as the cluster
accepts the job, with `restart: "no"`.

`submit-job.sh` (in `flink/`) does two things that matter operationally:

- **Submits detached** (`flink run -d`). The previous form stayed attached for
  the whole life of the job, holding a ~550 MB JVM open per job - 2.2 GB across
  the four, doing nothing after the first second.
- **Checks the cluster first.** It queries `/jobs/overview` and skips
  submission if a job of that name is already live, so `docker compose up -d`
  is idempotent no matter how many times it runs. A job that has genuinely
  died (cancelled, failed, or lost with the cluster) *is* resubmitted, which
  makes the same command double as recovery.

Neither container carries a `-s <savepoint>` flag in its default command - see
[Redeploying after a code change](#redeploying-after-a-code-change) before you
stop or cancel any of these jobs directly.

State backend is RocksDB, checkpointing every 60s
(`x-flink-state-properties` in `docker-compose.yml`), checkpoints at
`/opt/flink/checkpoints`, savepoints at `/opt/flink/savepoints` inside every
Flink container (same paths, since they all build from `flink/Dockerfile`
and talk to the same `jobmanager`).
Every sink is at-least-once, so a shorter interval would only shorten the replay
after a restart, at the cost of rewriting the full state to disk each time.

The image runs Flink and the PyFlink workers on the base image's Java 17
(`/opt/java/openjdk`). It installs no JDK or compiler, and the Python
dependencies are installed before the source is copied, so rebuilding after a
code change reuses the PyFlink layer and takes seconds. Adding a Python
dependency that has to be compiled needs the build toolchain added back.

## Checking status

```bash
# All running jobs, with IDs
docker compose exec jobmanager flink list

# Same info plus history (finished/cancelled/failed), via the REST API
curl -s http://localhost:8081/jobs/overview | python3 -m json.tool

# One job's detail (status, uptime, checkpoint stats)
curl -s http://localhost:8081/jobs/<job-id> | python3 -m json.tool
```

Or just open `http://localhost:8081` - the dashboard shows the same thing
with checkpoint history and a UI for the operations below.

## Logs

```bash
docker compose logs jobmanager --tail 100 -f
docker compose logs taskmanager --tail 100 -f
# The submitting container's own log is mostly just the CLI's submission
# output, not the job's runtime logs - those are on jobmanager/taskmanager.
docker compose logs flink-job --tail 50
```

## Redeploying after a code change

**This used to be the sharpest trap in the repo, and is now handled by
`submit-job.sh`** - but the history is worth knowing, because the symptoms
still appear if you submit by hand with `flink run`.

Formerly each submitting container stayed attached to its job and exited when
that job stopped for any reason. With `restart: unless-stopped`, cancelling a
job from the dashboard made its container immediately resubmit a brand-new,
non-resumed duplicate - not what you want mid-redeploy. A second form of the
same trap: `docker compose up -d <job>` also starts everything in its
`depends_on` chain, and each of those resubmitted *its* job, so bringing up
`pattern-detection-job` produced duplicate `mesh-decode-decrypt` and
`mesh-postprocessing` jobs that competed for slots and left everything
`RESTARTING`. The documented workaround was to bring containers up one at a
time, checking `flink list` between each.

Both are fixed at the source: the submitters are one-shot (`restart: "no"`,
so nothing resubmits on exit) and idempotent (a job that is already live is
left alone). **Bringing all four up in a single command is now correct and
safe:**

```bash
docker compose up -d flink-job postprocessing-job pattern-detection-job absence-detection-job
```

The `depends_on` chain uses `service_completed_successfully`, so they submit in
dependency order, each waiting for the previous one to be accepted. Running it
again is a no-op:

```
submit-job: 'mesh-decode-decrypt' is already running - nothing to do.
```

If you ever do end up with duplicates - from a manual `flink run`, or from
`submit-job.sh` finding more than one copy (it warns and refuses rather than
adding a third) - cancel the extras by JobID:

```bash
curl -s localhost:8081/jobs/overview | python3 -m json.tool | grep -E '"jid"|"name"|"state"'
curl -X PATCH "localhost:8081/jobs/<jid>?mode=cancel"
```

To ship a code change, use the redeploy script from the repository root:

```bash
./scripts/redeploy-flink.sh                        # every job, plus jobmanager and taskmanager
./scripts/redeploy-flink.sh pattern-detection-job  # only this job
# Locally, with the dev overlay:
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile full" \
    ./scripts/redeploy-flink.sh
```

It rebuilds the Flink image, stops `flink-watchdog`, stops each job with a
savepoint in its own savepoint directory, resubmits it with the new image (so it
resumes from that savepoint), checks that exactly one copy of each job is live,
and starts the watchdog again. It exits non-zero if a submission fails or a job
ends up with other than one live copy.

**Run it with no arguments when `common/` changed.** A submission ships the job
file itself, but anything under `common/` is installed into the image, so a UDF's
`from common import <module>` resolves against the taskmanager's own copy.
Redeploying a single job after a `common/` change leaves the taskmanager on the
old code, and the job fails at runtime with e.g.
`ImportError: cannot import name 'channels' from 'common'` (which surfaces
confusingly as "Failed to deserialize consumer record"). The no-argument form
recreates jobmanager and taskmanager too, after taking every savepoint.

If the change also affects the events consumed downstream of Flink
(`writer/point_builders.py`, `mesh_things.codec`), rebuild those consumers too;
see below.

**Stop `flink-watchdog` before stopping or cancelling a job by hand.** Within a
minute it resubmits any job that is not live, from that job's newest checkpoint
and with whatever image the watchdog was created from:

```bash
docker compose stop flink-watchdog
# ... manual work ...
docker compose up -d flink-watchdog
```

The job lives on `jobmanager`/`taskmanager` regardless of which container
submitted it, and a later `docker compose up -d flink-job` sees it already live
and does nothing.

## State survives restarts

Checkpoints and savepoints live on the `flink_checkpoints` and
`flink_savepoints` volumes, shared by `jobmanager`, `taskmanager`, `flink-watchdog` and the four
submitters. `submit-job.sh` gives each job its own directories
(`/opt/flink/checkpoints/<job-name>/<job-id>/chk-N` and
`/opt/flink/savepoints/<job-name>/savepoint-*`) and resumes from the newest
one that is complete. Checkpoints are kept when a job is cancelled
(`RETAIN_ON_CANCELLATION`) or when the cluster disappears under it, so
`docker compose down` / `up`, or recreating `jobmanager`, resumes every job
where it stopped instead of replaying its topics. `flink-watchdog` resubmits the
jobs by itself after a jobmanager restart or a reboot. Each submission removes the
checkpoint directories of earlier runs and any older savepoints of that job,
keeping only the one it resumes from.

Without this, a restarted cluster cold-started the decode job, which re-decoded
the whole raw topic, and pattern detection raised alarms for all of that
history at once.

If a code change makes the stored state incompatible, the submission fails to
restore. Remove that job's directories to start it fresh:

```bash
docker compose exec jobmanager rm -rf /opt/flink/checkpoints/<job-name> /opt/flink/savepoints/<job-name>
```

**Don't forget the downstream consumers.** `decode_job.py`'s output only
reaches InfluxDB through `influxdb_writer` (`writer/point_builders.py`) and
`s3_writer`, and only reaches registry's Device/DeviceTelemetryVariant catalogs through
`registry_device_consumer`/`registry_sensor_discovery_consumer`.
None of those are Flink jobs, so they don't need the savepoint dance, but
they **do** need `docker compose build <service> && docker compose up -d
<service>` if the change affects the shape of the events they consume -
forgetting this is exactly what made `mesh_id` show up as `null` the first
time it was tested end-to-end after the `decode_job.py` change above.

## Cold-restarting instead (accepting a full reprocess)

If you don't need continuity - e.g. you're fine reprocessing history, or
there's no meaningful state to carry over - skip the savepoint:

```bash
docker compose stop flink-watchdog
docker compose exec jobmanager flink cancel <job-id>
docker compose exec jobmanager rm -rf /opt/flink/checkpoints/mesh-decode-decrypt /opt/flink/savepoints/mesh-decode-decrypt
docker compose up -d --force-recreate flink-job
docker compose up -d flink-watchdog
```

Without a checkpoint or savepoint, `decode_job.py` reads `mesh.telemetry.raw.v1`
from the offsets `flink-decode-group` last committed (Flink commits them on every
checkpoint), and from the earliest only when the group has none. A cold restart
therefore resumes roughly where the job stopped. The config topics
(`mesh.keys.v1`, `mesh.node_rejections.v1`) are always read from the earliest,
since they rebuild the broadcast state.

To re-decode history on purpose, reset the group first, with the job cancelled:

```bash
docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:29092 \
  --group flink-decode-group --topic mesh.telemetry.raw.v1 --reset-offsets --to-earliest --execute
```

That replays whatever is still within the raw topic's retention window, not
the true beginning of time. Consequences to weigh:
- Every packet still in `mesh.telemetry.raw.v1`'s retention window gets
  re-decoded and re-written to InfluxDB (harmless overwrite for identical
  points, but real load and I/O while it catches up).
- This is actually how you'd *retroactively* backfill a tag like `mesh_id`
  onto already-decoded historical data, provided the raw topic still has it
  - a plain code-only redeploy (previous section) only tags data going
  forward.
- If the raw topic's retention has already passed the data you care about,
  it's gone either way - a cold restart doesn't recover data Kafka has
  already deleted.

## Taking a savepoint without stopping (backup, not a redeploy)

```bash
docker compose exec jobmanager flink savepoint <job-id>
# optionally: flink savepoint <job-id> file:///opt/flink/savepoints/manual-backup
```

The job keeps running; this just snapshots state to disk. Useful before any
risky operation (Kafka topic surgery, a Postgres restore that changes
`mesh.keys.v1`'s meaning, etc.) even when you don't plan to redeploy code.

## Cancelling a job outright (decommissioning)

For the optional jobs (`mesh-postprocessing`, `mesh-pattern-detection`,
`mesh-absence-detection`) if you want them off entirely, not just paused:

```bash
docker compose stop postprocessing-job pattern-detection-job absence-detection-job   # first, same reason as above
docker compose exec jobmanager flink cancel <job-id>
```

Leave those containers stopped in `docker-compose.yml` rather than removing
them if you might turn this back on later. Stopping `mesh-postprocessing` stops
every device's derived channels; registry keeps publishing their plans, so it
picks them up again when resubmitted.

## When a state change means you can't resume from a savepoint

`pattern_detection_job.py`'s data-quality rework changed both its keying
(`node_id:field` → `mesh_id:device_id:channel`) and its state descriptors
(`RULES_STATE` → `QUALITY_CONFIG_STATE`). A savepoint written by the old
version describes state that no longer maps onto the new operators, so the
savepoint dance above doesn't apply - use the cold-restart path instead and
accept the reprocess. Rule of thumb: if you renamed a state descriptor or
changed a `KeySelector`, resume is off the table.

`decode_job.py` gives its sources, its decode operator and its sinks a stable
`uid`, so adding or removing an output (as `mesh.traffic.v1` was) no longer
breaks the restore. The other jobs still rely on generated operator IDs, so
for them adding or removing an operator also rules resume out.

## Checkpoint storage must be shared

`jobmanager` decides when a checkpoint has expired and deletes it, but the
state files are written by `taskmanager`. Both therefore mount the
`flink_checkpoints` and `flink_savepoints` volumes. Without a shared volume,
the deletes run against `jobmanager`'s own empty directory and every
checkpoint `taskmanager` writes stays on its container filesystem forever;
at a 10s interval this filled a 160 GB disk.

To check that pruning works, compare both sides; they should match and stay
small:

```bash
docker compose exec taskmanager du -sh /opt/flink/checkpoints
docker compose exec jobmanager du -sh /opt/flink/checkpoints
```

## Housekeeping: checkpoint directories

Checkpoints live under `/opt/flink/checkpoints/<job-name>/<job-id>/`. Flink
prunes a running job's own checkpoints as new ones complete, and
`submit-job.sh` removes the directories of earlier runs on every submission,
so each job keeps one run at most. Savepoints are never removed
automatically:

```bash
docker compose exec jobmanager du -sh /opt/flink/checkpoints/* /opt/flink/savepoints/*
docker compose exec jobmanager rm -rf /opt/flink/savepoints/<job-name>/savepoint-<id>
```
