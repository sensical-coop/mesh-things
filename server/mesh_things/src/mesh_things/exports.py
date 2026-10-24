"""The formats and lifecycle of a mesh's data export."""

CSV = "csv"
PARQUET = "parquet"
FORMATS = (CSV, PARQUET)

QUEUED = "queued"
RUNNING = "running"
READY = "ready"
FAILED = "failed"
EXPIRED = "expired"
STATUSES = (QUEUED, RUNNING, READY, FAILED, EXPIRED)
ACTIVE = (QUEUED, RUNNING)
