#!/usr/bin/env bash
#
# Redeploy Flink jobs after a code change, carrying their state over through a
# savepoint. See docs/flink.md#redeploying-after-a-code-change.
#
#   ./scripts/redeploy-flink.sh                    # every job, and jobmanager/taskmanager
#   ./scripts/redeploy-flink.sh pattern-detection-job
#   COMPOSE="docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile full" \
#       ./scripts/redeploy-flink.sh
#
# Redeploy everything when common/ changed: the jobs import it from the
# jobmanager and taskmanager images, not from the submitted file.
#
set -euo pipefail

cd "$(dirname "$0")/.."
read -r -a COMPOSE <<<"${COMPOSE:-docker compose --profile full}"

# Submitter service -> job name, read from their `submit-job.sh <file> <name>` commands
# and listed in their depends_on order.
declare -A JOB_NAMES
SUBMITTERS=()
while read -r service name; do
	SUBMITTERS+=("$service")
	JOB_NAMES[$service]="$name"
done < <("${COMPOSE[@]}" config --format json | python3 -c '
import json, sys
services = json.load(sys.stdin)["services"]
submitters = {
    name: svc for name, svc in services.items()
    if (svc.get("command") or [])[:1] == ["./submit-job.sh"]
}
ordered = []
while len(ordered) < len(submitters):
    for name, svc in sorted(submitters.items()):
        upstream = set(svc.get("depends_on") or {}) & submitters.keys()
        if name not in ordered and upstream <= set(ordered):
            ordered.append(name)
for name in ordered:
    print(name, submitters[name]["command"][2])
')

TARGETS=("$@")
FULL=false
if [ ${#TARGETS[@]} -eq 0 ]; then
	FULL=true
	TARGETS=("${SUBMITTERS[@]}")
fi
for t in "${TARGETS[@]}"; do
	[ -n "${JOB_NAMES[$t]:-}" ] || { echo "unknown job service: $t (one of: ${SUBMITTERS[*]})" >&2; exit 64; }
done

# Prints the IDs of the live copies of a job.
live_jobs() {
	"${COMPOSE[@]}" exec -T jobmanager curl -sf localhost:8081/jobs/overview | python3 -c '
import json, sys
LIVE = {"RUNNING", "CREATED", "INITIALIZING", "RESTARTING", "RECONCILING", "SUSPENDED"}
for j in json.load(sys.stdin)["jobs"]:
    if j["name"] == sys.argv[1] and j["state"] in LIVE:
        print(j["jid"])
' "$1"
}

wait_healthy() {
	for _ in $(seq 60); do
		[ "$(docker inspect -f '{{.State.Health.Status}}' "$1")" = healthy ] && return 0
		sleep 3
	done
	echo "$1 did not become healthy" >&2
	exit 1
}

echo "==> building the Flink image"
"${COMPOSE[@]}" build jobmanager

# Otherwise it resubmits the old code the moment a job stops.
echo "==> stopping flink-watchdog"
"${COMPOSE[@]}" stop flink-watchdog

for service in "${TARGETS[@]}"; do
	name="${JOB_NAMES[$service]}"
	for jid in $(live_jobs "$name"); do
		echo "==> stopping $name ($jid) with a savepoint"
		"${COMPOSE[@]}" exec -T jobmanager flink stop -p "file:///opt/flink/savepoints/$name" "$jid"
	done
done

if $FULL; then
	echo "==> recreating jobmanager and taskmanager"
	"${COMPOSE[@]}" up -d --force-recreate --no-deps jobmanager taskmanager
	wait_healthy jobmanager
	wait_healthy taskmanager
fi

# In submitter order, since each depends on the previous one's output topic.
for service in "${SUBMITTERS[@]}"; do
	printf '%s\n' "${TARGETS[@]}" | grep -qx "$service" || continue
	echo "==> resubmitting $service"
	"${COMPOSE[@]}" up -d --force-recreate --no-deps "$service"
	status="$(docker wait "$("${COMPOSE[@]}" ps -aq "$service")")"
	"${COMPOSE[@]}" logs --no-log-prefix "$service" | grep '^submit-job:' || true
	[ "$status" -eq 0 ] || { echo "$service exited with $status" >&2; exit 1; }
done

failed=0
for service in "${TARGETS[@]}"; do
	name="${JOB_NAMES[$service]}"
	count="$(live_jobs "$name" | wc -l)"
	if [ "$count" -ne 1 ]; then
		echo "!! $name has $count live copies, expected 1" >&2
		failed=1
	fi
done

echo "==> starting flink-watchdog"
"${COMPOSE[@]}" up -d --force-recreate --no-deps flink-watchdog

[ "$failed" -eq 0 ] && echo "==> done: every redeployed job has exactly one live copy"
exit "$failed"
