# Testing

## Unit / integration tests (pytest)

No Docker required — about 620 tests run in a few seconds. This suite covers the
Flink/codec/writer layer, the server-only `common/` modules, the batch tier's pure logic
and the `mesh-things` package (`server/mesh_things/tests/`); the registry and
readings roles are Django apps with their own test runner (see below) — they're not
collected by pytest.

```bash
pip install "./server/mesh_things[codec]" \
  -r server/requirements.txt -r server/requirements-test.txt
pytest   # picks up both test folders and PYTHONPATH via pytest.ini
```

`pytest.ini` puts `mesh_things/src` on the path, so the tests always run the working
tree's package rather than whichever copy was last installed. The package's own tests
also run on a bare install: `pytest server/mesh_things/tests`.

`requirements-test.txt` is separate because `setup.py` reads `requirements.txt`
into `install_requires`, so anything listed there ships in every image that runs
`pip install .` - the pipeline image and the Flink image both do. It holds
pandas, pytest, mypy and the `types-*` stubs; moving them out took 73 MiB off
the pipeline image. Keep it that way: a package added to `requirements.txt`
because a test needed it gets shipped to production.

Run a single file or test:

```bash
pytest server/mesh_things/tests/test_codec.py -v
pytest server/tests/test_point_builders.py::test_position_is_persisted_not_dropped -v
```

What's covered:

| File | Covers |
|---|---|
| `mesh_things/tests/test_codec.py` | protobuf decode/decrypt round-trips, wrong-key handling, key-material parsing |
| `test_point_builders.py` | InfluxDB point construction per portnum, including the alarm event shape and `mesh_id` tagging |
| `test_s3_writer.py` | Parquet row shape (`_flatten()`), one object per mesh and hour, and the archive gate: only devices listed on `mesh.sink_config.v1` are kept |
| `mesh_things/tests/test_detectors.py` | stuck-value/range-check detectors |
| `test_algorithms.py` | the postprocessing algorithm registry (discovery, `Param` declarations checked against signatures, step and calibration validation) and the shipped algorithms, including the `offset_scale`/`lookup_table` calibration curves |
| `test_postprocessing_engine.py` | the postprocessing engine: the streaming join (skewed and batched channels, pruning, JSON state), step chaining within and across plans, calibration in force at each sample's time, fail-soft rows, plan round-trips |
| `test_postprocessing_stream.py` | what `postprocessing_job.py` does around the engine: decoded events to observations on storage timestamps, config events to plans, derived events, and the contract with pattern detection and the Influx writer |
| `mesh_things/tests/test_env_helpers.py` | `mesh_things.env` - "set but empty" env vars falling back to their default rather than to False/[] |
| `test_deploy_ports.py` | the deployment contract: loopback-only production bindings, authenticated admin UIs, one-shot idempotent Flink submitters, memory limits, and the dev/prod Django settings split |
| `test_stream_quality.py` | channel naming (`"<measurement>.<field>"`, which four components must agree on) and interval-derived flat-value windows |
| `test_quality_executor.py` | completeness/gap analysis including derived channels and their inputs' interval, and backfill batching over stored history |
| `test_writer_health.py` | InfluxDB/S3 writer health-check logic (real sink connectivity, not just Kafka) |
| `test_decode.py` | protobuf decode helpers exercised end to end through the pipeline entrypoint |
| `test_gateway.py` | gateway/node ID matching and the registered-gateways-only gate |
| `mesh_things/tests/test_influx_query.py` | Flux query construction for the readings role |
| `test_mqtt_client_id.py` | per-replica MQTT client ID derivation for the bridge |
| `test_source_gate.py` | source topic naming and namespaces, the bridge's subscription filters, and the gate that accepts a gateway only through its mesh's source |
| `test_sink_dispatcher.py` | MQTT sink routing from `mesh.sink_config.v1` (mesh and device attachments, streams, backfills), sink topics staying outside the bridge's filters, and publish-then-commit with a rewind on failure |
| `test_config_state.py` | the `mesh.keys.v1`/`mesh.node_rejections.v1` state shared by the lite decoder and the bridge, and replaying a compacted topic to its end |
| `test_node_ids.py` | node ID parsing/formatting across the `!aabbccdd` and integer forms |
| `test_monitor.py` | the server monitor: the probe decodes with its mesh's key and carries its marker, alert thresholds, reminders and recovery, and the status and on-demand routes (token, one shared probe, reuse within the minimum interval, the timeout cap) |
| `test_units.py` | unit handling in point construction and catalog decoration |
| `mesh_things/tests/test_channels_vocabulary.py` | the `payload_kind` and channel vocabulary |
| `mesh_things/tests/test_catalog.py` | which `Telemetry` protobuf fields become catalogued channels |
| `mesh_things/tests/test_portnums.py` | portnum names, including `ENCRYPTED` and unknown portnums |

