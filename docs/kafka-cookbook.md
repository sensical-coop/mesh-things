# Kafka cookbook

All commands assume the `kafka` container is running (`docker compose up -d kafka`) and
are run from the repo root. Kafka's CLI tools live at `/opt/kafka/bin/` inside the
container.

## Topic management

```bash
# List all topics
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list

# Create a topic (plain, time-retained)
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic my.test.topic --partitions 1 --replication-factor 1

# Create a compacted topic (for changelog-style topics like mesh.keys.v1)
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic my.test.topic --partitions 1 --replication-factor 1 \
  --config cleanup.policy=compact

# Describe a topic (partitions, config)
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic mesh.telemetry.raw.v1

# Delete a topic (safe cleanup after ad hoc testing)
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --delete --topic my.test.topic
```

## Checking message counts / offsets

`kafka-console-consumer` with `--from-beginning` can hang waiting for messages that
don't exist. Check the end offset first to know if there's anything to read:

```bash
docker exec kafka /opt/kafka/bin/kafka-get-offsets.sh --bootstrap-server localhost:9092 \
  --topic mesh.telemetry.raw.v1
# mesh.telemetry.raw.v1:0:<end-offset>   <- 0 means the topic is empty
```

## Consuming / inspecting messages

```bash
# Read the next few messages as they arrive
docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic mesh.telemetry.decoded.v1 --max-messages 5 --timeout-ms 15000

# Read from the beginning (history), showing the record key too
docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic mesh.keys.v1 --from-beginning --max-messages 10 --timeout-ms 8000 \
  --property print.key=true

# Same idea for the node reject-list changelog (key is "mesh_id:device_id", not
# gateway_id - see architecture.md#device-registration-and-the-is_allowed-gate)
docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic mesh.node_rejections.v1 --from-beginning --max-messages 10 --timeout-ms 8000 \
  --property print.key=true

# Telemetry-variant/Measurement discovery events (not compacted, no record key - same shape
# as mesh.devices.v1) - see architecture.md#device-telemetry-variant--measurement-catalog
docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic mesh.sensor_discovery.v1 --max-messages 5 --timeout-ms 15000
```

`mesh.keys.v1`, `mesh.node_rejections.v1`, `mesh.quality_config.v1`,
`mesh.postprocessing_config.v1` and `mesh.sink_config.v1` are only ever produced by
`registry_api` itself (`registry/kafka_publisher.py`'s `KeyEventPublisher`, via
`POST`/`PUT`/`DELETE` on `/devices`, `/telemetry-variants`,
`/telemetry-variants/{id}/measurements/{link_id}`, `/devices/{uuid}/postprocessings`
and `PUT /owners/{id}`) — publish through the API rather than by
hand, since registry is the source of truth they are rebuilt from. A `mesh.node_rejections.v1` record looks like:

```json
{"kind": "node_rejection", "key": "<mesh_id>:555000222", "mesh_id": "<mesh_id>", "device_id": 555000222, "op": "upsert", "updated_at": "2026-09-03T00:00:00+00:00"}
```

`"op": "upsert"` means rejected (present in `NODE_REJECTED_STATE`); `"op": "delete"`
means unrejected/removed from it — absence of any record for a key means the same thing
as `"op": "delete"`, matching the default-open model.

