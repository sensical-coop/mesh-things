# Incident response: personal data breaches

What to do when personal data may have been exposed, altered, lost or made unavailable.
This is the documented procedure the Data Processing Agreement (Annex II) refers to, and it
has to keep the promises made there and in the Privacy Policy:

- **Owners** (controllers of their mesh, source and sink data): notified **within 48 hours**
  of Sensical becoming aware of a breach affecting their data (DPA §9).
- **The AEPD**, for breaches of the data Sensical controls itself (accounts: names, email
  addresses, password hashes, terms acceptances): notified **within 72 hours** unless the
  breach is unlikely to result in a risk to people (GDPR Art. 33).
- **Account holders**, when a breach of their account data is likely to result in a high
  risk to them: told without undue delay (Art. 34).
- **Every breach is recorded**, including the ones nobody is notified about (Art. 33(5)).

The clock starts when someone at Sensical is reasonably certain a breach happened, not when
the investigation ends. Notify with what is known and add the rest later.

## 1. Report it internally (immediately)

Anyone who notices something (an alert, a strange log line, a report to info@sensical.es,
a message from Hetzner or Scaleway) tells the rest of the team at once, with the time they
noticed. That person owns the incident until they hand it over explicitly.

Open an entry in the breach log (see [Record](#6-record)) and write down the time.

## 2. Contain

Stop the damage first; keep evidence where it doesn't slow that down.

- **Take a Hetzner snapshot** of the affected server before changing it, if it may be needed
  to understand what happened. Delete it when the incident is closed.
- **Cut access**: block addresses with `ufw`, stop the affected service
  (`docker compose stop <service>`), deactivate compromised accounts in the Django admin.
- **Rotate what may have leaked**: the secrets in `.env` (Django secret key, database, InfluxDB,
  EMQX and S3/MinIO credentials, the Scaleway SMTP key), SSH keys, Hetzner console passwords.
  Revoke affected owners' API keys and sessions.
- **Sinks**: delete or pause affected sinks so their credentials are refused.
- If a sub-processor is involved (Hetzner, Scaleway), open a ticket with them and ask for their
  own incident details: their DPA obliges them to report to Sensical.

## 3. Assess

Answer, as far as known, and write the answers in the log:

- What happened, when it started, when it was found, whether it is still going on.
- Which data: account data (Sensical is controller), mesh/source/sink data (the owners are
  controllers), or both.
- Whose data, and roughly how many people and records. For mesh data, which meshes, and so
  which owners.
- Confidentiality (seen by someone who shouldn't), integrity (changed) or availability (lost
  or unreachable)?
- Likely consequences for the people concerned. Location history and contact details weigh
  more than device telemetry; hashed passwords and API keys weigh less than plaintext ones.
- What has been done, and what is still planned, to limit the harm.

## 4. Notify

### Owners, within 48 hours (Sensical as processor)

Email every owner whose meshes, sources or sinks are affected. Include (DPA §9):

1. What happened and when, as far as known.
2. The categories and approximate number of data subjects and records concerned.
3. The likely consequences.
4. The measures taken or proposed, including what they can do themselves.
5. A contact point: info@sensical.es.

Say what is still unknown and when the next update will come. Owners decide whether to
notify the AEPD and the people concerned, since they are the controllers; Sensical helps
them with the information it has (DPA §7).

### The AEPD, within 72 hours (Sensical as controller)

For breaches of account data, notify through the AEPD's electronic office
(https://sedeagpd.gob.es, "Notificación de brechas de seguridad de los datos personales"),
unless the assessment concludes the breach is unlikely to result in a risk to people. Record
that reasoning either way. A partial notification can be completed later.

### Account holders (high risk)

If the breach of account data is likely to result in a high risk (for example, email
addresses together with something that enables phishing or account takeover), email the
people concerned in plain language: what happened, the likely consequences, what Sensical
has done, and what they should do (such as change their password).

## 5. Recover and learn

- Restore service, from Hetzner backups if needed (the last 7 daily backups are kept).
- Once closed, write a short review: cause, what worked, what to change. Update the DPA's
  Annex II if a security measure changes, and this document if the procedure should.

## 6. Record

Keep a breach log outside this repository (it can contain personal data), with one entry per
incident, notified or not:

| Field | Content |
|---|---|
| Found | Date and time Sensical became aware, and by whom |
| Facts | What happened, which data, whose, how many |
| Effects | Likely consequences |
| Actions | Containment and remediation, with times |
| Notifications | Owners, AEPD, account holders: when, or why not |
| Closed | Date, and a link to the review |

Keep the log for at least 5 years, the same as the other evidence of proper processing.