The Flink jobs' UDFs themselves aren't unit-tested — they need a PyFlink runtime, so
their pure logic lives in `common/` and `mesh_things` (imported lazily inside `open()`, the convention
every UDF here follows) and the jobs are exercised by
[flink.md](flink.md#redeploying-after-a-code-change)'s live redeploy sequence instead.

## Registry role tests (Django, real Postgres)

The registry and readings roles are two apps (`registry`, `readings`) inside one
Django + DRF project, `server/api/`, sharing one `manage.py`. Registry's
tests live under `api/registry/tests/` and run via `manage.py test`, not pytest.
Unlike the pytest suite above, these need a **real Postgres** — `Owner` is a custom
`AUTH_USER_MODEL` and Django's test runner creates/tears down a real test database
(`test_<REGISTRY__DB_DSN database>`) around a live connection rather than mocking one:

```bash
docker compose up -d postgres
cd server/api
pip install -r requirements.txt -e "../mesh_things[codec]"
REGISTRY__DB_DSN=postgresql://<user>:<pass>@localhost:5432/<db> python manage.py test registry
```

418 tests, covering owner/mesh/device CRUD (both the gateway and node roles of the
unified `Device` model), Kafka-publish-per-mutation (`mesh.keys.v1` for gateways,
`mesh.node_rejections.v1` for node `is_allowed` transitions), PSK-rotation
republishing, rollback on publish failure, superuser bypass, the `createsuperuser`
management command, `seed_from_env`, login and email verification flows
(`test_login.py`, `test_email_verification.py`), API-key auth and per-owner
throttling (`test_authentication.py`, `test_auth.py`, `test_throttling.py`), the
grants `provision_read_role` gives the readings role's Postgres user
(`test_provision_read_role.py`), the location/NodeInfo auto-fill + sticky-override
behavior (`test_devices.py`'s `DeviceTelemetryAutoFillTests`), the `(mesh_id,
device_id)` shape `GET /owners/me`/`GET /owners/me/devices` return (see
[architecture.md#roles-registry-and-readings](architecture.md#roles-registry-and-readings)
for why `device_id` alone isn't enough), sensor/measurement catalog discovery and the
superuser-only `MeasurementType`/`TelemetryVariant`/`TelemetryVariantMeasurement` CRUD
(`test_sensor_discovery.py`, `test_seed_measurement_catalog.py`), postprocessing
blueprints and versions, device attachments, calibration history, chaining and
cycles, rollback on publish failure and backfills (`test_postprocessing.py`),
device interval publishing (`test_quality_config_publish.py`), quality-alarm-to-email routing including the
per-device window and its summary email (`test_quality_alarms.py`), and MQTT sources: the operator
role, source CRUD and its rollback on EMQX failure, attaching meshes, `sync_sources`
(`test_sources.py`) and the EMQX REST calls themselves (`test_emqx_client.py`), and the
per-device archive opt-in: who may set it, what it publishes to `mesh.sink_config.v1`,
rollback, role changes and deletions (`test_archive_sinks.py`), and MQTT sinks:
credentials shown once, attachments and their rollback, streams, rotation, terms and
lapses, `sync_sinks` (`test_sinks.py`). Kafka and EMQX are
mocked (`kafka_publisher._publisher` and `emqx_client._client` are swapped for fakes in
`registry/tests/helpers.py`) — only Postgres needs to be real.

## Readings role tests (Django, real Postgres)

Readings has no models of its own — it reads the same Postgres database as registry,
through a separate read-only role (`provision_read_role`, see above), plus InfluxDB
for the actual values. Authentication is a direct lookup against `registry`'s
`Owner`/`Device` tables now, not an HTTP call to another service, so these tests
need the same real Postgres as the registry suite; only InfluxDB is mocked:

```bash
docker compose up -d postgres
cd server/api
REGISTRY__DB_DSN=postgresql://<user>:<pass>@localhost:5432/<db> python manage.py test readings
```

42 tests, covering route shapes, per-`(mesh_id, node_id)` device scoping (not
`node_id` alone — see
[architecture.md#roles-registry-and-readings](architecture.md#roles-registry-and-readings)),
the no-`?payload_kind=` `/latest` variant (combined cross-measurement query + the
registry `MeasurementType` catalog decoration, `readings/measurement_catalog.py`),
and Flux-query construction including rejecting an invalid `mesh_id`/`agg` before it
reaches Flux (`test_influx_client.py`), with the `InfluxQueryClient` singleton mocked
(`readings/tests/test_views.py`). The archive routes (`test_archive.py`) cover who
reaches a mesh's archive, the session policy, the `AssumeRole` arguments for MinIO and
AWS, and the routes switched off on lite or without STS, with the S3 and STS clients
mocked.

If you change the *shape* of a request/response in either API, these Django test suites
are the fast feedback loop; use the live smoke tests below to confirm actual service
behavior end to end.

## Running a Flink job locally (no cluster needed)

Every job in `server/flink/` supports `--local`, which runs PyFlink's embedded
mini-cluster instead of submitting to `jobmanager`. This is by far the fastest way to
iterate on job logic.

```bash
cd server/flink
export PYTHONPATH=/path/to/mesh-things/server
export KAFKA_BOOTSTRAP_LOCAL=localhost:9092   # requires: docker compose up -d kafka
```

Point every topic env var at scratch topics so you don't touch real data, then run with
a timeout (these jobs run forever otherwise). Since the
[registered-gateways-only gate](architecture.md#registered-gateways-only-gate) landed,
`decode_job.py` needs both a raw topic *and* a keys topic — nothing decodes without a
matching gateway registration, even locally, and there's no more
`MESH_CH0_ENCRYPTION_KEY` fallback to lean on:

```bash
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic test.mesh.raw --partitions 1 --replication-factor 1
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic test.mesh.decoded --partitions 1 --replication-factor 1
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic test.mesh.keys --partitions 1 --replication-factor 1 --config cleanup.policy=compact

MQTT_BRIDGE__KAFKA_TOPIC=test.mesh.raw \
PROTO_DECODE__KAFKA_TOPIC=test.mesh.decoded \
REGISTRY__KAFKA_TOPIC=test.mesh.keys \
timeout 40 python3 decode_job.py --local
```

Publish a registration event to `test.mesh.keys` for whatever gateway_id you're about
to test with (see [kafka-cookbook.md](kafka-cookbook.md#postprocessing-plans-and-derived-telemetry)
for the JSON producer pattern — the key-event shape is the same idea, `key`/`op:
"upsert"`/`psk_b64`, where `key` is the gateway's `"!aabbccdd"`-style string, not a
channel_id or device_id), *then* publish a test message with a matching `--gateway-id`
(see [kafka-cookbook.md](kafka-cookbook.md)) and read back `test.mesh.decoded` to
confirm.

**Important caveat**: `--local` mode does not exercise the Beam-based subprocess UDF
runner the real `jobmanager`/`taskmanager` cluster uses, so it will not catch the
`structlog`-inside-a-UDF crash described in
[debugging.md](debugging.md#structlog-inside-a-udf-crashes-with-customprintprint-got-an-unexpected-keyword-argument-flush).
A `--local` run passing is necessary but not sufficient — confirm any change that adds
a new `log.*()` call inside a UDF method against the real cluster before trusting it.

`postprocessing_job.py` and `pattern_detection_job.py` follow the same pattern with their
own topic env vars (`REGISTRY__POSTPROCESSING_CONFIG_KAFKA_TOPIC`,
`POSTPROCESSING__DERIVED_KAFKA_TOPIC`, `PATTERN_DETECTION__ALARMS_TOPIC`).

**Common mistake**: forgetting to add the venv's own `bin/` to `PATH` before running
`--local`. PyFlink spawns a separate Python worker process for UDFs (the `MapFunction`/
`KeyedBroadcastProcessFunction` bodies) that resolves `python` via `PATH`, not via
`sys.executable` — if that resolves to a different Python without your dependencies
installed, you'll see `ModuleNotFoundError: No module named 'pyflink'` from a
subprocess, not from your own script. Fix: `export PATH=/path/to/venv/bin:$PATH` before
running.

Always clean up scratch topics afterward:

```bash
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --delete --topic test.mesh.raw
```

## Live smoke test against the real stack

See [kafka-cookbook.md#full-end-to-end-smoke-test](kafka-cookbook.md#full-end-to-end-smoke-test)
for injecting a real message through the full deployed pipeline (including the
registration step), and [api-reference.md](api-reference.md) for querying the result
back out.
