# Features

Capabilities implemented in this repository, grouped by product area. HTTP paths are relative to the public gateway (Caddy).

## Accounts and access

| Feature | How it works |
| --- | --- |
| Owner registration | `POST /owners` creates an account and returns an API key once |
| Email verification | Token emailed; `is_active` stays false until `GET /owners/verify-email` |
| Password login / logout | Session cookie via `POST /owners/login` and `/owners/logout` |
| Password reset and change | Token email plus `POST /owners/reset-password`, `/owners/me/change-password` |
| API key rotation | `POST /owners/me/rotate-key` |
| Bearer and session auth | `Authorization: Bearer` or registry session cookie (also accepted on readings) |
| Superuser | `manage.py createsuperuser`; sees every mesh; Django admin at `/admin/` |
| Read/write split | Registry mutates Postgres; readings uses role `readings_ro` and cannot see PSKs |

## Fleet management

| Feature | How it works |
| --- | --- |
| Register a mesh | `POST /meshes` with `channel_id` and `psk_b64`; keys go to compact Kafka `mesh.keys.v1` |
| Public meshes | `is_public` lets any verified owner *read* devices and readings; writes stay owner-only |
| Register devices | Manual `POST /devices` or automatic upsert from decode sightings |
| Gateways vs nodes | `is_gateway` marks the MQTT publisher whose id is used to look up the PSK |
| Allow / reject | `is_allowed = false` publishes `mesh.node_rejections.v1`; decode drops those packets |
| Admin keys | Up to three Meshtastic firmware admin keys, visible only to the mesh owner |
| Auto NodeInfo / position | Name, hardware, role, lat/lon fill in unless `nodeinfo_overridden` / `location_overridden` |
| Reading and publish intervals | Per device; used by detectors and blueprint alignment |
| Seed from env | Optional owner + mesh + gateway on first registry start |

## Measurement catalog

| Feature | How it works |
| --- | --- |
| Seeded catalog | `seed_measurement_catalog` loads known Meshtastic telemetry fields, units, quantity kinds |
| Telemetry variants | One row per protobuf variant or fixed `device:` / `computed:` kind |
| Measurement types | `(payload_kind, field_name)` with unit and optional vocabulary URI |
| Discovery | Decode emits `mesh.sensor_discovery.v1`; consumer creates device-variant and measurement rows |
| Per-device channels | `GET /devices/{id}/telemetry-variants` and `/measurements` |
| Detector defaults | Catalog `default_enabled_detectors`; device measurement may inherit, override, or silence |

Channel names are `measurement.field` (for example `environment_metrics.temperature`). That string is shared by blueprints, quality config, Flink keys, and Influx fields.

## Ingest and storage

| Feature | How it works |
| --- | --- |
| MQTT ingest | Shared subscription (`$share/...`) so a bridge pool can split load |
| Decrypt and decode | Lite: `decode_consumer`. Full: Flink `mesh-decode-decrypt` |
| Time series | InfluxDB points tagged by `mesh_id` and `node_id` |
| Historic query | `GET /readings/devices/{uuid}` or `/readings/meshes/{mesh}/nodes/{node}` with `start`/`stop`/`window`/`agg` |
| Latest values | `.../latest` |
| Quality series | `.../quality` |
| Parquet archive | Full: hourly objects under `telemetry/mesh_id=.../dt=.../hour=...` |

## Calibration

| Feature | How it works |
| --- | --- |
| Named functions | `identity`, `offset_scale` (`value * scale + offset`), `lookup_table` |
| Stream apply | Full: Flink reads compact `mesh.calibration.v1` and writes `mesh.telemetry.calibrated.v1` |
| Fail open | A bad function logs and passes the raw value through |

## Postprocessing blueprints

| Feature | How it works |
| --- | --- |
| Recipes | Owner CRUD on `/postprocessing-blueprints` |
| Algorithm catalog | `GET /algorithms` from `common.algorithms` |
| Pointwise examples | `ec_sensor_ppb`, `linear_temperature_correction`, unit conversions in `pollutants` / `corrections` |
| Attach to a device | `devices.postprocessing_blueprint_id` |
| Batch run | Quality worker aligns channels and writes Influx measurement `derived` |

## Data quality and alarms

Detectors are listed on `GET /detectors`.

| Detector | Scope | Where it runs | Needs |
| --- | --- | --- | --- |
| `flat_value` | measurement | Flink pattern job (full) | reading interval (window of about 3 hours of samples) |
| `range` | measurement | Flink pattern job (full) | `valid_min` and `valid_max` on the measurement |
| `absence` | device | Flink absence job (full) | `absence_detection_enabled` and `publish_interval_seconds` |
| `completeness` | measurement | quality worker batch | `reading_interval_seconds`; alarms on low fill ratio or long gaps |

Alarms are JSON events on `mesh.telemetry.alarms.v1`, also stored in Influx measurement `alarms`.

## Alarm email and summaries

| Feature | How it works |
| --- | --- |
| Immediate first mail | First alarm on a device emails the mesh owner |
| Cooldown window | Later alarms on that device (any detector or channel) are held in Redis |
| Summary | When the window closes, one email lists the held alarms |
| Cooldown 0 | Every alarm is emailed |
| Per-owner override | `PUT /owners/me` with `alarm_email_cooldown_seconds` |
| Links | Emails point at the frontend console (`REGISTRY__PUBLIC_FRONTEND_URL` + console path) |

## Operations

| Feature | How it works |
| --- | --- |
| Health | `/health` on each API role; pipeline processes expose their own health ports |
| Metrics | `GET /metrics` on registry |
| OpenAPI | `GET /schema` and Swagger at `/docs` (both roles described from registry) |
| Rate limits | Per-owner throttle on readings |
| Dev overlay | Published admin ports, MailHog, `MQTT_BRIDGE__INSTANCE_SUFFIX=dev` so local MQTT shares do not steal production traffic |
| TLS gateway | Caddy obtains certificates when `CADDY_SITE_ADDRESS` is a real hostname |
