#!/usr/bin/env bash
#
# Report where the deployment's disk goes: Docker images, build cache,
# container logs, volumes, Flink checkpoints and savepoints, and Kafka topics.
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
"${COMPOSE[@]}" exec -T kafka sh -c 'du -sm /var/lib/kafka/data/* | sort -rn | head -10'

# Dangling images are left behind by every rebuild.
echo "== images"
docker images --format '{{.Repository}}:{{.Tag}} {{.Size}} {{.CreatedSince}}' | grep -E "^${PROJECT}|<none>" | head -15
