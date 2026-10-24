# Setting up production email with Scaleway

`registry_api` sends two kinds of mail: owner email-verification/password-reset
links (`registry/emailing.py`) and quality-alarm notifications
(`registry/management/commands/consume_quality_alarms.py`). Both go through
Django's standard SMTP backend, so any SMTP provider works — this is the
Scaleway Transactional Email (TEM) version of the generic steps in
[deploy.md#email](deploy.md#email).

Why Scaleway: it is a French provider running in its own `fr-par` region, so mail
(owners' addresses, and the device labels and values in alarm emails) stays in the
EU and there is no third-country transfer to disclose in the DPA. The Essential
plan is pay-as-you-go: 300 emails/month free, then €0.25 per 1,000, with a default
quota of 10,000/month (raised on request).

## 1. Create a project and pick a plan

1. Sign up at [console.scaleway.com](https://console.scaleway.com) and create (or
   pick) a Project for this deployment.
2. **Domains & Web Hosting** → **Transactional Email** → **Select a plan** →
   **Essential**.

## 2. Verify a sending domain

1. **Choose a plan and add a domain**, then enter the domain you'll send from
   (e.g. `yourdomain.com` — it does not need to match `CADDY_SITE_ADDRESS`, but a
   subdomain like `mail.yourdomain.com` keeps this separate from any other mail
   already on the root domain).
2. Scaleway gives you SPF, DKIM, MX and DMARC records. Add all of them at your DNS
   provider (a domain registered with Scaleway can configure them automatically).
   Scaleway does not support recursive SPF `include`s, so keep its `include`
   directly in the domain's SPF record.
3. Wait for the domain to show as verified in the console. Propagation is usually
   fast but can take a few hours. Sending from an unverified domain fails at send
   time, not at startup — see [Troubleshooting](#troubleshooting).

## 3. Get the SMTP credentials

1. **IAM** → **Applications** → create an application (e.g. `meshtastic-things-smtp`).
2. **IAM** → **Policies** → create a policy with that application as principal,
   granting Transactional Email sending permissions **in this Project only** — the
   key only needs to send mail, not manage domains or anything else.
3. Create an API key for the application and copy the secret key now; Scaleway
   shows it once, the same way this API's own `POST /owners` shows an API key once.

| Setting | Value |
|---|---|
| Host | `smtp.tem.scaleway.com` |
| Port | `587` (STARTTLS) or `2465` (implicit TLS) |
| Username | the **Project ID** (Transactional Email → Domain overview), not your account email |
| Password | the API **secret key** from step 3 |

Encryption is mandatory. Prefer `587`: Hetzner blocks outgoing ports `25` and
`465` on new servers by default, so `465` may hang; `2465` is Scaleway's
alternative implicit-TLS port.

## 4. Set the `.env` variables

In the production `.env` on the VPS (built from `env.example` — see
[deploy.md#6-configure-env](deploy.md#6-configure-env)):

```bash
REGISTRY__EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
REGISTRY__EMAIL_HOST=smtp.tem.scaleway.com
REGISTRY__EMAIL_PORT=587
REGISTRY__EMAIL_HOST_USER=<the Project ID>
REGISTRY__EMAIL_HOST_PASSWORD=<the secret key from step 3>
REGISTRY__EMAIL_USE_TLS=true
REGISTRY__EMAIL_USE_SSL=false
REGISTRY__DEFAULT_FROM_EMAIL=noreply@yourdomain.com
```

`REGISTRY__DEFAULT_FROM_EMAIL` must be `@` the domain you verified in step 2
— Scaleway rejects sends from an unverified domain regardless of what the SMTP
credentials are. Using port `2465` instead of `587`, flip the TLS/SSL pair:
`REGISTRY__EMAIL_USE_TLS=false` and `REGISTRY__EMAIL_USE_SSL=true`.

## 5. Roll it out

```bash
docker compose up -d --build registry_api
```

`api_project/settings/prod.py` fails startup (`ImproperlyConfigured`) if
`EMAIL_BACKEND` is the SMTP backend but `EMAIL_HOST` is still `mailhog`,
`localhost`, or empty — so a successful boot already confirms the guard rail
passed; it does not confirm Scaleway itself is reachable or the domain is
verified.

## 6. Verify delivery

Trigger a real send through the app rather than a synthetic one, so you're
testing the same code path production traffic uses:

```bash
curl -s -X POST https://api.sensical.es/owners \
  -H "Content-Type: application/json" \
  -d '{"name": "Test", "email": "you@example.com", "password": "..."}'
```

This sends a verification email via `send_verification_email`
(`registry/emailing.py`). Check the domain's email activity under
**Transactional Email** in the console — it shows delivery status per message,
which is more reliable than waiting on the inbox alone while DNS/DKIM is still
settling.

## Troubleshooting

- **Rejected at send time (`5xx`)**: the `From` address's domain isn't verified
  yet, or DNS hasn't propagated. Check the domain's status in the console.
- **Authentication failure**: the username must be the Project ID the domain
  lives in, and the password the API *secret* key (not the access key), from an
  application whose policy covers that Project.
- **Connection hangs / `WORKER TIMEOUT` on a request that sends mail**: the port
  is blocked outbound. Hetzner blocks `25` and `465` by default; use `587` or
  `2465`. The SMTP connection gives up after 10 seconds, so the request still
  answers and the failure is logged as `*_email_send_failed`.
- **`ImproperlyConfigured: REGISTRY__EMAIL_HOST='mailhog' is not a
  production mail server`** at container startup: `REGISTRY__EMAIL_HOST`
  wasn't actually updated — this is `prod.py`'s guard against silently
  running mailhog in production (`docs/deploy.md#django-settings`).
- **Emails send but never arrive**: check the console's email activity first —
  it distinguishes sent from delivered from failed, which a missing inbox
  message alone cannot. A verified domain with no DMARC record set to at least
  `p=none` is a common cause of silent spam-folder delivery.
- **Quota**: the default is 10,000 emails/month, and each recipient counts as one
  email. Quality-alarm emails go out per device, at most one alarm plus one
  summary per window (`registry/management/commands/consume_quality_alarms.py`),
  so a mesh with many devices tripping alarms can add up — see
  `REGISTRY__ALARM_EMAIL_COOLDOWN_SECONDS` in `env.example` to lengthen the
  window, or ask Scaleway support to raise the quota.
