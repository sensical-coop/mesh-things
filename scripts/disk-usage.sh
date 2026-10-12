#!/usr/bin/env bash
#
# Report where the deployment's disk goes: Docker images, build cache,
# container logs, volumes, Flink checkpoints and savepoints, Kafka topics,
# InfluxDB buckets, Postgres tables and backups.
# Read-only; run it after a deploy or when the disk fills up.
#
#   ./scripts/disk-usage.sh
#   COMPOSE="docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile full" \
#       ./scripts/disk-usage.sh
#
set -uo pipefail

cd "$(dirname "$0")/.."
read -r -a COMPOSE <<<"${COMPOSE:-docker compose --profile full}"
PROJECT="$(basename "$PWD")"

echo "== disk"
df -h / | tail -1

echo "== docker"
docker system df

# Log files are root-owned, so their sizes need root or passwordless sudo.
echo "== container logs (MB)"
if [ "$(id -u)" -eq 0 ] || sudo -n true 2>/dev/null; then
	# Only the json-file driver keeps a log file per container; journald and
	# others leave LogPath empty and store logs elsewhere.
	driver="$(docker info -f '{{.LoggingDriver}}')"
	echo "log driver: $driver"
	[ "$driver" = journald ] && journalctl --disk-usage
	for c in $(docker ps -aq); do
		path="$(docker inspect -f '{{.LogPath}}' "$c")"
		[ -n "$path" ] || continue
		size="$(sudo -n stat -c %s "$path")"
		printf '%6d %s\n' "$((size / 1048576))" "$(docker inspect -f '{{.Name}}' "$c" | tr -d /)"
	done | sort -rn | head -10
else
	echo "(needs root: run it with sudo to see them)"
fi

echo "== volumes"
docker system df -v | grep -E "^${PROJECT}_" | sort -k3 -h -r

echo "== flink checkpoints and savepoints"
"${COMPOSE[@]}" exec -T jobmanager sh -c 'du -sh /opt/flink/checkpoints/* /opt/flink/savepoints/* 2>/dev/null'

echo "== kafka topics (MB)"
"${COMPOSE[@]}" exec -T kafka sh -c 'du -sm /var/lib/kafka/data; du -sm /var/lib/kafka/data/* | sort -rn | head -10'

# Bucket directories are named by ID; the token is only needed to name them.
echo "== influxdb buckets (MB)"
env_var() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }
sizes="$("${COMPOSE[@]}" exec -T influxdb sh -c 'cd /var/lib/influxdb2/engine/data && du -sm *')"
names="$("${COMPOSE[@]}" exec -T -e INFLUX_TOKEN="$(env_var INFLUX__TOKEN)" -e INFLUX_ORG="$(env_var INFLUX__ORG)" \
	influxdb influx bucket list --hide-headers 2>/dev/null)"
awk 'NR == FNR { name[$1] = $2; next } { print $1, ($2 in name ? name[$2] : $2) }' \
	<(echo "$names") <(echo "$sizes") | sort -rn

echo "== postgres tables (MB)"
"${COMPOSE[@]}" exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F " " -c "
	select round(pg_database_size(current_database()) / 1048576.0, 1), '"'"'(database)'"'"'
	union all
	(select round(pg_total_relation_size(relid) / 1048576.0, 1), relname
	 from pg_statio_user_tables order by 1 desc limit 10)"'

# Under sudo, HOME is root's, so the backups are looked up in the invoking user's home.
echo "== backups"
backup_dir="${BACKUP_DIR:-$(getent passwd "${SUDO_USER:-$USER}" | cut -d: -f6)/backups}"
if [ -d "$backup_dir" ]; then
	du -sh "$backup_dir"
	for kind in registry influx; do
		printf '%s: %s files, newest %s\n' "$kind" \
			"$(find "$backup_dir" -maxdepth 1 -name "$kind-*.age" | wc -l)" \
			"$(find "$backup_dir" -maxdepth 1 -name "$kind-*.age" -printf '%f\n' | sort | tail -1)"
	done
else
	echo "($backup_dir does not exist)"
fi

# Dangling images are left behind by every rebuild.
echo "== images"
docker images --format '{{.Repository}}:{{.Tag}} {{.Size}} {{.CreatedSince}}' | grep -E "^${PROJECT}|<none>" | head -15
