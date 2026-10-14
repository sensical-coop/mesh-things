# Mesh Things

Mesh Things is a system for ingesting Meshtastic-based mesh telemetry from MQTT into a data processing and storage pipeline. It lets you:

- Register meshes and their devices, and decrypt and decode their packets
- Discover a mesh's gateways from its traffic, and the nodes under each automatically
- Bridge meshes from remote MQTT brokers (`sources`) and share readings with third parties over MQTT (`sinks`)
- Store readings in a timeseries database (InfluxDB) and in a Parquet archive on S3 or MinIO
- Process readings as they arrive:
  + Sensor calibration and derived channels
  + Data-quality checks and pattern detection
  + Alarms (thresholds, flat or missing readings, gaps) with notifications (email and more)
- REST API

## Technology stack

- Message store and pipeline: [Apache Kafka](https://kafka.apache.org/)
- Decode and stream processing: Python (`lite`) or [Apache Flink](https://flink.apache.org/) (`full`)
- MQTT broker: [EMQX](https://www.emqx.io/)
- Storage: InfluxDB, PostgreSQL, Redis, and S3 or MinIO
- APIs: Django (registry and readings), behind Caddy

## Getting started

Everything runs with `docker compose`. Two tiers are selected with compose profiles:

- **lite**: MQTT ingestion, decrypting and decoding packets, storing readings in InfluxDB, managing meshes and devices, and reading the data back over the API. This should be small enough for a single board computer (SBC).
- **full**: everything in `lite`, plus the `Flink` stream jobs (decode, postprocessing and calibration, pattern and absence detection), the batch quality worker, MQTT sinks and the Parquet archive that operators switch on per device. Add the `minio` profile to keep the archive on the bundled MinIO, or leave it out and point the archive at an external S3.

Optional profiles on top of either tier: `quality` (the batch quality worker on `lite`), `sinks` (MQTT sinks on `lite`), `monitor` (the server monitor) and `kafka-ui` (a topic browser).

```bash
cp env.example .env    # then edit .env, see below
docker compose --profile lite up -d                     # lite
docker compose --profile lite --profile quality up -d   # lite with the batch quality worker
docker compose --profile full --profile minio up -d     # full, with the archive on MinIO
```

`env.example` is set up for local development: its `COMPOSE_FILE` adds the dev overlay `docker-compose.dev.yml`, which publishes the admin UI ports and switches Django to its `dev` settings. In production, delete the `COMPOSE_FILE` line so the base file runs alone, and set `COMPOSE_PROFILES` instead of passing `--profile`. Both API secret keys must be set before the APIs start.

## Work in progress

This repository is still a work in progress. Documentation and licensing are ongoing.

Feel free to open issues or PRs. Contact us at info@sensical.es for more information.
