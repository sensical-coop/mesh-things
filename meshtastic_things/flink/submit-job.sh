#!/usr/bin/env bash
#
# Submit a PyFlink job to the cluster, detached and only if it isn't already
# running.
#
#   submit-job.sh <job-file.py> <job-name>
#
set -euo pipefail

JOB_FILE="${1:?usage: submit-job.sh <job-file.py> <job-name>}"
JOB_NAME="${2:?usage: submit-job.sh <job-file.py> <job-name>}"
REST_URL="${FLINK_REST_URL:-http://jobmanager:8081}"
WAIT_SECONDS="${FLINK_SUBMIT_WAIT_SECONDS:-180}"

deadline=$(( $(date +%s) + WAIT_SECONDS ))
until curl -sf "$REST_URL/overview" >/dev/null 2>&1; do
	if [ "$(date +%s)" -ge "$deadline" ]; then
		echo "submit-job: jobmanager REST at $REST_URL not reachable after ${WAIT_SECONDS}s" >&2
		exit 1
	fi
	sleep 2
done

# States to show that "this job exists and does not need resubmitting"
live_count() {
	curl -sf "$REST_URL/jobs/overview" 2>/dev/null | python3 -c '
import json, sys
name = sys.argv[1]
LIVE = {"RUNNING", "CREATED", "INITIALIZING", "RESTARTING", "RECONCILING", "SUSPENDED"}
try:
    jobs = json.load(sys.stdin).get("jobs", [])
except Exception:
    jobs = []
print(sum(1 for j in jobs if j.get("name") == name and j.get("state") in LIVE))
' "$JOB_NAME"
}

count="$(live_count || echo 0)"
count="${count:-0}"

if [ "$count" -gt 1 ]; then
	echo "submit-job: WARNING - $count copies of '$JOB_NAME' are already running." >&2
	echo "submit-job: cancel the extras in the Flink UI; see docs/flink.md#duplicate-jobs" >&2
	exit 0
fi

if [ "$count" -eq 1 ]; then
	echo "submit-job: '$JOB_NAME' is already running - nothing to do."
	exit 0
fi

CHECKPOINTS_DIR="/opt/flink/checkpoints/$JOB_NAME"
SAVEPOINTS_DIR="/opt/flink/savepoints/$JOB_NAME"
mkdir -p "$CHECKPOINTS_DIR" "$SAVEPOINTS_DIR"

# A checkpoint or savepoint is complete once Flink has written its _metadata.
latest="$(ls -t "$CHECKPOINTS_DIR"/*/chk-*/_metadata "$SAVEPOINTS_DIR"/savepoint-*/_metadata 2>/dev/null | head -n 1 || true)"
restore_args=()
if [ -n "$latest" ]; then
	restore_from="$(dirname "$latest")"
	restore_args=(-s "$restore_from")
	echo "submit-job: resuming '$JOB_NAME' from $restore_from"
else
	restore_from=""
	echo "submit-job: no checkpoint or savepoint for '$JOB_NAME', starting fresh"
fi

# Retained checkpoints of earlier runs and old savepoints are never pruned by Flink.
for run_dir in "$CHECKPOINTS_DIR"/*/ "$SAVEPOINTS_DIR"/savepoint-*/; do
	[ -d "$run_dir" ] || continue
	case "$restore_from/" in
		"${run_dir}"*) ;;
		*) rm -rf "$run_dir" ;;
	esac
done

echo "submit-job: submitting '$JOB_NAME' from $JOB_FILE (detached)"
exec flink run -d \
	-Dstate.checkpoints.dir="file://$CHECKPOINTS_DIR" \
	-Dstate.savepoints.dir="file://$SAVEPOINTS_DIR" \
	"${restore_args[@]}" \
	-py "$JOB_FILE"
