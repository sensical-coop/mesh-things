"""The archive routes: who reaches a mesh's archive, and what the storage is asked for."""
import io
import json
import zipfile
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from botocore.exceptions import EndpointConnectionError
from django.core.cache import cache
from django.middleware.csrf import _get_new_csrf_string
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient, APITestCase

from readings import archive
from registry.auth import hash_api_key
from registry.models import Mesh, Owner, OwnerRole

ARCHIVE = {
    "ARCHIVE_BUCKET": "meshtastic-telemetry",
    "ARCHIVE_PREFIX": "telemetry",
    "ARCHIVE_ENDPOINT_URL": "http://minio:9000",
    "ARCHIVE_PUBLIC_ENDPOINT_URL": "https://s3.example.org",
    "ARCHIVE_REGION": "",
    "ARCHIVE_STS": "minio",
    "ARCHIVE_ROLE_ARN": "",
    "ARCHIVE_CREDENTIAL_TTL_S": 3600,
    "ARCHIVE_ACCESS_KEY": "archive-reader",
    "ARCHIVE_SECRET_KEY": "archive-reader-secret",
}
PARTITION = {"dt": date(2026, 9, 1), "hour": 13, "size": 2048, "last_modified": datetime(2026, 9, 1, 14, tzinfo=timezone.utc)}


@override_settings(ROOT_URLCONF="api_project.urls_readings", **ARCHIVE)
class ArchiveTestCase(APITestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        archive._clients.clear()
        self.operator = self.owner("operator@example.com", role=OwnerRole.OPERATOR)
        self.mesh = Mesh.objects.create(owner=self.operator, channel_id="LongFast", psk_b64="AQ==")

    def tearDown(self):
        archive._clients.clear()
        cache.clear()
        super().tearDown()

    @staticmethod
    def owner(email, role=OwnerRole.MEMBER, is_superuser=False):
        return Owner.objects.create_user(
            email=email, name=email, api_key_hash=hash_api_key(email), role=role, is_superuser=is_superuser
        )

    @staticmethod
    def auth(owner):
        return {"HTTP_AUTHORIZATION": f"Bearer {owner.email}"}

    def url(self, suffix="", mesh=None):
        base = f"/readings/archive/meshes/{(mesh or self.mesh).id}"
        return f"{base}/{suffix}" if suffix else base


class ArchiveAccessTests(ArchiveTestCase):
    @patch.object(archive, "list_partitions", return_value=[PARTITION])
    def test_the_owner_lists_the_partitions(self, list_partitions):
        response = self.client.get(self.url(), {"start": "2026-09-01"}, **self.auth(self.operator))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["prefix"], f"telemetry/mesh_id={self.mesh.id}/")
        self.assertEqual(body["partitions"], [{"dt": "2026-09-01", "hour": 13, "size": 2048, "last_modified": "2026-09-01T14:00:00Z"}])
        self.assertEqual(list_partitions.call_args.args[1:], (date(2026, 9, 1), None))

    @patch.object(archive, "list_partitions", return_value=[])
    def test_a_superuser_reaches_any_mesh(self, _):
        admin = self.owner("admin@example.com", is_superuser=True)

        self.assertEqual(self.client.get(self.url(), **self.auth(admin)).status_code, 200)

    @patch.object(archive, "list_partitions", return_value=[])
    def test_nobody_else_learns_the_mesh_exists(self, list_partitions):
        member_mesh_owner = self.owner("member@example.com")
        member_mesh = Mesh.objects.create(owner=member_mesh_owner, channel_id="LongFast", psk_b64="AQ==")
        other_operator = self.owner("other@example.com", role=OwnerRole.OPERATOR)
        self.mesh.is_public = True
        self.mesh.save()

        cases = [
            (member_mesh_owner, member_mesh),  # owns it, but is not an operator
            (other_operator, self.mesh),  # the mesh is public, but not theirs
        ]
        for caller, mesh in cases:
            with self.subTest(caller=caller.email):
                for suffix in ("", "partitions/2026-09-01/13"):
                    self.assertEqual(self.client.get(self.url(suffix, mesh), **self.auth(caller)).status_code, 404)
                self.assertEqual(self.client.post(self.url("credentials", mesh), **self.auth(caller)).status_code, 404)
        list_partitions.assert_not_called()

    def test_an_operator_who_lost_the_role_loses_access(self):
        self.operator.role = OwnerRole.MEMBER
        self.operator.save()

        self.assertEqual(self.client.get(self.url(), **self.auth(self.operator)).status_code, 404)

    def test_anonymous_callers_are_refused(self):
        self.assertIn(self.client.get(self.url()).status_code, (401, 403))

    @override_settings(ARCHIVE_BUCKET="")
    def test_an_instance_without_an_archive_has_no_routes(self):
        for response in (
            self.client.get(self.url(), **self.auth(self.operator)),
            self.client.post(self.url("credentials"), **self.auth(self.operator)),
            self.client.get(self.url("partitions/2026-09-01/13"), **self.auth(self.operator)),
        ):
            self.assertEqual(response.status_code, 404)

    @patch.object(archive, "list_partitions", side_effect=EndpointConnectionError(endpoint_url="http://minio:9000"))
    def test_unreachable_storage_is_a_bad_gateway(self, _):
        self.assertEqual(self.client.get(self.url(), **self.auth(self.operator)).status_code, 502)

    def test_a_malformed_date_is_refused(self):
        self.assertEqual(self.client.get(self.url(), {"stop": "yesterday"}, **self.auth(self.operator)).status_code, 400)


