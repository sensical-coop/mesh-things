"""Exports: who may request one, the job's life in Redis, and the zip the worker builds."""
import io
import zipfile
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from botocore.exceptions import EndpointConnectionError
from django.core import mail
from django.test import override_settings

from readings import archive, export_worker, exports
from registry.models import Mesh, OwnerRole

from .test_archive import ARCHIVE, ArchiveTestCase

EXPORTS = {**ARCHIVE, "EXPORT_ACCESS_KEY": "export-writer", "EXPORT_SECRET_KEY": "export-writer-secret", "EXPORT_MAX_DAYS": 31}
HOUR = {"dt": date(2026, 9, 1), "hour": 13, "size": 3, "last_modified": datetime(2026, 9, 1, 14, tzinfo=timezone.utc)}
ENVIRONMENT = {
    "tags": [],
    "fields": ["temperature"],
    "rows": [{"time": "2026-09-01T13:05:00Z", "node_id": 7, "temperature": 21.5}],
}


@override_settings(**EXPORTS)
class ExportTestCase(ArchiveTestCase):
    def setUp(self):
        super().setUp()
        exports._redis = None
        self.member = self.owner("member@example.com")
        self.member_mesh = Mesh.objects.create(owner=self.member, channel_id="LongFast", psk_b64="AQ==")

    def url(self, suffix="", mesh=None):
        base = f"/readings/meshes/{(mesh or self.member_mesh).id}/exports"
        return f"{base}/{suffix}" if suffix else base

    def request_export(self, owner=None, mesh=None, expect=202, **body):
        body = {"format": "csv", "start": "2026-09-01", "stop": "2026-09-02", **body}
        response = self.client.post(self.url(mesh=mesh), body, format="json", **self.auth(owner or self.member))
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()

    def fake_writer(self):
        s3 = MagicMock()
        s3.create_multipart_upload.return_value = {"UploadId": "u1"}
        self.uploaded = []
        s3.upload_part.side_effect = lambda **kw: self.uploaded.append(kw["Body"]) or {"ETag": f"e{kw['PartNumber']}"}
        archive._clients[("s3", "http://minio:9000", "export-writer")] = s3
        return s3

    def zip_written(self) -> zipfile.ZipFile:
        return zipfile.ZipFile(io.BytesIO(b"".join(self.uploaded)))


class ExportRequestTests(ExportTestCase):
    def test_the_owner_queues_a_csv_export(self):
        job = self.request_export(node_ids=[10, 7])

        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["days_total"], 2)
        self.assertEqual(job["node_ids"], [7, 10])
        self.assertIsNone(job["url"])
        self.assertEqual(exports.store().lrange("exports:queue", 0, -1), [job["id"]])

    def test_repeating_the_request_returns_the_same_export(self):
        first = self.request_export()

        second = self.request_export(expect=200)

        self.assertEqual(second["id"], first["id"])
        self.assertEqual(exports.store().llen("exports:queue"), 1)

    def test_another_export_waits_for_the_first(self):
        self.request_export()

        self.request_export(stop="2026-09-03", expect=429)

    def test_a_finished_export_frees_the_owner_for_another(self):
        job = exports.get(self.request_export()["id"])
        exports.fail(job, "boom")

        self.request_export(stop="2026-09-03")

    def test_a_public_mesh_is_exported_only_by_its_owner(self):
        self.member_mesh.is_public = True
        self.member_mesh.save()

        self.request_export(owner=self.operator, expect=404)

    def test_a_superuser_exports_any_mesh(self):
        admin = self.owner("admin@example.com", is_superuser=True)

        self.request_export(owner=admin)

    @override_settings(ARCHIVE_BUCKET="")
    def test_an_instance_without_a_bucket_has_no_exports(self):
        self.request_export(expect=404)

    def test_invalid_ranges_are_refused(self):
        self.request_export(start="2026-09-02", stop="2026-09-01", expect=400)
        self.request_export(start="2026-09-01", stop="2026-10-15", expect=400)

    def test_parquet_needs_the_operator_role(self):
        self.request_export(format="parquet", expect=403)

    @patch.object(archive, "list_partitions", return_value=[HOUR])
    def test_an_operator_exports_parquet_of_the_whole_mesh(self, _):
        self.request_export(owner=self.operator, mesh=self.mesh, format="parquet")

        self.request_export(owner=self.operator, mesh=self.mesh, format="parquet", node_ids=[7], expect=400)

    @patch.object(archive, "list_partitions", return_value=[])
    def test_a_parquet_range_with_nothing_archived_is_not_found(self, _):
        self.request_export(owner=self.operator, mesh=self.mesh, format="parquet", expect=404)


