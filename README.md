# Meshtastic Things

Meshtastic Things is a system for ingesting Meshtastic mesh telemetry from MQTT into Kafka, decoding/decrypting it, and storing it. It provides:

- Sensor data storage on timeseries databases (InfluxDB) and S3-like buckets as Parquet archives
- Data processing on-the-fly or in batch, to perform:
  + Sensor calibration
  + Pattern detection and data-quality checks
  + Alarms (threshold breach, malfunctioning, etc.) via email or other measurements
  + Sensor / measurement catalog
  + Per-owner access control
- Queries for sensor data
- Fleet management (registration of meshes, devices, data processing pipelines)

## Stack

- Message store and pipeline: Apache Kafka
- Decode and on-the-fly processing: pure python (Lite) and Apache Flink (Full)
- Storage: InfluxDB and S3/MinIO
- APIs (keys and query): Django

## Getting started

Deployment is a single `docker compose` stack (`docker-compose.yml`, which
`include:`s everything under `compose/`), built around two tiers selected with
`COMPOSE_PROFILES`:

- **lite** — MQTT ingestion, decode/decrypt packets, store data in InfluxDB, manage meshes/devices and access data back over the API.
- **full** — everything in `lite`, plus the Flink streams (decode, calibration, and the per-point quality checks), and the S3/MinIO Parquet archive.

`lite` can add an optional batch quality worker (postprocessing blueprints, completeness/gap analysis) with `--profile quality`.

### Local development

Local development additionally features `docker-compose.dev.yml` (which publishes admin UI ports, and switches Django to `dev` settings) — see `COMPOSE_FILE` in `env.example`, which already points at both files.

### Commands

```bash
cp env.example .env
docker compose up -d                # lite by default (COMPOSE_PROFILES in env.example)
docker compose --profile full up -d # or the full stack: Flink streams, and S3 archive
```

**Note**: For iterations on protobufs, install `meshtastic` locally as editable and
build protobufs locally — see [`scripts/regen-protos.sh`](meshtastic_things/scripts/regen-protos.sh).

**Warning**: Nothing reaches InfluxDB until a mesh has a **registered gateway** (registration authorizes decoding).

## Layout

| Path | What |
|---|---|
| [`bridge/`](meshtastic_things/bridge/) | MQTT → Kafka raw ingest |
| [`flink/`](meshtastic_things/flink/) | Streaming jobs (full tier): decode/decrypt, calibration, and the two stream-tier quality checks |
| [`pipeline/`](meshtastic_things/pipeline/) | Pure-Python decode consumer (lite tier), no Flink needed |
| [`writer/`](meshtastic_things/writer/) | Kafka → InfluxDB and Kafka → Parquet/S3 writers |
| [`api/`](meshtastic_things/api/) | Django/DRF project, one image with two roles picked by `APP_ROLE`: `registry` (owners, meshes, devices, sensor catalog, postprocessing blueprints) and `readings` (read API over InfluxDB, scoped against registry's own database) |
| [`quality_worker/`](meshtastic_things/quality_worker/) | Celery batch tier: postprocessing blueprints + completeness analysis |
| [`common/`](meshtastic_things/common/) | Shared: codec, calibration, detectors, channel naming, algorithm registry |
| [`examples/`](meshtastic_things/examples/) | Standalone scripts against both API roles |
| [`tests/`](meshtastic_things/tests/) | pytest suite (`registry` and `readings` have their own Django test runner, under `api/*/tests/`) |

## Docs

| Doc | For |
|---|---|
| [tutorial/index.html](docs/tutorial/index.html) | New to this repo: core concepts end to end, plus a real three-bug case study |
| [architecture.md](docs/architecture.md) | How it fits together, and why |
| [api-reference.md](docs/api-reference.md) | curl examples for both APIs |
| [data-quality.md](docs/data-quality.md) | Blueprints, fault detection, alarms |
| [flink.md](docs/flink.md) | Redeploying jobs, savepoints, the gotchas |
| [kafka-cookbook.md](docs/kafka-cookbook.md) | Inspecting topics, injecting test messages |
| [s3-access.md](docs/s3-access.md) | Reading the Parquet archive externally |
| [deploy.md](docs/deploy.md) | Deploying to a VPS: firewall, TLS, production `.env`, admin UIs |
| [testing.md](docs/testing.md) | Running the three test suites |
| [debugging.md](docs/debugging.md) | Logs, health checks, and real bugs hit while building this |
| [pending.md](docs/pending.md) | The single list of what is still open |
| [done.md](docs/done.md) | Finished work, kept for the reasoning, plus what was evaluated and rejected |
| [known-gaps.md](docs/known-gaps.md) | Record of findings from investigations, kept for how they were found |

Also useful: [`api.http` / `api-authenticated.http`](meshtastic_things/examples/) are
REST Client scratch files covering every endpoint.

