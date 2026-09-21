#!/usr/bin/env bash
#
# Dump the given targets to $BACKUP_DIR, then prune backups older than
# $RETENTION_DAYS. Meant to run unattended from cron - see
# docs/deploy.md#backups for the crontab entry.
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
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DATE="$(date +%F)"
mkdir -p "$BACKUP_DIR"

log() { echo "[$(date -Is)] $*"; }

# Reads only the vars this script needs, rather than hard-coding them or
# sourcing the whole file - .env has unquoted values (KAFKA_JMX_OPTS) that
# break a naive `. ./.env`.
env_var() { grep -E "^$1=" .env | tail -1 | cut -d= -f2-; }

if wants postgres; then
	POSTGRES_USER="$(env_var POSTGRES_USER)"
	POSTGRES_DB="$(env_var POSTGRES_DB)"
	log "backing up postgres..."
	docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
		| gzip > "$BACKUP_DIR/registry-$DATE.sql.gz"
fi

if wants influx; then
	INFLUX__TOKEN="$(env_var INFLUX__TOKEN)"
	INFLUX__ORG="$(env_var INFLUX__ORG)"
	if [ -n "${INFLUX__TOKEN:-}" ] && docker compose exec -T influxdb true 2>/dev/null; then
		log "backing up influxdb..."
		REMOTE_DIR="/tmp/influx-backup-$DATE"
		docker compose exec -T influxdb influx backup "$REMOTE_DIR" \
			--org "$INFLUX__ORG" --token "$INFLUX__TOKEN" >/dev/null
		docker compose cp "influxdb:$REMOTE_DIR" "$BACKUP_DIR/influx-$DATE"
		docker compose exec -T influxdb rm -rf "$REMOTE_DIR"
		tar -C "$BACKUP_DIR" -czf "$BACKUP_DIR/influx-$DATE.tar.gz" "influx-$DATE"
		rm -rf "${BACKUP_DIR:?}/influx-$DATE"
	else
		log "skipping influxdb (not running or INFLUX__TOKEN unset)"
	fi
fi

log "pruning backups older than ${RETENTION_DAYS}d in $BACKUP_DIR..."
find "$BACKUP_DIR" -maxdepth 1 -name '*.gz' -mtime "+$RETENTION_DAYS" -delete

log "done: $(find "$BACKUP_DIR" -maxdepth 1 -name "*-$DATE.*" -printf '%f ')"