class ArchiveCredentialsTests(ArchiveTestCase):
    def fake_sts(self):
        sts = MagicMock()
        sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AK",
                "SecretAccessKey": "SK",
                "SessionToken": "TOKEN",
                "Expiration": datetime(2026, 9, 1, 15, tzinfo=timezone.utc),
            }
        }
        archive._clients[("sts", "http://minio:9000", "archive-reader")] = sts
        return sts

    def test_credentials_are_scoped_to_the_mesh(self):
        sts = self.fake_sts()

        response = self.client.post(self.url("credentials"), **self.auth(self.operator))

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual((body["access_key_id"], body["session_token"]), ("AK", "TOKEN"))
        self.assertEqual(body["endpoint"], "https://s3.example.org")
        self.assertEqual(body["s3_path"], f"s3://meshtastic-telemetry/telemetry/mesh_id={self.mesh.id}/")
        policy = json.loads(sts.assume_role.call_args.kwargs["Policy"])
        self.assertEqual(
            policy["Statement"][0]["Resource"],
            [
                f"arn:aws:s3:::meshtastic-telemetry/telemetry/mesh_id={self.mesh.id}/*",
                f"arn:aws:s3:::meshtastic-telemetry/telemetry/mesh_id={self.mesh.id}",
            ],
        )
        self.assertEqual(sts.assume_role.call_args.kwargs["DurationSeconds"], 3600)

    @override_settings(CSRF_TRUSTED_ORIGINS=["https://things.example.org"])
    def test_a_session_needs_a_csrf_token_from_a_trusted_origin(self):
        self.fake_sts()
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.operator)
        token = _get_new_csrf_string()
        client.cookies["csrftoken"] = token

        cases = [
            ({"HTTP_ORIGIN": "https://things.example.org"}, 403),
            ({"HTTP_ORIGIN": "https://evil.example.org", "HTTP_X_CSRFTOKEN": token}, 403),
            ({"HTTP_ORIGIN": "https://things.example.org", "HTTP_X_CSRFTOKEN": token}, 201),
        ]
        for headers, status in cases:
            with self.subTest(**headers):
                self.assertEqual(client.post(self.url("credentials"), **headers).status_code, status)

    @override_settings(ARCHIVE_STS="")
    def test_no_credentials_where_the_storage_has_no_sts(self):
        self.assertEqual(self.client.post(self.url("credentials"), **self.auth(self.operator)).status_code, 404)


class ArchivePartitionTests(ArchiveTestCase):
    def fake_s3(self, exists=True):
        s3 = MagicMock()
        s3.generate_presigned_url.return_value = "https://s3.example.org/signed"
        if not exists:
            from botocore.exceptions import ClientError

            s3.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadObject")
        archive._clients[("s3", "http://minio:9000", "archive-reader")] = s3
        archive._clients[("s3", "https://s3.example.org", "archive-reader")] = s3
        return s3

    def test_redirects_to_a_signed_link(self):
        s3 = self.fake_s3()

        response = self.client.get(self.url("partitions/2026-09-01/13"), **self.auth(self.operator))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://s3.example.org/signed")
        key = s3.generate_presigned_url.call_args.kwargs["Params"]["Key"]
        self.assertEqual(key, f"telemetry/mesh_id={self.mesh.id}/dt=2026-09-01/hour=13/data.parquet")

    def test_an_hour_with_nothing_archived_is_not_found(self):
        self.fake_s3(exists=False)

        self.assertEqual(self.client.get(self.url("partitions/2026-09-01/13"), **self.auth(self.operator)).status_code, 404)

    def test_an_impossible_partition_is_not_found(self):
        s3 = self.fake_s3()
        for suffix in ("partitions/2026-13-01/13", "partitions/2026-09-01/24"):
            self.assertEqual(self.client.get(self.url(suffix), **self.auth(self.operator)).status_code, 404)
        s3.head_object.assert_not_called()


