# S3 access: the Parquet archive, its backends, and reading it

`s3_writer` archives the decoded and derived readings of the devices that opted in
(`archive_enabled`) as partitioned Parquet, independent of InfluxDB
(`writer/s3_writer.py`). This doc covers what is in the bucket, who holds which
credential, reading the archive, and running it on the bundled MinIO or an external
S3. How a device opts in and who may read the archive is in
[architecture.md#sinks-and-the-parquet-archive](architecture.md#sinks-and-the-parquet-archive);
the routes are in [api-reference.md#parquet-archive](api-reference.md#parquet-archive).

## What's in the bucket

- Bucket: `S3_WRITER__BUCKET` (`meshtastic-telemetry` by default).
- Key layout: `{S3_WRITER__PREFIX}/mesh_id={mesh_id}/dt=YYYY-MM-DD/hour=HH/data.parquet`
  - Hive-style partitioning, mesh-first so a key-prefix policy can scope to one mesh's
  data (see [Per-mesh scoped access](#per-mesh-scoped-access)). Hours are UTC, by
  arrival at the writer.
- **Only devices that opted in.** The writer follows `mesh.sink_config.v1` and drops
  everything else, including readings without a mesh; there is no `mesh_id=unknown`
  any more. Turning a device off keeps what was stored. A mesh's archive is deleted
  with its readings under the [data lifecycle](architecture.md#data-lifecycle).
- **Partition keys are not stored as columns.** `mesh_id` lives in the path and
  nowhere else. Storing it both places is what a Hive reader cannot merge: the path
  type and the column type disagree and the read fails outright. `node_id` is the
  opposite: a plain column, not a partition key, so filtering on it is an ordinary
  predicate.
- **One object per partition, rewritten in place.** `flush()` groups each batch by
  `mesh_id` and rolls it into that hour's single `data.parquet`: the object is read
  back, the new rows appended, and the whole thing written again. Parquet has no
  append, and S3 objects are immutable, so a rewrite is the only way to keep one file
  per partition. Rows are deduplicated on
  `(node_id, packet_id, rx_time, payload_kind, postprocessing_id)`, which makes a
  retried flush harmless.
- **Cost of that choice**: each flush costs a GET plus a PUT of the whole partition.
  An hour of one mesh's data is small, so this is cheap, but it is why
  `S3_WRITER__FLUSH_INTERVAL_S` defaults to 300 rather than 60.
- **File count** is bounded at 24 objects per mesh per day, regardless of device
  count or flush frequency. Measured on a 50-device mesh over a day, the older
  per-device, per-flush layout wrote 1200 objects and 3544 KiB where this writes 24
  objects and 87 KiB, and a single-device query got faster: a reader spends its time
  opening footers, and bigger files let dictionary encoding work.
- Schema (`writer/s3_writer.py`'s `SCHEMA`): `node_id`, `packet_id`, `portnum`,
  `rx_time`, `hop_start`, `channel_id`, `gateway_id`, `payload_kind`, `payload_json`
  (the decoded payload, JSON-encoded as a string, since its shape varies by
  `payload_kind`) and `postprocessing_id` (set on derived rows, which have no
  `packet_id` of their own; null on decoded ones). The schema is declared rather than
  inferred, so an all-null column in one batch cannot get a different type from the
  next. `node_id` is only unique within a mesh, so group on `(mesh_id, node_id)`
  across meshes (see
  [architecture.md#roles-registry-and-readings](architecture.md#roles-registry-and-readings)).
  `gateway_id` is the number it denotes (`431637602`, not `"!19ba4462"`), so it joins
  with `node_id`.

### Older layout generations

Nothing is deployed, so the API and the examples read only the current layout. A
bucket that ran earlier versions of the writer also holds:

1. `{prefix}/dt=.../hour=.../part-{uuid}.parquet`, with no `mesh_id=` at all.
2. `{prefix}/mesh_id=.../node_id=.../dt=.../hour=.../part-{uuid}.parquet`, the
   per-device layout, which also stored `mesh_id`/`node_id` as columns and, before
   the schema was declared, `gateway_id` as a string.
3. `{prefix}/mesh_id=unknown/...`, readings without a mesh.

DuckDB's globs in the examples skip them, but pandas and `pyarrow.dataset` discover
the whole prefix and fail on generation 2 (`Unable to merge: Field node_id has
incompatible types`). Delete them once, from the bundled MinIO:

```bash
docker compose exec minio sh -c '
  mc alias set local http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
  mc rm --recursive --force local/meshtastic-telemetry/telemetry/mesh_id=unknown/
  mc find local/meshtastic-telemetry/telemetry --path "*/node_id=*" --exec "mc rm {}"
  mc find local/meshtastic-telemetry/telemetry --name "part-*.parquet" --exec "mc rm {}"'
```

List before deleting by running the two `mc find` lines without `--exec`.

## Who holds which credential

| Holder | Credential | Can |
|---|---|---|
| `s3_writer` | `S3_WRITER__*`: the MinIO root account, or a writer IAM identity on AWS | create the bucket, read and write objects |
| `registry_data_lifecycle` | the same `S3_WRITER__*` | delete a mesh's partitions when its data is due |
| `readings_api` | `READINGS__ARCHIVE_*`: the `archive-reader` user on MinIO, or an IAM identity on AWS | list and read the bucket, and `AssumeRole` |
| a caller | temporary credentials from `POST /readings/archive/meshes/{id}/credentials` | list and read one mesh's prefix, until they expire |
| `readings_export_worker` | `READINGS__EXPORT_*`: the `export-writer` user on MinIO, or a writer IAM identity on AWS | upload under `exports/`, and nothing else |
| `readings_export_worker` | the same `READINGS__ARCHIVE_*` as readings | read archived partitions into a Parquet export |

readings never receives `S3_WRITER__*`: `compose/api.yml` gives it an explicit
environment list instead of the whole `.env`.

## Reading the archive

Through the API, as the mesh's owner (an operator) or a superuser. The details are in
[api-reference.md#parquet-archive](api-reference.md#parquet-archive), and
`server/mesh_things/examples/archive_duckdb.py`, `archive_pandas.py` and
`archive_download.py` run end to end:

- `GET /readings/archive/meshes/{id}`: the hourly files present.
- `POST /readings/archive/meshes/{id}/credentials`: temporary credentials scoped to the
  mesh. Hand them to DuckDB, pyarrow or boto3 and the prefix reads as a partitioned
  dataset.
- `GET /readings/archive/meshes/{id}/partitions/{day}/{hour}`: a `302` to a presigned
  link for one file.

**Presigned URLs lose the partitioning.** A presigned URL carries the object path plus a
query string. DuckDB reads it, but with `hive_partitioning=true` it fails with
`Referenced column "mesh_id" not found`. So links are for one known file, and
credentials are for querying the archive as a dataset.

With credentials, DuckDB (path-style for MinIO; drop `ENDPOINT` and `URL_STYLE` on AWS):

```sql
INSTALL httpfs; LOAD httpfs;
CREATE SECRET archive (TYPE s3, KEY_ID '...', SECRET '...', SESSION_TOKEN '...',
  REGION 'us-east-1', ENDPOINT 's3.api.yourdomain.com', URL_STYLE 'path');
SELECT node_id, payload_kind, dt, hour, count(*)
FROM read_parquet('s3://meshtastic-telemetry/telemetry/mesh_id=<mesh-id>/dt=*/hour=*/data.parquet',
                  hive_partitioning=true)
GROUP BY ALL ORDER BY dt, hour;
```

pyarrow, starting the dataset at the mesh's prefix, since the credential cannot list
above it:

```python
import pyarrow.dataset as ds, pyarrow.fs as fs

s3 = fs.S3FileSystem(access_key="...", secret_key="...", session_token="...",
                     region="us-east-1", endpoint_override="s3.api.yourdomain.com", scheme="https")
table = ds.dataset("meshtastic-telemetry/telemetry/mesh_id=<mesh-id>", filesystem=s3,
                   format="parquet", partitioning="hive").to_table(filter=ds.field("node_id") == 431637602)
```

## Per-mesh scoped access

The credentials readings issues carry an inline session policy, intersected with the
`archive-reader` identity's own read-only policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": ["s3:GetObject"],
     "Resource": ["arn:aws:s3:::meshtastic-telemetry/telemetry/mesh_id=<mesh-id>/*",
                  "arn:aws:s3:::meshtastic-telemetry/telemetry/mesh_id=<mesh-id>"]},
    {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": ["arn:aws:s3:::meshtastic-telemetry"],
     "Condition": {"StringLike": {"s3:prefix": ["telemetry/mesh_id=<mesh-id>/", "telemetry/mesh_id=<mesh-id>/*"]}}}
  ]
}
```

- **The `ListBucket` condition matters.** Without it, listing is either denied (so a
  reader cannot discover the partitions it may read) or, granted unconditionally, lets
  the credential enumerate every other mesh's key names.
- **The bare prefix is readable** because pyarrow probes it as an object before
  listing it as a directory, and a denied probe fails the whole read. Mesh ids are
  fixed-length UUIDs, so it matches only this mesh.
- **A mesh is as narrow as this gets.** `node_id` is a column rather than a path
  segment, so storage cannot scope a credential to one device. Since only opted-in
  devices are written, the credential reads exactly the devices the owner chose to
  archive.

Checked against the bundled MinIO: a credential lists and reads its mesh, and gets
`AccessDenied` listing the bucket root, listing another mesh's prefix and reading
another mesh's object. A presigned link downloads its file, and the same link with
another hour in the path answers `403`.

## Bundled MinIO

The `minio` profile runs it (`COMPOSE_PROFILES=full,minio`). Its root account is the
writer's own credential (`MINIO_ROOT_USER: ${S3_WRITER__ACCESS_KEY}`), which is why
nothing else gets it.

- **`minio_init`** (one-shot, idempotent) creates the bucket, a read-only
  `archive-reader` policy on it, and the user `READINGS__ARCHIVE_ACCESS_KEY` with that
  policy. MinIO's STS lets that user call `AssumeRole` with no further permission; the
  `RoleArn` boto3 requires is ignored.
- **`CADDY_S3_ADDRESS`** proxies the S3 API (`minio:9000`) for callers outside the
  stack, with no basic auth: S3 signs every request, and the signature covers the
  `Host` header, which Caddy passes through unchanged. Set it to its own hostname in
  production and point `READINGS__ARCHIVE_PUBLIC_ENDPOINT_URL` at it, since presigned
  links and returned credentials name that endpoint. In dev the overlay publishes
  `9000` directly, and `http://localhost:9000` is the public endpoint.
- **Exports**: `minio_init` also creates the user `READINGS__EXPORT_ACCESS_KEY` with an
  `export-writer` policy (`PutObject`, `AbortMultipartUpload` and
  `ListMultipartUploadParts` on `exports/*`), and a lifecycle rule expiring `exports/`
  after one day. Without `READINGS__EXPORT_ACCESS_KEY` it skips the user and the worker
  refuses to start.
- The MinIO console stays an admin UI behind basic auth on `CADDY_MINIO_ADDRESS`.

To give someone a standing read-only credential outside the API, add another user the
way `minio_init` does and attach the `archive-reader` policy, or a narrower one with the
shape above.

## External S3

Leave `minio` out of `COMPOSE_PROFILES`. `s3_writer` no longer waits for it
(`required: false`), and the Caddy S3 site is unused.

### AWS

1. A bucket, and a **writer** IAM identity for `S3_WRITER__*`. Registry uses the same
   credential to delete a mesh's data, so it needs `DeleteObject` too:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {"Effect": "Allow", "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"], "Resource": "arn:aws:s3:::your-bucket/*"},
       {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": "arn:aws:s3:::your-bucket"}
     ]
   }
   ```
   Set `S3_WRITER__ENDPOINT_URL=` (blank) and `S3_WRITER__REGION` to the bucket's
   region; without it boto3 raises `NoRegionError`.
2. An **archive reader role**, `READINGS__ARCHIVE_ROLE_ARN`, with the read-only
   policy (`GetObject` on `your-bucket/*`, `ListBucket` on `your-bucket`), a
   `MaxSessionDuration` of at least `READINGS__ARCHIVE_CREDENTIAL_TTL_S`, and a trust
   policy for the identity readings runs as:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {"Effect": "Allow", "Principal": {"AWS": "arn:aws:iam::<account>:user/meshtastic-readings"}, "Action": "sts:AssumeRole"}
     ]
   }
   ```
3. That identity (`READINGS__ARCHIVE_ACCESS_KEY`/`SECRET_KEY`) is allowed
   `sts:AssumeRole` on the role and nothing else. Set `READINGS__ARCHIVE_STS=aws`, both
   `READINGS__ARCHIVE_*ENDPOINT_URL` blank, and `READINGS__ARCHIVE_REGION` to the
   bucket's region. Credentials are then issued by the regional STS endpoint and come
   back with `endpoint: null`.

4. For [exports](architecture.md#exports), an **export writer** identity for
   `READINGS__EXPORT_*`, held only by `readings_export_worker`:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {"Effect": "Allow", "Action": ["s3:PutObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"],
        "Resource": "arn:aws:s3:::your-bucket/exports/*"}
     ]
   }
   ```
   readings signs export links with its own identity, so that identity also needs
   `s3:GetObject` on `your-bucket/exports/*`. Add a lifecycle rule expiring the
   `exports/` prefix after one day.

The `aws` mode is covered by unit tests only: it has not been run against a real AWS
account yet.

### Other providers

Set both `READINGS__ARCHIVE_*ENDPOINT_URL` to the provider's endpoint and give readings a
read-only key for the bucket. If the provider offers STS `AssumeRole` compatible with
MinIO's, `READINGS__ARCHIVE_STS=minio` may work; otherwise leave it blank. Then the
credentials route answers `404`, and the manifest and single-file downloads still work. For exports, create
an export writer limited to `exports/` as on AWS, and a lifecycle rule expiring `exports/`
after a day if the provider supports one; otherwise delete old exports by hand.
