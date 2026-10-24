# Mesh-Things docs

Practical manuals for running, testing, and debugging this pipeline locally. These are
written from commands actually run and verified against a live `docker compose` stack,
not theoretical examples.

- [tutorial/index.html](tutorial/index.html) — start here if you're new: core concepts walked through end to end, plus a real three-bug case study
- [architecture.md](architecture.md) — pipeline stages, topics, and service ports at a glance
- [kafka-cookbook.md](kafka-cookbook.md) — create/inspect topics, inject test messages at any pipeline stage
- [api-reference.md](api-reference.md) — curl examples for every endpoint, registry and readings alike
- [client.md](client.md) — the `mesh-things` Python package: using it, how it stays in step with the API, releasing it
- [testing.md](testing.md) — running the pytest suite, running Flink jobs locally against test topics
- [flink.md](flink.md) — redeploying a job after a code change, savepoints vs. cold restarts, cancelling, checkpoint housekeeping
- [data-quality.md](data-quality.md) — postprocessing (blueprints, device calibration, backfills), the two fault checks, and how alarms reach an owner's inbox
- [s3-access.md](s3-access.md) — reading the Parquet archive externally, least-privilege credentials, moving to real AWS S3
- [debugging.md](debugging.md) — logs, health checks, Flink UI/REST API, and gotchas found while building this
- [deploy.md](deploy.md) — deploying to a VPS: firewall, TLS, `.env` for production, and why `ufw` alone doesn't close a Docker-published port
- [backups.md](backups.md) — daily backups encrypted with age, the key kept off the server, and restoring
- [monitoring.md](monitoring.md) — the server monitor: end-to-end probe from MQTT to the readings API, superuser alert emails, and a status API for Uptime Robot
- [email-scaleway.md](email-scaleway.md) — production email with Scaleway Transactional Email: API key, domain verification, SMTP `.env` values, troubleshooting
- [incident-response.md](incident-response.md) — personal data breaches: contain, assess, notify owners within 48 h and the AEPD within 72 h, keep a breach log
- [plans/](../plans/README.md) — what is still open, one file per entry
- [done.md](done.md) — work that is finished, kept for the reasoning, plus what was evaluated and rejected
- [known-gaps.md](../plans/known-gaps.md) — the record of findings from investigations, kept for how they were found

## Quick start

```bash
cp env.example .env   # fill in MQTT broker credentials, optional REGISTRY__SEED_* bootstrap owner/mesh/gateway, etc.

# Required: REGISTRY__SECRET_KEY and READINGS__SECRET_KEY have no fallback - both APIs
# refuse to start without a real value. Generate ONE and paste it into BOTH -
# they must be identical, not a pair, since readings_api decodes registry_api's
# session cookies with it (see docs/deploy.md):
python3 -c "import secrets; print(secrets.token_urlsafe(50))"

docker compose up -d kafka postgres redis influxdb
docker compose up -d mqtt_kafka_bridge decode_consumer registry_api
docker compose up -d registry_device_consumer registry_sensor_discovery_consumer
docker compose up -d influxdb_writer readings_api
docker compose up -d caddy   # optional locally - fronts both roles on one port, see architecture.md#reverse-proxy
```

That's the **lite** tier — pure-python decode (`common/decode.py`), no
Flink. On an instance you run for yourself, set `REGISTRY__TERMS_ENFORCED=false`: the
terms a public instance asks for under GDPR (at signup, per mesh and per source) are
then skipped entirely (see [deploy.md](deploy.md#mqtt-sources)). `redis`/`postgres`/`kafka` would actually come up automatically
either way (every service that needs them declares it via `depends_on`) -
they're listed explicitly here just so the first command's purpose is
obvious at a glance.

For **full** (adds the Flink stream tier and the S3/Parquet archive),
swap `decode_consumer` for `jobmanager taskmanager flink-job`, add `minio`
to the first line and `s3_writer` to the fourth — or just run `docker
compose --profile full --profile minio up -d` for everything at once (leave
`minio` out when the archive is on an external S3). See
[done.md#0](done.md) for what each tier includes and why.

**Nothing will show up in InfluxDB/S3 until a mesh has a registered gateway** — see
[architecture.md#registered-gateways-only-gate](architecture.md#registered-gateways-only-gate)
and [api-reference.md#owners](api-reference.md#owners). Either set the
`REGISTRY__SEED_*` env vars before first startup, or call `POST /owners`, then
`POST /meshes`, then `POST /devices` (with `is_gateway: true`) once everything is up.

Optional extras, all safe to leave stopped:

```bash
# Postprocessing + the stream-tier quality checks (flat values, out-of-range values,
# "device stopped publishing"). One command is fine: the submitters are one-shot
# and idempotent, so this can't create duplicate jobs and is safe to re-run.
# See flink.md.
docker compose up -d postprocessing-job pattern-detection-job absence-detection-job

# Batch-tier quality: completeness/gap analysis + postprocessing backfills.
# Needs QUALITY_WORKER__REGISTRY_API_KEY set to a superuser key first.
docker compose up -d quality_worker quality_worker_beat

# Emails a device's owner when any quality alarm fires.
docker compose up -d registry_quality_alarms_consumer
```

See [data-quality.md](data-quality.md) for what each of those actually checks and
how to configure them.

Service UIs once running:

| What | URL |
|---|---|
| Kafka UI (kafbat-ui, `--profile kafka-ui`) | http://localhost:8080 — or http://localhost:8182 via Caddy, with basic auth |
| Flink dashboard | http://localhost:8081 — or http://localhost:8181 via Caddy, with basic auth |
| InfluxDB UI | http://localhost:8086 — or http://localhost:8183 via Caddy, with basic auth |
| MinIO console | http://localhost:9001 — or http://localhost:8184 via Caddy, with basic auth |
| API docs (both roles) | http://localhost/docs via Caddy, or http://localhost:8090/docs on the dev overlay |

The direct ports above are published on `0.0.0.0` with no authentication in front
of most of them, because `docker-compose.dev.yml` (see `COMPOSE_FILE` in
`env.example`) reopens them for local convenience — fine on a laptop, **not**
on a public server. The Caddy variants in the right-hand column are the same
UIs behind HTTP basic auth; add a credential with
`./scripts/caddy-admin-user.sh <name>`. The base `docker-compose.yml` is
loopback-bound by default (no dev overlay), which is what a VPS deployment
runs; see [deploy.md](deploy.md).

See [api-reference.md#base-urls](api-reference.md#base-urls) for the production URLs.
Caddy forwards paths unchanged, so they differ only by host.
