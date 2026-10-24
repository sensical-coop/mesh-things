# Deploying to a VPS

Step by step, from a fresh Debian/Ubuntu server to a working HTTPS deployment.

Everything here is `docker compose` on a single host. That's the honest scope of
this stack: one machine running Kafka, Flink, InfluxDB, Postgres, MinIO and two
Django APIs behind Caddy. It is not a multi-node or HA setup.

**The rule this whole document is built around:** only ports **80** and **443**
are reachable from the internet. Everything else — the Kafka UI, the Flink
dashboard, the MinIO console, the InfluxDB API, both Django ports — is bound to
loopback and reached through an SSH tunnel. See
[section 4](#4-why-ufw-alone-is-not-enough) for why that matters more than it
might sound.

**Contents**

- [Before you start](#before-you-start)
- [Sizing](#sizing)
- [1. Server preparation](#1-server-preparation)
- [2. Firewall, before Docker](#2-firewall-before-docker)
- [3. Install Docker](#3-install-docker)
- [4. Why ufw alone is not enough](#4-why-ufw-alone-is-not-enough)
- [5. Clone the repository](#5-clone-the-repository)
- [6. Configure `.env`](#6-configure-env)
- [Memory limits](#memory-limits)
- [Django settings](#django-settings)
- [7. DNS and TLS](#7-dns-and-tls)
- [8. First boot](#8-first-boot)
- [9. Bootstrap the registry](#9-bootstrap-the-registry)
- [10. Verify](#10-verify)
- [Admin UIs](#admin-uis)
- [Updating](#updating)
- [Backups](#backups)
- [Troubleshooting](#troubleshooting)

---

## Before you start

| Requirement | Notes |
|---|---|
| VPS | **4 vCPU / 8 GB RAM / 80 GB disk** runs the full stack comfortably. Kafka, Flink, InfluxDB, Postgres and MinIO all share this one box; 2 GB will not boot it. See [Sizing](#sizing) for measured numbers. |
| Debian 12 or Ubuntu 22.04/24.04 | Any systemd distro with a current Docker works; the `apt` commands below assume Debian/Ubuntu. |
| A domain name | You need one for TLS. Let's Encrypt does not issue certificates for bare IP addresses. |
| DNS control | To point an `A` record at the server. |
| SSH access as a non-root user with sudo | Step 1 sets this up if you only have `root`. |

Rough disk appetite: InfluxDB and Kafka grow with traffic, MinIO holds the
Parquet archive indefinitely. Watch `docker system df` and the volumes listed
under [Backups](#backups).

---

## Sizing

Measured on a running stack, not estimated:

| | Idle RSS |
|---|---|
| Whole stack, 26 services (19 long-running in production) | **~6-7 GB** |
| ├─ `taskmanager` (JVM 1.2 GB + one ~300 MB PyFlink worker per job) | 2.7 GB |
| ├─ `jobmanager` | 0.9 GB |
| ├─ Kafka broker | 1.0 GB |
| ├─ Kafka UI (opt-in, `--profile kafka-ui`; not counted in the total) | 0.4-0.75 GB |
| ├─ Python services (2 APIs, 6 consumers, 2 writers) | 0.9 GB |
| └─ Datastores (InfluxDB, Postgres, Redis, MinIO) | 0.6 GB |

Storage grows slowly. InfluxDB stores **7.8 bytes per point** here (1.47M
points in 11 MB), so 300 devices reporting every 5 minutes is roughly
245 MB/month, or ~2 GB for six months including derived and quality channels.
Kafka holds ~1-3 GB at its 7-day retention, and the MinIO Parquet archive grows
about 400 MB/month. Nothing expires on its own; readings are deleted when their owner
stops renewing the terms or deletes them (see [MQTT sources](#mqtt-sources)). **Docker images and build cache are the
largest single consumer.** The stack's images total about 5 GB, 1.6 GB of it the
Flink image, and the deploy builds on the server, so build cache comes on top. Each rebuild leaves the previous images
behind untagged; `docker image prune` and `docker builder prune` reclaim them.

For a demo of 200-300 devices — about one message per second — CPU is not the
constraint; the stack idles at roughly 1.5 cores. Budget on RAM and on Docker's
disk appetite.

The service count is less alarming than it looks: of 26 services, 5 are
one-shot (the four Flink submitters and `kafka-topics-init`, which exit after
doing their job) and 2 are off by default (`mailhog`, which exists only in the dev
overlay, and `kafbat-ui`, which runs only with `--profile kafka-ui`). The 11 services that are *our* code total about 900 MB
between them — the memory is dominated by infrastructure, chiefly Flink and
Kafka.

## 1. Server preparation

Log in as `root` (or an existing sudo user) and create an unprivileged account.
Everything after this step runs as that user.

```bash
adduser --gecos "" deploy
usermod -aG sudo deploy

# Copy your SSH key across so you can log in as the new user
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy/
```

Open a **second terminal** and confirm `ssh deploy@your-server` works before
closing the first one. Locking yourself out of a fresh VPS is the most common
way to lose an afternoon.

Then harden SSH — in `/etc/ssh/sshd_config`:

```
PermitRootLogin no
PasswordAuthentication no
```

```bash
sudo systemctl restart ssh
```

Keep security updates flowing:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

Add swap if the host has none (`free -h` shows `Swap: 0B`). The containers'
`mem_limit`s add up to more than an 8 GB host has, so when several services
peak together, swap is what keeps the kernel OOM killer from picking Kafka
or Postgres:

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf
sudo sysctl --system
```

4 GB covers the spikes a stack this size produces. If `free -h` shows several
GB of swap in steady use, the host needs more RAM rather than more swap: a
larger swap file only stretches out the slowdown before something is killed.
To resize it anyway (the `/etc/fstab` line stays as it is):

```bash
sudo swapoff /swapfile && sudo rm /swapfile
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

---

## 2. Firewall, before Docker

Install and configure `ufw` **before** installing Docker, and allow SSH
**before** enabling it.

```bash
sudo apt install -y ufw

sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH FIRST. Enabling ufw without this rule ends the session and locks
# you out of the machine.
sudo ufw allow OpenSSH          # 22/tcp

# The only two public ports this deployment needs.
sudo ufw allow 80/tcp           # ACME HTTP-01 challenge + the HTTP->HTTPS redirect
sudo ufw allow 443/tcp          # the API itself, over TLS

sudo ufw enable
sudo ufw status verbose
```

### Why both 80 and 443 for Let's Encrypt

Caddy obtains and renews certificates automatically, and it needs to answer an
ACME challenge to prove it controls the domain. It can use either:

- **HTTP-01**, served on **port 80**
- **TLS-ALPN-01**, served on **port 443**

Caddy tries them in turn, so leaving both open makes issuance and renewal
robust: if one method is blocked, the other still completes. Port 80 also
serves the automatic HTTP→HTTPS redirect, so closing it means plain-HTTP
visitors get a connection refused rather than being redirected.

Renewal happens roughly every 60 days with no interaction, but it needs those
ports open *at that time* — a firewall change months later that closes 80 and
443 to everything but a known IP will silently break renewal until the
certificate expires.

If you also run the MQTT bridge against an external broker, that's an
**outbound** connection (default `allow outgoing`) and needs no inbound rule.

---

## 3. Install Docker

Use Docker's own repository; distro packages are usually too old for the
Compose features this deployment relies on.

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy
newgrp docker    # or log out and back in
```

Check the Compose version — **v2.24 or newer is required** for the `!override`
tag used by `docker-compose.dev.yml`:

```bash
docker compose version
```

> Adding a user to the `docker` group is equivalent to giving them root: they
> can start a container that mounts `/` and writes anywhere. Only do it for
> accounts you would give sudo to anyway.

### Logs: journald, deleted after 30 days

The Privacy Policy promises that technical logs, which can include IP addresses
(Caddy's error log, SSH logins on the host), are deleted after **30 days**.
Docker's usual rotation (`max-size`/`max-file`) caps size, not age: a quiet
container can keep an IP address for months inside a few megabytes. journald
deletes by age, holds the host's own logs as well, and `docker logs` keeps
working with it.

Set it up now, before the first `docker compose up`, since a container keeps the
log driver it was created with:

Add `log-driver` to `/etc/docker/daemon.json`, keeping any keys already in the
file:

```json
{ "log-driver": "journald" }
```

`/etc/systemd/journald.conf`, under `[Journal]`:

```ini
Storage=persistent
MaxRetentionSec=30day
MaxFileSec=1day
SystemMaxUse=2G
```

journald only deletes whole journal files, and by default a file stays open for
a month. `MaxFileSec=1day` closes one every day, so no entry outlives the
retention period by more than a day.

```bash
sudo systemctl restart systemd-journald docker
```

Ubuntu also runs rsyslog, which copies SSH logins into `/var/log/auth.log`
and rotates it with logrotate for about five weeks, outside journald's
retention. Remove it so journald is the only copy, and delete what it already
wrote:

```bash
sudo apt purge -y rsyslog
sudo rm -f /var/log/auth.log* /var/log/syslog* /var/log/kern.log*
```

On a server that is already running, recreate the containers afterwards so they
pick up the new driver: `docker compose up -d --force-recreate`.

Don't add a `logging:` block to any service in the compose files: an explicit
driver overrides this default, and that service's logs would no longer be
deleted after 30 days. If you change the period, change the Privacy Policy
(§6) and the DPA (Annex II) in the frontend repository to match.

Check:

```bash
docker info --format '{{.LoggingDriver}}'              # journald
docker inspect -f '{{.HostConfig.LogConfig.Type}}' registry-api   # journald
journalctl --disk-usage
```

---

## 4. Why ufw alone is not enough

This is the part that catches people, so it's worth being precise.

When Docker publishes a container port it inserts a `DNAT` rule into iptables'
`nat` table. That rule is evaluated **before** ufw's `INPUT` chain. The
practical consequence:

> `sudo ufw deny 8080` does **not** close a Docker-published port on 8080.
> The traffic is redirected into the container before ufw ever sees it.

Any published port that isn't already loopback-bound at the compose level is
reachable from the internet on a public IP, regardless of what `ufw status`
says.

### Why the base file alone is the deploy target

`docker-compose.yml` (the base file, `compose/*.yml` under it) is loopback-safe
by default — this is deliberate, not incidental. Every port it publishes is
bound to `127.0.0.1` except Caddy's 80 and 443, and `mailhog` isn't defined in
it at all. **Deploy with the base file alone:**

```bash
docker compose --profile full --profile minio up -d
```

That's it — no second `-f` file, nothing to remember to add. `minio` runs the bundled
object store for the Parquet archive; leave it out when the archive lives on an
external S3 (see [The Parquet archive](#the-parquet-archive)). Setting
`COMPOSE_PROFILES=full,minio` in `.env` saves passing both. The alternative
design (base file open, a separate override closes it) was tried first and
rejected: forgetting to add an override is silent and remote — a stack comes
up looking fine, and the failure is only visible to whoever finds the open
port. Forgetting to *add* something you need (the dev overlay, next section)
fails loudly and locally instead — a `docker compose exec` against a service
that doesn't feel like local dev, or Django refusing to boot because
`settings.prod` demands `REGISTRY__ALLOWED_HOSTS` be set to something real
instead of `env.example`'s default `*`.

`server/tests/test_deploy_ports.py` enforces this directly on the
base file - every published port must be `127.0.0.1` except Caddy's, and
`mailhog` must not exist in it at all.

Confirm the resolved configuration before deploying:

```bash
docker compose --profile full --profile minio config | grep -A 3 'published:'
```

Every `host_ip` should be `127.0.0.1` except Caddy's two.

### Local development: `docker-compose.dev.yml`

This is the file that reopens bindings to `0.0.0.0` and adds `mailhog` -
**never use it on a public IP.** With it active, all of this becomes reachable
to anyone who can reach the host at all:

| Port | Service | What an unauthenticated visitor gets |
|---|---|---|
| 8080 | Kafka UI (kafbat-ui) | Browse and consume every topic. No login. |
| 8081 | Flink dashboard | Job control: cancel jobs, upload and run JARs. No login. |
| 8025 | MailHog | **Every captured email, including owner email-verification links.** No login. |
| 1025 | MailHog SMTP | An open mail sink. |
| 9001 | MinIO console | Login, but with the credentials from `.env`. |
| 9000 | MinIO S3 API | The whole Parquet telemetry archive. |
| 8086 | InfluxDB | API and UI; all raw telemetry. |
| 9092 / 9093 / 29092 | Kafka | Direct broker access. No auth configured. |
| 8090 / 8091 | registry / readings | Authenticated, but bypassing Caddy means bypassing TLS. |

MailHog is the sharpest edge: it holds the verification links that grant
account access - the reason it doesn't exist in the base file at all rather
than just being loopback-bound there.

`env.example`'s `COMPOSE_FILE` line already wires this overlay in for local
development:

```bash
COMPOSE_FILE=docker-compose.yml:docker-compose.dev.yml
```

With that set, every `docker compose` command - including the ones throughout
the rest of this repo's docs - transparently includes the dev overlay. A real
deployment should delete that line (or copy `env.example` fresh, which doesn't
carry any deploy-specific `.env` edits over).

> **The `!override` tags in that file are load-bearing.** Compose *concatenates*
> list-valued options like `ports` across files. A plain `ports:` list would
> **add** the 0.0.0.0 binding on top of the base file's 127.0.0.1 one instead
> of replacing it - harmless in that direction (loopback stays loopback too),
> but the same mistake in the *other* direction (an override narrowing a port)
> would leave it open while looking closed. `test_deploy_ports.py` checks this
> on the dev overlay for exactly that reason.

---

## 5. Clone the repository

Public repository over HTTPS:

```bash
sudo apt install -y git
cd ~
git clone https://github.com/<you>/mesh-things.git meshtastic-things
cd meshtastic-things
```

For a private repository, use a **read-only deploy key** rather than your
personal SSH key — it scopes access to this one repository, so a compromised
server can't reach the rest of your account:

```bash
ssh-keygen -t ed25519 -C "deploy@$(hostname)" -f ~/.ssh/id_deploy -N ""
cat ~/.ssh/id_deploy.pub
# Add that key in the repo's Settings -> Deploy keys, leaving "Allow write
# access" unchecked.

cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/id_deploy
  IdentitiesOnly yes
EOF

git clone git@github.com:<you>/mesh-things.git meshtastic-things
cd meshtastic-things
```

Pulling later is then just `git pull` — see [Updating](#updating).

---

## 6. Configure `.env`

```bash
cp env.example .env
chmod 600 .env
```

`.env` is listed in `.gitignore` and must never be committed — it ends up
holding database passwords, an InfluxDB token and a superuser API key.

Generate the secrets first:

```bash
# One Django secret key, used for BOTH REGISTRY__SECRET_KEY and
# READINGS__SECRET_KEY - see the note below, they must be identical.
python3 -c "import secrets; print(secrets.token_urlsafe(50))"

# Postgres and MinIO passwords
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Values that must change from the defaults

Leaving any of these at its shipped value is a live vulnerability, not a
cosmetic issue.

| Variable | Default | Set it to |
|---|---|---|
| `REGISTRY__SECRET_KEY` | *(empty)* | A generated value. The API refuses to start without one. |
| `READINGS__SECRET_KEY` | *(empty)* | **The exact same value as `REGISTRY__SECRET_KEY`, not a different one.** `readings_api` authenticates a browser's session cookie by reading the row `registry_api` wrote to the shared `django_session` table and decoding it with Django's signer, which is keyed on `SECRET_KEY` - there's no `SECRET_KEY_FALLBACKS` configured, so a different value here can only ever fail that decode. It shows up as `Session data corrupted` immediately followed by `Unauthorized` in `readings_api`'s logs on every session-cookie request; bearer-token requests are unaffected. |
| `POSTGRES_PASSWORD` | `meshtastic` | A generated password. |
| `S3_WRITER__ACCESS_KEY` | `meshtastic` | A generated value; this is also MinIO's root user. |
| `S3_WRITER__SECRET_KEY` | `meshtastic123` | A generated password. |
| `REGISTRY__ALLOWED_HOSTS` | `localhost,127.0.0.1` | **Append** your domain, don't replace the list: `localhost,127.0.0.1,api.yourdomain.com`. The healthcheck in `compose/api.yml` curls `http://localhost:$PORT/health` from inside the container, so dropping `localhost` breaks the healthcheck itself with `DisallowedHost`. The compose service name (`registry-api`, `readings-api`) is always allowed and never redirected to HTTPS, because other containers such as the quality worker call it directly; don't add it here. |
| `READINGS__ALLOWED_HOSTS` | `localhost,127.0.0.1` | Same — append, don't replace. |
| `REGISTRY__DEBUG` / `READINGS__DEBUG` | `false` | Leave `false`. Never `true` in production — it leaks settings and stack traces. |

### Values that must change for TLS and the gateway

| Variable | Set it to | Why |
|---|---|---|
| `CADDY_SITE_ADDRESS` | `api.yourdomain.com` | **No leading colon and no scheme.** A bare hostname is what triggers automatic Let's Encrypt issuance. `:80` (the local-dev default) means plain HTTP with no TLS. |
| `GATEWAY__PUBLIC_URL` | `https://api.yourdomain.com` | **With** the scheme. Used for the `servers` block in the OpenAPI documents so generated clients build the right URLs. |
| `REGISTRY__BEHIND_TLS` | `true` | Enables `SECURE_SSL_REDIRECT`, HSTS and secure cookies. Assumes the proxy sets `X-Forwarded-Proto`, which Caddy does. |
| `READINGS__BEHIND_TLS` | `true` | Same. |
| `REGISTRY__PUBLIC_BASE_URL` | `https://api.yourdomain.com` | This API's own externally reachable base URL, used for API-facing URLs like the OpenAPI schema's `servers` entry. |
| `REGISTRY__PUBLIC_FRONTEND_URL` | `https://app.yourdomain.com` | The base for email-verification and password-reset links, which open the frontend app instead of this API so the recipient sees a rendered page rather than raw JSON. The frontend reads the token from the query string, calling `GET /owners/verify-email?token=...` itself for verification, or sending it back as `token` in the body of `POST /owners/reset-password` for a reset. `prod.py` refuses to boot without it, same as `PUBLIC_BASE_URL`. |
| `REGISTRY__FRONTEND_CONSOLE_PATH` | `/console` (the default) | Prefix of the frontend's authenticated pages, under `PUBLIC_FRONTEND_URL`. Emails link to resource pages below it: `{prefix}/meshes/<mesh id>` when mesh access is granted, `{prefix}/meshes` when it is revoked, and `{prefix}/devices/<device uuid>` plus the mesh page in quality-alarm emails. The frontend must serve those routes. Change it only if the frontend moves its console; `/` puts it at the frontend root. |
| `REGISTRY__CORS_ORIGINS` / `READINGS__CORS_ORIGINS` | `https://things.yourdomain.com` | **With** the scheme, like `GATEWAY__PUBLIC_URL` — not like `CADDY_SITE_ADDRESS` above. A bare hostname fails Django's system check and the API won't start at all. Needed whenever a browser app — including the frontend that `PUBLIC_FRONTEND_URL` points at — calls the API from another origin. |
| `REGISTRY__COOKIE_DOMAIN` | *(unset)* | Only set this when the frontend and `registry_api` are on different subdomains of the same site, e.g. `things.yourdomain.com` and `api.yourdomain.com`. Set it to the shared parent with a leading dot: `.yourdomain.com`. Without it the session/csrftoken cookies are scoped to `registry_api`'s own host, so the browser still sends them there but the frontend's own JavaScript can't read `csrftoken` to echo it back in `X-CSRFToken` — every write then fails CSRF verification even though `CORS_ORIGINS` is correct. |

### Email

MailHog captures mail instead of sending it, and its inbox is unauthenticated.
**Do not run it in production.** Point Django at a real SMTP provider:

```bash
REGISTRY__EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
REGISTRY__EMAIL_HOST=smtp.yourprovider.com
REGISTRY__EMAIL_PORT=587
REGISTRY__EMAIL_HOST_USER=...
REGISTRY__EMAIL_HOST_PASSWORD=...
REGISTRY__EMAIL_USE_TLS=true
REGISTRY__DEFAULT_FROM_EMAIL=noreply@yourdomain.com
```

Email matters here: owner verification and quality alarms both go out this way.
For step-by-step setup with Scaleway Transactional Email specifically (API
key, domain verification, DNS records, troubleshooting), see
[email-scaleway.md](email-scaleway.md). It keeps mail in the EU, which the DPA
relies on: pick another provider and it becomes a sub-processor to disclose.

### Remaining `REQUIRES USER ACTION` items

`env.example` marks eight of these. Beyond the ones above:

- `MQTT_BRIDGE__BROKER`, `MQTT_BRIDGE__PORT`, `MQTT_BRIDGE__USER`,
  `MQTT_BRIDGE__PASS`, `MQTT_BRIDGE__TOPIC` — your Meshtastic MQTT broker.
  Nothing enters the pipeline until these are set.
- `INFLUX__TOKEN`, `INFLUX__ORG`, `INFLUX__BUCKET` — filled in during
  [First boot](#8-first-boot); InfluxDB is not auto-initialised.
- `QUALITY_WORKER__REGISTRY_API_KEY` — a superuser key, minted in
  [step 9](#9-bootstrap-the-registry).
- `S3_WRITER__ENDPOINT_URL` / `S3_WRITER__REGION` — only if you move off MinIO
  to real S3; see [s3-access.md](s3-access.md).

---

## Memory limits

Every service in `docker-compose.yml` carries a `mem_limit`. That is not
tuning, it's blast-radius control: without a limit, one leaking or wedged
container drives the *host* out of memory, and the kernel OOM killer then picks
a victim by score — frequently Postgres or the jobmanager rather than the
culprit. With a limit, Docker kills the offending container, restarts it per
its `restart:` policy, and everything else keeps running.

Verified rather than assumed — a container allocating past its limit:

```
OOMKilled : true
exit code : 137
```

The limits are measured usage plus headroom. Two need care:

- **`taskmanager` (3600m)** — its JVM is capped at 1536m, including 128m of direct memory for PyFlink's gRPC channel, but the container
  also carries one PyFlink Python worker per job (~300-400 MB each) which lives
  *outside* the JVM budget. A limit sized to the JVM alone would kill it.
- **`jobmanager` (1600m)** — JVM capped at 1024m.

If a container is being OOM-killed, `docker inspect -f '{{.State.OOMKilled}}'
<name>` returns `true` and the exit code is 137. Raise that service's
`mem_limit` rather than removing it.

## Django settings

Both APIs use a settings package, not a single `settings.py`:

```
api_project/settings/
    base.py    shared by every environment
    dev.py     local conveniences - MailHog, DEBUG on, ALLOWED_HOSTS "*"
    prod.py    no dev config at all, and fails fast on a leftover dev value
```

`docker-compose.yml` (the base file) selects `...settings.prod` by default -
see [section 4](#4-why-ufw-alone-is-not-enough); `docker-compose.dev.yml`
overrides it to `...settings.dev` for local development.

The split exists so production never references development-only
infrastructure. MailHog is the clearest case: it appears in `dev.py` and
nowhere else, so a production container cannot be pointed at a mail catcher
that isn't running. And rather than discovering a misconfiguration at the first
signup, `prod.py` refuses to boot:

```
ImproperlyConfigured: REGISTRY__ALLOWED_HOSTS is '*', which accepts any Host
header. Name the real hostnames - see docs/deploy.md#6-configure-env

ImproperlyConfigured: REGISTRY__EMAIL_HOST='mailhog' is not a production mail
server. MailHog captures mail instead of delivering it and does not run in
production - set a real SMTP host, or use the console backend.
```

`prod.py` checks: `ALLOWED_HOSTS` is set and not `*`; `EMAIL_HOST` is a real
server when the SMTP backend is selected; `PUBLIC_BASE_URL` is set (this API's
own base URL); `PUBLIC_FRONTEND_URL` is set (verification and password-reset
links are both built from it — see the frontend row above). It also forces `DEBUG = False`
with no environment
override — no variable should be able to turn that on by accident — and enables
the HTTPS redirect, HSTS and secure cookies by default.

One subtlety worth knowing: an environment variable that is *set but empty* is
treated as unset (`mesh_things.env`). `REGISTRY__BEHIND_TLS=` in `.env` used to
mean "false", silently disabling HSTS and secure cookies while looking
configured. It now falls back to the default, which in production is on.

## 7. DNS and TLS

Point an `A` record at the server before starting Caddy:

```
api.yourdomain.com.   A   203.0.113.10
```

Verify it has propagated — Caddy's certificate request will fail if Let's
Encrypt can't reach the name:

```bash
dig +short api.yourdomain.com
curl -sS http://api.yourdomain.com   # connection refused is fine; DNS resolving is the point
```

Certificates are stored in the `caddy_data` named volume, so they survive
`docker compose down` and container recreation. Don't delete that volume
casually: re-issuing repeatedly can hit Let's Encrypt's rate limit of
**5 certificates per exact domain per week**.

If you expect to iterate on the configuration, use the staging CA first — it
has far looser limits and issues untrusted certificates you can still verify
the *flow* with. Add to the `Caddyfile` inside the site block:

```
acme_ca https://acme-staging-v02.api.letsencrypt.org/directory
```

Remove that line and run `docker compose restart caddy` once it works.

---

## 8. First boot

Start the datastores first. InfluxDB needs manual setup before anything that
writes to it will work.

```bash
cd ~/meshtastic-things
docker compose up -d kafka postgres redis minio influxdb
docker compose ps
```

### If this first pull fails

Not a firewall problem, even though it's the first command that touches the
network and looks like one. `minio/minio` is no longer available on Docker
Hub — MinIO stopped publishing there — so a pull of it 403s with:

```
Error response from daemon: pull access denied for minio/minio, repository
does not exist or may require 'docker login'
```

Compose pulls images in parallel and cancels the rest of the batch the moment
one fails hard, so the other four show `Interrupted` rather than a real error
of their own — that's a side effect of MinIO's pull failing, not five
separate problems. The image is already pinned to
`quay.io/minio/minio` in `compose/pipeline.yml`; if you're seeing this on a
checkout from before that fix, `git pull` and retry.

### Initialise InfluxDB

InfluxDB ships uninitialised and its port is now loopback-only, so use an SSH
tunnel from your laptop:

```bash
# On your local machine
ssh -L 8086:127.0.0.1:8086 deploy@api.yourdomain.com
```

Note, make sure that you don't have a port already being used locally. If so:

```bash
# On your local machine
ssh -L 18086:127.0.0.1:8086 deploy@api.yourdomain.com
```

Open <http://localhost:8086> (or `:18086` if you used the alternate port
above), complete the setup wizard, then create an **API token** with write
access to the bucket. Copy the organisation, bucket and token into `.env`:

**Skip the wizard's optional "Configure a Scraper" step**, or delete the
scraper it creates afterwards (Data > Scrapers in the UI). It defaults the
target to whatever host:port is in your browser's address bar — `localhost:8086`
normally, but `localhost:18086` if you're going through the alternate tunnel.
The scrape itself runs server-side, inside the InfluxDB container, where
nothing listens on `18086` (only its own `8086` does) — an SSH-tunnelled port
that only exists on your laptop, not the server. That mismatch shows up
continuously in `docker compose logs influxdb` as:
```
lvl=error msg="Unable to gather" service=scraper scraper-name="new target" \
  error="Get \"http://localhost:18086/metrics\": dial tcp [::1]:18086: connect: connection refused"
```
If you already hit this, delete the stray scraper rather than fixing its URL —
scraping InfluxDB's own metrics isn't needed for anything in this stack:
```bash
# find its id
curl -s -H "Authorization: Token $INFLUX__TOKEN" http://localhost:8086/api/v2/scrapers | python3 -m json.tool
# delete it
curl -X DELETE -H "Authorization: Token $INFLUX__TOKEN" http://localhost:8086/api/v2/scrapers/<id>
```

```bash
INFLUX__TOKEN=<the generated token>
INFLUX__ORG=<your org>
INFLUX__BUCKET=<your bucket>
```

Alternatively, do it entirely on the server without a tunnel:

```bash
docker compose exec influxdb influx setup \
  --org yourorg --bucket telemetry --username admin \
  --password "$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')" \
  --retention 0 --force
docker compose exec influxdb influx auth list
```

`influx_init` then creates the `alarms` bucket (30-day retention) and the
`alarm_counts` bucket on every `up`, using `INFLUX__TOKEN`, which must be allowed to
create buckets: the setup token above is.

### Start the rest

`mesh-things/pipeline`, `mesh-things/flink` and `mesh-things/api`
don't exist locally yet on a fresh host, and this is the first `up` that needs
one of them. Build before starting them:

```bash
docker compose --profile full build mqtt_kafka_bridge jobmanager taskmanager flink-job registry_api
docker compose up -d mqtt_kafka_bridge jobmanager taskmanager flink-job registry_api
docker compose up -d registry_device_consumer registry_sensor_discovery_consumer
docker compose up -d influxdb_writer s3_writer readings_api
docker compose up -d caddy
```

### If this fails with "pull access denied"

Same shape as the MinIO failure above, different cause. The `image:` line
beside each `x-*-image` anchor in `compose/` only names the tag to give the
image *after* building it locally (see [Updating](#updating)) — it is not a
published image. If nothing with that tag exists yet and `up -d` runs before
a `build`, Compose tries to pull it as if it were a registry image and fails:

```
pull access denied for mesh-things/flink, repository does not exist or
may require 'docker login'
```

Fix: `docker compose --profile full build <the services that failed>`, then
`up -d` them as above.

Database migrations and the measurement catalog seed both run automatically from
the registry container's `CMD`.

The Flink job submitters are one-shot containers: they submit detached and
exit, and skip a job that is already running. One command, safe to repeat:

```bash
docker compose up -d postprocessing-job pattern-detection-job absence-detection-job
```

`docker compose ps` will show them as `Exited (0)` afterwards. That is the
expected steady state - the jobs themselves run inside `taskmanager`. See
[flink.md](flink.md).

Optional batch tier (needs the superuser key from step 9):

```bash
docker compose up -d quality_worker quality_worker_beat
docker compose up -d registry_quality_alarms_consumer
```

Watch Caddy get its certificate:

```bash
docker compose logs -f caddy | grep -iE "certificate|obtain|error"
```

---

## 9. Bootstrap the registry

Nothing is written to InfluxDB or S3 until a mesh has a **registered gateway** —
see [architecture.md#registered-gateways-only-gate](architecture.md#registered-gateways-only-gate).

Create a superuser and mint its API key:

```bash
docker compose exec registry_api python manage.py createsuperuser \
  --email you@yourdomain.com --name "Your Name"
```

The command prints an API key **once**. Put it in `.env` as
`QUALITY_WORKER__REGISTRY_API_KEY` and restart the worker:

```bash
docker compose up -d quality_worker quality_worker_beat
```

Then register an owner, a mesh and a gateway device — either by setting the
`REGISTRY__SEED_*` variables before first startup, or through the API:

```bash
curl -X POST https://api.yourdomain.com/owners \
  -H "Content-Type: application/json" \
  -d '{"name": "You", "email": "you@yourdomain.com"}'
```

See [api-reference.md#owners](api-reference.md#owners) for the mesh and device
calls that follow.

### MQTT sources

Sources bridge remote MQTT brokers into this instance through EMQX (see
[architecture.md#mqtt-sources](architecture.md#mqtt-sources)). They need:

- **The bridge reading the EMQX that registry controls.** `MQTT_BRIDGE__BROKER` must
  be the same EMQX as `REGISTRY__EMQX_API_URL`, because that is where each source is
  republished.
- **An EMQX API key** with the `administrator` role, created in the EMQX dashboard
  (System, API Keys) or through EMQX's `api_key.bootstrap_file`. Set it in `.env`:

  ```bash
  REGISTRY__EMQX_API_URL=https://mqtt.yourdomain.com:18084/api/v5
  REGISTRY__EMQX_API_KEY=<key>
  REGISTRY__EMQX_API_SECRET=<secret>
  ```

  Registry calls `/connectors`, `/sources` and `/rules` for sources, and the built-in
  authentication and authorization databases and `/clients` for [sinks](#mqtt-sinks). If
  the key is missing or wrong, every source write answers `502` and nothing is kept.
- **Broker permission for the bridge user** to subscribe to `mt-sources/#` (the value
  of `MQTT_CONNECTORS__NAMESPACE`, default `mt-sources`). The same value prefixes the
  sinks' users and topics. Leave `MQTT_CONNECTORS__NAMESPACE` blank in production, and
  do not change it once sources or sinks exist: every name on the broker includes it.
  The dev overlay sets `mt-sources-dev`.
- **A bridge own-topic filter that does not overlap the source topics.** A bridge
  whose `MQTT_BRIDGE__TOPIC` is `#` refuses to start.
- **Internal addresses.** EMQX connects to a source from inside this deployment, so
  loopback, `0.0.0.0`, link-local (including the cloud metadata address), bare hostnames
  such as `emqx` or `kafka`, and names resolving to any of those are always refused.
  Private network addresses are refused unless `REGISTRY__SOURCES_ALLOW_PRIVATE_BROKERS=true`,
  which a self-hosted instance can set to bridge a broker on its LAN. The resolution
  check runs when the source is saved; a name that is repointed later is not re-checked.
- **This instance's own broker.** A source may not point back at it, since its traffic
  would be republished into itself. The host is compared with the hosts of
  `REGISTRY__EMQX_API_URL`, `MQTT_BRIDGE__BROKER` and `REGISTRY__SINKS_BROKER`, by name
  and by every address they resolve to, so a raw IP or another DNS name for the same
  broker is refused too.
- **Reserved topics.** A topic filter that could match what a stack republishes or sinks
  on its broker is refused wherever the broker is: `#`, anything starting with `+/`, and
  anything whose first level starts with this instance's namespace or the default
  `mt-sources` (so `mt-sources/#` and `mt-sources-sinks/...` alike).
- **Blocklists.** `REGISTRY__SOURCES_BLOCKED_BROKERS` and
  `REGISTRY__SOURCES_BLOCKED_TOPICS` (comma-separated) refuse brokers and topic filters
  an operator may not bridge. Brokers are `host` or `host:port` patterns with `*`
  wildcards, so `*.example.org` blocks every host under it; topics must match exactly.
  Topics default to `#` when blank. They are checked on create and update only, so a
  source that already exists keeps working after its broker or topic is blocked.

  ```bash
  REGISTRY__SOURCES_BLOCKED_BROKERS=*.example.org,broker.example.net:1883
  REGISTRY__SOURCES_BLOCKED_TOPICS=#,+/#,msh/#
  ```
- **Terms.** `REGISTRY__TERMS_ENFORCED` (blank = on) asks owners to accept the account,
  mesh and source terms, and records it, as the public instance must under GDPR. On an
  instance run by its own mesh owner, such as a lite install on a Raspberry Pi, set it
  to `false`: the terms routes answer `404` (the console skips its terms steps), signup,
  meshes and sources need no `terms_version`, nothing is recorded, no renewals or lapses
  run, `REGISTRY__DATA_RETENTION_DAYS` is ignored, and anything a lapse had paused is
  resumed on the next lifecycle pass. Deleting a mesh still removes its readings after
  the grace period (`REGISTRY__DATA_DELETION_GRACE_DAYS=0` for straight away).
- **Data lifecycle.** `registry_data_lifecycle` runs in every profile. It needs the
  InfluxDB token (`INFLUX__TOKEN`) with delete rights and, on the full profile, the
  archive credentials (`S3_WRITER__*`). Leave `S3_WRITER__BUCKET` blank on a lite
  deployment. It also publishes to Kafka, to pause and resume gateways.
  `REGISTRY__DATA_RETENTION_DAYS` (blank keeps data indefinitely),
  `REGISTRY__DATA_DELETION_GRACE_DAYS` (30) and `REGISTRY__TERMS_RENEWAL_NOTICE_DAYS` (30)
  set the policy; both the mesh and the source terms quote them, so changing them
  changes the text owners accept. Run one pass by hand
  with `docker compose exec registry_data_lifecycle python manage.py run_data_lifecycle --once`.
- **Operators.** Only an operator creates sources. Owners request the role through
  `POST /owners/me/operator-request`, and every active superuser is emailed. Superusers
  therefore need a real, reachable email address. Grant the role directly as a
  superuser with `PUT /owners/{id}` `{"role": "operator"}`, or approve a request, see
  [api-reference.md#operator](api-reference.md#operator).

EMQX keeps its bridges in its own data directory, not in Postgres. After EMQX is
redeployed without its data, or if a write was lost, reconcile it:

```bash
# Report what differs, exit non-zero if anything does
docker compose exec registry_api python manage.py sync_sources --check
# Re-create every source's bridge and remove bridges no source owns
docker compose exec registry_api python manage.py sync_sources
```

It only touches resources named in this instance's namespace, so other stacks sharing
the EMQX are left alone.

A source can read `connected` while it receives nothing: EMQX keeps the connection to the
remote broker after the subscription on it has stopped delivering (Mesh Hub UK, October
2026). The silent-source alert below catches it. Restart it from the console's Sources
page, with `POST /sources/<id>/restart`, or on the server:

```bash
./scripts/restart-source.sh                # every source, its status and message count
./scripts/restart-source.sh <source id>    # re-apply its bridge and resubscribe
```

The script runs `manage.py restart_source` in `registry_api`, so the EMQX API key stays
in `.env`. Restarting turns the EMQX source off and on, since EMQX 5.8 has no restart
operation for sources. Run it twice a minute apart and compare the message counts to
see whether it worked.

### MQTT sinks

Sinks let third parties subscribe to readings on this instance's EMQX (see
[architecture.md#mqtt-sinks](architecture.md#mqtt-sinks)). They use the same EMQX API key
as sources, and run on the full profile or on lite with `--profile sinks`:

```bash
docker compose --profile lite --profile sinks up -d
```

**Once per broker**, put EMQX's built-in authorization database in front of its other
authorization sources. This changes the whole broker, so run it on purpose, not from a
script. Clients that match none of its rules fall through to the existing ones, so
nothing else changes:

```bash
docker compose exec registry_api python manage.py sync_sinks --install-authz
docker compose exec registry_api python manage.py sync_sinks --check
```

Until it is in place, creating a sink answers `502`. To undo it, delete the
`built_in_database` source in the EMQX dashboard (Access Control, Authorization); every
sink's consumer is then refused.

Then set, in `.env`:

- `MQTT_SINKS__USER`/`MQTT_SINKS__PASS`: the broker user `sink_dispatcher` publishes as.
  Blank uses `MQTT_BRIDGE__USER`/`MQTT_BRIDGE__PASS`. Registry allows this user to
  publish sink topics when the first sink is created or `sync_sinks` runs.
- `REGISTRY__SINKS_BROKER`: where consumers connect, as `host:port`, shown with a sink's
  credentials. Blank uses `MQTT_BRIDGE__BROKER:MQTT_BRIDGE__PORT`. It must be the
  broker's TLS listener reachable from the internet.
- `SINK_DISPATCHER__HEALTHCHECK_PORT` (19093).

**Session limits.** The broker keeps an offline consumer's persistent session, and queues
its messages in memory, by its broker-wide `mqtt` settings: `session_expiry_interval`,
`max_mqueue_len` and `message_expiry_interval`. Those suit the bridge, not third parties.
One consumer that leaves with a persistent session open can hold weeks of readings in the
broker's memory. Two limits apply on top, each lifecycle pass (`registry_data_lifecycle`):

- `REGISTRY__SINKS_MAX_OFFLINE_HOURS` (24): a sink session offline longer than this is
  discarded, with whatever it queued.
- `REGISTRY__SINKS_MAX_QUEUED` (10000): a sink session holding more queued messages than
  this is discarded, and a consumer still connected that far behind is disconnected.

**Status alerts.** The same pass emails a source's or sink's operator once per outage, if
the operator opted in (`status_alerts_enabled` on `PUT /owners/me`, off by default):

- `REGISTRY__SOURCE_ALERT_HOURS` (2): a source whose bridge has not been `connected` for
  this long, including one missing from the broker.
- `REGISTRY__SINK_ALERT_HOURS` (24): a sink with meshes or devices attached that nobody
  has been connected to for this long.

The start of each outage is kept in Redis for a week, so an outage is counted from the
first pass that saw it. Paused sources and sinks are not reported. `0` turns either off.

**Silent sources.** `REGISTRY__SOURCE_SILENT_ALERT_HOURS` (6) emails every superuser
once when a source's rule has handled no message for this long, whatever its status, and
the operator too if they set `status_alerts_enabled`. It is the only alert that catches a
bridge still `connected` to a remote broker that has stopped delivering. A source with a
quiet topic may need a longer setting. `0` turns it off.

**Busy sources.** `REGISTRY__SOURCE_RATE_ALERT_MSGS_PER_S` (20) emails every superuser
once when a source averages more messages per second than this between two passes, and
the operator too if they set `source_rate_alerts_enabled`. Production's only source ran
at about 0.5 msg/s in October 2026, so 20 means a source bridging far more than its
meshes need. `0` turns it off.

The pass runs every `REGISTRY__DATA_LIFECYCLE_INTERVAL_SECONDS`, so a session can outlive
the limit by up to that long. The broker enforces the same limits on every message as it
arrives on a listener of its own: `meshtastic-things-mqtt` runs one on **8884**, in an EMQX
zone holding sessions for 24 hours and queueing at most 10,000 messages (its
`docs/deploy.md`, "Sink consumers"). Point consumers at it:

```bash
REGISTRY__SINKS_BROKER=mqtt.sensical.es:8884
```

A sink's user can still log in on 8883 and get the broker-wide limits, since listeners
do not restrict who connects; the lifecycle pass covers those.

Sink passwords are held only by EMQX. After EMQX is redeployed without its data,
reconcile the rules and find the sinks whose users were lost; those need
`POST /sinks/{id}/credentials` and the new password handed to their consumer:

```bash
docker compose exec registry_api python manage.py sync_sinks
```

### Forwarding a lite site to a full instance

A lite site whose broker is not reachable from the internet cannot be added to a full
instance as a [source](#mqtt-sources). Forward its Meshtastic traffic at broker level
instead: its local broker bridges the topics out to the full instance's default broker,
which the full instance then reads like any gateway's uplink. No code is involved.

1. On the full instance, the site's operator creates the mesh with its channel and PSK,
   accepts the mesh terms, and registers the site's gateways, as any owner does. The full
   instance decodes with its own copy of the key.
2. On the site's broker, bridge the uplink topics out. With Mosquitto, in
   `mosquitto.conf`:

   ```
   connection full-instance
   address mqtt.yourdomain.com:8883
   bridge_protocol_version mqttv311
   bridge_capath /etc/ssl/certs
   remote_username <user on the full instance's broker>
   remote_password <password>
   cleansession false
   topic msh/EU_868/2/e/MyChannel/# out 1
   ```

   With EMQX, create an MQTT connector to the full instance's broker and a rule
   republishing `msh/EU_868/2/e/MyChannel/#` to it.
3. The topic that arrives must match the full instance's `MQTT_BRIDGE__TOPIC`, and its
   last segment must stay the `!gateway` id. Forward only `out`: bridging back `in` on an
   overlapping filter makes the two brokers loop.

Gateways added at the site later must also be registered on the full instance, or their
traffic is dropped there, and a change of PSK must be made on both.

### The Parquet archive

Full profile only. Operators switch it on per device (`archive_enabled`), and only the
mesh's owner, while an operator, and superusers read it through readings
([api-reference.md#parquet-archive](api-reference.md#parquet-archive)). On lite, leave
`S3_WRITER__BUCKET` and `READINGS__ARCHIVE_BUCKET` blank: registry then refuses
`archive_enabled` and the archive routes answer `404`.

**On the bundled MinIO** (`--profile minio`):

1. Set `READINGS__ARCHIVE_ACCESS_KEY`/`READINGS__ARCHIVE_SECRET_KEY` to a real secret.
   `minio_init` creates that user, read-only on the bucket, on every `up`.
2. Give the S3 API its own hostname, like the admin UIs, and point readings at it:
   ```
   s3.api.yourdomain.com.   A   203.0.113.10
   ```
   ```bash
   CADDY_S3_ADDRESS=s3.api.yourdomain.com
   READINGS__ARCHIVE_PUBLIC_ENDPOINT_URL=https://s3.api.yourdomain.com
   READINGS__ARCHIVE_STS=minio
   ```
   It has no basic auth: S3 signs every request, and the signature covers the `Host`
   header, which Caddy passes through. Presigned links and issued credentials name this
   endpoint, so it must be the one callers reach.

**On an external S3**: leave `minio` out of the profiles, set `S3_WRITER__*` to a writer
identity (it needs `DeleteObject` too, for the data lifecycle), and `READINGS__ARCHIVE_*`
to a separate read-only identity. On AWS, `READINGS__ARCHIVE_STS=aws` with
`READINGS__ARCHIVE_ROLE_ARN`; on a provider without STS, leave it blank and only the
manifest and single-file downloads are served. The IAM policies are in
[s3-access.md#external-s3](s3-access.md#external-s3).

**Exports** run on the full profile as `readings_export_worker`. Set
`READINGS__EXPORT_ACCESS_KEY`/`SECRET_KEY`: on the bundled MinIO, `minio_init` creates
that user and the lifecycle rule; on an external S3, create both by hand
([s3-access.md#external-s3](s3-access.md#external-s3)). The worker emails owners with
registry's `REGISTRY__EMAIL_*` settings. `READINGS__EXPORT_MAX_DAYS` (366) caps a range.

readings receives only its own variables (`compose/api.yml` lists them), never
`S3_WRITER__*`. Registry publishes each device's sinks to `mesh.sink_config.v1`, which
`s3_writer` follows. If that topic is lost, or a role was changed in the Django admin,
rebuild it:

```bash
docker compose exec registry_api python manage.py publish_sink_config
```

Check it end to end: switch one device on, wait a flush (`S3_WRITER__FLUSH_INTERVAL_S`),
then list the mesh with `GET /readings/archive/meshes/{id}` or run
`mesh_things/examples/archive_duckdb.py`.

---

## 10. Verify

From your laptop, not the server:

```bash
# TLS is live and the certificate is trusted
curl -sSI https://api.yourdomain.com/ | head -1

# The service index and the merged OpenAPI document
curl -sS https://api.yourdomain.com/ | python3 -m json.tool
curl -sS -o /dev/null -w '%{http_code}\n' https://api.yourdomain.com/schema

# Both services are healthy through the proxy
curl -sS https://api.yourdomain.com/health
curl -sS https://api.yourdomain.com/health

# HTTP redirects to HTTPS rather than serving plaintext
curl -sSI http://api.yourdomain.com/ | head -1
```

Now confirm nothing else is exposed. Run this **from your laptop**, against the
public IP:

```bash
for p in 8080 8081 8086 8090 8091 9000 9001 9092 8025 1025 5432 8181 8182 8183 8184; do
  timeout 3 bash -c "</dev/tcp/api.sensical.es/$p" 2>/dev/null \
    && echo "OPEN  $p  <-- should not be" || echo "closed $p"
done
```

Every line should read `closed` — including 8181-8184, whose local-dev
publications the prod override drops. Anything `OPEN` means the prod override
wasn't applied — check `docker compose config | grep published` and confirm
`COMPOSE_FILE` is set.

```bash
sudo ufw status verbose      # only 22, 80, 443 allowed
docker compose ps            # every service Up / healthy
```

### Monitoring from another machine

Once the checks above pass, set up the [server monitor](monitoring.md) on a separate
small machine. From there it publishes a probe packet every few minutes, follows it
through to the readings API, and emails the superusers when anything fails. It also
gives Uptime Robot a `/status` URL to watch. It needs its own member account on this
instance, a user on the MQTT broker allowed to publish under `MQTT_BRIDGE__TOPIC`, and
SMTP credentials, which can be the same Scaleway ones. Nothing changes on this server:
the monitor only uses the public API and the broker.

```bash
# On the monitor's machine
cp monitor.env.example monitor.env    # fill it in, see docs/monitoring.md
docker compose -f compose/monitor.yml --env-file monitor.env run --rm server_monitor \
  python -m monitor setup --accept-terms
docker compose -f compose/monitor.yml -f compose/monitor.caddy.yml \
  --env-file monitor.env --profile monitor up -d --build
```

`compose/monitor.caddy.yml` serves the status API on `MONITOR__DOMAIN` over HTTPS. Without
a domain, use `compose/monitor.public.yml` instead, which publishes port 8095 directly.

---

## Admin UIs

The Flink dashboard, Kafka UI, InfluxDB and the MinIO console are reachable —
through Caddy, with HTTP basic auth in front of every one of them. Their own
ports stay bound to loopback by default (the base file, no override needed),
so Caddy is the only way in.

Basic auth is doing real work here, not adding a second factor: **the Flink
dashboard and Kafka UI have no authentication at all**, and the Flink one
offers job control including uploading and running arbitrary JARs.

The Kafka UI is not started with the rest of the stack. Start it when you need
it and stop it afterwards; until then its hostname answers 502:

```bash
docker compose --profile kafka-ui up -d kafbat-ui
docker compose --profile kafka-ui stop kafbat-ui
```

### Why each UI gets its own hostname

Three of the four cannot be served from a subpath like `/admin/flink/`.
Measured, not assumed — from each UI's own HTML:

| UI | Asset references | Works under a subpath? |
|---|---|---|
| Flink | `assets/…` (relative) | Yes |
| Kafka UI | `/assets/…` (absolute) | No |
| InfluxDB | `<base href="/">`, `/64a6…js` | No — upstream has no base-path option |
| MinIO | `<base href="/">` + `./…` | Only with `MINIO_BROWSER_REDIRECT_URL` |

Served at the root of their own hostname they all work unmodified, so that's
what the Caddyfile does.

In production give each one a DNS `A` record pointing at the same server and
set:

```bash
CADDY_FLINK_ADDRESS=flink.api.yourdomain.com
CADDY_KAFKAUI_ADDRESS=kafka.api.yourdomain.com
CADDY_INFLUX_ADDRESS=influx.api.yourdomain.com
CADDY_MINIO_ADDRESS=minio.api.yourdomain.com
```

Caddy obtains a certificate for each automatically, all on 443 — no extra
firewall rules, and the base file never publishes the local-dev ports
(8181-8184) at all — those only exist under `docker-compose.dev.yml`.

**Any subdomain depth works.** `flink.api.yourdomain.com` is as valid as
`flink.yourdomain.com` — Caddy matches on the `Host` header, which it does not
parse into labels, and ACME issues per-name certificates regardless of depth
(verified: an explicit multi-label name produces no special TLS policy, so it
goes through the normal HTTP-01/TLS-ALPN-01 flow). Grouping the admin UIs under
the same `api.` parent as the gateway is a reasonable way to keep them
together.

Two things to know if you go deeper:

- **Don't use a wildcard site address** (`*.api.yourdomain.com`). Wildcard
  certificates can only be issued via the DNS-01 challenge, which needs a
  DNS-provider plugin compiled into Caddy — the stock `caddy:2-alpine` image
  doesn't have one. The config *validates* either way, so this fails at
  certificate-issuance time rather than at startup. Name each host explicitly
  and every one is issued over HTTP-01 with no plugin.
- **An existing `*.yourdomain.com` certificate does not cover
  `flink.api.yourdomain.com`.** A wildcard matches exactly one label. This only
  matters if you're bringing your own certificate; Caddy's automatic issuance
  handles it either way.

A **wildcard DNS record** is fine and often convenient — point
`*.api.yourdomain.com` at the server once and you never touch DNS again when
adding a service. That's wildcard *DNS*, not a wildcard *certificate*: Caddy
still requests an individual certificate per hostname over HTTP-01.

At whatever provider manages `yourdomain.com`, add two `A` records pointing at
the server's public IP:

| Host/Name | Type | Value |
|---|---|---|
| `api` | A | `203.0.113.10` |
| `*.api` | A | `203.0.113.10` |

Both are needed — the wildcard matches exactly one label under it
(`flink.api.yourdomain.com`, `kafka.api.yourdomain.com`, …), it does **not**
cover the bare `api.yourdomain.com` itself. No firewall change is needed
either way: every hostname still resolves to the same host and goes through
Caddy on 80/443, the wildcard only saves you from adding a DNS record per
admin UI. Verify propagation before relying on it:

```bash
dig +short flink.api.yourdomain.com   # should return the server IP even
                                       # though you never created this record
```

Certificate count is not a concern at this scale: Let's Encrypt allows 50 per
registered domain per week, and all subdomains of `yourdomain.com` share that
one budget.

Locally the defaults are extra ports on the same Caddy, so
<http://localhost:8181> is the Flink dashboard with auth in front.

### Creating a credential

Passwords are never stored, and never typed as a command argument (which would
put them in `ps` and your shell history). Only a bcrypt hash is written:

```bash
./scripts/caddy-admin-user.sh alice
# prompts for a password twice (confirmation), without echoing either time,
# then writes caddy/credentials/10-alice.txt (mode 600)

docker compose restart caddy
```

If this hangs indefinitely right after you type the password, you're on a
checkout from before the script stopped combining `docker compose run -it`
with piping its output through `tr`/`tail` to capture the hash — that
combination stalls on a real terminal. `git pull` and retry; the fixed
version prompts for the password with plain `read -rs` in the script itself
and feeds it to `caddy hash-password` over stdin (`-i`, no `-t`), which needs
no terminal at all.

Behind that script is one command, if you'd rather run it yourself:

```bash
docker compose exec caddy caddy hash-password --algorithm bcrypt
```

**Credentials live in files, not in `.env`.** That's deliberate: Compose
*interpolates* `env_file` values, so a hash pasted raw arrives mangled —
`$argon2id$v=19$m=47104,…` becomes `=19=47104,…`. That silently breaks
authentication, and an invalid credential stops Caddy from starting at all,
taking the API down with it. A mounted file is never interpolated.

Each user gets their own file, so access control is file management:

```bash
ls caddy/credentials/           # who has access
rm caddy/credentials/10-alice.txt && docker compose restart caddy   # revoke
```

`caddy/credentials/*` is gitignored apart from `00-locked.txt`, which is a
committed placeholder: a bcrypt hash of a random string that was thrown away.
It exists because Caddy refuses to start with an empty `basic_auth` block, so
without it an unconfigured deployment would fail to boot rather than fail
closed. With it, every admin UI answers `401` until you add a real credential.

> All credentials in the block must be **bcrypt** — one algorithm applies to
> every account, and `caddy hash-password`'s argon2id output would parse fine
> and then never authenticate (Caddy logs `bcrypt algorithm version 'a' …
> newer than current version`).

### InfluxDB needs `/api/*` exempted from basic auth

Unlike Flink and Kafka UI (no login of their own) and MinIO (its console POSTs
JSON to its own API), InfluxDB's UI logs in via real HTTP Basic Auth —
`POST /api/v2/signin` with `Authorization: Basic <user:pass>`, the same header
`basic_auth` above inspects on every request. Without an exemption, Caddy
re-checks that header against its *own* credential store (the `caddy-admin-user.sh`
accounts) instead of letting it reach InfluxDB, sees InfluxDB's admin
credentials don't match any of those, and rejects the request with its own
`401` before InfluxDB ever sees it. The UI just shows a generic "Could not
sign in" — it looks like a bad InfluxDB password, but it never got that far.

It shows up as: the tunnel works (Caddy isn't in the path there), the same
login through `CADDY_INFLUX_ADDRESS` doesn't.

Fix — scope `basic_auth` to everything except `/api/*`, so only the static UI
shell needs a Caddy credential and the login call reaches InfluxDB's own
(real) authentication:

```caddyfile
{$CADDY_INFLUX_ADDRESS::8183} {
	@ui not path /api/*
	basic_auth @ui bcrypt {
		import /etc/caddy/credentials/*.txt
	}
	reverse_proxy influxdb:8086
}
```

This doesn't weaken anything - `/api/*` was never protected by anything
*other than* InfluxDB's own login/token check to begin with, Caddy's basic
auth on top of it was just colliding with it, not adding a second factor.

### Verifying

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://flink.yourdomain.com/          # 401
curl -s -o /dev/null -w '%{http_code}\n' -u alice:... https://flink.yourdomain.com/   # 200
```

### SSH tunnels still work

If you'd rather not expose the UIs at all, leave the `CADDY_*_ADDRESS`
variables at their loopback defaults and forward the services' own ports
instead — they're bound to `127.0.0.1` on the server:

```bash
ssh -N \
  -L 8081:127.0.0.1:8081 \
  -L 8080:127.0.0.1:8080 \
  -L 8086:127.0.0.1:8086 \
  -L 9001:127.0.0.1:9001 \
  deploy@api.yourdomain.com
```

Do **not** open these ports in ufw instead. As
[section 4](#4-why-ufw-alone-is-not-enough) explains they're closed by the
loopback binding rather than by the firewall, so a ufw rule wouldn't even
work — and changing the binding would put an unauthenticated admin interface
on the internet.

## Updating

```bash
cd ~/meshtastic-things
git pull

# Four images back nineteen services, so building one updates every service
# that shares it. With no arguments this rebuilds every service in the active
# profile, which is the safe default; name specific services only to save time.
docker compose --profile full --profile minio build
docker compose --profile full --profile minio up -d
```

This builds on the server, which is what makes images and build cache the
largest consumer of disk here. Pulling CI-built images instead is wired up but
switched off: uncomment the `image:` line beside each `x-*-image` anchor in
`compose/`, re-enable the publish jobs in `.github/workflows/deploy.yml`, and
give this host a ghcr pull credential.

`registry_data_lifecycle` emails every superuser, at most once a day, when the disk is
more than `REGISTRY__DISK_ALERT_PERCENT` (80) full: a full disk is what stops Postgres.
If the email cannot be sent, the next pass (hourly) tries again.
To see where the disk goes (images, build cache, container logs, volumes, Flink
checkpoints and Kafka topics), run `./scripts/disk-usage.sh`. After a rebuild,
`docker image prune -f` and `docker builder prune -f` free what the old images and
their cache held.

One gotcha worth repeating:

- **`common/` is `pip install`ed into the Flink image.** Changing it means
  rebuilding the Flink image too, or jobs fail at runtime with a confusing
  `Failed to deserialize consumer record`. `docker compose build` (no
  arguments) builds all four images and avoids the question entirely.

Nineteen services build from four Dockerfiles, and each of those four is a
**single shared image** (`mesh-things/api:latest` and friends, defined
by the `x-*-image` anchors at the top of `docker-compose.yml`). Building any one
service therefore updates every sibling that shares its image - they cannot
drift apart. That was not always true: Compose derives a tag *per service*
unless you name the image, which is how a stale sensor-discovery consumer once
ran a day-old build while the API next to it was current.

To confirm what's running:

```bash
docker images mesh-things/*     # four images, one line each
```

- **`common/` is `pip install`ed into the Flink image.** Changing it means
  rebuilding `taskmanager` and `jobmanager` too, or jobs fail with a confusing
  `Failed to deserialize consumer record`. See [flink.md](flink.md).

An upgrade that adds catalog entries needs no action: `registry_api` seeds them on
its next start, and leaves any curated values alone.

Rolling back is `git checkout <previous-tag>`, rebuild, `up -d`. Database
migrations are not automatically reversible — take a Postgres dump before
upgrading if the release includes schema changes.

---

## Backups

Everything durable lives in named Docker volumes:

| Volume | Contents | Losing it means |
|---|---|---|
| `postgres_data` | Owners, meshes, devices, API key hashes, blueprints | The registry. Devices stop being recognised. |
| `influx_data` | All telemetry timeseries | Historical data. |
| `minio_data` | Parquet archive | The long-term archive. |
| `caddy_data` | TLS certificates and ACME account | Re-issuance; mind the rate limit. |
| `kafka_data` | Topic logs | In-flight messages only. |

Postgres is the one to back up regularly — it's small and irreplaceable.
InfluxDB holds the historical telemetry itself, also irreplaceable, and worth
the same treatment; it's larger but still small enough here (see
[Sizing](#sizing)) that a daily dump is cheap. `minio_data`, `kafka_data` and
`caddy_data` are intentionally left out — the Parquet archive can grow large
enough that a full copy is its own project rather than a cron one-liner,
Kafka only ever holds in-flight messages at 7-day retention, and Caddy's
certificates simply re-issue (mind the rate limit in
[section 7](#7-dns-and-tls)).

Dumps are encrypted with age to a key kept off the server and pruned after 7
days, by `scripts/backup.sh` from cron. The key, the setup, the crontab entry and
restoring are in [backups.md](backups.md).

## Troubleshooting

**InfluxDB's UI says "Could not sign in" through `CADDY_INFLUX_ADDRESS`, but
the same credentials work through an SSH tunnel.**
See [InfluxDB needs `/api/*` exempted from basic auth](#influxdb-needs-api-exempted-from-basic-auth)
above - Caddy's `basic_auth` is intercepting InfluxDB's own login request and
checking it against the wrong credential store.

**`readings_api` logs `Session data corrupted` then `Unauthorized` for a
browser session that's clearly logged in.**
`READINGS__SECRET_KEY` doesn't match `REGISTRY__SECRET_KEY` - they must be
identical (see the table above). Fix `.env` and recreate both containers:
`docker compose up -d registry_api readings_api`. Requests carrying
`Authorization: Bearer` instead of a session cookie aren't affected, since
they never touch `django_session`.

**Caddy won't get a certificate.**
Check `docker compose logs caddy`. Usual causes, in order of likelihood: DNS
not pointing at this server yet; port 80 or 443 blocked (`sudo ufw status`);
`CADDY_SITE_ADDRESS` still `:80` or written with a scheme or a leading colon;
or the Let's Encrypt rate limit already hit — the log says so explicitly.

**Verification or password-reset emails link to the wrong place, or the
frontend gets a `401`/`400` trying to redeem the token.**
`REGISTRY__PUBLIC_FRONTEND_URL` is unset, wrong, or the frontend's origin is
missing from `REGISTRY__CORS_ORIGINS` (needed since the frontend calls this
API cross-origin to redeem the token). The token itself is single-use and
expires after `REGISTRY__EMAIL_VERIFICATION_TTL_HOURS` or
`REGISTRY__PASSWORD_RESET_TTL_HOURS` — reusing one, or waiting past the TTL,
also produces an error and isn't a config problem.

**`registry_api` (or `readings_api`) logs `DisallowedHost: Invalid HTTP_HOST
header: 'localhost:8090'` and its healthcheck never goes healthy.**
`REGISTRY__ALLOWED_HOSTS` (or `READINGS__ALLOWED_HOSTS`) was set to just the
public domain, replacing the `localhost,127.0.0.1` default instead of adding
to it. The compose healthcheck curls `http://localhost:$PORT/health` from
inside the container, so it needs `localhost` in the list regardless of what
the public hostname is. Fix in `.env`:
```bash
REGISTRY__ALLOWED_HOSTS=localhost,127.0.0.1,api.yourdomain.com
READINGS__ALLOWED_HOSTS=localhost,127.0.0.1,api.yourdomain.com
```
then `docker compose up -d registry_api readings_api`.

**`registry_api` logs `DisallowedHost: Invalid HTTP_HOST header:
'registry-api:8090'`, followed by `Bad Request: /devices`.**
The image predates the change that always allows the compose service name, so
the quality worker's calls are rejected. Rebuild the API image and recreate
`registry_api` and `readings_api`. Adding `registry-api` to `ALLOWED_HOSTS` by
hand is not enough on an old image: the request is then redirected to
`https://registry-api:8090`, which has no TLS.

**`registry_api` won't start: `password authentication failed for user "meshtastic"`.**
`POSTGRES_PASSWORD` and `REGISTRY__DB_DSN` are two independent copies of the
same credential — nothing derives one from the other. This shows up when
`POSTGRES_PASSWORD` was changed (as [step 6](#6-configure-env) tells you to)
without also editing the password embedded in `REGISTRY__DB_DSN`: Postgres
initializes correctly with the new password, but `registry_api` is still
authenticating with whatever was in the DSN. Fix in `.env`:
```bash
REGISTRY__DB_DSN=postgresql://meshtastic:<the real POSTGRES_PASSWORD>@postgres:5432/meshtastic_keys
```
then `docker compose up -d registry_api`. `READINGS__DB_DSN` /
`READINGS__DB_PASSWORD` have the same failure mode for the read-only role.

If the password already matches on both sides, the other cause is a
`postgres_data` volume that was initialized once with an old password and
never re-read `.env` since — Postgres only applies `POSTGRES_PASSWORD` on
first initialization of an empty data directory. Update the live role instead
of relying on `.env`:
```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d postgres \
  -c "ALTER USER \"$POSTGRES_USER\" WITH PASSWORD '<the password currently in .env>';"
docker compose restart registry_api readings_api
```

**Swagger's "Try it out" fails with a CORS error.**
Set `REGISTRY__CORS_ORIGINS` / `READINGS__CORS_ORIGINS` if you're calling the API
from a browser app on another origin. Requests from the gateway's own docs
pages are same-origin and need no allowlist. `/docs` on registry's published
port (`:8090`) is not: its requests go to `GATEWAY__PUBLIC_URL`, so the dev
overlay appends `http://localhost:$REGISTRY__PORT` to both allowlists. Without the
overlay, open `/docs` through the gateway instead. Each origin needs a **scheme**
and no trailing slash — `things.yourdomain.com` fails, `https://things.yourdomain.com`
works.

**Registry API won't start: `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` "missing scheme or netloc".**
```
corsheaders.E013: Origin 'things.yourdomain.com' in CORS_ALLOWED_ORIGINS is
missing scheme or netloc
4_0.E001: the values in the CSRF_TRUSTED_ORIGINS setting must start with a
scheme (usually http:// or https://) but found things.yourdomain.com
```
`REGISTRY__CORS_ORIGINS` (and `READINGS__CORS_ORIGINS`) was set to a bare
hostname. `CSRF_TRUSTED_ORIGINS` is derived directly from that value, so one
missing scheme fails both checks at once and the API won't boot at all. Fix
in `.env`:
```bash
REGISTRY__CORS_ORIGINS=https://things.yourdomain.com
READINGS__CORS_ORIGINS=https://things.yourdomain.com
```
then `docker compose up -d registry_api readings_api`.

**A non-superuser owner can view their device (`GET`) but editing it (`PUT`) fails with "CSRF verification failed", even though `REGISTRY__CORS_ORIGINS` already lists the frontend's origin.**
This is unrelated to device/mesh ownership despite the generic `Forbidden: /devices/<uuid>` line in the container log — GET isn't CSRF-checked, so it always looks fine regardless of the real cause. It shows up whenever the frontend and `registry_api` are on different subdomains of the same site (e.g. `things.yourdomain.com` and `api.yourdomain.com`): the `csrftoken` cookie defaults to being scoped to `registry_api`'s own host, so the browser still attaches it to requests sent *to* that host, but JavaScript running on the frontend's origin can't read it via `document.cookie` to echo it back as the `X-CSRFToken` header. Set `REGISTRY__COOKIE_DOMAIN` to the shared parent domain:
```bash
REGISTRY__COOKIE_DOMAIN=.yourdomain.com
```
then `docker compose up -d registry_api`. Also worth checking after any `.env` edit that touches `registry_api`: a plain `docker compose restart` reuses the container's existing environment, so it looks unchanged even after the file is fixed — use `docker compose up -d registry_api` to actually pick up new values.

**A port is open that shouldn't be.**
`COMPOSE_FILE` in this server's `.env` still points at
`docker-compose.dev.yml` — likely copied over from a local dev `.env` instead
of a fresh `env.example`. Confirm with `docker compose config | grep -B 2
published` (every `host_ip` should be `127.0.0.1` except Caddy's), then delete
the `COMPOSE_FILE` line and `docker compose --profile full --profile minio up -d` again with
the base file alone.

**Nothing appears in InfluxDB.**
Almost always the registered-gateway gate rather than a broken pipeline. See
[debugging.md](debugging.md) and
[architecture.md#registered-gateways-only-gate](architecture.md#registered-gateways-only-gate).

**Out of disk.**
`docker system df`, then `docker image prune -a`. Check InfluxDB retention and
the MinIO bucket; neither expires anything by default.

For pipeline-level debugging — logs, Flink UI, tracing a message through the
stages — see [debugging.md](debugging.md).
