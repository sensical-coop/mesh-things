#!/bin/bash
# Fail when the client's OpenAPI snapshot changed against BASE but the mesh-things
# version was not raised.
set -euo pipefail
cd "$(dirname "$0")/.."

BASE=${1:-origin/main}
SNAPSHOT=server/mesh_things/src/mesh_things/client/openapi.json
VERSION_FILE=server/mesh_things/src/mesh_things/__init__.py

version_of() { sed -n 's/^__version__ = "\(.*\)"$/\1/p'; }

if ! git cat-file -e "$BASE:$SNAPSHOT" 2>/dev/null; then
  echo "No snapshot on $BASE yet, nothing to compare."
  exit 0
fi
if [ "$(git rev-parse "$BASE:$SNAPSHOT")" = "$(git hash-object "$SNAPSHOT")" ]; then
  echo "The API schema is unchanged against $BASE."
  exit 0
fi

old=$(git show "$BASE:$VERSION_FILE" | version_of)
new=$(version_of < "$VERSION_FILE")
if [ "$old" = "$new" ] || [ "$(printf '%s\n%s\n' "$old" "$new" | sort -V | tail -1)" != "$new" ]; then
  echo "::error::The API schema changed, so raise __version__ in $VERSION_FILE above $old (it is $new), then rerun scripts/regen-client-schema.sh."
  exit 1
fi
echo "The API schema changed and the version went from $old to $new."
