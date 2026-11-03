import pytest

pytest.importorskip("pyarrow")

from mesh_things import archive  # noqa: E402


def test_open_dataset_asks_for_credentials(monkeypatch):
    calls = []

    class Api:
        allow_insecure_http = False

        def call(self, operation_id, *args):
            calls.append((operation_id, args))
            return {"bucket": "b", "prefix": "p/"}

    monkeypatch.setattr(archive, "dataset", lambda credentials, **_: credentials)
    assert archive.open_dataset(Api(), "m") == {"bucket": "b", "prefix": "p/"}
    assert calls == [("readings_archive_meshes_credentials_create", ("m",))]


def test_s3_credentials_are_not_sent_over_plain_http_to_another_host(monkeypatch):
    from mesh_things.client import InsecureTransport

    monkeypatch.delenv("MESH_THINGS_ALLOW_HTTP", raising=False)
    credentials = {
        "access_key_id": "a", "secret_access_key": "s", "session_token": "t", "region": "us-east-1",
        "endpoint": "http://minio.internal:9000", "bucket": "b", "prefix": "p/",
    }
    with pytest.raises(InsecureTransport, match="minio.internal"):
        archive.dataset(credentials)