class ExportStatusTests(ExportTestCase):
    def test_a_ready_export_carries_its_download_link(self):
        job = exports.get(self.request_export()["id"])
        exports.finish(job, size=1234)

        with patch.object(archive, "presigned_url", return_value="https://s3.example.org/x") as presigned:
            body = self.client.get(self.url(job["id"]), **self.auth(self.member)).json()

        self.assertEqual((body["status"], body["size"], body["url"]), ("ready", 1234, "https://s3.example.org/x"))
        key, = presigned.call_args.args
        self.assertEqual(key, f"exports/{self.member_mesh.id}/{job['id']}.zip")
        self.assertGreater(presigned.call_args.kwargs["expires_in"], 23 * 3600)
        self.assertTrue(presigned.call_args.kwargs["filename"].endswith("_2026-09-01_2026-09-02_csv.zip"))

    def test_nobody_else_reads_an_export(self):
        job = self.request_export()
        admin = self.owner("admin@example.com", is_superuser=True)

        self.assertEqual(self.client.get(self.url(job["id"]), **self.auth(admin)).status_code, 404)

    def test_the_list_holds_the_callers_exports_of_the_mesh(self):
        job = self.request_export()
        admin = self.owner("admin@example.com", is_superuser=True)
        self.request_export(owner=admin, mesh=self.mesh)

        body = self.client.get(self.url(), **self.auth(self.member)).json()

        self.assertEqual([e["id"] for e in body], [job["id"]])


class ExportHistoryTests(ExportTestCase):
    def test_every_mesh_is_listed_together(self):
        member_job = self.request_export()
        exports.fail(exports.get(member_job["id"]), "boom")
        other_mesh = Mesh.objects.create(owner=self.member, channel_id="Other", psk_b64="AQ==")
        other_job = self.request_export(mesh=other_mesh)

        body = self.client.get("/readings/exports", **self.auth(self.member)).json()

        self.assertEqual([e["id"] for e in body], [other_job["id"], member_job["id"]])

    def test_a_ready_export_expires_with_its_file_and_stays_listed(self):
        job = exports.finish(exports.get(self.request_export()["id"]), size=10)
        exports._update(job["id"], expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))

        body = self.client.get(self.url(job["id"]), **self.auth(self.member)).json()

        self.assertEqual((body["status"], body["url"]), ("expired", None))
        self.assertEqual([e["status"] for e in self.client.get("/readings/exports", **self.auth(self.member)).json()], ["expired"])
        self.assertNotEqual(self.request_export()["id"], job["id"])

    @override_settings(ARCHIVE_BUCKET="")
    def test_an_instance_without_a_bucket_lists_nothing(self):
        self.assertEqual(self.client.get("/readings/exports", **self.auth(self.member)).json(), [])


