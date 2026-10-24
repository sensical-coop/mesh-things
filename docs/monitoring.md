# Server monitor

`server_monitor` checks a running instance end to end, from outside, and emails the
superusers when something breaks. It is meant to run on a **different machine** from the
stack, a small VPS or a Raspberry Pi, so a dead host still gets reported. It also serves
a small HTTP API of its own that Uptime Robot or a similar service can poll.

Container healthchecks only show that a process is up. The monitor shows that a packet
published on MQTT actually comes out of the readings API.

## What it checks

Every `MONITOR__INTERVAL_SECONDS` (default 300) the monitor runs one round of checks.

| Check | Passes when | A failure points at |
|---|---|---|
| `api_root` | `GET /` answers 200 | Caddy |
| `api_health` | `GET /health` answers 200 | `registry_api`, Postgres |
| `api_schema` | `GET /schema` answers 200 | `registry_api` |
| `readings_api` | `GET /readings/devices/{gateway}/latest` answers 200 with the monitor's key | `readings_api`, InfluxDB, auth |
| `email` | `GET /status/email` says registry's latest email was accepted by its mail server | SMTP settings (`REGISTRY__EMAIL_*`), the mail provider. Needs a superuser's key; `MONITOR__EMAIL_CHECK=false` skips it |
| `ingestion` | the probe reaches the readings API within `MONITOR__INGEST_TIMEOUT` | the broker, `mqtt_kafka_bridge`, Kafka, decode (`flink-job` or `decode_consumer`), `influxdb_writer` |
| `registry_sighting` | the test gateway's `last_seen` advances | decode's sightings, `registry_device_consumer` |
| `sink` (optional) | the probe arrives on the monitor's MQTT sink | `sink_dispatcher`, EMQX sink authorization |

**The probe.** The public routes are called without credentials. For the rest, the monitor
owns a mesh with a random PSK and one gateway registered on it. Each round it publishes, as
that gateway, a telemetry packet encrypted with the mesh's PSK, to
`{MONITOR__MQTT_TOPIC_PREFIX}/{channel}/!{gateway hex}`, exactly as a real node's
gateway would. The packet carries a unique marker in `device_metrics.uptime_seconds`,
the send time in unix seconds. The monitor then polls the readings API until that
marker is the latest value. It checks the registry and the sink the same way, all from
the one packet.

If the publish itself fails, `ingestion` reports why, and `registry_sighting` and
`sink` report `not run: publish failed`, so the alert names the real cause.

## Setting it up

1. **An account for the monitor.** Sign up a normal member account, for example
   `monitor@yourdomain.com`, and verify its email. The monitor never needs more than
   that. The optional sink check needs the operator role, which a superuser grants with
   `PUT /owners/{id}`.

2. **Its mesh and gateway.** On the monitor's machine, clone the repository, then:

   ```bash
   cp monitor.env.example monitor.env
   # Fill MONITOR__API_URL and MONITOR__API_KEY first, then:
   docker compose -f compose/monitor.yml --env-file monitor.env run --rm server_monitor \
     python -m monitor setup --accept-terms          # add --sink for the sink check
   ```

   Without `--accept-terms` it prints the mesh terms and stops. It creates a mesh
   labelled `server monitor` with a random PSK and a gateway with a random node number,
   and prints the `MONITOR__MESH_ID`, `MONITOR__PSK_B64`, `MONITOR__GATEWAY_*` lines,
   plus the `MONITOR__SINK_*` lines with `--sink`. Paste them into `monitor.env`. The
   sink password is shown only once.

3. **MQTT.** Set `MONITOR__MQTT_BROKER` to the broker the bridge reads
   (`MQTT_BRIDGE__BROKER`), with a user allowed to publish there. Set
   `MONITOR__MQTT_TOPIC_PREFIX` to a prefix inside `MQTT_BRIDGE__TOPIC`, such as
   `msh/EU_868/2/e` when the bridge reads `msh/#`.

4. **Alerts.** Set `MONITOR__ALERT_EMAILS` to the superusers' addresses and fill the
   `MONITOR__EMAIL_*` SMTP settings. The same Scaleway values as `REGISTRY__EMAIL_*` work
   (see [email-scaleway.md](email-scaleway.md)). The list lives on the monitor, not in
   the registry, so alerts still go out when the API is down. Keep it in step with the
   superusers.

5. **Start it** on a domain of its own. Point `MONITOR__DOMAIN`'s DNS at the machine,
   open ports 80 and 443, then:

   ```bash
   docker compose -f compose/monitor.yml -f compose/monitor.caddy.yml \
     --env-file monitor.env --profile monitor up -d --build
   ```

   `compose/monitor.caddy.yml` adds a Caddy container that gets a Let's Encrypt
   certificate for `MONITOR__DOMAIN` and proxies to the monitor, whose port stays on
   loopback. Without a domain, use `compose/monitor.public.yml` instead: it publishes port
   `MONITOR__PORT` (8095) on every interface over plain HTTP. Leave both out to keep the
   port on loopback, for example behind a reverse proxy of your own.

