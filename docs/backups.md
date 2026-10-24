# Backups

Two layers protect the data:

| Layer | What | Kept | Encrypted |
|---|---|---|---|
| Hetzner backups | The whole server, daily | Last 7 | No key held by Sensical; Hetzner stores and manages them |
| `scripts/backup.sh` | Postgres (the registry) and InfluxDB (readings, alarms, mesh statistics), daily | 7 days, in `~/backups` on the server | Yes, with [age](https://age-encryption.org), to a key Sensical keeps off the server |

The 7 days match the terms: data deleted from the service leaves the backups
within 7 days. The DPA's Annex II describes both layers, so change it if either
changes.

Not backed up: `minio_data` (the Parquet archive, large enough to need its own
solution), `kafka_data` (in-flight messages only) and `caddy_data` (certificates
re-issue). `.env` belongs in the password manager, not in a backup.

## The key

The dumps are encrypted to an age **public key** (a recipient, `age1...`), which is
all the server holds. The **private key** decrypts them and never goes on the
server: whoever takes the server or its Hetzner backups gets the dumps but cannot
read them.

Generate it once, on a trusted machine, not the server:

```bash
age-keygen -o mesh-things-backups.key
# Public key: age1...   <- goes into the server's .env
```

Store `mesh-things-backups.key` in Sensical's password manager, and keep a second
copy somewhere offline. Losing it makes every encrypted dump unreadable.

## Setting up the server

```bash
sudo apt install -y age
```

In `.env`:

```bash
BACKUP__AGE_RECIPIENT=age1...
```

The script refuses to run without it, or without `age`, rather than write an
unencrypted dump. Test it once by hand:

```bash
./scripts/backup.sh postgres
ls -l ~/backups      # registry-YYYY-MM-DD.sql.gz.age
```

## Running it daily

```cron
0 3 * * * BACKUP_DIR=/home/deploy/backups /home/deploy/meshtastic-things/scripts/backup.sh postgres influx >> /home/deploy/backups/backup.log 2>&1
```

`scripts/backup.sh` takes the targets as arguments (`postgres`, `influx`; none
means both, InfluxDB only if `INFLUX__TOKEN` is set). It dumps, compresses,
encrypts, writes each file under a `.partial` name and renames it only once
complete, then deletes `.age`, `.gz` and leftover `.partial` files older than
`RETENTION_DAYS` (default 7). InfluxDB's backup is copied out of the container
unencrypted before it is archived, and that copy is removed even when the run fails.

`INFLUX__TOKEN` must be an all-access token for `influx backup`; one that can only
create buckets makes the InfluxDB step fail. Run `./scripts/backup.sh influx` once by
hand after setting it. The first run after upgrading also prunes the
unencrypted `.gz` dumps written before encryption.

For cron:

- Use the absolute path to the script: cron does not run from the checkout.
- Cron's `PATH` is minimal. If the log shows `docker: command not found` or
  `age is not installed`, add a `PATH=/usr/local/bin:/usr/bin:/bin` line above
  the job.
- Redirect both stdout and stderr, as above. Cron rarely has mail configured, so
  an unredirected failure disappears.

## Restoring

Copy the dump to the machine holding the private key and decrypt it there, or,
when restoring on the server, bring the key in for the restore only and delete
it afterwards.

Postgres:

```bash
age -d -i mesh-things-backups.key registry-2026-10-08.sql.gz.age | gunzip > registry.sql
# on the server, from the checkout:
set -a && . ./.env && set +a
docker compose exec -T postgres psql -U "$POSTGRES_USER" "$POSTGRES_DB" < registry.sql
rm registry.sql
```

InfluxDB, into a **fresh, re-provisioned** InfluxDB: run the `influx setup` step of
[deploy.md](deploy.md#initialise-influxdb) first and use its new admin token, since
`--org` and `--bucket` must not already exist on the target:

```bash
age -d -i mesh-things-backups.key influx-2026-10-08.tar.gz.age > influx-restore.tar.gz
docker compose cp influx-restore.tar.gz influxdb:/tmp/influx-restore.tar.gz
docker compose exec -T influxdb sh -c \
  'cd /tmp && tar xzf influx-restore.tar.gz && influx restore /tmp/influx-2026-10-08 --org "'"$INFLUX__ORG"'" --bucket "'"$INFLUX__BUCKET"'" --token "<the new admin token>"'
rm influx-restore.tar.gz
```

Test a restore a few times a year, into a scratch database, so the key and the
steps are known to work before they are needed.

## Changing the key

Generate a new key, put its public key in `.env`, and keep the old private key
until the last dump encrypted to it has been pruned, 7 days later.
