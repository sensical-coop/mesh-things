# Data quality

Two tiers of checks, plus a way to derive new channels from raw telemetry.
This is the practical guide; for *why* it's shaped this way see
[architecture.md#data-quality-checks](architecture.md#data-quality-checks),
[#device-fault-detection](architecture.md#device-fault-detection) and
[#postprocessing](architecture.md#postprocessing).

| Tier | Service | Runs | Does |
|---|---|---|---|
| Stream | `postprocessing-job` (Flink) | per point | derived channels, from every enabled device postprocessing |
| Stream | `pattern-detection-job`, `absence-detection-job` (Flink) | per point | `flat_value`, `range`, `absence`, on sensor and derived channels |
| Batch | `quality_worker` + `quality_worker_beat` (Celery) | scheduled | `completeness`, postprocessing backfills |

Everything is off by default: no curated thresholds means no alarms, and no
enabled postprocessing means no derived channels.

## Bringing it up

```bash
# Stream tier. Safe in one command and safe to re-run - the submitters are
# one-shot and skip jobs that are already running (see flink.md).
docker compose up -d postprocessing-job pattern-detection-job absence-detection-job
docker compose exec jobmanager flink list     # expect 4 RUNNING jobs

# Batch tier - needs a superuser key first
docker compose exec registry_api python manage.py createsuperuser \
  --email quality-worker@internal --name "Quality Worker"
# paste the printed key into .env as QUALITY_WORKER__REGISTRY_API_KEY, then:
docker compose up -d quality_worker quality_worker_beat

# Alarm -> email
docker compose up -d registry_quality_alarms_consumer
```

## The two device faults are not the same fault

This is the distinction the whole design turns on:

| | **Absence** | **Completeness** |
|---|---|---|
| Question | "have we heard from it?" | "was what we heard complete?" |
| Timed against | `publish_interval_seconds` | `reading_interval_seconds` |
| Runs in | `absence-detection-job` (Flink timers) | `quality_worker` (InfluxDB query) |
| Fires when | nothing arrives for N publish intervals | received timestamps have holes |

A device that batches telemetry is **silent by design** and then delivers a
full history — absence fires, completeness doesn't, and nothing is wrong. A
device that publishes on schedule but with a broken sensor shows the
opposite. Both intervals are set per-device, falling back to
`TelemetryVariant.default_reading_interval_seconds`:

```bash
curl -s -X PUT http://localhost:8090/devices/<device id> \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"reading_interval_seconds": 300, "publish_interval_seconds": 3600}'
```

Clearing **both** (`null`) stops absence monitoring for that device
entirely — it publishes an `op: "delete"`, which is the only way to reach a
device that has already gone silent (a silent device produces no events, so
`on_timer` re-reads config rather than reusing what it armed with).

## Enabling alarms

**Alarms are off until you turn them on**, per detector, per measurement. Some
channels alarm purely because of what they measure: barometric pressure is meant
to be stable and wind is often calm, so both would trip `flat_value` forever.

Two levels, resolved the same way the reading intervals are - the device's own
value wins, otherwise the catalog default applies:

| Level | Field | Who sets it |
|---|---|---|
| Catalog default, shared by every device reporting the channel | `TelemetryVariantMeasurement.default_enabled_detectors` | superuser |
| This device's channel | `Measurement.enabled_detectors` | the mesh owner |

`null` inherits the catalog default; `[]` silences the channel on that device
whatever the default says.

```bash
# Alarm on out-of-range pressure (with the range set below), but never on it being flat
curl -s -X PUT http://localhost:8090/devices/<device uuid>/measurements/<measurement id> \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"enabled_detectors": ["range", "completeness"], "valid_min": -40, "valid_max": 85}'

# Hand it back to the catalog default
curl -s -X PUT http://localhost:8090/devices/<device uuid>/measurements/<measurement id> \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"enabled_detectors": null}'
```

`GET /devices/{uuid}/measurements` reports both, because two settings combine:

| this device | catalog default | `effective_detectors` | |
|---|---|---|---|
| `null` | `["range"]` | `["range"]` | inherited |
| `[]` | `["range"]` | `[]` | turned off here |
| `["flat_value"]` | `["range"]` | `["flat_value"]` | overridden here |

Rows 1 and 2 are why both are reported: with an empty catalog default they would
both show `[]`, but only the first follows the catalog when it changes.

`GET /detectors` lists the valid names, each with the `scope` it applies at and
the config it also needs, so a UI does not have to hardcode them.

`absence` has no channel, so it hangs off the device instead:

```bash
curl -s -X PUT http://localhost:8090/devices/<device uuid> \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"absence_detection_enabled": true, "publish_interval_seconds": 900}'
```

`completeness` metrics are still computed and written to InfluxDB whether or not
the detector is enabled - only the alarm is suppressed, so the figures on
`/readings/.../quality` stay available.

## Tuning the stream checks

Thresholds are **not** a separate config file — they're the catalog from
[architecture.md#device-telemetry-variant--measurement-catalog](architecture.md#device-telemetry-variant--measurement-catalog),
except the range detector's bounds, which have no catalog entry - they only
ever come from the device's own `Measurement` row (see the `enabled_detectors`
example above). Editing either publishes to the compacted
`mesh.quality_config.v1`, which both Flink jobs hold as broadcast state.

```bash
# Enable a detector by default for every device reporting this channel - superuser-only
curl -s -X PUT http://localhost:8090/telemetry-variants/<telemetry variant id>/measurements/<link id> \
  -H "Content-Type: application/json" -H "Authorization: Bearer $SUPERUSER_API_KEY" \
  -d '{"default_enabled_detectors": ["flat_value"]}'

# Or via the example script - the catalog default above, then one device's range
python3 server/mesh_things/examples/registry_curate_telemetry_catalog.py \
  --payload-kind telemetry:environment_metrics --device-uuid <device uuid> \
  --field-name temperature --range-min -40 --range-max 85
```

**When each detector fires.**

| Detector | Fires when | While it holds |
|---|---|---|
| `range` | 3 readings in a row fall outside the device's bounds (2 on devices reading every 30 min or slower) | At most one alarm per hour |
| `flat_value` | A channel reports exactly the same value for `PATTERN_DETECTION__FLAT_VALUE_HOURS` (12), over at least 3 readings | At most one alarm per hour |
| `absence` | The device is silent for `ABSENCE_DETECTION__MISSED_INTERVALS` (3) publish intervals | Nothing more. After it publishes, a new silence alarms only once `ABSENCE_DETECTION__REPEAT_FACTOR` (3) times that limit has passed since the previous alarm, held until then if due earlier |
| `completeness` | A gap longer than `QUALITY_WORKER__GAP_INTERVALS_THRESHOLD` (6) reading intervals and `QUALITY_WORKER__GAP_MIN_SECONDS` (1800), reported once when first seen; or fewer than 80% of the expected readings in 24 h, at most once a day | - |

The hourly limit (`PATTERN_DETECTION__ALARM_REPEAT_HOURS`) follows the readings'
own timestamps, so a replayed backlog raises at most one alarm per hour of data.
Alarms after the first carry `"repeat": true`. A condition that clears, by a
reading where it does not hold, for less than that hour is the same condition, so
a value hovering at a bound is one condition. There is no "cleared" event.

`completeness` leaves outages to `absence`: on a device with absence detection, a
gap at least as long as absence's silence limit is not reported, and that time
is not counted against the ratio. The ratio also skips channels that are silent
right now and devices expecting fewer than `QUALITY_WORKER__RATIO_MIN_EXPECTED`
(24) readings in the window.

`absence` timers left over from a Flink outage restart their countdown instead
of firing, so a restart does not alarm every device.

## Postprocessing

A **blueprint** is the recipe: input slots, and ordered steps each running an
algorithm. Attaching it to a device binds the slots to that device's channels;
each device then gets its own **calibration**. Derived channels are registered
on the device as soon as it is attached, so detectors and ranges can be set on
them before data arrives.

```bash
# What can run, and which parameters are per-device calibration
python3 server/mesh_things/examples/registry_manage_blueprint.py --list-algorithms

# Create the built-in NO2 example (or pass --blueprint-file)
python3 server/mesh_things/examples/registry_manage_blueprint.py

# Attach, calibrate, enable
EX=server/mesh_things/examples/registry_device_postprocessing.py
python3 $EX attach --device-uuid <device uuid> --blueprint-id <blueprint id>
python3 $EX calibrate --device-uuid <device uuid> --postprocessing-id <id> \
    --step ppb --params '{"sensitivity": 0.42, "working_zero": 220.0}'
python3 $EX enable --device-uuid <device uuid> --postprocessing-id <id>
python3 $EX show --device-uuid <device uuid>
```

`show` lists `problems` - what keeps a postprocessing from being enabled: an
unbound slot, a step without the calibration it needs, or an input produced by
a disabled postprocessing. Enabling is refused until the list is empty.

**Recalibrating** records a new calibration with a `valid_from`; readings
taken before it keep the old one. Changing **steps** means adding a blueprint
version (`registry_manage_blueprint.py --new-version-of <id> --blueprint-file
...`) and moving devices to it with `PUT .../postprocessings/{id}`
`{"blueprint_version": 2}`. Calibrations carry over for steps whose key and
algorithm are unchanged.

**Two sensors of the same build on one device** attach the same blueprint twice
with different bindings and an `output_prefix` each, since derived channel
names must be unique per device.

**Backfilling history.** A new postprocessing, or a corrected calibration, only
affects live telemetry. To recompute what is already stored:

```bash
python3 $EX backfill --device-uuid <device uuid> --postprocessing-id <id> --start 2026-09-01
python3 $EX show --device-uuid <device uuid>   # status: pending -> running -> done
```

The worker picks it up within `QUALITY_WORKER__BACKFILL_POLL_SECONDS` (60s),
runs up to 90 days per request with the calibration in force at each reading,
and publishes to the derived topic, replacing values stored for the same
times. Backfilled values never raise alarms. `--include-dependants` also
recomputes postprocessings reading this one's outputs.

### Adding an algorithm

Drop a decorated function into a module under
`server/common/algorithms/`:

```python
from . import POINTWISE, Param, algorithm

@algorithm(
    name="my_correction",
    inputs=("value", "temperature"),        # positional arguments, bound to slots by each step
    outputs=("corrected",),                 # each bound to a derived field name by a step
    params=(
        Param("coefficient", calibration=True, unit="1/degC", doc="Per-sensor drift."),
        Param("reference_temperature", unit="degC"),
    ),
    mode=POINTWISE,
    output_units={"corrected": "@value"},   # unit-preserving; see below
)
def my_correction(value, temperature, *, coefficient, reference_temperature=20.0):
    return value * (1 + coefficient * (temperature - reference_temperature))
```

**`params` must list every keyword-only argument**, and `inputs` every
positional one; a mismatch fails at import time. A parameter's default is its
signature default, and one without a default is required. `calibration=True`
marks what describes one physical sensor, which each device sets; everything
else is set on the blueprint step.

**Declare `output_units`.** A derived channel has no protobuf field to inherit
a unit from, so the algorithm is the only thing that can say what it emits.
Either a literal (`{"dew_point": "degC"}`) or `"@<input>"` when the algorithm
preserves its input's unit. Literals are checked at import time against
`mesh_things.units`, and `quantity_kind` follows from the unit automatically.
Units chain the way values do: a correction consuming `dew_point` (`degC`)
outputs `degC` too.

Then rebuild everything that imports it - **including taskmanager**, since
`common/` is `pip install`ed into the Flink image - and resubmit the
postprocessing job (see [flink.md](flink.md#redeploying-after-a-code-change)):

```bash
docker compose build registry_api quality_worker taskmanager jobmanager
docker compose up -d registry_api quality_worker taskmanager
```

Derived values go to the `derived` measurement (tagged `mesh_id`, `node_id`,
`postprocessing_id`) under the flat `derived` namespace, so they are queried,
curated and checked like real sensor fields - see
[where everything lives](#where-everything-lives).

## Where everything lives

| What | Where | Shape |
|---|---|---|
| Completeness metrics | InfluxDB, measurement **`quality`** | fields `completeness_ratio`, `observed`, `expected`, `largest_gap_seconds`; tags `mesh_id`, `node_id`, `channel`. Catalogued with units, so `?payload_kind=computed:quality` finds them |
| Fired alarms | InfluxDB, measurement **`alarms`** | fields `value`, `message`; tags `mesh_id`, `node_id`, `channel`, `detector`, `source` |
| Postprocessing outputs | InfluxDB, measurement **`derived`**; Kafka `mesh.telemetry.derived.v1` | one field per derived channel; tags `mesh_id`, `node_id`, `postprocessing_id` |
| Alarm event stream | Kafka `mesh.telemetry.alarms.v1` | the live feed both tiers publish to |
| Thresholds, intervals & switches (**config**, not metrics) | Postgres via registry, mirrored to Kafka `mesh.quality_config.v1` | `TelemetryVariantMeasurement.default_enabled_detectors`, `Measurement.enabled_detectors`/`valid_min`/`valid_max`, `Device.reading_interval_seconds`/`publish_interval_seconds`/`absence_detection_enabled` |
| Owner notifications | email, via `registry_quality_alarms_consumer` | first alarm per device emailed straight away, then one summary of every later alarm on that device when the cooldown window ends - default server-wide, overridable per owner (`Owner.alarm_email_cooldown_seconds`) |

Nothing quality-related is stored in Postgres except the **configuration** —
every measurement and every alarm is a timeseries in InfluxDB, so quality is
trendable rather than a single current-state flag.

### They're in the catalog too, not just InfluxDB

`derived` and `quality` channels are registered in the same catalog as real
sensor fields, so they're discoverable without knowing they exist:

```bash
curl -s "http://localhost:8090/measurements?kind=computed" -H "Authorization: Bearer $OWNER_API_KEY"
curl -s "http://localhost:8090/measurements?payload_kind=computed:quality" -H "Authorization: Bearer $OWNER_API_KEY"
curl -s "http://localhost:8090/devices/<device id>/measurements" -H "Authorization: Bearer $OWNER_API_KEY"
```

Every row carries an **`origin`** naming who produced the value — `measured` for
a sensor, `device` for what a node reports about itself, `computed` for what this
pipeline works out — so a frontend can separate readings from diagnostics instead
of plotting `completeness_ratio` next to `temperature`:

```
measured  environment_metrics.temperature      unit=degC
computed  derived.dew_point                    unit=None
computed  quality.completeness_ratio           unit=ratio
computed  quality.largest_gap_seconds          unit=s
```

**`alarms` is deliberately absent.** Its `value` has no stable unit (a ratio
for completeness, seconds for absence, a sensor reading for range) and
`message` is free text — it's an event log, not a measurement series. Query it
directly as an InfluxDB measurement instead.

Quality channels attach to a device through the worker publishing ordinary
`mesh.sensor_discovery.v1` events, the same path decoded telemetry fields take.
Derived channels are created by registry when a blueprint is attached, and
their rows carry `produced_by`, the postprocessing computing them.

**Why the namespaces are flat.** `derived` and `quality`, not
`derived:<blueprint>`: every postprocessing's output lands in one InfluxDB
`derived` measurement (attributed by the point's `postprocessing_id` tag), and
a catalog channel name has to match the series that actually exists. A
payload_kind of `derived:weather-v1` would yield the channel
`weather-v1.dew_point`, which is not a series anything writes — so a range set
on it could never match real data.

`quality` in particular is written on every `check_completeness` run, so the
completeness ratio is a series you can graph, not just the input to an alarm
threshold.

## Reading the results back

`derived`, `quality` and `alarms` are ordinary InfluxDB measurements carrying
the same `mesh_id`/`node_id` tags as raw telemetry, so readings serves them
through the existing routes with no special handling — and with the same
per-owner scoping:

```bash
# A postprocessing's output
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/devices/<device_uuid>?channel=derived.dew_point&start=-7d&stop=now()&window=1h&agg=mean"

# Completeness as a trend, not just an instantaneous alarm
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/devices/<device_uuid>?channel=quality.completeness_ratio&start=-7d&stop=now()"

# Every channel's latest value at once, each tagged with its origin
# ("measured" | "derived" | "quality")
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/devices/<device_uuid>/latest" | python3 -m json.tool
```

`<device_uuid>` is registry's `Device.id`, the same identifier
`GET /devices/{id}` takes. The store-native
`/meshes/<mesh_id>/nodes/<node_id>/...` form works too and returns identical
bodies — see
[api-reference.md#which-address-to-use](api-reference.md#which-address-to-use).

Which channels a device actually has is registry's question, not readings':

```bash
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8090/devices/<device_uuid>/measurements" | python3 -m json.tool
```

## Alarms

One shape from both tiers on `mesh.telemetry.alarms.v1`:

```json
{"mesh_id": "...", "device_id": 111222333, "channel": "environment_metrics.temperature",
 "detector": "absence|flat_value|range|completeness", "source": "stream|batch",
 "value": 21.4, "message": "...", "triggered_at": "...", "replay": true}
```

For `flat_value` and `range`, `triggered_at` is the time of the reading that
fired, resolved the same way storage resolves it (`mesh_things.timestamps`). A
reading processed twice therefore rewrites the alarm point already stored for
it instead of adding one. `absence` and `completeness` have no single reading,
so theirs is when the check ran.

**Replays are never emailed.** When the decode job restarts without a
checkpoint it re-decodes the raw topic from the start, and pattern detection
sees years of readings arriving in seconds. No device reports one channel that
fast: `pattern-detection-job` treats `REPLAY_BURST_READINGS` (10) readings of a
channel within `REPLAY_BURST_SECONDS` (10s) of processing time as a replay
(`mesh_things.detectors`'s `track_arrival`). Duplicates of one packet heard by a
few gateways stay below it. Every stream alarm is held for
`REPLAY_HOLD_SECONDS` (5s) before it is sent, so the first reading of a replay,
which looks live on its own, is caught too once the burst shows. Alarms from a
burst go out with `"replay": true`: the writer stores them, the email consumer
drops them. `replay` is absent otherwise.

Two consumers: `influxdb_writer` persists them to the `alarms` measurement
in their own bucket, `INFLUX__ALARMS_BUCKET` (`writer/point_builders.py`'s
`build_alarm_points`, which keys off the `detector` field and tags the point
with `mesh_id`/`node_id`/`channel`/`detector`/`source`, plus `repeat`), and
`registry_quality_alarms_consumer` emails the device's owner.

**Storage.** Each alarm is kept `INFLUX__ALARMS_RETENTION_DAYS` (30) days. Every
night at 00:30 UTC `quality_worker`'s `count_alarms` writes the previous day's
`alarm_counts` into `INFLUX__ALARM_COUNTS_BUCKET`, kept for good: one point per
device, channel and detector at midnight, with

- `alarms`: every alarm that day;
- `new_conditions`: the ones that started a condition (no `repeat` tag);
- `hours_active`: for `flat_value` and `range`, the hours with an alarm; for
  `absence`, the hours from each alarm to the device's next reading, so a device
  silent for days counts 24 on each of them. `completeness` has none.

Rerun a day with `docker compose exec quality_worker python -c "from
quality_worker.tasks import count_alarms; count_alarms('2026-09-28')"`; it
replaces that day's counts. The readings API reads alarms one by one within the
retention and the counts beyond it. `influx_init` creates both buckets on every
`up`.

`build_alarm_points` also accepts the pre-rename `node_id`/`field` spelling,
since the alarms topic is retained rather than purged and a replay of old
events must not wedge the writer. Note the writer logs "Bad message skipped"
and continues on a malformed event rather than crashing — so a shape mismatch
here fails *silently*, dropping alarms while everything still looks healthy.
If alarms stop appearing in InfluxDB, check
`docker compose logs influxdb_writer | grep -i keyerror` first.

Emails are grouped per device:

1. The first alarm on a device is emailed straight away and opens a window of
   `REGISTRY__ALARM_EMAIL_COOLDOWN_SECONDS` (default 1h).
2. Every later alarm on that device during the window, from **any** detector or
   channel, is held in Redis: a count, the first and last `triggered_at`, and
   the latest value and message per `(detector, channel)`.
3. When the window ends, one summary email lists what was held. Nothing is sent
   if nothing was held. The next new alarm opens a new window.

Exceptions:

- **`repeat` alarms are counted in an open window's summary.** Outside one, a
  re-raise is emailed as a reminder ("Still active: ...") once
  `REGISTRY__ALARM_REMINDER_HOURS` (default 24) have passed since the condition was
  last emailed, by its start, a summary or an earlier reminder; otherwise it is only
  stored. A condition with no record (it started before reminders, or Redis was
  cleared) is reminded at its next re-raise. The record is
  `registry:alarm-condition:<mesh>:<device>|<detector>|<channel>` and lapses two
  days after the re-raises stop. `0` turns reminders off.
- **`absence` is emailed straight away**, even during an open window, at most once
  per device per day (`registry:absence-emailed:<mesh>:<device>`). A later one the
  same day is treated like a `repeat`, so a device publishing slower than its
  configured interval does not email all day.
- **`replay` alarms are never emailed.**

The consumer checks for ended windows every 10s, from its poll loop (there is no
scheduler). Windows and held alarms live in Redis (`registry:alarm-windows`, a
sorted set scored by closing time, and one `registry:alarm-held:<mesh>:<device>`
hash per window), which is persisted with AOF so a redeploy does not drop
pending summaries. A summary that fails to send stays pending and is retried on
the next check. This assumes a single consumer replica.

The env var is only the server-wide default: an owner can set their own window
via `PUT /owners/me`'s `alarm_email_cooldown_seconds` (`0` up to 2592000 seconds
/ 30 days; `null` reverts to the server default). `0` emails every alarm and
sends no summaries — see
[Managing your own owner record](api-reference.md#managing-your-own-owner-record-ownersme)
in the API reference.

## Checking it works

```bash
# Alarms flowing?
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka:29092 --topic mesh.telemetry.alarms.v1 --timeout-ms 30000

# Did the catalog edit reach Flink? (compacted - shows current config per key)
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka:29092 --topic mesh.quality_config.v1 \
  --from-beginning --property print.key=true --timeout-ms 10000

# Emails (dev)
open http://localhost:8025          # mailhog

# Completeness on demand
docker compose exec quality_worker python -c "
from quality_worker import celery_app
from quality_worker.tasks import check_completeness
print(check_completeness.apply(args=['<device uuid>']).get())"
```

## Troubleshooting

**No alarms at all.** Most likely nothing is enabled: alarms are opt-in, so a
freshly discovered channel reports `effective_detectors: []` and stays quiet. See
[Enabling alarms](#enabling-alarms). Past that, a detector still needs its
inputs - no `valid_min`/`valid_max` set on the device's own `Measurement` row
means no range check, and no interval means no absence timer, deliberately,
because a guessed interval produces meaningless alarms. Confirm config
actually reached Flink by consuming `mesh.quality_config.v1`.

**Alarms fire but no email.** Check the owner is verified (`is_active`) and
has an email; check whether the device already has an open window (server
default, or the owner's own `alarm_email_cooldown_seconds`), in which case the
alarm is held for the summary (`redis-cli ZRANGE registry:alarm-windows 0 -1
WITHSCORES`); check
`registry-quality-alarms-consumer` logs. It reads from `latest`, so
alarms published before it first started are never emailed.

**Alarms fire on Kafka but never reach InfluxDB.** `influxdb_writer` logs
"Bad message skipped" and continues rather than crashing, so a mismatch
between the alarm event shape and `build_alarm_points` silently drops every
alarm while the pipeline looks healthy. Confirm with:

```bash
docker compose logs influxdb_writer --since 10m | grep -iE "KeyError|Bad message skipped"
```

**`ImportError: cannot import name '<x>' from 'common'` in a Flink job.**
You changed `common/` without rebuilding taskmanager — see
[flink.md](flink.md#redeploying-after-a-code-change). It surfaces
misleadingly as "Failed to deserialize consumer record".

**An enabled postprocessing produces nothing.** Its inputs never have samples
close enough in time to join. `show` prints the effective tolerance: half the
device's `reading_interval_seconds` unless set on the postprocessing, 30s
without either. Channels a device reports in separate packets can be further
apart than that. The taskmanager log (`docker compose logs taskmanager`) also
reports, once per step, rows skipped because the algorithm raised, such as a
division by a zero sensitivity.

**A backfill finishes with 0 values.** Nothing was stored for its inputs in
that range, or they never joined, as above. A failed one carries the reason in
`error`.
