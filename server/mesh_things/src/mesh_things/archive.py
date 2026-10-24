"""A mesh's Parquet archive, read straight from S3. Needs mesh-things[archive]."""
try:
    import pyarrow.dataset as ds
    import pyarrow.fs as fs
except ImportError as error:
    raise ImportError("mesh_things.archive needs pyarrow: pip install 'mesh-things[archive]'") from error

from mesh_things.client._helpers import ARCHIVE_CREDENTIALS


def dataset(credentials: dict) -> ds.Dataset:
    """The archive the temporary `credentials` grant, as a Hive-partitioned dataset.

    `dt` and `hour` come back as columns and prune whole files when filtered on.
    """
    options = {
        "access_key": credentials["access_key_id"],
        "secret_key": credentials["secret_access_key"],
        "session_token": credentials["session_token"],
        "region": credentials["region"],
    }
    # A null endpoint means AWS, which pyarrow reaches on its own.
    if credentials["endpoint"]:
        scheme, host = credentials["endpoint"].split("://", 1)
        options.update({"endpoint_override": host, "scheme": scheme})
    s3 = fs.S3FileSystem(**options)
    # The credentials can list this mesh's prefix only, so the dataset starts there.
    root = f"{credentials['bucket']}/{credentials['prefix'].rstrip('/')}"
    return ds.dataset(root, filesystem=s3, format="parquet", partitioning="hive")


def open_dataset(api, mesh_id: str) -> ds.Dataset:
    """Request temporary credentials for a mesh's archive and open it. Operators only."""
    return dataset(api.call(ARCHIVE_CREDENTIALS, mesh_id))
