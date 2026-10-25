#!/usr/bin/env bash
#
# Keep the Flink jobs running. Every interval, resubmit any listed job that is
# no longer live, resuming from its newest checkpoint. The cluster has no high
# availability, so a jobmanager restart or a host reboot drops every job.
#
#   watch-jobs.sh <job-file.py>:<job-name> [...]
#
set -uo pipefail

[ $# -gt 0 ] || { echo "usage: watch-jobs.sh <job-file.py>:<job-name> [...]" >&2; exit 64; }
INTERVAL="${FLINK_WATCH_INTERVAL_SECONDS:-60}"

while true; do
	for pair in "$@"; do
		out="$(./submit-job.sh "${pair%%:*}" "${pair#*:}" 2>&1)"
		case "$out" in
			*"is already running - nothing to do"*) ;;
			*) printf '%s\n' "$out" ;;
		esac
	done
	sleep "$INTERVAL"
done
