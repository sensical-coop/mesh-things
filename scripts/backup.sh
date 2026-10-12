#!/usr/bin/env bash
#
# Dump the given targets to $BACKUP_DIR, encrypted with age to
# BACKUP__AGE_RECIPIENT, then prune backups older than $RETENTION_DAYS. Meant to
# run unattended from cron - see docs/backups.md for the key, the crontab entry
# and restoring.
#
#   ./scripts/backup.sh                 # postgres, and influx if configured
#   ./scripts/backup.sh postgres        # postgres only
#   ./scripts/backup.sh postgres influx
#   BACKUP_DIR=/mnt/backups RETENTION_DAYS=30 ./scripts/backup.sh
#
set -euo pipefail

usage() {
	echo "usage: $0 [postgres] [influx]" >&2
	echo "  no arguments backs up postgres, and influx if INFLUX__TOKEN is set" >&2
	exit 64
}

TARGETS=("$@")
if [ ${#TARGETS[@]} -eq 0 ]; then
	TARGETS=(postgres influx)
fi
for t in "${TARGETS[@]}"; do
	case "$t" in
		postgres | influx) ;;
		*) usage ;;
	esac
done
wants() { printf '%s\n' "${TARGETS[@]}" | grep -qx "$1"; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
DATE="$(date +%F)"
mkdir -p "$BACKUP_DIR"

log() { echo "[$(date -Is)] $*"; }
die() { log "error: $*"; exit 1; }

# Reads only the vars this script needs, rather than hard-coding them or
# sourcing the whole file - .env has unquoted values (KAFKA_JMX_OPTS) that
# break a naive `. ./.env`.
env_var() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }

# Only the public key lives on the server; the private key that decrypts stays with Sensical.
AGE_RECIPIENT="${BACKUP__AGE_RECIPIENT:-$(env_var BACKUP__AGE_RECIPIENT)}"
AGE_RECIPIENT="${AGE_RECIPIENT//\"/}"
[ -n "$AGE_RECIPIENT" ] || die "BACKUP__AGE_RECIPIENT is not set; refusing to write an unencrypted backup"
command -v age >/dev/null || die "age is not installed (apt install age)"

# Encrypts stdin to $1, renaming it into place only once complete.
encrypt_to() {
	age -r "$AGE_RECIPIENT" -o "$1.partial"
	mv "$1.partial" "$1"
}

if wants postgres; then
	POSTGRES_USER="$(env_var POSTGRES_USER)"
	POSTGRES_DB="$(env_var POSTGRES_DB)"
	log "backing up postgres..."
	docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
		| gzip | encrypt_to "$BACKUP_DIR/registry-$DATE.sql.gz.age"
fi

if wants influx; then
	INFLUX__TOKEN="$(env_var INFLUX__TOKEN)"
	INFLUX__ORG="$(env_var INFLUX__ORG)"
	if [ -n "${INFLUX__TOKEN:-}" ] && docker compose exec -T influxdb true 2>/dev/null; then
		log "backing up influxdb..."
		REMOTE_DIR="/tmp/influx-backup-$DATE"
		# The copy is unencrypted and the prune below only matches files, so a failed run
		# must not leave it behind.
		trap 'rm -rf "${BACKUP_DIR:?}/influx-$DATE"; docker compose exec -T influxdb rm -rf "$REMOTE_DIR" 2>/dev/null' EXIT
		docker compose exec -T influxdb influx backup "$REMOTE_DIR" \
			--org "$INFLUX__ORG" --token "$INFLUX__TOKEN" >/dev/null
		docker compose cp "influxdb:$REMOTE_DIR" "$BACKUP_DIR/influx-$DATE"
		docker compose exec -T influxdb rm -rf "$REMOTE_DIR"
		tar -C "$BACKUP_DIR" -czf - "influx-$DATE" | encrypt_to "$BACKUP_DIR/influx-$DATE.tar.gz.age"
		rm -rf "${BACKUP_DIR:?}/influx-$DATE"
	else
		log "skipping influxdb (not running or INFLUX__TOKEN unset)"
	fi
fi

log "pruning backups older than ${RETENTION_DAYS}d in $BACKUP_DIR..."
# -mtime +N matches files at least N+1 whole days old, so N-1 keeps no dump past N days.
# *.gz also prunes the unencrypted dumps written before encryption.
find "$BACKUP_DIR" -maxdepth 1 \( -name '*.age' -o -name '*.gz' -o -name '*.partial' \) \
	-mtime "+$((RETENTION_DAYS - 1))" -delete

log "done: $(find "$BACKUP_DIR" -maxdepth 1 -name "*-$DATE.*" -printf '%f ')"
