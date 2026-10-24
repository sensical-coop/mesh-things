#!/bin/bash
# Regenerate the OpenAPI snapshot the mesh-things client is bound to, and the type
# stub that lists the methods the client builds from it.
#
# The schema does not depend on the environment, so the image runs with a fixed
# minimal one rather than .env. `servers` is dropped so no deployment's hostname
# ships to PyPI.
set -euo pipefail
cd "$(dirname "$0")/.."

SRC=meshtastic_things/mesh_things/src
OUT=$SRC/mesh_things/client/openapi.json
STUB=$SRC/mesh_things/client/_namespaces.pyi

docker compose -f docker-compose.yml build registry_api >&2
docker run --rm \
  -e APP_ROLE=registry \
  -e DJANGO_SETTINGS_MODULE=api_project.settings.dev \
  -e REGISTRY__SECRET_KEY=schema-only \
  meshtastic-things/api:latest \
  sh -c 'python manage.py spectacular --urlconf api_project.urls_all --format openapi-json \
           --validate --fail-on-warn --file /tmp/schema.json >&2 &&
         python -c "import json; s = json.load(open(\"/tmp/schema.json\")); s.pop(\"servers\", None); print(json.dumps(s, indent=2, ensure_ascii=False))"' \
  > "$OUT.tmp"
mv "$OUT.tmp" "$OUT"
echo "Wrote $OUT" >&2

# The image's own copy of the package predates the snapshot just written, so the
# working tree's source is mounted over it.
docker run --rm -v "$(pwd)/$SRC:/src:ro" -e PYTHONPATH=/src \
  meshtastic-things/api:latest python -m mesh_things.client._stubgen > "$STUB.tmp"
mv "$STUB.tmp" "$STUB"
echo "Wrote $STUB" >&2
