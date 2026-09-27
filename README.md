# Meshtastic Things

Meshtastic Things is an advanced system for ingesting Meshtastic mesh telemetry via MQTT into a data processing and storage pipeline. It allows you to:

- Store telemetry data on timeseries databases (InfluxDB) and S3-like buckets as Parquet archives
- Process data on-the-fly or in batch to perform:
  + Sensor calibration
  + Pattern detection and data-quality checks
  + Alarms (thresholds, malfunctioning, etc.) via email
- Retrieve historic sensor data
- Fleet management (register meshes, devices and data processing pipelines)
- Remote calibration and adaptive sensing strategies

## Technology stack

Meshtastic Things has two modes: `lite` and `full`. Ideally, the `lite` version can be deployed on a Raspberry pi, while `full` needs a bigger machine.

- Message store and pipeline: [Apache Kafka](https://kafka.apache.org/)
- Decode and on-the-fly processing: pure python (Lite) and [Apache Flink](https://flink.apache.org/) (Full)
- Storage: InfluxDB and S3/MinIO
- APIs (keys and query): Django

## Getting started

To deploy, simply use `docker compose`. There are two modes (`lite` and `full`), which can be selected with
`COMPOSE_PROFILES`:

- **lite**: includes MQTT ingestion, decode/decrypt packets, store data in InfluxDB, manage meshes/devices and access data back over the API.
- **full**: everything in `lite`, plus data processing on the fly with Flink streams (decode, device postprocessing and calibration, and the per-point quality checks), and a S3/MinIO Parquet archive.

```bash
cp env.example .env                    # edit .env with your settings
docker compose up -d                   # lite
docker compose --profile full up -d    # or the full stack: Flink streams, and S3 archive
```

Note: `lite` can add an optional batch quality worker (completeness/gap analysis) with `--profile quality`. Postprocessing runs in the Flink tier, so it needs `full`:

```bash
docker compose up -d --profile quality # lite with profile quality
```

### Local development

For local development, a special compose configuration is used with: `docker-compose.dev.yml`. This publishes admin UI ports, and switches Django to `dev` settings). Edit `COMPOSE_FILE` in `env.example`.

```
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

## Work in progress

This repository is still WIP. Documentation and licensing is on-going.

Feel free to open issues or PRs. Contact us at info@sensical.es for more information.
