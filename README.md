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