class ArchiveZipTests(ArchiveTestCase):
    HOUR = {"dt": date(2026, 9, 1), "hour": 22, "size": 3, "last_modified": datetime(2026, 9, 1, 22, 59, tzinfo=timezone.utc)}

    def test_objects_are_zipped_in_order_from_the_mesh_prefix(self):
        s3 = MagicMock()
        s3.get_object.side_effect = lambda Bucket, Key: {"Body": io.BytesIO(Key.encode())}
        archive._clients[("s3", "http://minio:9000", "archive-reader")] = s3
        hours = [dict(self.HOUR, hour=h) for h in range(24)]
        out, written = io.BytesIO(), []

        archive.zip_partitions(self.mesh.id, hours, out, progress=written.append)

        self.assertEqual(written, hours)
        with zipfile.ZipFile(out) as zf:
            self.assertEqual([info.filename[-10:-8] for info in zf.infolist()], [f"{h:02d}" for h in range(24)])
            self.assertEqual(
                zf.read("2026-09-01/2026-09-01_07.parquet").decode(),
                f"telemetry/mesh_id={self.mesh.id}/dt=2026-09-01/hour=07/data.parquet",
            )
            self.assertEqual(zf.getinfo("2026-09-01/2026-09-01_07.parquet").date_time, (2026, 9, 1, 22, 59, 0))


@override_settings(**ARCHIVE)
class ArchiveStorageTests(SimpleTestCase):
    MESH = "5b1f3c1e-8a55-4a8e-9a0f-1d2b3c4d5e6f"

    def test_listing_keeps_current_partitions_in_range(self):
        s3 = MagicMock()
        prefix = f"telemetry/mesh_id={self.MESH}"
        modified = datetime(2026, 9, 1, tzinfo=timezone.utc)
        s3.get_paginator.return_value.paginate.return_value = [
            {
                "Contents": [
                    {"Key": f"{prefix}/dt=2026-09-02/hour=01/data.parquet", "Size": 2, "LastModified": modified},
                    {"Key": f"{prefix}/dt=2026-08-31/hour=23/data.parquet", "Size": 1, "LastModified": modified},
                    {"Key": f"{prefix}/dt=2026-09-01/hour=05/data.parquet", "Size": 3, "LastModified": modified},
                    {"Key": f"{prefix}/node_id=1/dt=2026-09-01/hour=05/part-x.parquet", "Size": 9, "LastModified": modified},
                ]
            }
        ]
        with patch.object(archive, "_client", return_value=s3):
            partitions = archive.list_partitions(self.MESH, start=date(2026, 9, 1))

        self.assertEqual([(p["dt"].isoformat(), p["hour"]) for p in partitions], [("2026-09-01", 5), ("2026-09-02", 1)])
        self.assertEqual(s3.get_paginator.return_value.paginate.call_args.kwargs["Prefix"], f"{prefix}/")

    def test_listing_is_limited_to_the_mesh_prefix(self):
        statements = archive.session_policy(self.MESH)["Statement"]

        self.assertEqual(statements[1]["Resource"], ["arn:aws:s3:::meshtastic-telemetry"])
        self.assertEqual(
            statements[1]["Condition"]["StringLike"]["s3:prefix"],
            [f"telemetry/mesh_id={self.MESH}/", f"telemetry/mesh_id={self.MESH}/*"],
        )

    @override_settings(ARCHIVE_STS="aws", ARCHIVE_ROLE_ARN="arn:aws:iam::123456789012:role/archive-reader")
    def test_aws_assumes_the_configured_role(self):
        args = archive.assume_role_args(self.MESH, "owner-1")

        self.assertEqual(args["RoleArn"], "arn:aws:iam::123456789012:role/archive-reader")
        self.assertEqual(args["RoleSessionName"], "owner-1")

    @override_settings(ARCHIVE_STS="aws", ARCHIVE_ENDPOINT_URL="", ARCHIVE_PUBLIC_ENDPOINT_URL="", ARCHIVE_REGION="eu-west-1")
    def test_aws_uses_the_providers_endpoints(self):
        sts = MagicMock()
        sts.assume_role.return_value = {
            "Credentials": {"AccessKeyId": "a", "SecretAccessKey": "s", "SessionToken": "t", "Expiration": datetime.now(timezone.utc)}
        }
        with patch.object(archive, "_client", return_value=sts) as client:
            body = archive.issue_credentials(self.MESH, "owner-1")

        client.assert_called_once_with("sts", "")
        self.assertIsNone(body["endpoint"])
        self.assertEqual(body["region"], "eu-west-1")