class ExportWorkerTests(ExportTestCase):
    def take(self, **body):
        self.request_export(**body)
        return exports.take(timeout=1)

    def test_a_csv_export_is_a_file_per_measurement_and_day(self):
        s3 = self.fake_writer()
        influx = MagicMock()
        influx.day_rows.side_effect = lambda mesh_id, day, node_ids: {"environment_metrics": ENVIRONMENT} if day.day == 1 else {}
        catalog = {
            "environment_metrics.temperature": {
                "payload_kind": "telemetry:environment_metrics", "field_name": "temperature", "unit": "degC",
                "description": "Temperature measured", "quantity_kind": "physical_property", "vocabulary_uri": None,
            }
        }
        job = self.take()
        self.assertEqual(job["status"], "running")

        with patch.object(export_worker, "get_client", return_value=influx), patch.object(
            export_worker, "get_measurement_types", return_value=catalog
        ):
            job = export_worker.run(job)

        self.assertEqual((job["status"], job["days_done"]), ("ready", 2))
        self.assertEqual(job["size"], len(b"".join(self.uploaded)))
        s3.complete_multipart_upload.assert_called_once()
        with self.zip_written() as zf:
            self.assertEqual(zf.namelist(), ["2026-09-01/environment_metrics.csv", "channels.csv"])
            self.assertEqual(
                zf.read("2026-09-01/environment_metrics.csv").decode(), "time,node_id,temperature\n2026-09-01T13:05:00Z,7,21.5\n"
            )
            self.assertEqual(
                zf.read("channels.csv").decode().splitlines(),
                [
                    "channel,name,unit,description,telemetry_variant,derived,quantity_kind,vocabulary_uri",
                    "environment_metrics.temperature,temperature,degC,Temperature measured,"
                    "telemetry:environment_metrics,false,physical_property,",
                ],
            )
        self.assertEqual(exports.store().llen("exports:processing"), 0)
        self.request_export(stop="2026-09-03")

    def test_a_range_without_readings_fails_and_discards_the_upload(self):
        s3 = self.fake_writer()
        influx = MagicMock()
        influx.day_rows.return_value = {}
        job = self.take()

        with patch.object(export_worker, "get_client", return_value=influx), patch.object(
            export_worker, "get_measurement_types", return_value={}
        ):
            job = export_worker.run(job)

        self.assertEqual((job["status"], job["error"]), ("failed", "No readings in that range"))
        s3.abort_multipart_upload.assert_called_once()
        s3.complete_multipart_upload.assert_not_called()

    @patch.object(archive, "read_object", side_effect=lambda key: key.encode())
    @patch.object(archive, "list_partitions", return_value=[HOUR, dict(HOUR, dt=date(2026, 9, 2), hour=5)])
    def test_a_parquet_export_holds_the_archive_files(self, *_):
        self.fake_writer()
        self.request_export(owner=self.operator, mesh=self.mesh, format="parquet")

        job = export_worker.run(exports.take(timeout=1))

        self.assertEqual((job["status"], job["days_done"]), ("ready", 2))
        with self.zip_written() as zf:
            self.assertEqual(zf.namelist(), ["2026-09-01/2026-09-01_13.parquet", "2026-09-02/2026-09-02_05.parquet"])

    def test_unreachable_storage_fails_the_export(self):
        s3 = self.fake_writer()
        s3.create_multipart_upload.side_effect = EndpointConnectionError(endpoint_url="http://minio:9000")

        with patch.object(export_worker, "get_client"), patch.object(export_worker, "get_measurement_types"):
            job = export_worker.run(self.take())

        self.assertEqual((job["status"], job["error"]), ("failed", "The archive storage could not be reached"))

    def test_large_exports_are_uploaded_in_parts(self):
        s3 = self.fake_writer()
        with patch.object(exports, "PART_SIZE", 10):
            upload = exports.MultipartUpload(s3, "bucket", "exports/x.zip")
            upload.write(b"a" * 25)
            size = upload.complete()

        self.assertEqual(size, 25)
        self.assertEqual(self.uploaded, [b"a" * 10, b"a" * 10, b"a" * 5])
        parts = s3.complete_multipart_upload.call_args.kwargs["MultipartUpload"]["Parts"]
        self.assertEqual([p["PartNumber"] for p in parts], [1, 2, 3])

    def test_a_job_whose_worker_stopped_is_failed(self):
        job = self.take()
        exports._update(job["id"], heartbeat_at=datetime.now(timezone.utc) - timedelta(hours=1))

        export_worker.recover()
        export_worker.recover()

        job = exports.get(job["id"])
        self.assertEqual(job["status"], "failed")
        self.assertEqual(exports.store().llen("exports:processing"), 0)
        self.request_export(stop="2026-09-03")

    def test_a_running_job_is_left_alone(self):
        job = self.take()

        export_worker.recover()

        self.assertEqual(exports.get(job["id"])["status"], "running")


@override_settings(
    EXPORT_EMAIL=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@example.com",
)
class ExportEmailTests(ExportTestCase):
    def test_the_owner_is_emailed_the_link_when_ready(self):
        job = exports.finish(exports.get(self.request_export()["id"]), size=2048)

        link = "https://s3.example.org/x.zip?X-Amz-Date=1&X-Amz-Signature=2"
        with patch.object(archive, "presigned_url", return_value=link):
            export_worker.notify(job)

        [message] = mail.outbox
        self.assertEqual(message.to, ["member@example.com"])
        self.assertEqual(message.subject, "Your export is ready")
        self.assertIn(link, message.body)
        [(html, mimetype)] = message.alternatives
        self.assertEqual(mimetype, "text/html")
        self.assertIn('href="https://s3.example.org/x.zip?X-Amz-Date=1&amp;X-Amz-Signature=2"', html)
        self.assertIn("2.0 KB", html)

    def test_the_owner_is_emailed_why_it_failed(self):
        job = exports.fail(exports.get(self.request_export()["id"]), "No readings in that range")

        export_worker.notify(job)

        [message] = mail.outbox
        self.assertEqual(message.subject, "Your export failed")
        self.assertIn("No readings in that range", message.body)
        self.assertIn("No readings in that range", message.alternatives[0][0])

    def test_a_mail_failure_does_not_fail_the_export(self):
        job = exports.fail(exports.get(self.request_export()["id"]), "boom")

        with patch.object(export_worker.EmailMultiAlternatives, "send", side_effect=OSError("smtp down")):
            export_worker.notify(job)


class ChannelsCsvTests(ExportTestCase):
    def test_derived_and_device_channels_carry_no_telemetry_variant(self):
        catalog = {"derived.dew_point": {"payload_kind": "computed:derived", "field_name": "dew_point", "unit": "degC"}}

        rows = exports.channels_csv({"derived.dew_point", "nodeinfo.user_id"}, catalog).decode().splitlines()

        self.assertEqual(rows[1], "derived.dew_point,dew_point,degC,,,true,,")
        self.assertEqual(rows[2], "nodeinfo.user_id,user_id,,,,false,,")