The service has no `depends_on`, so the same file also runs beside the stack for
local testing, with `MONITOR__API_URL=http://caddy`:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile monitor up -d server_monitor
```

The dev stack's bridges and production's are in different share groups, so both receive
a probe. Only the stack where the monitor's gateway is registered decodes it. The other
drops it, as it drops any unregistered gateway.

## Its HTTP API

| Route | Auth | Returns |
|---|---|---|
| `GET /health` | none | 200 while the check loop is running, 503 if it has stalled |
| `GET /status` | none | the latest result of every check: 200 when all pass, 503 otherwise |
| `GET /status/{check}` | none | the same for one check |
| `GET` or `POST /run` | token | runs every check now, and returns the fresh results |
| `GET` or `POST /run/{check}` | token | runs one check now |

`/status` returns results from the last round:

```json
{
  "ok": false,
  "checked_at": "2026-09-30T10:05:12+00:00",
  "alerting": true,
  "checks": {
    "api_health": {"ok": true, "detail": "ok", "latency_s": 0.041, "checked_at": "...", "consecutive_failures": 0},
    "ingestion": {"ok": false, "detail": "probe 1790762700 not in the readings API in time (latest device_metrics.uptime_seconds is 1790762400)", "latency_s": 180.2, "checked_at": "...", "consecutive_failures": 3}
  }
}
```

`alerting` is false when the last alert email could not be sent, or when no recipients or
SMTP host are configured.

**On-demand runs.** `/run` exists only when `MONITOR__RUN_TOKEN` is set, and returns 404
otherwise. Pass the token as `Authorization: Bearer <token>`, or as `?token=` for
probes that cannot set headers. HTTP checks run alone. `ingestion`, `registry_sighting`
and `sink` share one probe, so asking for any of them publishes one. To keep requests
from flooding the pipeline:

- a request made while a probe is in flight waits for that probe;
- within `MONITOR__RUN_MIN_INTERVAL_SECONDS` (default 30) of the last probe, a request
  gets that probe's results.

Both of those responses carry `"cached": true`. `?timeout=<seconds>` shortens the wait for
the probe, capped at `MONITOR__INGEST_TIMEOUT`. On-demand results update `/status` and
count towards alerts like scheduled ones.

```bash
curl -s localhost:8095/status | python3 -m json.tool
curl -s -X POST -H "Authorization: Bearer $MONITOR_RUN_TOKEN" "localhost:8095/run/ingestion?timeout=50"
```

`server/examples/monitor_status.py` does the same from Python.

## Uptime Robot

- **The monitor itself:** an HTTP monitor on `https://<MONITOR__DOMAIN>/health`, or
  `http://<monitor host>:8095/health` with `compose/monitor.public.yml`.
- **The instance, from the last round:** an HTTP monitor on `/status`, which alerts on
  the 503. Or a keyword monitor for `"ok": true`. Add one per check with
  `/status/ingestion` and so on to see which part failed.
- **The instance, tested at request time:** an HTTP monitor on
  `/run/ingestion?token=<token>&timeout=40`. Keep `timeout` below Uptime Robot's own
  request timeout, and the robot's interval above `MONITOR__RUN_MIN_INTERVAL_SECONDS`.
  Otherwise the robot is shown the previous result.

The monitor emails on its own either way. Uptime Robot adds an outside view of the
monitor.

## Alerts

- A check is failing once it has failed `MONITOR__FAILURES_BEFORE_ALERT` times in a row
  (default 2), so one slow round stays quiet.
- An email goes out when a check starts failing, listing every failing check and its
  detail.
- While anything still fails, a reminder goes out every `MONITOR__REMINDER_HOURS`
  (default 6, 0 turns reminders off).
- One "recovered" email goes out when everything passes again.

State is kept in memory, so a restart during an outage sends at most one extra alert.

## Caveats

- **Terms.** On an instance with `REGISTRY__DATA_RETENTION_DAYS`, the mesh terms
  acceptance lapses like any owner's. The monitor's account gets the renewal email and
  must renew it (`POST /meshes/{id}/terms-acceptance`). Otherwise its mesh stops
  ingesting and `ingestion` fails.
- **It is a real account.** It is counted in `/metrics`, and its probes are stored like
  any reading: one small `device_metrics` point per round.
- **Clock.** The marker is the monitor host's time, but matching never compares clocks:
  it looks for the marker's value, and for `last_seen` changing.
