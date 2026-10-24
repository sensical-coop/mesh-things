# API reference

One API, served by two container roles: **registry** answers for owners, meshes,
devices and the catalog, and **readings** answers for the values those devices
recorded. Interactive OpenAPI docs live at `/docs` and cover both.

This doc exists for copy-pasteable `curl` examples and for scripting. From Python, use
the [`mesh-things` client](client.md), which exposes every operation below as a method. Examples
use the direct ports (`:8090` registry, `:8091` readings), which is what local
dev publishes. In production one Caddy instance fronts both on a single domain
and **forwards paths unchanged**, so every path below is already the external
one — only the host differs. See
[architecture.md#reverse-proxy](architecture.md#reverse-proxy).

## Base URLs

| Resource | Local dev (direct port) | Production (behind Caddy) |
|---|---|---|
| owners | `http://localhost:8090/owners...` | `https://api.yourdomain.com/owners...` |
| meshes | `http://localhost:8090/meshes...` | `https://api.yourdomain.com/meshes...` |
| devices (registration) | `http://localhost:8090/devices...` | `https://api.yourdomain.com/devices...` |
| measurement types / telemetry variants | `http://localhost:8090/measurements...`, `/telemetry-variants...` | `https://api.yourdomain.com/measurements...`, `/telemetry-variants...` |
| telemetry variant ↔ measurement type links | `http://localhost:8090/telemetry-variants/{id}/measurements`, `/telemetry-variants/{id}/measurements/{link_id}` | `https://api.yourdomain.com/telemetry-variants/{id}/measurements`, `/telemetry-variants/{id}/measurements/{link_id}` |
| postprocessing | `http://localhost:8090/postprocessing-blueprints...`, `/devices/{uuid}/postprocessings...`, `/algorithms` | `https://api.yourdomain.com/postprocessing-blueprints...`, `/devices/{uuid}/postprocessings...`, `/algorithms` |
| alarm detectors | `http://localhost:8090/detectors` | `https://api.yourdomain.com/detectors` |
| metrics (counts of registered things) | `http://localhost:8090/metrics` | `https://api.yourdomain.com/metrics` |
| email status (superusers) | `http://localhost:8090/status/email` | `https://api.yourdomain.com/status/email` |
| readings by device UUID | `http://localhost:8091/readings/devices/{device_uuid}[/latest\|/quality]` | `https://api.yourdomain.com/readings/devices/{device_uuid}...` |
| readings by mesh+node | `http://localhost:8091/readings/meshes/{mesh_id}/nodes/{node_id}[/latest\|/quality]` | `https://api.yourdomain.com/readings/meshes/{mesh_id}/nodes/{node_id}...` |
| mesh traffic stats | `http://localhost:8091/readings/meshes/{mesh_id}/stats` | `https://api.yourdomain.com/readings/meshes/{mesh_id}/stats` |
| radio links and traceroutes | `http://localhost:8090/meshes/{mesh_id}/links`, `/meshes/{mesh_id}/traceroutes` | `https://api.yourdomain.com/meshes/{mesh_id}/links`, `/meshes/{mesh_id}/traceroutes` |
| service index | — (proxy only) | `https://api.yourdomain.com/` |
| schema + docs | `http://localhost:8090/schema`, `/docs` | `https://api.yourdomain.com/schema`, `/docs` |

`GET /status/email` (superusers only) reports whether registry's emails reach its mail
server: `ok` is false while the most recent send failed, with `last_error` and the
template that failed, and `sent_24h`/`failed_24h` count the last day. It cannot tell
whether a message then lands in an inbox. The server monitor alerts on it.

Note that `/metrics` counts registered things, while
`/readings/.../quality` reports how good one device's data is. Different
questions, different roles.

### Discovering all of it

The root answers two questions without needing this table:

```bash
curl -s https://api.yourdomain.com/ | python3 -m json.tool          # the index
curl -s https://api.yourdomain.com/schema                           # OpenAPI 3.0, YAML by default
curl -s "https://api.yourdomain.com/schema?format=json" | python3 -m json.tool
```

`GET /schema` is a single generated document covering both roles, and
`GET /docs` is one Swagger UI over it. Because the two roles share no paths,
nothing is merged or rewritten and there is no cross-service call that can
fail. It is generated at request time from the live urlconfs, so it cannot
fall behind the routes.

Every response, errors included, carries an `API-Version` header. It holds the
same version as the schema's `info.version` and the `mesh-things` Python package,
and goes up with every change to the schema. Browsers can read it cross-origin.

Every operation declares its query parameters, its request body and its response
schema, so the Swagger "Try it out" form offers the real inputs and a generated
client gets typed models. The form sends its requests to the schema's server,
`GATEWAY__PUBLIC_URL`, so it is same-origin when `/docs` is opened through the
gateway (`http://localhost/docs` locally). On `http://localhost:8090/docs` it is
cross-origin, and works only because the dev overlay adds that origin to both
`*__CORS_ORIGINS`. These are plain `APIView`s reading `request.query_params`
directly, which nothing can introspect, so each one is declared explicitly with
`@extend_schema` in `registry/views.py` and `readings/views.py`; a new query
parameter has to be added there as well as to the view, or it will not appear.

`GET /` is a small static index in the Caddyfile pointing at `/schema`,
`/docs`, `/health`, `/metrics` and `/readings`. It stays static because Caddy
cannot query Postgres, which is why counts live behind the `/metrics` link
rather than inline.

## Registry role (`:8090`)

Django + Django REST Framework, backed by Postgres via real migrations (see
`registry/migrations/`). Two resources model a Meshtastic mesh network: a **Mesh** holds
the shared `channel_id` + `psk_b64` every device on it uses, and a **Device** is a single
unified resource for both roles a physical device can play — a single `is_gateway`
boolean, no separate `is_node` field, since a Device that isn't a gateway is a node by
definition. A gateway relays MQTT traffic for its mesh and must be
explicitly registered; a node is normally auto-discovered the first time one of its
packets decrypts successfully, though it can also be pre-registered directly (e.g. to
set `admin_keys_b64` in advance). Every gateway create/update/delete (and every mesh PSK
rotation, which republishes its gateways) publishes to the compacted `mesh.keys.v1`
topic; every node `is_allowed` transition publishes to the compacted
`mesh.node_rejections.v1` topic instead. `flink-job` consumes both as broadcast state
(see [architecture.md](architecture.md) and
[debugging.md#kafka-tombstones-crash-simplestringschema](debugging.md#kafka-tombstones-crash-simplestringschema)).
**Registering a gateway is now required before its mesh's data gets decoded at all** —
see [architecture.md#registered-gateways-only-gate](architecture.md#registered-gateways-only-gate).
A node needs no explicit registration of its own to have its data accepted; it's allowed
the moment it's first seen through a registered gateway, unless later rejected by the
mesh owner — see
[architecture.md#device-registration-and-the-is_allowed-gate](architecture.md#device-registration-and-the-is_allowed-gate).

`psk_b64` (on Meshes) and `admin_keys_b64` (on Devices) are password fields: they only
appear in a response to the resource's owner (the mesh's `owner`, or the
owner of the mesh a device belongs to) and to superusers (see [Superuser](#superuser)
below). Every other caller gets the same response with the field omitted. See [Meshes](#meshes) and [Devices](#devices).

Authenticated requests are rate-limited to 120/minute per owner; `GET /owners`/
`GET /owners/{id}` to 60/minute per source IP; `POST /owners` to 20/hour per source IP;
`POST /owners/login` to 10/minute per source IP and email;
`POST /owners/me/resend-verification` to 3/hour per owner. Exceeding any of them
returns `429`. Superusers are never throttled, on registry or readings, and their key
is accepted even from an address blocked for invalid keys. Logging in is still
limited, as the caller is not known yet. See
[architecture.md#registry-rate-limiting](architecture.md#registry-rate-limiting).

**A new owner starts unverified** (`is_active: false`) and can't do anything but manage
their own account until they click the link in a verification email — see
[Verifying your email](#verifying-your-email) below and
[architecture.md#registry-email-verification](architecture.md#registry-email-verification).

### Owners

`POST /owners` is the only unauthenticated write on this API — it's the "sign up" step,
so it can't itself require a token. Rate-limited to 20/hour per source IP (the highest-
value abuse target on this API, being the one unauthenticated write). It returns a
server-generated `api_key` **exactly once, in that response, and it is never shown or
stored in retrievable form again** (only its hash is kept). Save it immediately.

`password` is required (validated by Django's standard password rules - at least 8
characters, not too similar to your name/email, not a common password, not all-numeric)
- it's the credential for [password login](#password-login) below, independent of
`api_key`.

**Signing up accepts the account terms.** On an instance that does not enforce terms
(`REGISTRY__TERMS_ENFORCED=false`, see [deploy.md](deploy.md#mqtt-sources)) every terms
route below, and the mesh and source ones, answers `404`, `terms_version` is optional
and ignored everywhere, and nothing is recorded. Otherwise, read them first, without an
account:

```bash
curl -s "http://localhost:8090/terms?locale=en" | python3 -m json.tool
```

The answer is `{version, locale, title, description, statements: [{id, text}], footnote}`,
the same shape as the [mesh terms](#meshes) and [source terms](#sources). The account
terms cover only the account (Terms of Use and Privacy Policy): signing up stores no mesh
data, so someone can sign up just to explore public meshes. Send the served `version` as
`terms_version` (required; `400` when missing or out of date) and optionally
`terms_locale` (`en` or `es`). The acceptance is recorded, with who accepted (name and
email at that moment), the locale and a hash of the exact text served. The owner record
carries `terms_accepted_version`.

Account terms never lapse. When they change, accept the new version with

```bash
curl -s -X POST http://localhost:8090/owners/me/terms-acceptance \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"terms_version": "<version from /terms>", "terms_locale": "en"}' | python3 -m json.tool
```

```bash
curl -s -X POST http://localhost:8090/owners \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com", "password": "correct-horse-battery-staple",
       "terms_version": "<version from /terms>", "terms_locale": "en"}' | python3 -m json.tool
```

```json
{
  "id": "7e56cb57-9023-4596-8b82-ea493980a0ec",
  "name": "Alice",
  "email": "alice@example.com",
  "is_superuser": false,
  "is_staff": false,
  "is_active": false,
  "email_verified_at": null,
  "email_verification_sent_at": "2026-08-30T00:29:01.629378Z",
  "last_login": null,
  "created_at": "2026-08-30T00:29:01.815303Z",
  "api_key": "<43 characters, shown only in this response>"
}
```

`is_active: false` means unverified — a verification email was just sent, and every
route except `/owners/me` and the verification routes below returns `403` until the
link is clicked. Signup also sets a session cookie, so a browser is signed in straight
away; scripts ignore it and use `api_key`.
Duplicate `email` returns `409`. `GET /owners`, `GET /owners/{id}`, and
`GET /owners/me` never include `api_key`, its hash, or `password` — the only two
responses that ever show `api_key` are `POST /owners` and `POST /owners/me/rotate-key`.

`GET /owners` and `GET /owners/{id}` are public (no auth required) and rate-limited to
60 requests/minute per source IP — a directory of who exists, not a way to look up
contact info, so `email` is omitted (only `GET /owners/me` includes it, to the owner
themselves). `is_superuser` is omitted for the same reason: these routes are
unauthenticated, and naming the privileged accounts tells an attacker which one to
go after. `GET /owners/me` still reports it to the owner themselves.

The response scales with the caller. `GET /owners/{id}` returns the **full record**
when the caller is the owner being requested, or a superuser — the same fields
`GET /owners/me` returns. `GET /owners` stays on the public shape for everyone except
a superuser, deliberately: an owner's own row is not widened there, so every row in
the array has the same shape and a generated client gets one type. Read your own
record in full from `GET /owners/me` or `GET /owners/{your id}`.

`api_key` is never included, for any caller.

```bash
# Public shape - id, name, created_at
curl -s http://localhost:8090/owners | python3 -m json.tool
curl -s http://localhost:8090/owners/<id> | python3 -m json.tool

# Your own record in full, on the same route
curl -s http://localhost:8090/owners/<your id> -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool

# A superuser reads every owner in full
curl -s http://localhost:8090/owners -H "Authorization: Bearer $SUPERUSER_API_KEY" | python3 -m json.tool
```

```json
{
  "id": "<owner id>",
  "name": "Alice",
  "email": "alice@example.com",
  "is_superuser": false,
  "is_staff": false,
  "is_active": true,
  "email_verified_at": "2026-09-03T00:05:00Z",
  "email_verification_sent_at": "2026-09-03T00:00:00Z",
  "last_login": "2026-09-14T15:03:19Z",
  "created_at": "2026-09-03T00:00:00Z"
}
```

Three of those fields are easy to misread:

- `is_active` means the email address has been verified, not that the account is
  enabled some other way.
- `is_staff` is access to the Django admin at `/admin/`, a separate capability from
  `is_superuser`. Promoting an account to superuser does not grant it; only
  `createsuperuser` sets both.
- `last_login` is the last session sign-in: signup (`POST /owners`) or a password login
  (`POST /owners/login`). A bearer-key request never updates it. It is not a "last
  seen" timestamp.

For a superuser this is also the only way to see which accounts have not yet verified
their address, and when their verification email was last sent.

```json
{
  "id": "7e56cb57-9023-4596-8b82-ea493980a0ec",
  "name": "Alice",
  "created_at": "2026-08-30T00:29:01.975377"
}
```

### Verifying your email

Click the link in the verification email (in local dev, view it at
`http://localhost:8025` via the `mailhog` compose service instead of a real inbox — see
[debugging.md](debugging.md)). It opens the frontend app, which reads the token from
the query string and calls this endpoint itself — or call it directly:

```bash
curl -s "http://localhost:8090/owners/verify-email?token=<token from the email>"
```

No `Authorization` header — the token in the query string is the credential. Returns
`200` on success (and stays `200` if you hit an already-verified link again — safe to
retry/re-click). An invalid or expired token returns `400`; links expire after
`REGISTRY__EMAIL_VERIFICATION_TTL_HOURS` (24 by default).

**Resend the verification email** (3/hour, per owner):

```bash
curl -s -X POST http://localhost:8090/owners/me/resend-verification \
  -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
```

Requires a valid bearer key but *not* verification itself — this is one of the two
routes (along with `/owners/me`) an unverified owner can still call. No-ops with `200`
if already verified. Note: changing your email via `PUT /owners/me` below also resets
verification and sends a fresh link to the new address.

### Managing your own owner record (`/owners/me`)

All four routes below require `Authorization: Bearer <api_key>` and act on whichever
owner that key belongs to — there's no `owner_id` in the path, so there's no way to
target anyone else's record through them.

```bash
# fetch your own profile
curl -s http://localhost:8090/owners/me -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool

# update name, email, alarm email frequency and/or status alerts (all optional, partial update)
curl -s -X PUT http://localhost:8090/owners/me \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"name": "Alice Renamed", "alarm_email_cooldown_seconds": 7200}' | python3 -m json.tool
```

Duplicate `email` on `PUT` returns `409`, same as `POST /owners`. Changing `email` to a
new address resets verification (`is_active` goes back to `false`) and sends a fresh
verification link to the new address — see
[Verifying your email](#verifying-your-email) above.

`alarm_email_cooldown_seconds` sets the length of each device's alarm window for this
owner, overriding the server-wide default (see
[data-quality.md#alarms](data-quality.md#alarms)). The first alarm on a device is
emailed straight away; any further alarms on that device during the window, from any
check, arrive as one summary email when it ends. Accepts `0` (email on every alarm, no
summaries) up to `2592000` (30 days), or `null` to go back to using the server default.
Each alarm email links to the device's and the mesh's pages in the frontend console,
`/devices/<device uuid>` and `/meshes/<mesh id>` under `REGISTRY__FRONTEND_CONSOLE_PATH`.

`status_alerts_enabled` (default `false`) opts an operator in to emails about the sources
and sinks they created: a source not connected to its broker for a couple of hours, a
source that has received no message for six hours even though it reads `connected`, and
a sink with meshes or devices attached that nobody has been connected to for a day. Each
outage is emailed once; the next one only after it recovers. Superusers always get the
silent-source email, since restarting the source usually fixes it (see
[Sources](#sources)).

`source_rate_alerts_enabled` (default `false`) also emails an operator when a source they
created averages more messages per second over an hour than the instance allows
(`REGISTRY__SOURCE_RATE_ALERT_MSGS_PER_S`, 20 by default). Superusers get this email
whatever the setting, since a busy source costs the whole instance bandwidth and disk.

**Rotate your API key** — issues a new key and immediately invalidates the old one
(same owner, same meshes/gateways; only the credential changes). Fixes "my key may
have leaked" or "I just want a fresh one." It does **not** help if the key is already
completely lost, since there's no other way to prove identity — register a new owner
and re-register the meshes/gateways in that case.

```bash
curl -s -X POST http://localhost:8090/owners/me/rotate-key \
  -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
```

Response is shaped like `POST /owners`'s — a fresh `api_key`, shown exactly once.

**Delete your own account** — cascades: publishes a Kafka delete event for every allowed
gateway you registered and an unreject event for every rejected node across your meshes
(same effect as looping `DELETE /devices/{id}`), and revokes the credentials of every
[sink](#sinks) you created, disconnecting its consumers, then removes your meshes, devices
and sinks, before removing anything else from Postgres. If any publish fails, the whole thing
aborts with `502` and *nothing* is deleted yet — safe to retry. Events already published
before a mid-loop failure stay applied to Flink's broadcast state regardless
(fail-closed), even though their DB rows persist until a successful retry finishes the
job.

```bash
curl -s -o /dev/null -w "status: %{http_code}\n" -X DELETE http://localhost:8090/owners/me \
  -H "Authorization: Bearer $OWNER_API_KEY"
```

**Delete another owner's account** (superusers only) — `DELETE /owners/{id}` runs the
same cascade as `DELETE /owners/me` above (gateway deregistration, node unrejection,
sink revocation, then the owner and their meshes, devices and sinks), just against an arbitrary owner instead of
only the caller. A non-superuser gets `403`; an unknown `id` gets `404`.

```bash
curl -s -o /dev/null -w "status: %{http_code}\n" -X DELETE http://localhost:8090/owners/<id> \
  -H "Authorization: Bearer $SUPERUSER_API_KEY"
```

### Password login

A second, independent credential from the bearer `api_key` above - for a future
dashboard's login form, not for scripts/integrations (keep using `api_key` and
`POST /owners/me/rotate-key` for those). Sets a session cookie rather than
returning a token; see [architecture.md#password-login](architecture.md#password-login)
for why. A browser client should call `GET /owners/csrf-cookie` once before its first
login/logout/reset call, to pick up the CSRF cookie Django's session auth needs on
unsafe methods.

```bash
# prime the CSRF cookie (once, before any of the below)
curl -s -c cookies.txt http://localhost:8090/owners/csrf-cookie

# log in - cookie jar carries the session on subsequent requests
curl -s -c cookies.txt -b cookies.txt -X POST http://localhost:8090/owners/login \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "correct-horse-battery-staple"}' | python3 -m json.tool
```

Response is shaped like `GET /owners/me` (profile + `devices`), not like `POST /owners`
- no `api_key` in it. Wrong email/password returns `401`. An unverified owner is signed
in too, with `is_active: false`, and can only reach its own account until it verifies.
Login is limited to 10 attempts a minute for the same email from the same source IP;
past that it returns `429` for that pair, even with the right password, until the
oldest attempt is a minute old.

Once logged in, every route on this API works the same over the session cookie as over
`Authorization: Bearer` - `curl -b cookies.txt http://localhost:8090/owners/me` needs no
`Authorization` header at all.

```bash
# log out - clears the session
curl -s -b cookies.txt -X POST http://localhost:8090/owners/logout
```

**Forgot your password:**

```bash
curl -s -X POST http://localhost:8090/owners/request-password-reset \
  -H "Content-Type: application/json" -d '{"email": "alice@example.com"}'
```

Always `200` with a generic message, whether or not that email is registered -
deliberately, since the caller hasn't proven they own the address. If it is registered,
an email is sent with a link to the frontend app (`REGISTRY__PUBLIC_FRONTEND_URL`)
carrying a token in the query string (valid `REGISTRY__PASSWORD_RESET_TTL_HOURS`,
1 hour by default); it's also how an owner who signed up before password login existed
sets one for the first time (`set_unusable_password()` from signup, until they do).

The frontend reads that token and sends it back with the new password:

```bash
curl -s -X POST http://localhost:8090/owners/reset-password \
  -H "Content-Type: application/json" \
  -d '{"token": "<token from the email>", "new_password": "a-new-strong-password"}'
```

Single-use - the token is the only credential, same shape as email verification.
Invalid/expired/unknown token returns `400` on `token`.

**Change your password while logged in** (requires the *current* one, even though
you're already authenticated, so a hijacked or left-open session can't take over the
login credential):

```bash
curl -s -X POST http://localhost:8090/owners/me/change-password \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"current_password": "correct-horse-battery-staple", "new_password": "a-new-strong-password"}'
```

### Authentication for mesh and device mutations

Every `/meshes*` and `/devices*` route — `POST`, `GET` (list and single), `PUT`,
`DELETE` — requires `Authorization: Bearer <api_key>`. The owner's identity is derived
entirely from the token, **not** from any `owner_id` field in the request body (there
is no such field in either request schema). A `Device` has no owner field of its own at
all — `Mesh.owner` is the *only* ownership relationship in the whole schema, and it's
what gates every mutation of the mesh itself and of every device on it, gateway or node
(registering, editing, or flipping `is_allowed`). `GET /meshes` and `GET /devices` only
ever return **the caller's own** rows (own meshes, and devices on meshes the caller
owns) — there is no way to list or browse another owner's registrations through this
API. A device can only be created against a mesh the caller owns (`404`/`403`, same as
the table below). For cross-owner operational visibility (e.g. "which owner registered
device X"), query Postgres directly — see
[debugging.md](debugging.md#a-mesh-goes-dark-after-deploying-the-ownership-gate-with-no-error-anywhere).

| Situation | Status |
|---|---|
| No `Authorization` header | `401` |
| Malformed/unknown API key | `401` |
| Valid key, but the mesh/device belongs to a *different* owner (`GET`/`PUT`/`DELETE` single-resource routes only) | `403` |
| `POST /devices` with an unknown `mesh_id` | `404` |
| `POST /devices` against a mesh owned by someone else | `403` |

### Superuser

An `Owner` with `is_superuser: true` bypasses every ownership check above: full
read/write on every owner's meshes and devices, and every list route (`GET /meshes`,
`GET /devices`) returns everyone's rows instead of just the caller's own. It gets **no**
special access to `psk_b64` or `admin_keys_b64` on resources it doesn't itself own —
those stay hidden for a superuser exactly as for anyone else, see the note at the top
of this doc. A superuser can also remove any owner outright — see
[Delete another owner's account](#owners) above.

There is deliberately no API route to grant or revoke superuser — `POST /owners` is
public unauthenticated signup, so self- or peer-escalation through the API has to be
impossible. Instead, registry is Django + DRF, and this is `manage.py createsuperuser`
(overridden to also mint the bearer API key superusers actually use to call the REST
API, since Django's stock version only knows about username/password):

```bash
docker compose exec registry_api python manage.py createsuperuser \
  --email you@example.com --name "You"
```

Creates the owner (printing a one-time API key, exactly like `POST /owners`, plus a
Django admin-panel login password) if they don't exist yet, or just grants superuser
and mints an API key if they don't already have one. Safe to re-run — promoting an
already-superuser owner with a key is a no-op. See
`registry/management/commands/createsuperuser.py`.

A superuser can also browse and edit everything (`psk_b64`/`admin_keys_b64` are shown
read-only, since a key changed there would not reach the pipeline) through the Django admin site at
`http://localhost:8090/admin/`, logging in with the password the command above printed.

### Operator

`role: "operator"` lets an owner create [sources](#sources) and [sinks](#sinks) and see
and manage the ones they created, and archive devices on the meshes they own and read that
[archive](#parquet-archive). It widens nothing else. A superuser counts as an operator. Only a superuser grants it:

```bash
curl -s -X PUT http://localhost:8090/owners/<owner id> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $SUPERUSER_API_KEY" \
  -d '{"role": "operator"}' | python3 -m json.tool
```

`role` is `member` or `operator`. The response is the full owner record, which now
includes `role`. Anyone else gets `403`. The Django admin exposes the same field, but
does not tell the pipeline: after a role change there, run `manage.py publish_sink_config`.
Granting `operator` this way also approves any pending operator request from that owner,
without emailing them. Taking it away stops archiving the owner's devices (their
`archive_enabled` is kept, and applies again if the role is granted back); if that
cannot be published the role is kept and the answer is `502`.

#### Requesting the role

A verified owner can ask for the role instead of contacting a superuser directly:

```bash
curl -s -X POST http://localhost:8090/owners/me/operator-request \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"reason": "I run the regional broker for our community"}' | python3 -m json.tool

# the latest request and its status: pending, approved or rejected
curl -s http://localhost:8090/owners/me/operator-request -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
```

Every active superuser with an email address is emailed a link to
`{console}/operator-requests/<id>`. One pending request per owner (`409` for a second,
and for an owner who is already an operator), and at most 3 a day (`429`). A failed
notification email does not undo the request. After a rejection the owner may file
again.

A superuser lists and decides them. The list defaults to `pending`; pass
`?status=approved|rejected|all` for the rest. It includes the requester's name and email.

```bash
curl -s http://localhost:8090/operator-requests -H "Authorization: Bearer $SUPERUSER_API_KEY" | python3 -m json.tool

curl -s -X PUT http://localhost:8090/operator-requests/<request id> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $SUPERUSER_API_KEY" \
  -d '{"decision": "approve", "note": "Welcome aboard"}' | python3 -m json.tool
```

`decision` is `approve` or `reject`, and `note` is optional and included in the email to
the requester. Approving sets `role` to `operator` in the same transaction. A request
that is no longer pending answers `409`. Everyone but a superuser gets `403` on
`/operator-requests`. The Django admin shows requests read-only, so a decision always
sets the role and emails the requester.

A device created by a superuser against someone else's mesh is still gated by that
mesh's own owner going forward, not the superuser — a `Device` has no `owner_id` field
of its own to begin with (see
[Authentication for mesh and device mutations](#authentication-for-mesh-and-device-mutations)
above); only `Mesh.owner` matters, and it's unaffected by who happened to create the
device.

### Browsing GET routes directly from a browser address bar

A plain browser navigation can't set an `Authorization` header, so every authenticated
route also accepts the key as an `access_token` query parameter, checked only when no
`Authorization` header is present. This exists purely so you can paste a URL into a
browser tab to poke around — prefer the header (see the `curl` examples throughout this
doc) for anything scripted, since query strings end up in browser history and in the
server's access logs, unlike headers.

```
http://localhost:8090/owners/me?access_token=$OWNER_API_KEY
http://localhost:8090/meshes?access_token=$OWNER_API_KEY
http://localhost:8090/devices?access_token=$OWNER_API_KEY
```

Paste one of these into a browser (with `$OWNER_API_KEY` substituted for the real
value) to view the JSON response directly. This only helps for `GET` — a browser
address bar can't issue `POST`/`PUT`/`DELETE`, so those still need `curl`, the
[Python examples](../server/mesh_things/examples/), or the interactive `/docs` UI.

### Meshes

A Mesh is the shared secret for a physical Meshtastic network: `channel_id` + `psk_b64`,
the same for every device on it. Creating a Mesh alone authorizes nothing by itself —
only its gateway devices do that (see [Devices](#devices) below).

**Create:**

```bash
curl -s -X POST http://localhost:8090/meshes \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{
    "channel_id": "LongFast",
    "psk_b64": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "label": "home mesh",
    "terms_version": "<version from /meshes/terms>",
    "terms_locale": "en"
  }' | python3 -m json.tool
```

**Mesh terms.** A mesh on the default broker stores traffic that can carry personal data
of people who never signed up, and its owner is the controller of that traffic. Creating
one needs its mesh terms accepted:

```bash
curl -s "http://localhost:8090/meshes/terms?locale=en" -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
```

`terms_version` is required without a `source_id` (`400` when missing or out of date) and
ignored with one, since the source's terms cover it. Moving a mesh from a source onto
the default broker (`PUT` with `"source_id": null`) asks for them too, unless the mesh
already holds a current acceptance. The mesh record carries `terms_accepted_version`,
`terms_expires_at` (null when data is kept without a time limit) and `paused_at`, shown to
the owner and, read-only, to superusers. Renew, or accept changed terms, with

```bash
curl -s -X POST http://localhost:8090/meshes/<mesh id>/terms-acceptance \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"terms_version": "<version from /meshes/terms>", "terms_locale": "en"}' | python3 -m json.tool
```

Only the mesh's owner (`403` otherwise), and `409` on a mesh with a source. See
[Data lifecycle](#data-lifecycle) for what a lapse does.

Response includes a generated `id` (UUID) — save it, you'll need it to register
gateways against this mesh. `psk_b64` can be `""` for a plaintext-only mesh.
`source_id` is optional: leave it unset for a mesh heard on this instance's own broker,
or set it to a [source](#sources) you can see to ingest a mesh that lives on a remote
broker.
Everything after that, gateways included, works the same.
**`psk_b64` appears in the response only to the mesh's owner** — every other caller,
on this or any other mesh-returning route, gets the response with `psk_b64` omitted
(see the note at the top of this section).

**List / get:**

```bash
curl -s http://localhost:8090/meshes -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
curl -s http://localhost:8090/meshes/<id> -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool

# just the ones you own, excluding public meshes
curl -s "http://localhost:8090/meshes?owned=true" -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool

# just the ones bridged from one source (only meshes you own; any mesh for a superuser)
curl -s "http://localhost:8090/meshes?source_id=<source id>" -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool

# no credentials: public meshes only
curl -s http://localhost:8090/meshes | python3 -m json.tool
```

The list covers every mesh the caller may read: their own and any with
`is_public: true` (see [Public meshes](#public-meshes) below). Each row carries `owner_id`, so a client
can tell which are its own. A mesh the caller may **not** read answers `404`, not
`403` — a `403` would confirm that a private mesh exists to someone with no access
to it.

**Update:**

```bash
curl -s -X PUT http://localhost:8090/meshes/<id> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"psk_b64": "new-key-base64=="}' | python3 -m json.tool
```

`channel_id`, `psk_b64`, `label`, `is_public`, `source_id` and `discover_gateways` are
all independently optional in the PUT body.
Changing `channel_id`, `psk_b64` or `source_id` republishes an upsert for every gateway
already registered on this mesh, so it's redistributed to all of them in one call — if
any of those publishes fails partway through, the whole update rolls back, and the
gateways already republished are sent the old values again, so no gateway is left on a
stale value while others moved to the new one. Decryption itself keys off
`psk_b64` per gateway; `channel_id` is redistributed for consistency, not because
decoding depends on it.

**Gateway discovery** — register gateways without typing their node numbers:

```bash
curl -s -X PUT http://localhost:8090/meshes/<id> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"discover_gateways": true}' | python3 -m json.tool
```

`discover_gateways` (default `false`, also accepted on `POST /meshes`) registers any
gateway whose packets decode with this mesh's channel and PSK, on its source or the
default broker, as soon as one of them proves it. There is no approval step: the
gateway appears in [`/devices`](#devices) with `is_gateway: true` and `discovered_at`
set, and its traffic is decoded from then on. Packets it relayed before that are not
recovered.

The first few new gateways the bridge hears are checked straight away; on a busy broker
the rest can take up to 15 minutes (`MQTT_BRIDGE__DISCOVERY__*` in `.env`). A gateway is
**not** registered when:

- another mesh, with discovery on or off, shares the same source, channel and PSK, since
  only one mesh can have it;
- it is already an allowed gateway on any mesh;
- this mesh holds a rejected (`is_allowed: false`) row for it. To keep a discovered
  gateway out, reject it rather than delete it: a deleted one is found again.

A node already registered on this mesh becomes its gateway. Switching discovery off
keeps the gateways already found.

With the default key (`AQ==`), any other one-byte key or a blank PSK, every gateway on
that channel decrypts the traffic, so only an operator may switch discovery on, or move a
mesh with discovery on to such a key. Anyone else gets `403`.

**Delete:**

```bash
curl -s -o /dev/null -w "status: %{http_code}\n" -X DELETE http://localhost:8090/meshes/<id> \
  -H "Authorization: Bearer $OWNER_API_KEY"
```

Cascades: publishes a Kafka delete for every gateway on this mesh first (fail-closed,
same pattern as `DELETE /owners/me`), then removes the gateways and the mesh from
Postgres.

**Devices on this mesh** — every device registered or discovered on this mesh, gateways
and nodes alike, returned directly (no synthesis):

```bash
curl -s http://localhost:8090/meshes/<id>/devices -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
```

```json
[
  {"uuid": "<device uuid>", "node_id": 111222333, "mesh_id": "<mesh id>", "label": "office gateway", "is_gateway": true, "admin_keys_b64": [], "is_allowed": true, "last_seen": "2026-08-30T18:50:36", "created_at": "2026-08-30T18:49:35", "updated_at": "2026-08-30T18:49:35"},
  {"uuid": "<device uuid>", "node_id": 555000222, "mesh_id": "<mesh id>", "label": null, "is_gateway": false, "admin_keys_b64": [], "is_allowed": true, "last_seen": "2026-08-30T18:51:28", "created_at": "2026-08-30T18:51:28", "updated_at": "2026-08-30T18:51:28"}
]
```

There's no `POST` on this route — register or pre-register a device via `POST /devices`
(see [Devices](#devices) below) with this mesh's `id` as `mesh_id`. A node row can also
appear here without ever having been `POST`ed at all: `registry/management/commands/
consume_device_sightings.py` auto-creates one the first time that device's packets
decrypt successfully against this mesh's PSK (see
[architecture.md#device-catalog](architecture.md#device-catalog)). A gateway's own row
always appears here (`is_gateway: true`) from the moment it's registered, even before
it's relayed any of its own telemetry — in that case `last_seen` is still `null`, since
there's no real sighting yet to back it.

### Sources

A source bridges a remote MQTT broker into this instance, so a mesh whose traffic is
published elsewhere can be ingested like one on the instance's own broker. See
[architecture.md#mqtt-sources](architecture.md#mqtt-sources) for how it works.

Sources are visible only to [operators](#operator). An operator lists, reads, updates,
deletes and attaches meshes to the sources they created, and nothing else; a superuser
does all of that on every source. Any other owner gets `403` on `/sources`, and a source
created by another operator answers `404`, as if it did not exist.

**Terms** (operator). Creating a source first needs the operator to accept the source
terms, which the API serves and versions:

```bash
curl -s "http://localhost:8090/sources/terms?locale=en" -H "Authorization: Bearer $OPERATOR_API_KEY" | python3 -m json.tool
```

The answer is `{version, locale, title, description, statements: [{id, text}], footnote}`
in `en` or `es` (anything else falls back to `en`). Every statement must be accepted.
The footnote states how long the source's data is kept, from the server's retention
settings. The operator is the controller of the bridged traffic and Sensical its
processor, so acceptance is recorded as evidence: who accepted (name and email at that
moment), the version, the locale and a hash of the exact text served. These records
outlive the source and the operator's account.

**Create** (operator):

```bash
curl -s -X POST http://localhost:8090/sources \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPERATOR_API_KEY" \
  -d '{
    "label": "public meshtastic, EU",
    "server": "mqtt.meshtastic.org:1883",
    "ssl": false,
    "username": "meshdev",
    "password": "large4cats",
    "topic": "msh/EU_868/2/e/MyChannel/#",
    "qos": 1,
    "terms_version": "<version from /sources/terms>",
    "terms_locale": "en"
  }' | python3 -m json.tool
```

| Field | Default | Notes |
|---|---|---|
| `server` | required | `host:port` (`[v6]:port` for IPv6). This instance's own broker is refused, by name or by address, since it would loop, as is any broker the server blocks (`REGISTRY__SOURCES_BLOCKED_BROKERS`, see [deploy.md](deploy.md#mqtt-sources)). So is anything that reaches this deployment rather than a remote broker: `localhost` and every loopback spelling (`127.1`, `::1`, `0.0.0.0`, ...), link-local addresses, bare hostnames such as `emqx`, a name that resolves to any of those, and private network addresses unless the server allows them. |
| `topic` | required | Remote filter. `$share/...`, `$SYS/...` and the filters the server blocks (`REGISTRY__SOURCES_BLOCKED_TOPICS`, `#` by default) are refused, as is any filter that could match the topics sources are republished and sinks are sent on: `#`, `+/...`, and a first level starting with `mt-sources` or the server's namespace. Keep it narrow: everything it matches is ingested and checked against the registered gateways. |
| `ssl` | `true` | TLS to the remote broker. |
| `username`, `password` | null | The password is **write-only** and is never returned, to anyone. A username may be set alone; a password needs a username (`400`). |
| `qos` | `1` | `0` or `1`. |
| `label` | null | Free text. |
| `terms_version` | required | The `version` from `/sources/terms`. A missing or out-of-date one answers `400 {"terms_version": [...]}`; reload the terms and accept them again. Write-only. |
| `terms_locale` | `en` | Locale the terms were shown in, `en` or `es`. Write-only. |

The response adds `terms_accepted_version`, `terms_expires_at` (null when data is kept
without a time limit) and `paused_at`.

The bridge is created before the response returns, and the response carries its live
`status` (`connected`, `connecting`, `disconnected`, ...). If the bridge cannot be
created the source is not kept and the call answers `502`. An unreachable remote broker
is not an error: the source is created and reports `disconnected` until it connects.

**List / get** (operator, own sources; superuser, all):

```bash
curl -s http://localhost:8090/sources -H "Authorization: Bearer $OPERATOR_API_KEY" | python3 -m json.tool
curl -s http://localhost:8090/sources/<id> -H "Authorization: Bearer $OPERATOR_API_KEY" | python3 -m json.tool
```

Both carry `status`; the list fetches every status in one call to the broker. It reads
`unknown` when the broker cannot be asked, `missing` when the bridge is gone (run
`manage.py sync_sources`, see [deploy.md](deploy.md#mqtt-sources)), and `paused` once the
terms have lapsed.

**Update** (operator, own sources): any subset of the create fields, without the terms.
The bridge is reconfigured before the response returns, and the update rolls back with
`502` if that fails. Send `"password": ""` (or `null`) to remove the stored password; the
bridge keeps the username and connects without a password. Removing the username while a
password is stored answers `400`. A paused source is updated without touching the
broker.

**Restart** (operator, own sources; superuser, all):

```bash
curl -s -X POST http://localhost:8090/sources/<id>/restart -H "Authorization: Bearer $OPERATOR_API_KEY" | python3 -m json.tool
```

Reapplies the source's bridge, re-creating anything missing on the broker, then makes it
subscribe to the remote topic again. Use it when a source reads `connected` but its
meshes have stopped receiving data: a bridge can keep its connection after the remote
broker has stopped delivering to it. Answers the source with its new `status`, `409` for
a paused source (renew its terms instead), and `502` if the broker refuses. Messages the
remote broker sends during the few seconds it takes are not received.

**Renew the terms** (the operator who created the source):

```bash
curl -s -X POST http://localhost:8090/sources/<id>/terms-acceptance \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPERATOR_API_KEY" \
  -d '{"terms_version": "<version from /sources/terms>", "terms_locale": "en"}' | python3 -m json.tool
```

When the server sets a retention period, an acceptance is valid for that long. The
operator is emailed before it lapses. A lapsed source is **paused**: its bridge is
removed, it takes no new meshes, and its meshes' readings are scheduled for deletion
(see [Data lifecycle](#data-lifecycle)). Renewing restarts the bridge and cancels those
deletions, as long as the grace period has not ended. `403` for anyone but the creator,
superusers included, since the acceptance is the controller's.

**Delete** (operator, own sources): removes the bridge, then the source. `409` while meshes are
attached, and `502` with nothing removed if the bridge cannot be torn down. The terms
acceptances are kept.

**Attach a mesh** (the mesh's owner, who must also be able to see the source):

```bash
curl -s -X PUT http://localhost:8090/meshes/<mesh id> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPERATOR_API_KEY" \
  -d '{"source_id": "<source id>"}' | python3 -m json.tool
```

From then on the mesh's gateways are accepted **only** through that source. The same
gateway arriving on the instance's own topic, or through a different source, is dropped
before Kafka. Set `source_id` back to `null` to return the mesh to the own topic.

A source the caller cannot see is refused with the same `400` as one that does not
exist, and a paused source with `400` until its terms are renewed. Resending a mesh's
current `source_id` is always accepted, so an owner who is no longer an operator can
still edit the mesh. `source_id` appears to the mesh's owner and, read-only, to
superusers; viewers of a public mesh do not see it.

Moving a mesh off a source (to `null` or to another source) ends that source's service
for the mesh: the readings stored until then are scheduled for deletion after the grace
period. Moving it back within the grace period cancels it.

### Sinks

A sink lets a third party subscribe, on this instance's broker, to the readings of the
meshes and devices an operator attaches to it. Each message is one reading or alarm as
JSON. The third party connects with credentials the API generates, and can subscribe to
that sink's topics and nothing else. See
[architecture.md#mqtt-sinks](architecture.md#mqtt-sinks) for how it works.

Sinks are visible only to [operators](#operator), with the same scoping as sources: an
operator sees only the sinks they created, a superuser every sink, and anyone else gets
`403` on `/sinks`. Every sink route answers `404` on an instance without
`REGISTRY__EMQX_API_URL`.

**Terms** (operator). Creating a sink first needs the operator to accept the sink terms,
served and recorded like the [source terms](#sources):

```bash
curl -s "http://localhost:8090/sinks/terms?locale=en" -H "Authorization: Bearer $OPERATOR_API_KEY" | python3 -m json.tool
```

The operator is the controller of the readings the sink sends. The current text is a
placeholder pending legal review.

**Create** (operator):

```bash
curl -s -X POST http://localhost:8090/sinks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPERATOR_API_KEY" \
  -d '{
    "label": "Partner",
    "streams": ["decoded", "alarms"],
    "mesh_ids": ["<mesh id>"],
    "device_ids": [],
    "terms_version": "<version from /sinks/terms>",
    "terms_locale": "en"
  }' | python3 -m json.tool
```

| Field | Default | Notes |
|---|---|---|
| `streams` | `["decoded"]` | Any of `decoded`, `derived`, `alarms`. Stored in that order, without repeats. `derived` carries readings only on instances that run postprocessing (full), and `alarms` only on those that run quality checks (full, or lite with `--profile quality`). |
| `mesh_ids` | `[]` | Meshes whose every node is sent, including nodes that appear later. |
| `device_ids` | `[]` | Registrations (`uuid`) of single devices to send. A device is sent while one of its registrations is allowed. |
| `label` | null | Free text. |
| `terms_version`, `terms_locale` | | As for sources. |

Each mesh, and each device's mesh, must be one the caller may edit and owned by an
operator or a superuser; otherwise `400`. The response carries the credentials, **shown
only this once**:

```json
{
  "id": "<sink id>",
  "streams": ["decoded", "alarms"],
  "mesh_ids": ["<mesh id>"],
  "device_ids": [],
  "broker": "mqtt.example.org:8883",
  "username": "mt-sources-sink-<sink id>",
  "password": "<shown once>",
  "topic_filter": "mt-sources-sinks/<sink id>/#",
  "connections": 0,
  "paused_at": null,
  "terms_accepted_version": "sinks-2026-09",
  "terms_expires_at": null
}
```

Nothing is kept, and the call answers `502`, if the broker or the pipeline cannot be set
up, or if the broker does not yet keep sink topics private (see
[deploy.md](deploy.md#mqtt-sinks)).

**List / get** (operator, own sinks; superuser, all): the same fields without the
password. `connections` is how many consumers are connected now, fetched for the whole
list in one call to the broker, and null when the broker cannot be asked.

**Update** (operator, own sinks): any subset of `label`, `streams`, `mesh_ids` and
`device_ids`. A list sent **replaces** the current one, so `"mesh_ids": []` detaches
every mesh; a list left out is kept. Each attach and detach is recorded as the
controller's instruction. Changes the pipeline cannot be told about are rolled back with
`502`.

**Rotate the credentials** (operator, own sinks): issues a new password, shown once,
and disconnects connected consumers. The old password is kept, with `502`, if the broker
cannot be told.

```bash
curl -s -X POST http://localhost:8090/sinks/<id>/credentials -H "Authorization: Bearer $OPERATOR_API_KEY" | python3 -m json.tool
```

**Renew the terms** (the operator who created the sink):
`POST /sinks/<id>/terms-acceptance` with `terms_version` and `terms_locale`. With a
retention period configured, a lapsed sink is **paused**: nothing is sent and its
consumers are disconnected and refused. Renewing resumes it with the same credentials.
A sink stores nothing, so a lapse schedules no deletion.

**Delete** (operator, own sinks): revokes the credentials and disconnects consumers,
then removes the sink. `409` while meshes or devices are attached, and `502` with
nothing removed if the broker cannot be told. The terms acceptances and instructions are
kept.

#### Consuming a sink

The third party needs only the credentials. It connects to `broker` over TLS, MQTT 3.1.1
or 5, and subscribes to `topic_filter` or anything narrower:

```
{topic root}/{sink id}/{stream}/{mesh id}/{node id}
```

Subscribing outside the sink's topics is refused (`Not authorized` in the SUBACK), and
so is publishing anywhere. Messages are QoS 1 and not retained, so a consumer that is
offline misses them, unless it uses a persistent session (MQTT 5 session expiry, or
`clean_session=false`). The broker then queues messages for it, in memory, within these
limits by default:

| Limit | Default | What is lost past it |
|---|---|---|
| Messages queued per session | 10,000 | The oldest queued messages, as new ones arrive |
| Age of a queued message | 24 hours | Each message older than that |
| Time offline | 24 hours | The session, with everything it queued |

A consumer still connected but 10,000 messages behind is disconnected, and its queue is
dropped. Size the gap a consumer can afford against the sink's traffic: a sink that
receives 10 messages a minute fills the queue in about 17 hours. Anything lost this
way can still be read by the sink's operator through the readings API. An operator who
sets `status_alerts_enabled` on their account is emailed when a sink with meshes or
devices attached has nobody connected for a day.
`examples/sink_consume.py` is a working consumer, and `examples/sink_count.py` counts
what a sink delivers.

Every message carries `"schema": 1`, the version of this shape:

| Stream | Message |
|---|---|
| `decoded` | The [decoded message](architecture.md#decoded-message-shape): `node_id`, `mesh_id`, `packet_id`, `rx_time`, `channel_id`, `gateway_id`, `payload_kind` and `payload`, the protobuf's fields as an object. |
| `derived` | The same shape with `postprocessing_id` and no `packet_id`. Recomputations of stored history are never sent. |
| `alarms` | The alarm event: `mesh_id`, `device_id`, `channel`, `detector`, `source`, `value`, `message`, `triggered_at`. |

Field names and units follow the Meshtastic protobufs of the version this instance
runs, so they can change when it is upgraded; `schema` changes when this shape does.

### Data lifecycle

No stored readings are deleted without asking the owner first. On an instance that does
not enforce terms, none of the renewal part below applies: nothing lapses,
`REGISTRY__DATA_RETENTION_DAYS` is ignored, and only the grace-period deletions after a
mesh is deleted or moved off its source run. The same workflow covers
each mesh on the default broker (its mesh terms) and each source (its source terms). The
account terms store no mesh data and never lapse.

**Renewal.** With `REGISTRY__DATA_RETENTION_DAYS` set, each mesh or source terms
acceptance is valid for that many days. The mesh's owner (or the source's operator) is
emailed `REGISTRY__TERMS_RENEWAL_NOTICE_DAYS` before it lapses and renews by accepting
again. If it lapses:

- **Mesh terms:** the mesh stops storing data (its gateways are deregistered from the
  decoder, and any gateway added meanwhile stays deregistered). `paused_at` is set on
  the mesh.
- **Source terms:** the source is paused (its bridge is removed, `status` reads
  `paused`) and takes no new meshes.

Either way, the affected meshes' readings stored until the lapse are scheduled for
deletion. Renewing within the grace period resumes ingestion and cancels it. Unset,
acceptances do not lapse and readings are kept while in use.

**Grace period.** Deletions wait `REGISTRY__DATA_DELETION_GRACE_DAYS` (30 by default),
with the readings left in place and still readable and exportable:

| Event | Readings deleted | Cancelled by |
|---|---|---|
| A mesh is deleted, or its owner is | every reading of the mesh | - |
| A mesh is moved off its source | the readings stored until the move | moving it back |
| A mesh's terms lapse | the mesh, until the lapse | renewing |
| A source's terms lapse | its meshes, until the lapse | renewing |

Then they are deleted from the time-series store and the Parquet archive.

Superusers can see the schedule:

```bash
curl -s "http://localhost:8090/data-deletions?status=all" -H "Authorization: Bearer $SUPERUSER_API_KEY" | python3 -m json.tool
```

`status` is `pending` (the default), `cancelled`, `done` or `all`; `mesh_id` narrows it
to one mesh. A deletion that fails is retried on the next pass, with its `attempts` and
`last_error` shown here. Copies in Kafka (7 days) and in backups (14 days by default)
roll over on their own schedule.

### Public meshes

A mesh is readable by anyone other than its owner only when it is public, including
callers with no credentials at all. **This widens reads only.** Editing and deleting a mesh, its devices and their measurement
configuration stays with the owner (and superusers) in every case, and a caller without
write access gets `403`.

What a signed-in reader gets, on both the registry and the readings role: the mesh, its
devices (excluding any the owner has rejected), their telemetry variants and
measurements, and their readings.

Without credentials, a public mesh exposes:

| route | |
|---|---|
| `GET /meshes`, `GET /meshes/{id}` | public meshes only; private ones are absent or `404` |
| `GET /meshes/{id}/devices` | allowed devices only, without `admin_keys_b64` or the archive fields |
| `GET /readings/devices/{uuid}/latest`, `GET /readings/meshes/{id}/nodes/{node}/latest` | latest readings |
| `GET /readings/meshes/{id}/stats` | traffic stats, busiest nodes and gateway share |
| `GET /meshes/{id}/links`, `GET /meshes/{id}/traceroutes` | radio links and traceroutes |

Timeseries, quality, archive, `/devices` and every other route still need an API key.
Anonymous reads are rate-limited to 60 requests/minute per source IP.

Anyone other than the owner or a superuser gets the mesh in its public shape: `id`,
`channel_id`, `label`, `owner_id`, `is_public`, `created_at` and `updated_at`.
`psk_b64`, `source_id` and the terms status (`terms_accepted_version`,
`terms_expires_at`, `paused_at`) are never included, and `?source_id=` only matches
meshes the caller owns, so it cannot reveal a public mesh's source either. Nobody but
the owner gets `admin_keys_b64` or any write.

The owner publishes a mesh with:

```bash
curl -s -X PUT http://localhost:8090/meshes/<id> \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"is_public": true}' | python3 -m json.tool
```

Meshes are private (`is_public: false`) unless this is set. Public meshes appear in
every caller's `GET /meshes`, signed in or not. Publishing a mesh notifies nobody.

Setting `is_public` back to `false` takes effect on the next request.

### Radio links and traceroutes

Who hears whom on a mesh, from three sources: traceroute hops, neighbor info reports
(portnum 71), and direct receptions, a node heard by a gateway with no hop in between.
Readable without credentials on a public mesh. Both are kept 30 days after they were
last heard.

```bash
# Links heard in the last 7 days (default), longest first
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8090/meshes/<mesh_id>/links?since=7d" | python3 -m json.tool

# Only the links of one node, in either form
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8090/meshes/<mesh_id>/links?node_id=!334af480" | python3 -m json.tool
```

```json
[
  {
    "from_node": 2444775163,
    "to_node": 860550272,
    "from_device_uuid": "aaaaaaaa-...",
    "to_device_uuid": null,
    "source": "traceroute",
    "samples": 14,
    "snr_mean": 6.2,
    "last_snr": 5.5,
    "first_seen": "2026-10-02T08:14:03Z",
    "last_seen": "2026-10-08T21:59:31Z",
    "distance_km": 3.4
  }
]
```

- A link is directional: `from_node` transmitted and `to_node` measured the SNR. A pair
  heard both ways has two links, and one per source.
- `since` is `24h`, `7d` (default) or `30d`. `distance_km` is null unless both nodes are
  registered on the mesh with a position.
- Direct links are added once an hour, when `mesh_stats_writer` closes the hour.

```bash
# The 50 newest traceroutes; pass the last heard_at as `before` for the next page
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8090/meshes/<mesh_id>/traceroutes?limit=50" | python3 -m json.tool
```

```json
[
  {
    "id": 1,
    "from_node": 860550272,
    "to_node": 2444775163,
    "packet_id": 777001,
    "request_id": 777000,
    "origin": 2444775163,
    "target": 860550272,
    "towards": [2444775163, 43981, 860550272],
    "snr_towards": [7.5, 5.5],
    "back": [860550272, 43981, 2444775163],
    "snr_back": [4.5, 6.5],
    "complete": true,
    "gateway_ids": [2444775163],
    "heard_at": "2026-10-08T21:59:31Z",
    "distance_km": null
  }
]
```

- A traceroute heard by several gateways is listed once, with the most complete route
  any of them saw, and every gateway in `gateway_ids`.
- `towards` runs from `origin` to `target` and `back` returns; `snr_towards[i]` is the SNR
  measured on arriving at `towards[i + 1]`, null where the firmware did not measure it.
- A reply (`request_id` set) carries both directions. A request heard on its way out
  only has the hops taken so far, and `complete` is false.
- `node_id` keeps only traceroutes from, to or through that node. `distance_km` is the
  length of `towards` when every node on it has a position.

### Devices

A single resource covers both roles a physical device can play — a single required
`is_gateway` boolean says which (`400` if you omit it; there's no separate `is_node`
field to also send). A device always belongs to a mesh (`mesh_id`, required at creation) and has no
owner field of its own — `Mesh.owner` is the only ownership relationship in the schema,
and it's what gates every mutation below (see
[Authentication for mesh and device mutations](#authentication-for-mesh-and-device-mutations)).

`is_allowed` (default `true`) is **default-open, not pending-approval**: a gateway is
allowed the instant it's registered, a node is allowed the instant it's first
auto-discovered (or pre-registered). The mesh owner's lever is *rejection* —
`PUT /devices/{id}` with `{"is_allowed": false}` — not approval. See
[architecture.md#device-registration-and-the-is_allowed-gate](architecture.md#device-registration-and-the-is_allowed-gate).

- **Gateway**: registering one is what actually authorizes decoding for the whole mesh
  behind it — the Flink job's broadcast state is keyed by `gateway_id`, so any packet
  relayed through this `node_id` starts decoding immediately with the mesh's PSK.
  Rejecting a gateway cascades: nothing from any node relayed through it gets through
  either, regardless of that node's own `is_allowed`.
- **Node**: normally never `POST`ed by a device operator at all — it's auto-discovered
  by `registry/management/commands/consume_device_sightings.py` the first time one of
  its packets decrypts successfully, which is what actually proves it belongs to that
  mesh. It can also be pre-registered directly by the mesh owner (e.g. to set
  `admin_keys_b64` in advance of ever seeing the device). Rejecting a node stops just
  that node's data — `decode_job.py` drops its future packets *before* even attempting
  decrypt (see `mesh.node_rejections.v1` in
  [architecture.md#kafka-topics](architecture.md#kafka-topics)).

`node_id` is unique only among currently **allowed** rows, not globally — a rejected
row doesn't block a fresh registration of the same `node_id`, including on a
different mesh (see the takeover flow below). An allowed **gateway**'s `node_id` is
unique across every mesh, since the decoder looks gateways up by number alone. A
plain **node**'s `node_id` only has to be unique within its mesh, so two meshes (for
example two sources) may each have an allowed node with the same number.

**Register a gateway** (the mesh must already exist and belong to the caller):

```bash
curl -s -X POST http://localhost:8090/devices \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{
    "node_id": 111222333,
    "mesh_id": "<mesh id from above>",
    "is_gateway": true,
    "label": "office gateway"
  }' | python3 -m json.tool
```

```json
{
  "uuid": "<device uuid>",
  "node_id": 111222333,
  "mesh_id": "<mesh id>",
  "label": "office gateway",
  "is_gateway": true,
  "admin_keys_b64": [],
  "is_allowed": true,
  "latitude": null,
  "longitude": null,
  "location_overridden": false,
  "name": null,
  "short_name": null,
  "hardware_type": null,
  "role": null,
  "nodeinfo_overridden": false,
  "last_seen": null,
  "discovered_at": null,
  "created_at": "2026-09-03T00:00:00Z",
  "updated_at": "2026-09-03T00:00:00Z"
}
```

`discovered_at` is set when [gateway discovery](#meshes) registered the gateway rather
than its owner.

**Register or pre-register a node** — same route, `is_gateway: false` instead,
optionally setting `admin_keys_b64` up front:

```bash
curl -s -X POST http://localhost:8090/devices \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{
    "node_id": 555000222,
    "mesh_id": "<mesh id from above>",
    "is_gateway": false,
    "admin_keys_b64": ["AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="],
    "label": "test node"
  }' | python3 -m json.tool
```

Omitting `is_gateway` returns `400` ("This field is required."). More than 3
`admin_keys_b64` entries also returns `400`. A duplicate `node_id` returns `409` when
it is already allowed on the same mesh, or, for a gateway, already an allowed gateway
on any mesh.

**List / filter:**

```bash
curl -s http://localhost:8090/devices -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
curl -s "http://localhost:8090/devices?mesh_id=<id>" -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
curl -s "http://localhost:8090/devices?is_gateway=true" -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
curl -s "http://localhost:8090/devices?is_gateway=false&is_allowed=false" -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
curl -s "http://localhost:8090/devices?has_postprocessing=true" -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
```

`?mesh_id=`, `?is_gateway=true|false`, `?is_allowed=true|false` and
`?has_postprocessing=true|false`
all compose — omit whichever you don't want to filter on (nodes are `?is_gateway=false`,
there's no separate `?is_node=`). A superuser's list includes
every owner's devices; anyone else's is scoped to devices on meshes they own.

**Get one:**

```bash
curl -s http://localhost:8090/devices/<device uuid> -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
```

**Update** — `label`, `admin_keys_b64`, `is_allowed`, and the location/NodeInfo fields
below are mutable; `node_id`, `mesh`, and role (`is_gateway`) are fixed at
creation:

```bash
curl -s -X PUT http://localhost:8090/devices/<device uuid> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"label": "renamed"}' | python3 -m json.tool
```

**Fault-detection intervals** — `reading_interval_seconds` (how often it samples,
which drives completeness and the default postprocessing join tolerance),
`publish_interval_seconds` (how often it transmits, which drives absence) and
`absence_detection_enabled`:

```bash
curl -s -X PUT http://localhost:8090/devices/<device uuid> \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"reading_interval_seconds": 300, "publish_interval_seconds": 3600}' | python3 -m json.tool
```

The two are deliberately separate — "not publishing" and "not reading" are
different faults once telemetry is batched, see
[architecture.md#device-fault-detection](architecture.md#device-fault-detection).
Both are nullable and fall back to `TelemetryVariant.default_reading_interval_seconds`;
clearing both stops absence monitoring for that device. Editing them publishes
to `mesh.quality_config.v1`, which is how the Flink quality checks are tuned.

**Archive** — `archive_enabled` stores the device's decoded and derived readings in the
[Parquet archive](#parquet-archive) from then on. Off by default:

```bash
curl -s -X PUT http://localhost:8090/devices/<device uuid> \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"archive_enabled": true}' | python3 -m json.tool
```

It is refused with `400` on a mesh whose owner is not an operator (or a superuser), and
on an instance without an archive (lite). Turning it off stops storing new readings and
keeps those stored, which go with the mesh's data when it is deleted. Only an allowed
registration is archived, so rejecting the device stops it too. The response carries
`archive_enabled_at` and `archive_enabled_by` (the owner id of whoever switched it on,
the mesh's owner or a superuser), cleared when it is switched off. Every change is also
appended to a history that outlives the device, as evidence of the owner's instruction;
superusers see it in the Django admin. The three fields are shown to the mesh's owner
and to superusers only.

The mesh and source terms say so: accepting them authorises the archive for the devices
the owner chooses, so switching it on asks for no further acceptance. The change is published to
`mesh.sink_config.v1` before answering; if that fails the answer is `502` and nothing in
the request is applied, other fields included. The same holds for `is_allowed`: when the
decoder cannot be told, the whole update is dropped. Deleting an archived device, its mesh or its owner stops archiving first, and
nothing is removed if that cannot be published.

**Location and NodeInfo auto-fill** — `latitude`/`longitude` are auto-filled from the
device's own Position packets, and `name`/`short_name`/`hardware_type`/`role` from its
NodeInfo packets, as they're decoded (see
[architecture.md#auto-filled-location-and-nodeinfo-fields](architecture.md#auto-filled-location-and-nodeinfo-fields)).
Both groups are **default-open, sticky-override**: a `PUT`/`POST` value pins its group
against future telemetry until explicitly cleared.

```bash
# Pin a location manually - future Position sightings won't touch it
curl -s -X PUT http://localhost:8090/devices/<device uuid> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"latitude": 45.4642, "longitude": 9.19}' | python3 -m json.tool

# Release it back to auto-fill - both latitude and longitude must be null together
curl -s -X PUT http://localhost:8090/devices/<device uuid> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"latitude": null, "longitude": null}' | python3 -m json.tool

# Pin the NodeInfo group - setting even one field freezes all four against telemetry
curl -s -X PUT http://localhost:8090/devices/<device uuid> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"hardware_type": "TBEAM"}' | python3 -m json.tool

# Release the NodeInfo group - all four fields must be null together
curl -s -X PUT http://localhost:8090/devices/<device uuid> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"name": null, "short_name": null, "hardware_type": null, "role": null}' \
  | python3 -m json.tool
```

`latitude`/`longitude` must always be sent together (both present or both absent) —
sending only one returns `400`. There's no such pairing across the NodeInfo fields;
only the *override flag* is shared, each field is independently settable. Both groups
can also be supplied at `POST` time, which pins them immediately so the device's first
telemetry sighting doesn't overwrite the value just registered.

**Reject a device** — the mesh owner's lever to stop its data, whichever role it is:

```bash
curl -s -X PUT http://localhost:8090/devices/<device uuid> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"is_allowed": false}' | python3 -m json.tool
```

For a gateway this publishes the same Kafka delete `DELETE` would — dropping it from
Flink's broadcast state and stopping decode for that `gateway_id` immediately — but
keeps the Postgres row for audit history. For a node it publishes to
`mesh.node_rejections.v1` instead, adding it to `decode_job.py`'s reject-list broadcast
state — future packets from that node are dropped *before* decrypt is even attempted.

Re-allowing (`{"is_allowed": true}`) republishes an upsert/unreject and returns `409` if
that would break the rule above: another allowed row on the same mesh, or for a
gateway, another allowed gateway anywhere. Reject that one first, there's no automatic
takeover.

**Takeover flow — move a gateway to a different mesh without losing history:**

```bash
# 1. Reject the gateway on its current mesh - stops decoding, keeps the row
curl -s -X PUT http://localhost:8090/devices/<device uuid> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"is_allowed": false}' | python3 -m json.tool

# 2. Register the same node_id as a gateway on the new mesh - now succeeds
#    (409 while the old row was still allowed)
curl -s -X POST http://localhost:8090/devices \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{
    "node_id": 111222333,
    "mesh_id": "<new mesh id>",
    "is_gateway": true,
    "label": "moved gateway"
  }' | python3 -m json.tool
```

The same reject-then-recreate pattern moves a node to a different mesh.

**Delete:**

```bash
curl -s -o /dev/null -w "status: %{http_code}\n" -X DELETE http://localhost:8090/devices/<device uuid> \
  -H "Authorization: Bearer $OWNER_API_KEY"
```

For an allowed gateway, publishes the Kafka delete event before removing the Postgres
row, so a Kafka publish failure never leaves Flink still trusting a key the operator
believes is gone. For a currently-rejected node, publishes an unreject first to clear
its `mesh.node_rejections.v1` entry — otherwise a stale rejection would block a future
registration of the same `node_id` elsewhere forever, since Flink's broadcast state
has no way to know the row that rejected it is gone.

**`admin_keys_b64` appears in the response only to the device's own mesh owner**, same
password-field treatment as `psk_b64` (see the note at the top of this doc). `PUT`
still replaces the whole list — the pattern to add one key is `GET` the device (as its
owner) to read the current list back, then `PUT` the full set with the new key
appended. See `mesh_things/examples/registry_add_admin_key.py`.

### Device telemetry variants and Measurements

A `Device`'s telemetry is catalogued automatically as it's decoded - `DeviceTelemetryVariant`
and `Measurement` are per-device instances, auto-discovered, pointing at two global, shared
catalogs: `TelemetryVariant` (one row per Meshtastic Telemetry protobuf "variant" -
e.g. `telemetry:environment_metrics` - NOT verified physical hardware, since one
variant can be produced by several different chips) and `MeasurementType`
(unit/quantity_kind/vocabulary_uri). `DeviceTelemetryVariant` is read-only, no `PUT`
route exists for it; `Measurement` does have one (below) for the two things that are
per-device rather than shared: which detectors run, and the range detector's bounds.
A third global table, `TelemetryVariantMeasurement`, links a `TelemetryVariant` to
every `MeasurementType` it carries and which detectors default on for that pairing -
see [data-quality.md](data-quality.md). See
[architecture.md#device-telemetry-variant--measurement-catalog](architecture.md#device-telemetry-variant--measurement-catalog)
for the full discovery pipeline and the pre-seeded unit table.

The two levels are **two separate endpoints**. They used to be one
(`GET /devices/{id}/sensors`, now removed) which nested channels inside variants -
conflating "what telemetry types does this device report" with "what channels does it
produce", and forcing a caller who wanted either to receive both.

**Which telemetry types this device reports:**

```bash
curl -s http://localhost:8090/devices/<device uuid>/telemetry-variants -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
```

```json
[
  {
    "id": "<device telemetry variant id>",
    "telemetry_variant": {
      "id": "<telemetry variant id>",
      "payload_kind": "telemetry:environment_metrics",
      "name": null,
      "model": null,
      "datasheet_url": null,
      "description": null,
      "default_reading_interval_seconds": 900
    },
    "first_seen": "2026-09-04T00:00:00Z",
    "last_seen": "2026-09-04T00:05:00Z"
  }
]
```

**Which channels it actually produces** - flat across every variant, and including
the device's computed channels (postprocessing outputs and quality metrics). Each
row carries the `"<measurement>.<field>"` `channel` name used by blueprint slot
defaults, curated quality thresholds and InfluxDB queries, so
there's nothing to reassemble by hand, plus an `origin` telling you which kind it is:

```bash
curl -s http://localhost:8090/devices/<device uuid>/measurements -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
```

```json
[
  {
    "id": "<measurement id>",
    "telemetry_variant_id": "<telemetry variant id>",
    "measurement_type": {
      "id": "<measurement type id>",
      "payload_kind": "telemetry:environment_metrics",
      "field_name": "temperature",
      "channel": "environment_metrics.temperature",
      "origin": "measured",
      "display_name": null,
      "description": "Temperature measured",
      "native_unit": "degC",
      "quantity_kind": "physical_property",
      "vocabulary_uri": null,
      "created_at": "2026-09-04T00:00:00Z",
      "updated_at": "2026-09-04T00:00:00Z"
    },
    "enabled_detectors": null,
    "effective_detectors": [],
    "valid_min": null,
    "valid_max": null,
    "first_seen": "2026-09-04T00:00:00Z",
    "last_seen": "2026-09-04T00:05:00Z"
  }
]
```

**Alarms are opt-in.** Two fields, because two settings combine:
`enabled_detectors` is what this device sets and may be `null`, and
`effective_detectors` is what results once the shared catalog's
`default_enabled_detectors` is applied. `valid_min`/`valid_max` have no
catalog default at all - they only ever come from this device.

| this device | catalog default | `effective_detectors` | |
|---|---|---|---|
| `null` | `["range"]` | `["range"]` | inherited |
| `[]` | `["range"]` | `[]` | turned off here |
| `["flat_value"]` | `["range"]` | `["flat_value"]` | overridden here |

A freshly discovered channel alarms on nothing.

```bash
# Alarm on out-of-range values (with the range set below), but never on the channel being flat
curl -s -X PUT http://localhost:8090/devices/<device uuid>/measurements/<measurement id> \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"enabled_detectors": ["range", "completeness"], "valid_min": -40, "valid_max": 85}' | python3 -m json.tool

# null inherits the catalog default; [] silences the channel here regardless of it.
# valid_min/valid_max must be provided together, or cleared together with null.
curl -s -X PUT http://localhost:8090/devices/<device uuid>/measurements/<measurement id> \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"enabled_detectors": null}' | python3 -m json.tool
```

`GET /detectors` lists the options rather than requiring them to be hardcoded,
which is what a dropdown should be built from. `scope` says where each one is
switched on, and `requires` is the config it also needs before it can fire:

```bash
curl -s http://localhost:8090/detectors -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
```

```json
[
  {
    "name": "range",
    "scope": "measurement",
    "requires": ["valid_min", "valid_max"],
    "description": "Fires when a reading falls outside the range configured for this device."
  },
  {
    "name": "absence",
    "scope": "device",
    "requires": ["publish_interval_seconds"],
    "description": "Fires when a device stops publishing for several of its publish intervals."
  }
]
```

Only `scope: "measurement"` entries go in `enabled_detectors`; anything else is
a `400`. The `device` one is `absence_detection_enabled` on the device itself. The same set
is in the schema as `DetectorEnum`, so a generated client gets it too. See
[data-quality.md#enabling-alarms](data-quality.md#enabling-alarms).

**`MeasurementType`/`TelemetryVariant` catalogs — full CRUD, but writes are
superuser-only:**

```bash
# GET is open to any verified owner
curl -s http://localhost:8090/measurements -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
curl -s http://localhost:8090/telemetry-variants -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool

# Every payload_kind is "<namespace>:<measurement>". The namespaces are
# "telemetry" for sensor fields, "device" for what a node reports about itself,
# and "computed" for what this pipeline works out. Filter on ?kind= (the
# namespace), ?payload_kind= (exact) and ?field_name=. This is the only place
# the catalog lives - readings doesn't re-expose it.
curl -s "http://localhost:8090/measurements?kind=computed" -H "Authorization: Bearer $OWNER_API_KEY"
curl -s "http://localhost:8090/measurements?payload_kind=computed:quality" -H "Authorization: Bearer $OWNER_API_KEY"
curl -s "http://localhost:8090/measurements?payload_kind=telemetry:environment_metrics" -H "Authorization: Bearer $OWNER_API_KEY"
curl -s "http://localhost:8090/measurements?field_name=temperature" -H "Authorization: Bearer $OWNER_API_KEY"

# POST/PUT/DELETE require a superuser key - anyone else gets 403
curl -s -X POST http://localhost:8090/measurements \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $SUPERUSER_API_KEY" \
  -d '{"payload_kind": "telemetry:environment_metrics", "field_name": "temperature", "vocabulary_uri": "https://qudt.org/vocab/quantitykind/Temperature"}' \
  | python3 -m json.tool

curl -s -X PUT http://localhost:8090/measurements/<id> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $SUPERUSER_API_KEY" \
  -d '{"vocabulary_uri": "https://qudt.org/vocab/quantitykind/Temperature"}' \
  | python3 -m json.tool

curl -s -X DELETE http://localhost:8090/measurements/<id> -H "Authorization: Bearer $SUPERUSER_API_KEY"
```

Every catalog row also carries `channel` (its `"<measurement>.<field>"` name)
and `origin` - `measured`, `device` or `computed`, naming who produced the
value - so a consumer can tell a sensor reading from a computed diagnostic
without parsing `payload_kind`.
`alarms` is deliberately **not** catalogued: its `value` has no stable unit and
`message` is free text, so it's an event log rather than a measurement series -
query it directly as an InfluxDB measurement. See
[data-quality.md](data-quality.md#where-everything-lives).

`payload_kind` (and `field_name` for `MeasurementType`) is the row's identity -
fixed after creation, a `PUT` that includes them is silently ignored for those two
fields. A duplicate `(payload_kind, field_name)` (or `payload_kind` alone for
`TelemetryVariant`) on `POST` returns `409`. Same routes/shapes for
`/telemetry-variants`, with `name`/`model`/`datasheet_url`/`description`/
`default_reading_interval_seconds` instead - the last one is a fact about the *telemetry
type* (Meshtastic firmware configures interval per telemetry module, e.g.
`environment_metrics`, not per device), always `null` until curated; `name`/`model`/
`datasheet_url` are an optional curated "commonly this chip" hint, not verified
hardware identity - see
[architecture.md#device-telemetry-variant--measurement-catalog](architecture.md#device-telemetry-variant--measurement-catalog):

```bash
curl -s -X PUT http://localhost:8090/telemetry-variants/<telemetry variant id> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $SUPERUSER_API_KEY" \
  -d '{"default_reading_interval_seconds": 900}' \
  | python3 -m json.tool
```

**`TelemetryVariant` and `MeasurementType` are pre-seeded from the Meshtastic protobuf
schema**, not created by hand via the routes above. The registry container seeds them
on every start, so a `meshtastic` package upgrade that adds fields needs no action.

**`TelemetryVariantMeasurement` — which fields a `TelemetryVariant` carries, plus
which detectors default on for that pairing.** No `POST`/`DELETE` of its own - the
pairing's existence is owned entirely by the catalog seed; only
`default_enabled_detectors` is editable, superuser-only. The range detector's
bounds are not part of this catalog - see `PUT /devices/{id}/measurements/{id}`
above, which sets them per device:

```bash
# GET is open to any verified owner, same as /measurements and /telemetry-variants
curl -s http://localhost:8090/telemetry-variants/<telemetry variant id>/measurements \
  -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
```

```json
[
  {
    "id": "<telemetry_variant_measurement id>",
    "measurement_type": {
      "id": "<measurement type id>",
      "payload_kind": "telemetry:environment_metrics",
      "field_name": "temperature",
      "native_unit": "degC",
      "quantity_kind": "physical_property",
      "vocabulary_uri": null
    },
    "default_enabled_detectors": [],
    "created_at": "2026-09-04T00:00:00Z",
    "updated_at": "2026-09-04T00:00:00Z"
  }
]
```

```bash
# Enable a detector by default for every device on this field - superuser-only
curl -s -X PUT http://localhost:8090/telemetry-variants/<telemetry variant id>/measurements/<link id> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $SUPERUSER_API_KEY" \
  -d '{"default_enabled_detectors": ["flat_value"]}' \
  | python3 -m json.tool
```

Detector defaults and intervals survive the catalog seed, which matters more now
that it runs on every registry start: it creates rows that don't exist yet and
fills in columns left blank, but never overwrites a value that is already set.

### Postprocessing

Postprocessing derives new channels from a device's telemetry. A **blueprint**
is the reusable recipe; attaching it to a device binds its input slots to that
device's channels and gives it the device's own **calibration**. Derived
channels are computed on live telemetry by the stream tier, stored and served
like any sensor channel, and can be recomputed over history with a
**backfill**. See [architecture.md#postprocessing](architecture.md#postprocessing)
for the model and [data-quality.md#postprocessing](data-quality.md#postprocessing)
for the walkthrough.

#### Algorithms

Read-open to any verified owner. There is no write route: an algorithm exists
by being a decorated function in `common/algorithms/`.

```bash
curl -s http://localhost:8090/algorithms -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
```

```json
[
  {
    "name": "ec_sensor_ppb",
    "inputs": ["working", "auxiliary", "temperature"],
    "outputs": ["concentration_ppb"],
    "params": [
      {"name": "sensitivity", "calibration": true, "required": true, "default": null,
       "unit": "mV/ppb", "doc": "Working electrode response per ppb, non-zero."},
      {"name": "reference_temperature", "calibration": false, "required": false, "default": 20.0,
       "unit": "degC", "doc": ""}
    ],
    "mode": "pointwise",
    "output_units": {"concentration_ppb": "ppb"},
    "doc": "Electrochemical four-electrode sensor -> concentration in ppb. ..."
  }
]
```

`calibration: true` parameters describe one physical sensor and are set per
device; the others are set on a blueprint step. `output_units` gives each
output's unit, `"@<input>"` meaning the unit of whichever channel is bound to
that input. Only `pointwise` algorithms can run; a version using a `windowed`
one is refused.

#### Blueprints and versions

```bash
curl -s -X POST http://localhost:8090/postprocessing-blueprints \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{
    "name": "no2-electrochemical",
    "is_public": false,
    "inputs": [
      {"slot": "working", "default_channel": "ads1115.channel_0"},
      {"slot": "auxiliary", "default_channel": "ads1115.channel_1"},
      {"slot": "temperature", "default_channel": "environment_metrics.temperature"}
    ],
    "steps": [
      {"key": "ppb", "order": 0, "function_name": "ec_sensor_ppb",
       "inputs": {"working": "slot:working", "auxiliary": "slot:auxiliary", "temperature": "slot:temperature"},
       "params": {"temperature_coefficient": 0.01},
       "outputs": {"concentration_ppb": "no2_ppb"}},
      {"key": "ugm3", "order": 1, "function_name": "ppb_to_ugm3",
       "inputs": {"concentration_ppb": "step:ppb.concentration_ppb", "temperature": "slot:temperature"},
       "params": {"molecular_weight": 46.01},
       "outputs": {"concentration_ugm3": "no2_ugm3"}}
    ]}' | python3 -m json.tool
```

This creates the blueprint and its version 1, returned as `latest_version`.
A step input is `slot:<declared slot>` or `step:<earlier step key>.<output>`;
outputs name derived fields, stored as `derived.<field>`. Everything is
validated when written, so a mis-bound step fails here:

```
400 {"steps": {"function_name": ["'ec_sensor_ppb' param(s) ['sensitivity'] are calibration parameters, set per device"]}}
```

| Route | Who | Does |
|---|---|---|
| `GET /postprocessing-blueprints[?owned=true]` | owner | own and public blueprints; `owned` drops public ones |
| `GET/PUT/DELETE /postprocessing-blueprints/{id}` | owner of it | `PUT` changes only `name`, `description`, `is_public`; `DELETE` is `409` while a device uses a version |
| `GET/POST /postprocessing-blueprints/{id}/versions` | owner of it (`POST`) | versions are immutable, so changing steps means posting a new one |
| `GET /postprocessing-blueprints/{id}/versions/{number}` | anyone who can see it | one version and its steps |

A duplicate `name` for the same owner returns `409`. Deleting an owner keeps
their blueprints that other owners' devices use, with `owner_id: null` and
editable by superusers only.

#### Attaching to a device

```bash
curl -s -X POST http://localhost:8090/devices/<device uuid>/postprocessings \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"blueprint_id": "<blueprint id>"}' | python3 -m json.tool
```

```json
{
  "id": "<postprocessing id>",
  "blueprint_name": "no2-electrochemical",
  "blueprint_version": 1,
  "input_bindings": {"working": "<measurement id>", "auxiliary": "<measurement id>", "temperature": "<measurement id>"},
  "output_prefix": "",
  "tolerance_seconds": null,
  "effective_tolerance_seconds": 150.0,
  "is_enabled": false,
  "outputs": [
    {"field_name": "no2_ppb", "channel": "derived.no2_ppb", "measurement_id": "...", "unit": "ppb"},
    {"field_name": "no2_ugm3", "channel": "derived.no2_ugm3", "measurement_id": "...", "unit": "ug/m3"}
  ],
  "problems": ["Step 'ppb' needs a calibration setting ['sensitivity']"]
}
```

Slots bind to the device's channel named by their `default_channel`, or to the
measurement ids given in `input_bindings`, which may include another
postprocessing's derived channel. The outputs appear straight away in
`GET /devices/{uuid}/measurements` with `produced_by` set, so detectors and
ranges can be configured on them. The blueprint must be the mesh owner's own or
public. `output_prefix` renames the outputs, which is needed to attach the same
blueprint twice. `effective_tolerance_seconds` is how far apart two inputs may
be to be joined: `tolerance_seconds` if set, otherwise half the device's
`reading_interval_seconds`, otherwise 30.

`PUT /devices/{uuid}/postprocessings/{id}` takes `blueprint_version`,
`input_bindings` (null unbinds a slot), `output_prefix`, `tolerance_seconds`
and `is_enabled`. Enabling is refused while `problems` is not empty. Moving to
another version keeps bindings for slots it still declares and calibrations for
steps with the same key and algorithm. `DELETE` detaches and removes the
derived channels; stored readings stay queryable. Changes that would make a
postprocessing depend on its own output, or remove a channel another
postprocessing reads, are refused. Every change is rolled back if the stream
tier cannot be notified (`502`).

`GET /devices?has_postprocessing=true|false` filters devices by whether any
postprocessing is attached.

#### Calibration

```bash
curl -s -X POST http://localhost:8090/devices/<device uuid>/postprocessings/<id>/calibrations \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"step_key": "ppb", "params": {"sensitivity": 0.42, "working_zero": 220.0},
       "valid_from": "2026-09-01T00:00:00Z"}'
```

Every required calibration parameter of the step's algorithm must be given,
and configuration parameters are refused. `valid_from` defaults to now. History
is kept: each reading is processed with the calibration in force when it was
taken. `GET` on the same path lists the history; `DELETE .../calibrations/{id}`
removes one recorded by mistake, refused (`409`) if it would leave an enabled
postprocessing uncalibrated.

#### Backfills

```bash
curl -s -X POST http://localhost:8090/devices/<device uuid>/postprocessings/<id>/backfills \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OWNER_API_KEY" \
  -d '{"start": "2026-09-01T00:00:00Z", "include_dependants": true}'
```

Returns `202` with `status: pending`; `GET` on the same path shows progress
(`pending`, `running`, `done`, `failed`), `points_published` and `error`. At
most 90 days per request, `stop` defaulting to now. The postprocessing must be
runnable but need not be enabled. Backfilled values replace stored derived
values for the same times and never raise alarms.

The quality worker drives backfills through superuser-only routes:
`GET /postprocessing-backfills?status=pending`,
`POST /postprocessing-backfills/{id}/claim` (returns the resolved plans; `409`
if another worker holds it, a run older than an hour can be reclaimed), and
`PUT /postprocessing-backfills/{id}` with the outcome.

### Health

```bash
curl -s http://localhost:8090/health
```

### Metrics

Public, unauthenticated — counts of *things that exist*. Values over time
(alarms, completeness, points ingested) are readings' — see
[Per-device metrics](#per-device-metrics) below.

```bash
curl -s http://localhost:8090/metrics | python3 -m json.tool
```

```json
{"devices": 42, "owners": 7, "meshes": 9, "active_gateways": 11}
```

`active_gateways` counts devices with `is_gateway=true` and `is_allowed=true`
— the same "allowed until explicitly rejected" definition used everywhere
else in this API (see [architecture.md](architecture.md)).

### Data-quality config (`mesh.quality_config.v1`)

**This one does have an API** — it's the routes documented above. Editing a
`TelemetryVariantMeasurement`'s bounds, a `TelemetryVariant`'s interval, or a
`Device`'s intervals publishes to this compacted topic, which the Flink quality jobs
hold as broadcast state. There's no separate config resource to manage: the catalog
*is* the config. See [data-quality.md](data-quality.md).

`mesh.rules.v1` is **superseded** by this and is no longer read by any job.

## Readings role (`:8091`)

Read-only, backed by InfluxDB. All query-string params (`measurement`, `field`, `start`,
`stop`, `window`, `agg`) are validated against a strict allowlist/regex before being
interpolated into a Flux query — see `readings/telemetry/influx_client.py`'s
`_validate_ident` / `_validate_range_bound` / `ALLOWED_AGG`. Anything that doesn't look
like a plain identifier or a relative duration (`-1h`, `-30d`, `now()`) is rejected with
`400`.

### Authentication

Every route except `/health` requires `Authorization: Bearer <key>` — any key minted by
registry's `POST /owners` works here too. readings has no `Owner` model of its own; it
reads registry's tables directly as a read-only Postgres role, so a key is resolved by
one indexed lookup rather than a call to another service
(`registry/authentication.py`). A missing or invalid key is `401`. Registrations, key
rotations and revocations therefore take effect immediately, with no cache to wait out
(see
[architecture.md#roles-registry-and-readings](architecture.md#roles-registry-and-readings)).

**Scoped to the caller's own meshes** — a superuser key sees everything; any other key
sees the meshes it owns and every node on them. A mesh the caller doesn't own returns
`404`, not `403`, since readings can't honestly tell "doesn't exist" from "not yours".

The unit is the mesh, not the device: `Mesh.owner` is the only ownership relationship
in the schema, and non-gateway devices are never registered by hand — sightings create
them. So a node whose telemetry has arrived but whose registration row does not exist
yet is still readable by the owner of the mesh it arrived on. The node-keyed routes are
nested under a mesh because a Meshtastic node number is only unique per mesh among
currently-*allowed* devices, not globally or over time.

Same `access_token` query-param fallback as registry for pasting a GET URL straight into a
browser — see
[#browsing-get-routes-directly-from-a-browser-address-bar](#browsing-get-routes-directly-from-a-browser-address-bar).

Authenticated traffic is rate-limited to 120 requests/minute per owner
(`DEFAULT_THROTTLE_RATES` in `api_project/settings/base.py`) — exceeding it returns
`429`. Separately, failed attempts are capped at 30/minute per source IP, so an invalid
key cannot be brute-forced against the owner table (`registry/authentication.py`).

### Which address to use

Every per-device query is reachable two ways, and both land on the same
implementation — the UUID form is pure address translation, not a second query
path:

| Address | Use when |
|---|---|
| `/devices/{device_uuid}/...` | **Default.** The same UUID registry's `/devices/{id}` uses, so the two APIs line up and you never have to join `node_id` by hand. Requires a registry registration row. |
| `/meshes/{mesh_id}/nodes/{node_id}/...` | The store-native address — InfluxDB is tagged by `mesh_id`/`node_id`, so this still reaches a device that has telemetry but **no** registration row (points predating the tag, or a device whose registration was deleted). |

`nodes`, not `devices`, in the second form: `node_id` is a Meshtastic node
number, a different identifier space from registry's device UUID, and naming them
alike is what made the two APIs look interchangeable when they aren't.

**readings has no device or channel listing of its own.** *What exists* is
registry's job, and a second copy only ever drifts from the first:

| To discover | Ask registry |
|---|---|
| which devices exist | `GET /devices` — includes each device's `uuid` and `mesh_id`/`node_id` |
| which channels a device reports | `GET /devices/{device_uuid}/measurements` — each carrying `origin`, its unit and `effective_detectors` |
| the full catalog | `GET /measurements` |

Run the channel lookup first if you don't know a device's measurement/field
names: querying `device_metrics` on a node that only ever reported
`environment_metrics` returns an empty series, not an error.

`server/mesh_things/examples/readings.py` walks the whole flow.

### Timeseries

```bash
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/devices/<device_uuid>?channel=device_metrics.battery_level&start=-24h" \
  | python3 -m json.tool

# Identical response, addressed the store-native way
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/meshes/<mesh_id>/nodes/111222333?channel=device_metrics.battery_level&start=-24h" \
  | python3 -m json.tool

# With downsampling
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/meshes/<mesh_id>/nodes/111222333?channel=environment_metrics.temperature&start=-30d&window=6h&agg=mean" \
  | python3 -m json.tool

# One calendar day, by date
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/meshes/<mesh_id>/nodes/111222333?payload_kind=telemetry:environment_metrics&start=2026-09-01&stop=2026-09-02" \
  | python3 -m json.tool

# A precise window, and a date opened up to now
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/meshes/<mesh_id>/nodes/111222333?payload_kind=telemetry:environment_metrics&start=2026-09-01T08:00:00Z&stop=2026-09-01T17:30:00Z" \
  | python3 -m json.tool
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/meshes/<mesh_id>/nodes/111222333?payload_kind=telemetry:environment_metrics&start=2026-09-01" \
  | python3 -m json.tool
```

- `field` is optional — omit it to get every field of the measurement.
- `agg` must be one of `mean`, `max`, `min`, `last`, `first`, `sum`, `count` (only
  applied when `window` is also set).
- Setting `window` restricts the response to **numeric** fields — string fields like
  `timestamp_quality` have no meaningful average, and including them would fail the
  whole Flux query. Omit `window` to get them back.
- `start`/`stop` each accept a relative duration (`-24h`), `now()`, a date
  (`2026-09-01`) or a timestamp (`2026-09-01T13:45:00Z`), and the two forms mix
  freely. A date is taken as midnight and a timestamp without an offset is read
  as UTC, so `start=2026-09-01&stop=2026-09-02` is the whole of 1 September.
  Offsets are honoured: `2026-09-01T13:45:00+02:00` is 11:45 UTC. Remember to
  URL-encode the `+` as `%2B` if you pass one.

Response shape:

```json
{
  "mesh_id": "11111111-2222-3333-4444-555555555555",
  "node_id": 111222333,
  "payload_kind": "telemetry:device_metrics",
  "series": [
    {"channel": "device_metrics.battery_level", "points": [{"time": "2026-08-29T23:15:11+00:00", "value": 88.0}]}
  ]
}
```

### Latest reading

```bash
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/devices/<device_uuid>/latest?payload_kind=telemetry:device_metrics" | python3 -m json.tool
```

Same response shape as timeseries, but each channel's `points` array has exactly
one entry (the most recent).

For a device on a [public mesh](#public-meshes), this route works without credentials:

```bash
curl -s "http://localhost:8091/readings/devices/<device_uuid>/latest" | python3 -m json.tool
```

**`payload_kind` is optional.** Omit it to get the latest value of *every*
channel the device has ever reported, in one call, decorated with unit/
quantity_kind/vocabulary_uri from registry's `MeasurementType` catalog (see
[architecture.md#latest-readings-across-every-sensor-readings](architecture.md#latest-readings-across-every-sensor-readings)):

```bash
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/devices/<device_uuid>/latest" | python3 -m json.tool

# Widen the search window for a device that reports infrequently
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/devices/<device_uuid>/latest?lookback=-90d" | python3 -m json.tool
```

`lookback` defaults to `-30d`. A device whose last reading is older than the
window comes back with no readings at all, so raise it rather than assuming the
device never reported.

```json
{
  "mesh_id": "11111111-2222-3333-4444-555555555555",
  "node_id": 111222333,
  "readings": [
    {
      "payload_kind": "environment_metrics",
      "channel": "environment_metrics.temperature",
      "value": 21.4,
      "time": "2026-09-04T00:05:00+00:00",
      "unit": "degC",
      "quantity_kind": "physical_property",
      "vocabulary_uri": null,
      "origin": "measured"
    }
  ]
}
```

`origin` is `measured`, `device` or `computed` — the same vocabulary registry's
`GET /devices/{uuid}/measurements` uses, so a postprocessing output
(`derived.dew_point`) or a completeness diagnostic (`quality.completeness_ratio`)
is distinguishable from a real sensor reading without parsing channel names.
It comes from the measurement itself, so a field with no catalog row still has one.

Note the response shape differs from the `?payload_kind=` case (`"readings"`, not
`"payload_kind"`/`"series"`) - a channel with no catalog match yet still comes back
with `unit: null` rather than being dropped, the reading itself is still real.

### Per-device metrics

Aggregates the `quality` and `alarms` InfluxDB measurements the batch/stream
quality tiers already write — no new computation, see
[done.md#9](done.md). Same `start`/`stop` window params as timeseries
(default `-1h`/`now()`); same dual addressing (UUID or mesh+node).

```bash
# Defaults to the last hour
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/devices/<device_uuid>/quality" | python3 -m json.tool

# A longer window
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/devices/<device_uuid>/quality?start=-24h" | python3 -m json.tool

# A closed window, addressed the store-native way
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/meshes/<mesh_id>/nodes/111222333/quality?start=-7d&stop=-1d" \
  | python3 -m json.tool

# A specific month, by date
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/devices/<device_uuid>/quality?start=2026-09-01&stop=2026-10-01" \
  | python3 -m json.tool
```

`start`/`stop` take the same forms as on [Timeseries](#timeseries) above.

```json
{
  "mesh_id": "11111111-2222-3333-4444-555555555555",
  "node_id": 111222333,
  "start": "-24h",
  "stop": "now()",
  "points_ingested": 190.0,
  "range_ratio": 0.98,
  "alarms_by_detector": {"range": 2, "completeness": 0, "flat_value": 0, "absence": 0},
  "channels": [
    {
      "channel": "device_metrics.battery_level",
      "completeness_ratio": 0.95,
      "observed": 190.0,
      "expected": 200.0,
      "largest_gap_seconds": 300.0
    }
  ]
}
```

- `points_ingested` is `sum(observed)` across channels from the `quality`
  measurement — **empty/zero if the batch quality tier hasn't evaluated this
  device yet** (`quality_worker` not running
  — e.g. a `lite` deployment without `--profile quality`). It is not a raw
  Kafka/packet count.
- `range_ratio` is the share of the hours the device reported in without a `range`
  alarm on any channel (`range` re-raises hourly while a value stays out of range).
  Hours before the device existed or while it was silent do not count. `null` when
  the device reported nothing in the window.
- `alarms_by_detector` counts every alarm, repeats included. Alarms are kept one by
  one for `INFLUX__ALARMS_RETENTION_DAYS` (30); a window reaching further back is
  answered from the daily counts, rounded to whole days and without the current day.
- `channels` is empty and `alarms_by_detector` is `{}` when nothing has been
  evaluated/fired in the window — both are valid, quiet results, not errors.

### Mesh traffic stats

`GET /readings/meshes/{mesh_id}/stats?range=1h|24h|7d|30d` (default `24h`) returns a
mesh's traffic and congestion figures in one response: the numbers behind the
console's Traffic tab. Readable without credentials on a public mesh.

```bash
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/meshes/<mesh_id>/stats?range=7d" | python3 -m json.tool
```

```json
{
  "mesh_id": "11111111-2222-3333-4444-555555555555",
  "range": "7d",
  "window": "1h",
  "activity_window": "1d",
  "hourly_start": "2026-10-01T10:00:00Z",
  "generated_at": "2026-10-08T10:15:02.118Z",
  "summary": {
    "packets": 7792,
    "receptions": 9310,
    "receptions_per_packet": 1.19,
    "bytes": 214880,
    "decoded_packets": 7650,
    "rejected_packets": 12,
    "active_nodes": 4,
    "channel_utilization_mean": 4.9,
    "channel_utilization_peak": 16.6
  },
  "traffic": [
    {"portnum": 67, "name": "TELEMETRY_APP", "packets": 5120, "receptions": 6100,
     "points": [{"time": "2026-10-01T11:00:00+00:00", "value": 31}]},
    {"portnum": null, "name": "ENCRYPTED", "packets": 40, "receptions": 44, "points": []}
  ],
  "airtime": [
    {"channel": "device_metrics.air_util_tx", "mean": 0.8, "peak": 3.1, "points": []},
    {"channel": "device_metrics.channel_utilization", "mean": 4.9, "peak": 16.6, "points": []}
  ],
  "nodes": [
    {"node_id": 111222333, "device_uuid": "aaaaaaaa-...", "packets": 2410, "receptions": 2890}
  ],
  "gateways": [
    {"node_id": 431637602, "device_uuid": "bbbbbbbb-...", "receptions": 9310, "share": 1.0,
     "direct_receptions": 6020, "rx_snr_mean": 5.8, "rx_rssi_mean": -97.2}
  ],
  "hops": [{"hops": 0, "packets": 5100}, {"hops": 1, "packets": 2600}, {"hops": null, "packets": 92}],
  "signal": {
    "snr": [{"bucket": 5.0, "receptions": 3100}],
    "rssi": [{"bucket": -100.0, "receptions": 2800}]
  },
  "gateway_pairs": [
    {"gateway_a": 431637602, "gateway_b": 3935277364, "device_uuid_a": "bbbbbbbb-...",
     "device_uuid_b": null, "common_packets": 65, "snr_diff_mean": 3.1, "rssi_diff_mean": -23.5}
  ],
  "relays": [
    {"gateway_id": 431637602, "device_uuid": "bbbbbbbb-...", "relay": 236, "receptions": 30,
     "candidates": [{"node_id": 2864434412, "device_uuid": "cccccccc-..."}]}
  ],
  "activity": {
    "nodes": [{"time": "2026-10-07T00:00:00+00:00", "value": 81}],
    "gateways": [{"time": "2026-10-07T00:00:00+00:00", "value": 14}]
  }
}
```

- Every packet a registered gateway of the mesh hears is counted, including text,
  routing, packets that could not be decrypted (`portnum: null`, named `ENCRYPTED`)
  and packets from rejected nodes. Rejected nodes count in `summary` but are never
  listed in `nodes`.
- `packets` counts each packet once; `receptions` counts it once per gateway that
  heard it. Their ratio says how much gateway coverage overlaps.
- `decoded_packets` decrypted to a known portnum. Packets from rejected nodes are never
  decrypted, so the decodable share is `decoded_packets / (packets - rejected_packets)`.
- `traffic` is per Meshtastic portnum, busiest first; its `points` are receptions per
  `window` (`1m`, `15m`, `1h` or `6h` for the four ranges).
- `nodes`, `gateways`, `hops` and `signal` are counted per hour and start at
  `hourly_start`, the whole hour on or before the start of the range. `nodes` holds the
  20 nodes that sent the most packets; `device_uuid` is `null` for a node not
  registered on the mesh, and names come from `GET /meshes/{id}/devices`.
- `direct_receptions` are receptions heard straight from the sender, with no hop.
  `rx_snr_mean`, `rx_rssi_mean` and `signal` only cover receptions heard over the air,
  so they are `null` or empty for a gateway that only hears through MQTT.
- `hops` is how many hops a packet took before a gateway first heard it; `null` for
  firmware that does not report it.
- `airtime` is the `channel_utilization` and `air_util_tx` the nodes report about
  themselves, averaged across nodes per bucket. Empty when no node sends device
  metrics.
- `gateway_pairs` compares gateways that heard the same packets, most shared first (top
  30). `snr_diff_mean` and `rssi_diff_mean` are `gateway_a` minus `gateway_b` over the
  packets both heard over the air, so a positive SNR difference means `gateway_a` heard
  them better.
- `relays` counts, per gateway, the node that passed each relayed packet on to it (top
  50). The firmware reports only the last byte of that node's number (`relay`), so
  `candidates` lists the registered nodes of the mesh whose number ends in it; a
  candidate the gateway also hears directly (see the links route) is the likely one.
- `activity` is how many nodes sent, and how many gateways heard, at least one packet
  per `activity_window` (`1h` for the `1h` and `24h` ranges, `1d` otherwise).
- Figures start when the platform began counting traffic, and the last few minutes
  are still being counted. The response is cached for 60 s per mesh and range, shared
  by every API worker.

### Node traffic

`GET /readings/devices/{device_uuid}/traffic?range=1h|24h|7d|30d` (or
`/readings/meshes/{mesh_id}/nodes/{node_id}/traffic`) returns what one node transmitted:
packets and receptions, packets per portnum, and packets over time. Readable without
credentials on a public mesh.

```bash
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  "http://localhost:8091/readings/devices/<device_uuid>/traffic?range=7d" | python3 -m json.tool
```

```json
{
  "mesh_id": "11111111-2222-3333-4444-555555555555",
  "node_id": 111222333,
  "range": "7d",
  "window": "6h",
  "hourly_start": "2026-10-01T10:00:00Z",
  "packets": 186,
  "receptions": 301,
  "ports": [{"portnum": 67, "name": "TELEMETRY_APP", "packets": 140}],
  "points": [{"time": "2026-10-01T12:00:00+00:00", "value": 7}]
}
```

- Counted per hour from `hourly_start`; `points` are packets per `window` (`1h`, `1h`,
  `6h` or `1d` for the four ranges), stamped at the start of each window.
- Packets that could not be decrypted have `portnum: null` (`ENCRYPTED`). Rejected
  nodes are not counted.

### Parquet archive

Decoded and derived readings of the devices with `archive_enabled` (see
[Devices](#devices)), as one Parquet file per mesh and hour (UTC), for analysis at a scale
the routes above are not built for:

```
{prefix}/mesh_id={mesh_id}/dt=YYYY-MM-DD/hour=HH/data.parquet
```

Only the mesh's owner, while an [operator](#operator), and superusers reach a mesh's
archive. Everyone else gets `404`, as if the mesh did not exist, including owners who
are not operators and viewers of a [public mesh](#public-meshes). On an instance
without an archive (lite) every route below answers `404`. An unreachable object store
answers `502`. The columns are `node_id`, `packet_id`, `portnum`, `rx_time`,
`hop_start`, `channel_id`, `gateway_id`, `payload_kind`, `payload_json` and
`postprocessing_id` (set on derived rows); `mesh_id`, `dt` and `hour` come from the
path.

**Manifest**: the hourly files present, oldest first.

```bash
curl -s "http://localhost:8091/readings/archive/meshes/<mesh id>?start=2026-09-01&stop=2026-09-30" \
  -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
```

```json
{
  "mesh_id": "<mesh id>",
  "prefix": "telemetry/mesh_id=<mesh id>/",
  "partitions": [
    {"dt": "2026-09-27", "hour": 13, "size": 7778, "last_modified": "2026-09-27T13:59:12Z"}
  ]
}
```

`start` and `stop` are optional days (`YYYY-MM-DD`, `400` otherwise). Empty until an
archived device reports.

**Credentials**: temporary S3 credentials that read this mesh's prefix and nothing
else, so the archive can be queried as a partitioned dataset.

```bash
curl -s -X POST http://localhost:8091/readings/archive/meshes/<mesh id>/credentials \
  -H "Authorization: Bearer $OWNER_API_KEY" | python3 -m json.tool
```

```json
{
  "access_key_id": "...",
  "secret_access_key": "...",
  "session_token": "...",
  "expires_at": "2026-09-27T14:55:29Z",
  "endpoint": "https://s3.api.yourdomain.com",
  "region": "us-east-1",
  "bucket": "meshtastic-telemetry",
  "prefix": "telemetry/mesh_id=<mesh id>/",
  "s3_path": "s3://meshtastic-telemetry/telemetry/mesh_id=<mesh id>/"
}
```

`201`. The secret is shown in this response only. The credentials last
`READINGS__ARCHIVE_CREDENTIAL_TTL_S` (an hour by default) and cannot be revoked: they
stay valid until `expires_at` even if the caller loses the role or the mesh meanwhile.
`endpoint` is `null` on AWS, where clients find it themselves; use path-style
addressing otherwise. Listing is allowed only under `prefix`. At most 20 an hour per
owner (`429`). On a storage provider without STS this route answers `404` and the two
others still work.

From a browser console logged in with a session cookie, this is the one readings
route that needs a CSRF token: prime it with `GET /owners/csrf-cookie` on registry
and send the `csrftoken` cookie's value back as `X-CSRFToken`. The console's origin
must be in `READINGS__CORS_ORIGINS`, and when it runs on another subdomain,
`REGISTRY__COOKIE_DOMAIN` must cover it so its JavaScript can read the cookie.
Bearer-key callers need none of this.

With DuckDB:

```sql
INSTALL httpfs; LOAD httpfs;
CREATE SECRET archive (TYPE s3, KEY_ID '...', SECRET '...', SESSION_TOKEN '...',
  REGION 'us-east-1', ENDPOINT 's3.api.yourdomain.com', URL_STYLE 'path');
SELECT node_id, dt, count(*) FROM
  read_parquet('s3://meshtastic-telemetry/telemetry/mesh_id=<mesh id>/dt=*/hour=*/data.parquet',
               hive_partitioning=true)
GROUP BY 1, 2;
```

`mesh_things/examples/archive_duckdb.py` and `mesh_things/examples/archive_pandas.py` do this end to end.

**One hour as a file**: a `302` to a temporary download link, for clients without an S3
library.

```bash
curl -sL -o 2026-09-27-13.parquet \
  -H "Authorization: Bearer $OWNER_API_KEY" \
  http://localhost:8091/readings/archive/meshes/<mesh id>/partitions/2026-09-27/13
```

The link lasts as long as issued credentials. `404` for an hour with nothing archived.
curl drops the `Authorization` header when it follows the redirect to another host or port,
which the signed link needs.

**A range as one zip**: request a Parquet [export](#exports).

### Exports

A mesh's readings over a range of days as one zip, built in the background. Only the
mesh's owner and superusers, public mesh or not; Parquet also needs the operator role.
Full profile only: an instance without a bucket answers `404`.

| | CSV | Parquet |
|---|---|---|
| Source | InfluxDB, every device | the archive, devices whose archive is on |
| Layout | `YYYY-MM-DD/<measurement>.csv`, plus `channels.csv` | `YYYY-MM-DD/YYYY-MM-DD_HH.parquet` |
| Columns | `time`, `node_id`, descriptive tags (a node's name), then one per field | as archived |
| `node_ids` | limits it to those devices | refused (`400`): files hold the whole mesh |

`channels.csv` describes each exported channel from the measurement catalog: `channel`,
`name`, `unit`, `description`, `telemetry_variant` (for example
`telemetry:environment_metrics`, blank for device and computed channels), `derived`
(`true` for postprocessing outputs), `quantity_kind` and `vocabulary_uri`. `name` stays
blank until the catalog is curated with display names. `quality` and `alarms` are left out. Points sharing a time and node, such as
one packet heard by several gateways, share a row. Days are UTC, both ends included, at
most `READINGS__EXPORT_MAX_DAYS` (366) of them.

```bash
curl -s -X POST -H "Authorization: Bearer $OWNER_API_KEY" -H 'Content-Type: application/json' \
  -d '{"format": "csv", "start": "2026-09-27", "stop": "2026-09-28", "node_ids": [431637602]}' \
  http://localhost:8091/readings/meshes/<mesh id>/exports
```

`202` with the export, `queued`. One export per owner is queued or running at a time:
the same request again answers `200` with it, a different one `429`. A Parquet range with
nothing archived is refused up front (`404`). At most 30 requests an hour per owner.

```bash
curl -s -H "Authorization: Bearer $OWNER_API_KEY" \
  http://localhost:8091/readings/meshes/<mesh id>/exports/<export id>
```

`status` moves through `queued`, `running` (with `days_done` of `days_total`), then
`ready` with `size` and a `url`, or `failed` with an `error` such as `No readings in that
range`. The owner is also emailed either way, in HTML with a plain-text part. `url` is a presigned link that works for
anyone who has it, named `mesh-<first 8 characters of the mesh id>_<days>_<format>.zip`,
valid until `expires_at`: 24 hours after the export finished, when the file is deleted.
The export itself is kept 30 days: once its file is gone its `status` is `expired`, with
no `url`; request it again to rebuild it. `GET .../exports` lists the caller's exports of
the mesh, and `GET /readings/exports` those of every mesh, newest first (empty on an
instance without object storage).

`mesh_things/examples/export_download.py` requests one, waits and downloads it.

### Health

Unauthenticated — an infra liveness probe, not sensitive data.

```bash
curl -s http://localhost:8091/health
```
