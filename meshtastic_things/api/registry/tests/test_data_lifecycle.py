from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core import mail
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from common.alarm_counts import ALARM_COUNTS_BUCKET, ALARMS_BUCKET
from registry import data_lifecycle
from registry.data_store import DataStore, partition_start
from registry.models import DataDeletion, Source, TermsAcceptance, TermsKind
from registry.terms import VERSIONS

from .helpers import RegistryTestCase


class LifecycleTestCase(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.operator = self.create_owner(name="Operator", email="life-op@example.com")
        self.promote_to_operator(self.operator)
        mail.outbox.clear()

    def sourced_mesh(self):
        source = self.create_source(self.operator)
        mesh = self.create_mesh(self.operator)
        self.client.put(
            f"/meshes/{mesh['id']}", {"source_id": source["id"]}, format="json", **self.auth_headers(self.operator)
        )
        return source, mesh


class SchedulingTests(LifecycleTestCase):
    @override_settings(DATA_DELETION_GRACE_DAYS=30)
    def test_deleting_a_mesh_schedules_all_its_readings(self):
        mesh = self.create_mesh(self.operator)

        self.client.delete(f"/meshes/{mesh['id']}", **self.auth_headers(self.operator))

        deletion = DataDeletion.objects.get()
        self.assertEqual((str(deletion.mesh_id), deletion.reason, deletion.status), (mesh["id"], "mesh_deleted", "pending"))
        self.assertIsNone(deletion.data_until)
        self.assertEqual((deletion.delete_after - deletion.requested_at).days, 30)
        self.fake_store.delete_mesh_readings.assert_not_called()

    def test_moving_a_mesh_off_its_source_schedules_the_readings_until_then(self):
        source, mesh = self.sourced_mesh()

        self.client.put(f"/meshes/{mesh['id']}", {"source_id": None}, format="json", **self.auth_headers(self.operator))

        deletion = DataDeletion.objects.get()
        self.assertEqual((deletion.reason, str(deletion.source_id)), ("source_detached", source["id"]))
        self.assertIsNotNone(deletion.data_until)

    def test_moving_it_back_within_the_grace_period_cancels_it(self):
        source, mesh = self.sourced_mesh()
        self.client.put(f"/meshes/{mesh['id']}", {"source_id": None}, format="json", **self.auth_headers(self.operator))

        self.client.put(
            f"/meshes/{mesh['id']}", {"source_id": source["id"]}, format="json", **self.auth_headers(self.operator)
        )

        self.assertEqual(DataDeletion.objects.get().status, "cancelled")

    def test_attaching_a_default_mesh_to_a_source_deletes_nothing(self):
        self.sourced_mesh()

        self.assertFalse(DataDeletion.objects.exists())

    def test_deleting_an_owner_schedules_each_of_their_meshes(self):
        member = self.create_owner(name="Member", email="life-member@example.com")
        self.create_mesh(member, channel_id="A")
        self.create_mesh(member, channel_id="B")
        admin = self.create_owner(name="Admin", email="life-admin@example.com")
        self.promote_to_superuser(admin)

        self.client.delete(f"/owners/{member['id']}", **self.auth_headers(admin))

        self.assertEqual(DataDeletion.objects.filter(reason="mesh_deleted").count(), 2)


class PurgeTests(LifecycleTestCase):
    def test_a_deletion_runs_once_its_grace_period_ends(self):
        mesh = self.create_mesh(self.operator)
        self.client.delete(f"/meshes/{mesh['id']}", **self.auth_headers(self.operator))
        deletion = DataDeletion.objects.get()

        data_lifecycle.purge_due_deletions(deletion.delete_after - timedelta(minutes=1))
        self.fake_store.delete_mesh_readings.assert_not_called()

        now = deletion.delete_after + timedelta(minutes=1)
        data_lifecycle.purge_due_deletions(now)

        self.fake_store.delete_mesh_readings.assert_called_once_with(mesh["id"], now)
        deletion.refresh_from_db()
        self.assertEqual(deletion.status, "done")

    def test_a_detached_mesh_keeps_readings_after_the_detach(self):
        _, mesh = self.sourced_mesh()
        self.client.put(f"/meshes/{mesh['id']}", {"source_id": None}, format="json", **self.auth_headers(self.operator))
        deletion = DataDeletion.objects.get()

        data_lifecycle.purge_due_deletions(deletion.delete_after)

        self.assertEqual(self.fake_store.delete_mesh_readings.call_args.args[1], deletion.data_until)

    def test_a_failed_deletion_is_retried_next_pass(self):
        mesh = self.create_mesh(self.operator)
        self.client.delete(f"/meshes/{mesh['id']}", **self.auth_headers(self.operator))
        deletion = DataDeletion.objects.get()
        self.fake_store.delete_mesh_readings.side_effect = [RuntimeError("influx down"), None]

        data_lifecycle.purge_due_deletions(deletion.delete_after)
        deletion.refresh_from_db()
        self.assertEqual((deletion.status, deletion.attempts, deletion.last_error), ("pending", 1, "influx down"))

        data_lifecycle.purge_due_deletions(deletion.delete_after)
        deletion.refresh_from_db()
        self.assertEqual((deletion.status, deletion.attempts, deletion.last_error), ("done", 2, ""))


@override_settings(DATA_RETENTION_DAYS=365, TERMS_RENEWAL_NOTICE_DAYS=30, DATA_DELETION_GRACE_DAYS=30)
class LapseTests(LifecycleTestCase):
    def setUp(self):
        super().setUp()
        self.source, self.mesh = self.sourced_mesh()
        self.acceptance = TermsAcceptance.objects.get(source_id=self.source["id"])
        mail.outbox.clear()

    def test_the_operator_is_emailed_once_inside_the_notice_window(self):
        TermsAcceptance.objects.filter(kind="mesh").update(expires_at=None)
        early = self.acceptance.expires_at - timedelta(days=31)
        self.assertEqual(data_lifecycle.send_renewal_notices(early), 0)

        inside = self.acceptance.expires_at - timedelta(days=10)
        self.assertEqual(data_lifecycle.send_renewal_notices(inside), 1)
        self.assertEqual(data_lifecycle.send_renewal_notices(inside), 0)

        self.assertEqual([m.to[0] for m in mail.outbox], ["life-op@example.com"])
        self.assertIn(f"sources/{self.source['id']}", mail.outbox[0].body)

    def test_a_lapsed_source_is_paused_and_its_meshes_scheduled(self):
        now = self.acceptance.expires_at + timedelta(minutes=1)

        self.assertEqual(data_lifecycle.pause_lapsed_sources(now), 1)

        self.fake_emqx.delete_source.assert_called_once_with(self.source["id"])
        self.assertIsNotNone(Source.objects.get(pk=self.source["id"]).paused_at)
        deletion = DataDeletion.objects.get()
        self.assertEqual((str(deletion.mesh_id), deletion.reason), (self.mesh["id"], "terms_lapsed"))
        self.assertEqual(deletion.data_until, now)
        self.assertIn("paused", mail.outbox[0].body)

    def test_a_renewed_source_does_not_lapse(self):
        lapse = timezone.now() + timedelta(days=1)
        TermsAcceptance.objects.filter(pk=self.acceptance.pk).update(expires_at=lapse)
        self.client.post(
            f"/sources/{self.source['id']}/terms-acceptance",
            {"terms_version": self.acceptance.terms_version},
            format="json",
            **self.auth_headers(self.operator),
        )

        self.assertEqual(data_lifecycle.pause_lapsed_sources(lapse + timedelta(days=1)), 0)

    def test_a_failed_pause_is_retried(self):
        self.fake_emqx.delete_source.side_effect = RuntimeError("emqx down")

        self.assertEqual(data_lifecycle.pause_lapsed_sources(self.acceptance.expires_at + timedelta(minutes=1)), 0)
        self.assertIsNone(Source.objects.get(pk=self.source["id"]).paused_at)
        self.assertFalse(DataDeletion.objects.exists())

    def test_paused_sources_stay_out_of_sync(self):
        data_lifecycle.pause_lapsed_sources(self.acceptance.expires_at + timedelta(minutes=1))
        self.fake_emqx.managed_source_ids.return_value = set()
        self.fake_emqx.apply_source.reset_mock()

        call_command("sync_sources", stdout=StringIO())

        self.fake_emqx.apply_source.assert_not_called()


class NoRetentionTests(LifecycleTestCase):
    def test_without_a_retention_period_nothing_lapses(self):
        self.sourced_mesh()
        far_future = timezone.now() + timedelta(days=10000)

        self.assertEqual(data_lifecycle.pause_lapsed_sources(far_future), 0)
        self.assertEqual(data_lifecycle.pause_lapsed_meshes(far_future), 0)
        self.assertEqual(data_lifecycle.send_renewal_notices(far_future), 0)

    def test_the_command_runs_one_pass(self):
        out = StringIO()

        call_command("run_data_lifecycle", "--once", stdout=out)

        self.assertIn("deletions_done=0", out.getvalue())


@override_settings(DATA_RETENTION_DAYS=365, TERMS_RENEWAL_NOTICE_DAYS=30, DATA_DELETION_GRACE_DAYS=30)
class MeshLapseTests(LifecycleTestCase):
    """A mesh on the default broker follows the source workflow: ask again before deleting."""

    def setUp(self):
        super().setUp()
        self.member = self.create_owner(name="Member", email="life-lapse@example.com")
        self.mesh = self.create_mesh(self.member)
        self.gateway = self.create_gateway(self.member, self.mesh, device_id=7)
        self.acceptance = TermsAcceptance.objects.get(mesh_id=self.mesh["id"])
        self.lapse = self.acceptance.expires_at + timedelta(minutes=1)
        self.fake_publisher.reset_mock()
        mail.outbox.clear()

    def renew(self):
        return self.client.post(
            f"/meshes/{self.mesh['id']}/terms-acceptance",
            {"terms_version": VERSIONS[TermsKind.MESH]},
            format="json",
            **self.auth_headers(self.member),
        )

    def test_the_owner_is_emailed_before_the_lapse(self):
        data_lifecycle.send_renewal_notices(self.acceptance.expires_at - timedelta(days=5))

        self.assertIn("life-lapse@example.com", [m.to[0] for m in mail.outbox])
        self.assertIn(f"meshes/{self.mesh['id']}", mail.outbox[0].body)

    def test_a_lapse_stops_the_mesh_and_schedules_its_readings(self):
        self.assertEqual(data_lifecycle.pause_lapsed_meshes(self.lapse), 1)

        self.assertEqual(
            [str(c.args[0].id) for c in self.fake_publisher.publish_gateway_delete.call_args_list], [self.gateway["uuid"]]
        )
        mesh = self.client.get(f"/meshes/{self.mesh['id']}", **self.auth_headers(self.member)).json()
        self.assertIsNotNone(mesh["paused_at"])
        deletion = DataDeletion.objects.get(mesh_id=self.mesh["id"])
        self.assertEqual((deletion.reason, deletion.source_id, deletion.data_until), ("terms_lapsed", None, self.lapse))
        self.assertIn("stopped storing", mail.outbox[0].body)

    def test_each_mesh_lapses_on_its_own(self):
        other = self.create_mesh(self.member, channel_id="Other")
        TermsAcceptance.objects.filter(mesh_id=other["id"]).update(expires_at=self.lapse + timedelta(days=100))

        data_lifecycle.pause_lapsed_meshes(self.lapse)

        self.assertFalse(DataDeletion.objects.filter(mesh_id=other["id"]).exists())

    def test_a_gateway_added_while_paused_is_not_registered(self):
        data_lifecycle.pause_lapsed_meshes(self.lapse)
        self.fake_publisher.reset_mock()

        self.create_gateway(self.member, self.mesh, device_id=8)

        self.fake_publisher.publish_gateway_upsert.assert_not_called()
        self.fake_publisher.publish_gateway_delete.assert_called_once()

    def test_renewing_resumes_the_mesh_and_cancels_the_deletion(self):
        data_lifecycle.pause_lapsed_meshes(self.lapse)
        self.fake_publisher.reset_mock()

        resp = self.renew()

        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(resp.json()["paused_at"])
        self.fake_publisher.publish_gateway_upsert.assert_called_once()
        self.assertEqual(DataDeletion.objects.get(mesh_id=self.mesh["id"]).status, "cancelled")

    def test_a_failed_resume_keeps_the_mesh_paused(self):
        data_lifecycle.pause_lapsed_meshes(self.lapse)
        self.fake_publisher.publish_gateway_upsert.side_effect = RuntimeError("kafka down")

        self.assertEqual(self.renew().status_code, 502)
        mesh = self.client.get(f"/meshes/{self.mesh['id']}", **self.auth_headers(self.member)).json()
        self.assertIsNotNone(mesh["paused_at"])

    def test_moving_a_lapsed_mesh_back_with_new_terms_resumes_it(self):
        self.promote_to_operator(self.member)
        source = self.create_source(self.member)
        TermsAcceptance.objects.filter(pk=self.acceptance.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        data_lifecycle.pause_lapsed_meshes(timezone.now())
        self.client.put(
            f"/meshes/{self.mesh['id']}", {"source_id": source["id"]}, format="json", **self.auth_headers(self.member)
        )
        self.fake_publisher.reset_mock()

        resp = self.client.put(
            f"/meshes/{self.mesh['id']}",
            {"source_id": None, "terms_version": VERSIONS[TermsKind.MESH]},
            format="json",
            **self.auth_headers(self.member),
        )

        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["paused_at"])
        self.fake_publisher.publish_gateway_upsert.assert_called()
        self.fake_publisher.publish_gateway_delete.assert_not_called()
        lapsed = DataDeletion.objects.get(mesh_id=self.mesh["id"], reason="terms_lapsed")
        self.assertEqual(lapsed.status, "cancelled")

    def test_sourced_meshes_follow_their_source(self):
        source = self.create_source(self.operator)
        mesh = self.create_mesh(self.operator, channel_id="Sourced")
        self.client.put(
            f"/meshes/{mesh['id']}", {"source_id": source["id"]}, format="json", **self.auth_headers(self.operator)
        )
        TermsAcceptance.objects.filter(kind="source").update(expires_at=None)

        data_lifecycle.pause_lapsed_meshes(self.lapse + timedelta(days=1000))

        self.assertFalse(DataDeletion.objects.filter(mesh_id=mesh["id"]).exists())

    def test_account_terms_never_lapse(self):
        self.assertIsNone(TermsAcceptance.objects.get(owner_id=self.member["id"], kind="account").expires_at)


class DataDeletionListTests(LifecycleTestCase):
    def test_superusers_list_pending_deletions(self):
        mesh = self.create_mesh(self.operator)
        self.client.delete(f"/meshes/{mesh['id']}", **self.auth_headers(self.operator))
        admin = self.create_owner(name="Admin", email="life-admin2@example.com")
        self.promote_to_superuser(admin)

        listed = self.client.get("/data-deletions", **self.auth_headers(admin)).json()

        self.assertEqual([d["mesh_id"] for d in listed], [mesh["id"]])
        self.assertEqual(self.client.get("/data-deletions", **self.auth_headers(self.operator)).status_code, 403)
        self.assertEqual(self.client.get("/data-deletions?status=nope", **self.auth_headers(admin)).status_code, 400)


MESH = "5b1f3c1e-8a55-4a8e-9a0f-1d2b3c4d5e6f"


def _key(day, hour, mesh=MESH):
    return f"telemetry/mesh_id={mesh}/dt={day}/hour={hour:02d}/data.parquet"


class DataStoreTests(SimpleTestCase):
    def setUp(self):
        self.store = DataStore()
        self.store.influx_bucket, self.store.influx_org = "telemetry", "org"
        self.store.archive_bucket, self.store.archive_prefix = "archive", "telemetry"
        self.delete_api = MagicMock()
        self.store._delete_api = lambda: self.delete_api
        self.s3 = MagicMock()
        self.s3.get_paginator.return_value.paginate.return_value = [
            {"Contents": [{"Key": _key("2026-01-01", 9)}, {"Key": _key("2026-01-01", 10)}, {"Key": _key("2026-01-01", 11)}]}
        ]
        self.store._s3_client = lambda: self.s3

    def deleted_keys(self):
        return [o["Key"] for call in self.s3.delete_objects.call_args_list for o in call.kwargs["Delete"]["Objects"]]

    def test_partition_start_reads_the_hour(self):
        self.assertEqual(partition_start(_key("2026-01-01", 10)), datetime(2026, 1, 1, 10, tzinfo=dt_timezone.utc))
        self.assertIsNone(partition_start("telemetry/other/file"))

    def test_an_end_of_service_deletion_takes_the_straddling_hour(self):
        until = datetime(2026, 1, 1, 10, 30, tzinfo=dt_timezone.utc)

        self.store.delete_mesh_readings(MESH, until)

        self.assertEqual(self.deleted_keys(), [_key("2026-01-01", 9), _key("2026-01-01", 10)])
        kwargs = self.delete_api.delete.call_args.kwargs
        self.assertEqual((kwargs["stop"], kwargs["predicate"]), (until, f'mesh_id="{MESH}"'))

    def test_a_malformed_mesh_id_never_reaches_the_predicate(self):
        with self.assertRaises(ValueError):
            self.store.delete_mesh_readings('x" OR _measurement="y', datetime.now(dt_timezone.utc))
        self.delete_api.delete.assert_not_called()

    def test_without_an_archive_only_influx_is_touched(self):
        self.store.archive_bucket = ""

        self.store.delete_mesh_readings(MESH, datetime.now(dt_timezone.utc))

        self.assertEqual(self.delete_api.delete.call_count, 3)
        self.s3.delete_objects.assert_not_called()

    def test_the_mesh_alarms_and_their_counts_go_too(self):
        self.store.delete_mesh_readings(MESH, datetime.now(dt_timezone.utc))

        buckets = [c.kwargs["bucket"] for c in self.delete_api.delete.call_args_list]
        self.assertEqual(buckets, ["telemetry", ALARMS_BUCKET, ALARM_COUNTS_BUCKET])


@override_settings(SINKS_MAX_OFFLINE_HOURS=24, SINKS_MAX_QUEUED=100)
class SinkSessionTests(SimpleTestCase):
    NOW = datetime(2026, 10, 1, 12, 0, tzinfo=dt_timezone.utc)

    def setUp(self):
        self.emqx = MagicMock()
        for target in (
            patch.object(data_lifecycle, "get_emqx_client", return_value=self.emqx),
            patch.dict("os.environ", {"REGISTRY__EMQX_API_URL": "https://emqx.example.org/api/v5"}),
        ):
            target.start()
            self.addCleanup(target.stop)

    def session(self, clientid, connected=False, offline_hours=1, queued=0):
        disconnected_at = None if connected else (self.NOW - timedelta(hours=offline_hours)).isoformat()
        return {"clientid": clientid, "connected": connected, "disconnected_at": disconnected_at, "mqueue_len": queued}

    def discarded(self):
        return [c.args[0] for c in self.emqx.discard_session.call_args_list]

    def test_sessions_offline_too_long_or_queueing_too_much_are_discarded(self):
        self.emqx.sink_sessions.return_value = [
            self.session("recent", offline_hours=2),
            self.session("old", offline_hours=25),
            self.session("full", offline_hours=1, queued=101),
            self.session("slow-but-online", connected=True, queued=500),
            self.session("online", connected=True, queued=5),
        ]

        self.assertEqual(data_lifecycle.discard_stale_sink_sessions(self.NOW), 3)
        self.assertEqual(self.discarded(), ["old", "full", "slow-but-online"])

    @override_settings(SINKS_MAX_OFFLINE_HOURS=0, SINKS_MAX_QUEUED=0)
    def test_zero_turns_both_limits_off(self):
        self.emqx.sink_sessions.return_value = [self.session("old", offline_hours=1000, queued=10**6)]

        self.assertEqual(data_lifecycle.discard_stale_sink_sessions(self.NOW), 0)

    def test_one_failure_does_not_stop_the_others(self):
        self.emqx.sink_sessions.return_value = [self.session("a", offline_hours=30), self.session("b", offline_hours=30)]
        self.emqx.discard_session.side_effect = [RuntimeError("emqx down"), None]

        self.assertEqual(data_lifecycle.discard_stale_sink_sessions(self.NOW), 1)

    def test_an_unreachable_broker_skips_the_step(self):
        self.emqx.sink_sessions.side_effect = RuntimeError("emqx down")

        self.assertEqual(data_lifecycle.discard_stale_sink_sessions(self.NOW), 0)

    def test_nothing_runs_without_emqx(self):
        with patch.dict("os.environ", {"REGISTRY__EMQX_API_URL": ""}):
            self.assertEqual(data_lifecycle.discard_stale_sink_sessions(self.NOW), 0)
        self.emqx.sink_sessions.assert_not_called()
