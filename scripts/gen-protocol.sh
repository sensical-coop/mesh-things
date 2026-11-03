#!/bin/bash
# Generate one Meshtastic protocol version's protobuf modules into mesh_things.
#
#   scripts/gen-protocol.sh v2.7.26 v2_7
#
# The protos come from a ref of the Meshtastic protobufs repository, read from
# $PROTOBUFS_REPO (default ../protobufs, next to this checkout) or cloned from GitHub
# when that is missing. Every version gets its own proto package and file paths, so
# several sets load side by side in one descriptor pool.
#
# protoc 29 writes code that needs protobuf 5.29 or later at runtime, which is the
# package's floor and what the Flink image runs.
set -euo pipefail
cd "$(dirname "$0")/.."

REF=${1:?usage: gen-protocol.sh <git-ref> <slug>}
SLUG=${2:?usage: gen-protocol.sh <git-ref> <slug>}
[[ $SLUG =~ ^v[0-9]+_[0-9]+$ ]] || { echo "slug must look like v2_7" >&2; exit 1; }
GRPCIO_TOOLS=1.71.0
UPSTREAM=https://github.com/meshtastic/protobufs.git

OUT=server/mesh_things/src/mesh_things/protocols/$SLUG
PACKAGE=mesh_things.protocols.$SLUG
PROTO_DIR=mesh_things/protocols/$SLUG

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

REPO=${PROTOBUFS_REPO:-../protobufs}
if [ ! -d "$REPO/.git" ]; then
  REPO=$WORK/protobufs
  git clone --quiet --filter=blob:none "$UPSTREAM" "$REPO"
fi
COMMIT=$(git -C "$REPO" rev-parse --verify "$REF^{commit}")

mkdir -p "$WORK/in/$PROTO_DIR" "$WORK/out"
git -C "$REPO" archive "$COMMIT" meshtastic | tar -x -C "$WORK"
cp "$WORK"/meshtastic/*.proto "$WORK/in/$PROTO_DIR/"

# nanopb's options only shape the firmware's C code, and its extension of FieldOptions
# would clash between versions, so it is left out.
sed -i -E \
  -e "s/^package meshtastic;/package $PACKAGE;/" \
  -e "s#^import \"meshtastic/#import \"$PROTO_DIR/#" \
  -e '/^import "nanopb.proto";/d' \
  -e '/^option \(nanopb_fileopt\)/d' \
  -e 's/ \[\(nanopb\)[^]]*\]//' \
  "$WORK/in/$PROTO_DIR"/*.proto
if grep -n '(nanopb' "$WORK/in/$PROTO_DIR"/*.proto; then
  echo "nanopb options left after stripping; extend the sed above" >&2
  exit 1
fi

docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$WORK:/w" -w /w python:3.12-slim sh -c "
  pip install --quiet --disable-pip-version-check --user grpcio-tools==$GRPCIO_TOOLS &&
  python -m grpc_tools.protoc -I in --python_out=out --pyi_out=out in/$PROTO_DIR/*.proto"

rm -f "$OUT"/*_pb2.py "$OUT"/*_pb2.pyi "$OUT/_source.py"
mkdir -p "$OUT"
cp "$WORK/out/$PROTO_DIR"/*_pb2.py "$WORK/out/$PROTO_DIR"/*_pb2.pyi "$OUT/"
cat > "$OUT/_source.py" <<EOF
"""The protobufs ref this set was generated from, by scripts/gen-protocol.sh."""
REF = "$REF"
COMMIT = "$COMMIT"
EOF
echo "Wrote $OUT from $REF ($COMMIT)" >&2
