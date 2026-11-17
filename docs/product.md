# Product

Meshtastic Things turns LoRa mesh telemetry into a managed fleet: registered networks, devices, measurement catalogs, quality checks, and historic readings.

Gateways on a Meshtastic mesh publish protobuf packets to an MQTT broker. This stack subscribes, decrypts with the mesh PSK, stores readings, and lets an owner query and configure the fleet over HTTP.

## Who it is for

- Operators who run one or more Meshtastic meshes and want a durable record of sensor data.
- People who need to know when a node goes silent, a sensor sticks, or a channel falls outside a valid range.
- Teams that derive extra channels from raw ADC or environmental readings (postprocessing blueprints).
- Viewers who should read a public mesh without being able to change it.

## What it does

1. **Ingest.** MQTT traffic is forwarded into Kafka as raw envelopes.
2. **Decode.** Lite uses a Python consumer; full uses a Flink job. Both decrypt with keys published by the registry and emit structured JSON events.
3. **Catalog.** Sightings and sensor discovery upsert devices, telemetry variants, and measurement channels in Postgres.
4. **Store.** Decoded events and alarms go to InfluxDB. Full also archives decoded events as Parquet in MinIO/S3.
5. **Process.** Full applies per-field calibration and stream detectors. A batch worker runs blueprints and completeness checks over Influx history.
6. **Serve.** Two Django roles sit behind Caddy: registry (owners, meshes, devices, catalog, blueprints) and readings (time series, latest values, quality).

## Deployment modes

| Mode | Typical host | What you get |
| --- | --- | --- |
| `lite` | Raspberry Pi-class | MQTT ingest, Python decode, InfluxDB, registry + readings APIs |
| `lite` + `quality` | Same, with extra CPU | Batch blueprints and completeness analysis |
| `full` | Larger machine | Everything in lite, plus Flink streams, S3/Parquet archive, Kafka UI |

Compose selects this with `COMPOSE_PROFILES` (`lite` or `full`). The `quality` and `bridge-pool` profiles are optional extras. See [architecture.md](architecture.md).

## What is stored where

| Concern | Store |
| --- | --- |
| Accounts, meshes, keys, devices, catalog, blueprints | PostgreSQL |
| Telemetry, positions, nodeinfo, derived channels, quality metrics, alarms | InfluxDB |
| Decoded event archive (full) | MinIO / S3 Parquet |
| Sessions, rate limits, alarm-email windows | Redis |
| In-flight events and compact config | Kafka |

The relational schema and time-series layout are in [data-model.md](data-model.md).
