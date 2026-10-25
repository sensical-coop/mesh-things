#!/bin/bash
# Pin every Python dependency of each image, transitive ones included, with hashes.
# The images install from these locks, so builds are reproducible and scanners audit
# what is deployed.
#
#   scripts/lock-deps.sh            # follow changed requirements, keep every other pin
#   scripts/lock-deps.sh --upgrade  # move every pin to the newest allowed version
#
# The Python versions are the images' own: 3.11 for the python:3.11-slim images and
# 3.12 for the Flink image's Ubuntu 24.04.
set -euo pipefail
cd "$(dirname "$0")/../server"

UPGRADE=()
[ "${1:-}" = --upgrade ] && UPGRADE=(--upgrade)

lock() {
  local out=$1 python=$2
  shift 2
  uv pip compile --quiet --universal --generate-hashes --python-version "$python" \
    --custom-compile-command "scripts/lock-deps.sh" "${UPGRADE[@]}" "$@" -o "$out"
  echo "Wrote server/$out" >&2
}

lock requirements.lock 3.11 requirements.txt mesh_things/pyproject.toml --extra codec
lock api/requirements.lock 3.11 api/requirements.txt mesh_things/pyproject.toml --extra codec
lock monitor/requirements.lock 3.11 monitor/requirements.txt mesh_things/pyproject.toml --extra codec
lock quality_worker/requirements.lock 3.11 quality_worker/requirements.txt mesh_things/pyproject.toml
lock flink/requirements.lock 3.12 flink/requirements-flink.txt requirements.txt \
  mesh_things/pyproject.toml --extra codec
