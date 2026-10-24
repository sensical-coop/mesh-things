# The `mesh-things` Python package

`mesh-things` is the Python client for this API. It also holds the vocabulary, node-id
and protocol helpers that the API, the pipeline and the workers run on, so a client
and the server share one implementation. The package lives in
`server/mesh_things/` and is published to PyPI. Its own
[README](../server/mesh_things/README.md) is the user guide; this page covers
how it is kept in step with the API and how it is released.

## Using it

```bash
pip install mesh-things                    # from PyPI
pip install -e "server/mesh_things[codec,pandas,archive]"   # from this repository
```

```python
from mesh_things.client import MeshThings

api = MeshThings("https://api.yourdomain.com", api_key="...")
api.meshes.list()
api.readings.devices_latest_get(device_uuid)
```

- **Connection.** `MESH_THINGS_URL` and `MESH_THINGS_API_KEY` stand in for the
  arguments. There is no default URL. Pass `api_key=""` to send no key even when the
  variable is set.
- **Names.** There is one namespace per API tag. A method is its operationId without the
  tag prefix, with `retrieve` read as `get` and `destroy` as `delete`.
- **Arguments.** Path parameters are positional, in path order. Query parameters and
  `body` are keywords.
- **Async.** `AsyncMeshThings` offers the same methods as coroutines.

| Extra | Adds |
|---|---|
| none | the client (`httpx`) and the vocabulary |
| `[protobuf]` | the pinned `meshtastic` package: telemetry catalog, portnum names, `mesh_things.protobuf` |
| `[codec]` | `cryptography` on top: MQTT envelope parsing and channel encryption |
| `[pandas]` | `mesh_things.pandas`: readings, exports and archive rows as DataFrames |
| `[archive]` | `pyarrow` on top: `mesh_things.archive`, the Parquet archive read straight from S3 |

The examples in `server/mesh_things/examples/`, shipped in the sdist, use the client, so they double as
worked examples for each endpoint.

## How it stays in step with the API

Every method is generated from an OpenAPI snapshot shipped inside the package,
`mesh_things/client/openapi.json`. None is written by hand, so a new endpoint, parameter
or docstring reaches the client by regenerating the snapshot alone.

```bash
scripts/regen-client-schema.sh   # the snapshot, and the type stub _namespaces.pyi
```

The script builds the `registry_api` image and runs `manage.py spectacular` with
`--validate --fail-on-warn`. It runs with a fixed environment, since the schema does not
depend on `.env`, and drops `servers`, so no hostname ships to PyPI.

Any change to the schema also raises `__version__` in
`mesh_things/src/mesh_things/__init__.py`, docstrings included. That one version is:
- the package's version;
- the schema's `info.version`;
- the `API-Version` header on every response.

A client warns once (`MeshThingsVersionWarning`) when the API reports a different one.

Three checks enforce this:

| Check | Fails when |
|---|---|
| `client-schema` job in `pr-checks.yml` | the committed snapshot or stub differs from a fresh regeneration |
| `scripts/check-client-version.sh` (same job) | the snapshot changed against the base branch but the version did not go up |
| package tests (`root-tests`) | the snapshot's version is not `__version__`, an operation has no valid unique method, or hand-written code names an operation that no longer exists |

## Releasing

1. Raise `__version__` if it has not been raised since the last release, run
   `scripts/regen-client-schema.sh`, and merge.
2. Tag the merge commit `mesh-things-v<version>` and push the tag.
   `.github/workflows/release-mesh-things.yml` then:
   - runs the PR checks;
   - checks that the tag matches `__version__`;
   - builds the sdist and wheel;
   - tests the installed wheel from outside the checkout;
   - publishes with PyPI Trusted Publishing.

**One-time setup on PyPI.** Before the first release, add a pending publisher for the
project `mesh-things` (pypi.org, Your account, Publishing). Give it:
- owner `sensical-coop`;
- repository `mesh-things`;
- workflow `release-mesh-things.yml`;
- environment `pypi`.

Also create a `pypi` environment in the GitHub repository's settings. No token is
stored anywhere.

Release whenever a deploy changes the schema, so the newest release always matches the
production API.
