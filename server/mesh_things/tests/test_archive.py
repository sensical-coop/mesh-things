import pytest

pytest.importorskip("pyarrow")

from mesh_things import archive  # noqa: E402


def test_open_dataset_asks_for_credentials(monkeypatch):
    calls = []

    class Api:
        def call(self, operation_id, *args):
            calls.append((operation_id, args))
            return {"bucket": "b", "prefix": "p/"}

    monkeypatch.setattr(archive, "dataset", lambda credentials: credentials)
    assert archive.open_dataset(Api(), "m") == {"bucket": "b", "prefix": "p/"}
    assert calls == [("readings_archive_meshes_credentials_create", ("m",))]