`mesh.sensor_discovery.v1` is produced by `flink-job` (`decode_job.py`), not
`registry_api` — same producer as `mesh.devices.v1`, same reasoning (field
names only, never values; not deduplicated in Flink, `registry_sensor_
discovery_consumer`'s `get_or_create`s handle that cheaply on the Postgres side).
`quality_worker` publishes here too, reusing the same contract to register a
device's computed `quality` channels rather than needing its own endpoint.
Derived channels are not discovered: registry creates them when a blueprint is
attached. A record looks like:

```json
{"mesh_id": "<mesh_id>", "device_id": 111222333, "payload_kind": "telemetry:environment_metrics", "fields": ["temperature", "relative_humidity"], "op": "upsert"}
```

`mesh.telemetry.raw.v1` contains raw protobuf bytes and will print as garbled binary —
that's expected; use the decode-side topics (`mesh.telemetry.decoded.v1` and later) for
human-readable JSON.

A `TimeoutException` after "Processed a total of N messages" just means the consumer hit
`--timeout-ms` with no more data — not an error.

### Using `simple_test_consumer.py` instead

`server/scripts/simple_test_consumer.py` subscribes to every topic named by a
`*__KAFKA_TOPIC` env var at once — handy for watching the whole pipeline during manual
testing:

```bash
cd server
KAFKA_BOOTSTRAP_LOCAL=localhost:9092 python3 scripts/simple_test_consumer.py --local
```

## Injecting test data at each pipeline stage

### 1. Raw stage (`mesh.telemetry.raw.v1`) — needs valid protobuf

Hand-writing a Meshtastic `ServiceEnvelope` isn't feasible via shell, so use the helper
script `server/scripts/publish_test_envelope.py`. It builds a real protobuf
envelope (Telemetry, Position, or NodeInfo), optionally AES-CTR encrypts it, and
publishes it.

**Registration is required first, at the mesh/gateway level — encrypted or
plaintext.** Since the
[registered-gateways-only gate](architecture.md#registered-gateways-only-gate) landed,
`decode_job.py` drops any packet relayed by a gateway that hasn't been registered via
the registry role, before it even looks at whether the packet is encrypted. An
owner must exist, then a mesh, then a gateway **Device** for it:

```bash
OWNER_API_KEY=$(curl -s -X POST http://localhost:8090/owners -H "Content-Type: application/json" \
  -d '{"name": "Test Owner", "email": "test@example.com"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['api_key'])")

MESH_ID=$(curl -s -X POST http://localhost:8090/meshes -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"channel_id": "LongFast", "psk_b64": ""}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

curl -s -X POST http://localhost:8090/devices -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d "{\"device_id\": 111222333, \"mesh_id\": \"$MESH_ID\", \"is_gateway\": true}"
```

The owner's identity is derived from the bearer token, not passed in the body — see
[api-reference.md#authentication-for-mesh-and-device-mutations](api-reference.md#authentication-for-mesh-and-device-mutations).
`$OWNER_API_KEY` is only ever shown in that `POST /owners` response; save it if you want
to update/delete this registration later. In this example the gateway and the reporting
device are the same node (`111222333`), which is the common case for a lone test node,
but any `--node-id` sharing this `channel_id`/`psk_b64` would decode too, gateway or
not — only the *relaying* node needs to be registered as a gateway; the reporting node
itself gets auto-discovered as a `Device` with `is_gateway: false` the moment its first
packet decodes (see
[architecture.md#device-registration-and-the-is_allowed-gate](architecture.md#device-registration-and-the-is_allowed-gate)).

Then publish test packets for that same node_id/channel_id:

```bash
cd server
export PYTHONPATH=$(pwd)

# --gateway-id must match the *registered gateway's* device_id, formatted as
# Meshtastic's own "!" + 8 lowercase hex digits - here that's 111222333, the same
# node as --node-id since this example registers that node as its own mesh's gateway.
# The script's --gateway-id default ("!testgw") won't match any registration and the
# packet will be silently dropped - see architecture.md#registered-gateways-only-gate.
GATEWAY_ID=$(python3 -c "print(f'!{111222333:08x}')")

# Plaintext telemetry
python3 scripts/publish_test_envelope.py --topic mesh.telemetry.raw.v1 \
  --kind telemetry --node-id 111222333 --gateway-id "$GATEWAY_ID" --packet-id 1 --battery-level 87 --voltage 4.01

# Plaintext position
python3 scripts/publish_test_envelope.py --topic mesh.telemetry.raw.v1 \
  --kind position --node-id 111222333 --gateway-id "$GATEWAY_ID" --packet-id 2 --latitude 41.3851 --longitude 2.1734 --altitude 42

# Plaintext nodeinfo
python3 scripts/publish_test_envelope.py --topic mesh.telemetry.raw.v1 \
  --kind nodeinfo --node-id 111222333 --gateway-id "$GATEWAY_ID" --packet-id 3 --long-name "My Node" --short-name "MN"

# Environment telemetry (temperature) instead of device_metrics
python3 scripts/publish_test_envelope.py --topic mesh.telemetry.raw.v1 \
  --kind telemetry --node-id 111222333 --gateway-id "$GATEWAY_ID" --packet-id 4 --temperature 21.5

# Encrypted - re-register the mesh above with the real psk_b64 instead of "" first,
# using the *same* key here (this republishes every gateway on that mesh with it)
KEY_B64=$(python3 -c 'import os,base64;print(base64.b64encode(os.urandom(32)).decode())')
echo "Update the mesh's psk_b64 to: $KEY_B64 (PUT /meshes/$MESH_ID)"
python3 scripts/publish_test_envelope.py --topic mesh.telemetry.raw.v1 \
  --kind telemetry --node-id 111222333 --gateway-id "$GATEWAY_ID" --packet-id 5 --battery-level 50 \
  --encrypt-with-key "$KEY_B64"
```

The `position` and `nodeinfo` packets above don't just decode to
`mesh.telemetry.decoded.v1` - `decode_job.py` also opportunistically folds their fields
into the `mesh.devices.v1` sighting event it always publishes on a successful decode
(`latitude`/`longitude` from `position`, `name`/`short_name`/`hardware_type`/`role` from
`nodeinfo`), which `consume_device_sightings.py` applies to the `Device` row unless the
mesh owner has already pinned that field group via `PUT`/`POST /devices` - see
[architecture.md#auto-filled-location-and-nodeinfo-fields](architecture.md#auto-filled-location-and-nodeinfo-fields).
`GET /devices/<id>` after publishing the `position`/`nodeinfo` packets above (and giving
the pipeline a moment to run) should show the new `latitude`/`longitude`/`name`/
`short_name`/`hardware_type`/`role` values.

Likewise, the `telemetry` packets above also publish to `mesh.sensor_discovery.v1`
(field names only, e.g. `battery_level` for the `device_metrics` example) - see
[architecture.md#device-telemetry-variant--measurement-catalog](architecture.md#device-telemetry-variant--measurement-catalog).
`GET /devices/<id>/telemetry-variants` afterward should show
`telemetry:device_metrics`, and `GET /devices/<id>/measurements` a
`device_metrics.battery_level` channel.

Passing `--rx-time` (epoch seconds) is worth doing deliberately — it defaults to `0`
(1970-01-01), which the point-builders will use as the InfluxDB point's timestamp when
the payload itself has no `time` field, making the result invisible to any query with a
realistic `range`/`lookback` window unless you know to look there.

Run `python3 scripts/publish_test_envelope.py --help` for the full flag list
(`--channel-id`, `--gateway-id`, `--rx-time`, `--bootstrap` all have sensible
defaults, but `--gateway-id`'s default won't be registered anywhere - always pass one
that matches a real `Device.device_id` registered with `is_gateway: true`).

**Isolate your testing**: point `--topic` at a scratch topic (`test.mesh.raw`) instead of
the real `mesh.telemetry.raw.v1` if you don't want synthetic data flowing into your real
InfluxDB/S3. Create it first with the topic-management commands above, and remember to
`--delete` it when done.

### 2. Decoded stage (`mesh.telemetry.decoded.v1`) — plain JSON, no protobuf needed

Since this topic is just JSON, `kafka-console-producer` works directly — useful for
testing the sinks (Influx writer, S3 writer) in isolation, bypassing decode entirely:

```bash
docker exec -i kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:9092 \
  --topic mesh.telemetry.decoded.v1 <<'EOF'
{"node_id": 999999001, "packet_id": 1, "portnum": 67, "rx_time": 1700000000, "hop_start": 2, "channel_id": "TestVerify", "gateway_id": 999999002, "payload_kind": "telemetry:device_metrics", "payload": {"time": 1700000010, "device_metrics": {"battery_level": 88, "voltage": 4.05}}}
EOF
```

Or from Python (useful for multiple messages / a script):

```python
import json
from kafka import KafkaProducer

producer = KafkaProducer(bootstrap_servers="localhost:9092", value_serializer=lambda v: json.dumps(v).encode())
producer.send("mesh.telemetry.decoded.v1", value={
    "node_id": 999999001, "packet_id": 2, "portnum": 3, "rx_time": 1700000001,
    "hop_start": 2, "channel_id": "TestVerify", "gateway_id": 999999002,
    "payload_kind": "position",
    "payload": {"latitude_i": 413830000, "longitude_i": 24540000, "altitude": 100},
})
producer.flush()
```

Valid `payload_kind` values and what they map to in `writer/point_builders.py`:
`telemetry:device_metrics`, `telemetry:environment_metrics`, `telemetry:power_metrics`,
`telemetry:air_quality_metrics`, `telemetry:local_stats`, `telemetry:health_metrics`,
`telemetry:host_metrics`, `position`, `nodeinfo`, or `portnum:<n>` (generic fallback).

### Postprocessing plans and derived telemetry

`mesh.postprocessing_config.v1` carries, per device, every enabled plan in
dependency order, fully resolved by registry: concrete channels, blueprint
configuration and the whole calibration history. `postprocessing-job` holds it
as broadcast state and replaces a device's entry whole on each event:

```json
{"kind": "postprocessing_plans", "key": "<mesh_id>:431637602", "mesh_id": "<mesh_id>", "device_id": 431637602,
 "op": "upsert", "updated_at": "...",
 "plans": [{"id": "<postprocessing id>", "blueprint_id": "<blueprint id>", "blueprint_version": 1,
            "tolerance_seconds": 150.0,
            "steps": [{"key": "cal", "function_name": "offset_scale",
                       "inputs": {"value": "environment_metrics.temperature"},
                       "outputs": {"calibrated": "derived.temperature_calibrated"},
                       "params": {},
                       "calibrations": [{"valid_from": 1790000000.0, "params": {"offset": -0.5}}]}]}]}
```

`"op": "delete"` with no plans stops postprocessing for the device. If the topic
is lost, rebuild it from Postgres:

```bash
docker compose exec registry_api python manage.py publish_postprocessing_config
```

Derived values come out on `mesh.telemetry.derived.v1` in the decoded envelope
shape, one event per postprocessing and timestamp. Backfilled ones add
`"backfill": true`:

```json
{"mesh_id": "<mesh_id>", "node_id": 431637602, "rx_time": 1790000000, "payload_kind": "computed:derived",
 "payload": {"derived": {"temperature_calibrated": 21.0}},
 "postprocessing_id": "<postprocessing id>", "blueprint_id": "<blueprint id>", "blueprint_version": 1}
```

To exercise a device's plans without a radio, produce a decoded event for it
and read the derived topic back. The event is stored like real telemetry, so
use a throwaway device:

```python
import json, time
from kafka import KafkaProducer

producer = KafkaProducer(bootstrap_servers="localhost:9092", value_serializer=lambda v: json.dumps(v).encode())
producer.send("mesh.telemetry.decoded.v1", value={
    "mesh_id": "<mesh_id>", "node_id": 431637602, "packet_id": 1, "rx_time": int(time.time()),
    "payload_kind": "telemetry:environment_metrics", "payload": {"environment_metrics": {"temperature": 21.5}},
})
producer.flush()
```

```bash
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka:29092 --topic mesh.telemetry.derived.v1 --timeout-ms 15000
```

### Device sinks (`mesh.sink_config.v1`)

The sinks each device's readings go to, as effective state: `archive` is listed only
while the device has `archive_enabled`, is allowed, and its mesh's owner is an
operator. `s3_writer` replays it before consuming and archives only listed devices:

```json
{"kind": "device_sinks", "key": "<mesh_id>:539824877", "mesh_id": "<mesh_id>", "device_id": 539824877,
 "sinks": ["archive"], "op": "upsert", "updated_at": "..."}
```

An empty list is published as `"op": "delete"`. To see what is archived:

```bash
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server kafka:29092 \
  --topic mesh.sink_config.v1 --from-beginning --timeout-ms 5000 --property print.key=true
```

If the topic is lost, rebuild it from Postgres:

```bash
docker compose exec registry_api python manage.py publish_sink_config
```

**`mesh.rules.v1` is superseded** — `pattern_detection_job.py` no longer reads it.
Quality thresholds now come from the registry catalog via `mesh.quality_config.v1`
(below). The topic still exists but has no consumer.

### Data-quality config (`mesh.quality_config.v1`)

Unlike the topic above, **don't publish to this one by hand** — registry owns it. It's
written automatically when you edit the catalog or a device's intervals, which is what
makes the catalog the single source of truth for the quality checks:

```bash
# Catalog default detectors for a channel -> publishes a "variant_config" event
curl -s -X PUT http://localhost:8090/telemetry-variants/<telemetry variant id>/measurements/<link id> \
  -H "Content-Type: application/json" -H "Authorization: Bearer $SUPERUSER_API_KEY" \
  -d '{"default_enabled_detectors": ["flat_value"]}'

# A device's own detectors and range bounds -> publishes a "measurement_alarms" event
curl -s -X PUT http://localhost:8090/devices/<device uuid>/measurements/<measurement id> \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"enabled_detectors": ["range"], "valid_min": -40, "valid_max": 85}'

# Device intervals -> publishes a "device_intervals" event
curl -s -X PUT http://localhost:8090/devices/<device id> \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"reading_interval_seconds": 300, "publish_interval_seconds": 3600}'
```

Inspecting what the Flink jobs currently hold (compacted, so this shows the live
config per key):

```bash
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka:29092 --topic mesh.quality_config.v1 \
  --from-beginning --property print.key=true --timeout-ms 10000
```

```
environment_metrics.temperature  {"kind": "variant_config", "key": "environment_metrics.temperature",
                                  "payload_kind": "telemetry:environment_metrics", "field_name": "temperature",
                                  "default_reading_interval_seconds": 900, "default_enabled_detectors": ["flat_value"], "op": "upsert"}
<mesh_id>:777888                 {"kind": "device_intervals", "key": "<mesh_id>:777888", "mesh_id": "...",
                                  "device_id": 777888, "reading_interval_seconds": 300,
                                  "publish_interval_seconds": 3600, "op": "upsert"}
<mesh_id>:777888:environment_metrics.temperature  {"kind": "measurement_alarms",
                                  "key": "<mesh_id>:777888:environment_metrics.temperature", "mesh_id": "...",
                                  "device_id": 777888, "channel": "environment_metrics.temperature",
                                  "enabled_detectors": ["range"], "valid_min": -40.0, "valid_max": 85.0, "op": "upsert"}
```

The `kind` field routes each event to the right lookup in broadcast state, the same way
`decode_job.py` handles its two merged broadcast streams. Clearing **both** of a
device's intervals publishes `"op": "delete"` rather than an upsert of nulls — that's
what stops absence monitoring for a device that has already gone silent.

### Alarms (`mesh.telemetry.alarms.v1`)

Both quality tiers publish one shape here:

```bash
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka:29092 --topic mesh.telemetry.alarms.v1 --timeout-ms 30000
```

```json
{"mesh_id": "...", "device_id": 111222333, "channel": "environment_metrics.temperature",
 "detector": "absence|flat_value|range|completeness", "source": "stream|batch",
 "value": 21.4, "message": "...", "triggered_at": "..."}
```

Injecting a synthetic sighting is the deterministic way to test absence detection
without waiting on real hardware — it arms the timer for that device:

```bash
docker compose exec kafka /opt/kafka/bin/kafka-console-producer.sh \
  --bootstrap-server kafka:29092 --topic mesh.sensor_discovery.v1 <<'EOF'
{"mesh_id": "<mesh_id>", "device_id": 777888, "payload_kind": "telemetry:environment_metrics", "fields": ["temperature"], "op": "upsert"}
EOF
```

With `publish_interval_seconds` set on that device, an `absence` alarm appears after
`ABSENCE_DETECTION__MISSED_INTERVALS` × the interval (floored at 60s), once: it does
not repeat while the device stays silent. See
[data-quality.md](data-quality.md).

## Full end-to-end smoke test

With `mqtt_kafka_bridge`, `flink-job`, `registry_api`, `influxdb_writer`, and
`s3_writer` all running. This is the exact scenario the
[registered-gateways-only gate](architecture.md#registered-gateways-only-gate) exists
for: prove a packet relayed by an unregistered gateway is dropped, then prove the same
class of packet decodes once that gateway is registered.

```bash
cd server
export PYTHONPATH=$(pwd)
GATEWAY_ID=$(python3 -c "print(f'!{555000111:08x}')")

# 1. Baseline: note the current end offset
docker exec kafka /opt/kafka/bin/kafka-get-offsets.sh --bootstrap-server localhost:9092 \
  --topic mesh.telemetry.decoded.v1

# 2. Publish a plaintext packet relayed by a gateway that has never been registered
python3 scripts/publish_test_envelope.py --topic mesh.telemetry.raw.v1 \
  --kind telemetry --node-id 555000111 --gateway-id "$GATEWAY_ID" --packet-id 1 --battery-level 77 --channel-id LongFast

# wait a few seconds, then check the offset again - it must be UNCHANGED. If it's not,
# something regressed the gate.
docker exec kafka /opt/kafka/bin/kafka-get-offsets.sh --bootstrap-server localhost:9092 \
  --topic mesh.telemetry.decoded.v1

# 3. Register a mesh, then that gateway Device on it (owner identity/mesh ownership
# are both derived server-side, never from the request body)
OWNER_API_KEY=$(curl -s -X POST http://localhost:8090/owners -H "Content-Type: application/json" \
  -d '{"name": "Smoke Test", "email": "smoke@example.com"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['api_key'])")
MESH_ID=$(curl -s -X POST http://localhost:8090/meshes -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"channel_id": "LongFast", "psk_b64": ""}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -X POST http://localhost:8090/devices -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d "{\"device_id\": 555000111, \"mesh_id\": \"$MESH_ID\", \"is_gateway\": true}"

# 4. Publish a NEW packet through the same gateway (the earlier dropped one won't be
# replayed - flink-job's raw-topic offset already advanced past it)
python3 scripts/publish_test_envelope.py --topic mesh.telemetry.raw.v1 \
  --kind telemetry --node-id 555000111 --gateway-id "$GATEWAY_ID" --packet-id 2 --battery-level 80 --channel-id LongFast --rx-time $(date +%s)

# wait a few seconds - the offset must now have advanced
docker exec kafka /opt/kafka/bin/kafka-get-offsets.sh --bootstrap-server localhost:9092 \
  --topic mesh.telemetry.decoded.v1
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/meshes/$MESH_ID/nodes/555000111/latest?payload_kind=telemetry:device_metrics" | python3 -m json.tool
```

Then check `docker logs flink-job --tail 20`, `docker logs influxdb-writer --tail 20`,
`docker logs s3-writer --tail 20`, and query InfluxDB / MinIO (see
[api-reference.md](api-reference.md) and [debugging.md](debugging.md)) for anything
unexpected.
