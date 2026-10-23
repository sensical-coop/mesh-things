#!/usr/bin/env bash
#
# Restart a source's bridge on EMQX, for one that reports connected but receives
# nothing. Run on the server from the repository; it goes through registry-api, so
# the EMQX API key never leaves .env. See docs/deploy.md, "MQTT sources".
#
#   ./scripts/restart-source.sh                 # list sources, status and message count
#   ./scripts/restart-source.sh <source-id>     # restart that source
#   COMPOSE="docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile full" \
#     ./scripts/restart-source.sh                 # the local stack
#
set -euo pipefail

cd "$(dirname "$0")/.."

if [ $# -gt 1 ]; then
	echo "usage: $0 [<source-id>]" >&2
	exit 64
fi

read -r -a COMPOSE <<<"${COMPOSE:-docker compose --profile full}"
exec "${COMPOSE[@]}" exec -T registry_api python manage.py restart_source "$@"
