from unittest.mock import patch

from django.core import mail

from registry.models import OperatorRequest, Owner

from .helpers import RegistryTestCase


class OperatorRequestTestCase(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.member = self.create_owner(name="Member", email="opreq-member@example.com")
        self.admin = self.create_owner(name="Admin", email="opreq-admin@example.com")
        self.promote_to_superuser(self.admin)
        mail.outbox.clear()

    def file(self, owner, reason="I run the regional broker"):
        return self.client.post(
            "/owners/me/operator-request", {"reason": reason}, format="json", **self.auth_headers(owner)
        )

    def decide(self, request_id, decision, caller=None, **fields):
        return self.client.put(
            f"/operator-requests/{request_id}",
            {"decision": decision, **fields},
            format="json",
            **self.auth_headers(caller or self.admin),
        )


class FilingTests(OperatorRequestTestCase):
    def test_a_member_files_a_request_and_superusers_are_emailed(self):
        second_admin = self.create_owner(name="Admin 2", email="opreq-admin2@example.com")
        self.promote_to_superuser(second_admin)
        inactive_admin = self.create_owner(name="Admin 3", email="opreq-admin3@example.com")
        self.promote_to_superuser(inactive_admin)
        Owner.objects.filter(pk=inactive_admin["id"]).update(is_active=False)
        mail.outbox.clear()

        resp = self.file(self.member)

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["status"], "pending")
        self.assertEqual(
            sorted(m.to[0] for m in mail.outbox), ["opreq-admin2@example.com", "opreq-admin@example.com"]
        )
        self.assertIn("I run the regional broker", mail.outbox[0].body)
        self.assertIn(f"operator-requests/{resp.json()['id']}", mail.outbox[0].body)

    def test_the_requester_reads_their_latest_request(self):
        self.assertEqual(
            self.client.get("/owners/me/operator-request", **self.auth_headers(self.member)).status_code, 404
        )
        filed = self.file(self.member).json()

        resp = self.client.get("/owners/me/operator-request", **self.auth_headers(self.member))

        self.assertEqual(resp.json()["id"], filed["id"])
        self.assertNotIn("decided_by_id", resp.json())

    def test_a_second_pending_request_is_refused(self):
        self.file(self.member)

        self.assertEqual(self.file(self.member).status_code, 409)
        self.assertEqual(OperatorRequest.objects.count(), 1)

    def test_operators_and_superusers_cannot_file(self):
        self.promote_to_operator(self.member)

        self.assertEqual(self.file(self.member).status_code, 409)
        self.assertEqual(self.file(self.admin).status_code, 409)

    def test_a_reason_is_required(self):
        self.assertEqual(self.file(self.member, reason="").status_code, 400)

    def test_an_unverified_owner_cannot_file(self):
        Owner.objects.filter(pk=self.member["id"]).update(is_active=False)

        self.assertEqual(self.file(self.member).status_code, 403)

    def test_filing_is_throttled(self):
        for _ in range(3):
            filed = self.file(self.member).json()
            self.decide(filed["id"], "reject")

        self.assertEqual(self.file(self.member).status_code, 429)

    def test_a_failed_notification_keeps_the_request(self):
        with patch("registry.views.send_operator_request_email", side_effect=RuntimeError("smtp down")):
            resp = self.file(self.member)

        self.assertEqual(resp.status_code, 201)
        self.assertTrue(OperatorRequest.objects.filter(pk=resp.json()["id"]).exists())

    def test_a_rejected_owner_can_file_again(self):
        self.decide(self.file(self.member).json()["id"], "reject")

        self.assertEqual(self.file(self.member).status_code, 201)


class DecisionTests(OperatorRequestTestCase):
    def setUp(self):
        super().setUp()
        self.request_id = self.file(self.member).json()["id"]
        mail.outbox.clear()

    def test_approving_grants_the_role_and_emails_the_requester(self):
        resp = self.decide(self.request_id, "approve", note="Welcome aboard")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "approved")
        self.assertEqual(resp.json()["decided_by_id"], self.admin["id"])
        self.assertEqual(Owner.objects.get(pk=self.member["id"]).role, "operator")
        self.assertEqual([m.to[0] for m in mail.outbox], ["opreq-member@example.com"])
        self.assertIn("approved", mail.outbox[0].body)
        self.assertIn("Welcome aboard", mail.outbox[0].body)
        self.create_source(self.member)

    def test_rejecting_leaves_the_role_unchanged(self):
        resp = self.decide(self.request_id, "reject")

        self.assertEqual(resp.json()["status"], "rejected")
        self.assertEqual(Owner.objects.get(pk=self.member["id"]).role, "member")
        self.assertIn("rejected", mail.outbox[0].body)

    def test_a_decided_request_cannot_be_decided_again(self):
        self.decide(self.request_id, "reject")

        self.assertEqual(self.decide(self.request_id, "approve").status_code, 409)
        self.assertEqual(Owner.objects.get(pk=self.member["id"]).role, "member")

    def test_an_unknown_decision_is_rejected(self):
        self.assertEqual(self.decide(self.request_id, "maybe").status_code, 400)

    def test_a_failed_decision_email_keeps_the_decision(self):
        with patch("registry.views.send_operator_request_decided_email", side_effect=RuntimeError("smtp down")):
            resp = self.decide(self.request_id, "approve")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Owner.objects.get(pk=self.member["id"]).role, "operator")

    def test_only_superusers_list_read_and_decide(self):
        operator = self.create_owner(name="Operator", email="opreq-op@example.com")
        self.promote_to_operator(operator)

        for caller in (self.member, operator):
            self.assertEqual(self.client.get("/operator-requests", **self.auth_headers(caller)).status_code, 403)
            self.assertEqual(
                self.client.get(f"/operator-requests/{self.request_id}", **self.auth_headers(caller)).status_code,
                403,
            )
            self.assertEqual(self.decide(self.request_id, "approve", caller=caller).status_code, 403)

    def test_the_list_shows_pending_requests_by_default(self):
        other = self.create_owner(name="Other", email="opreq-other@example.com")
        other_id = self.file(other).json()["id"]
        self.decide(other_id, "reject")

        pending = self.client.get("/operator-requests", **self.auth_headers(self.admin)).json()
        everything = self.client.get("/operator-requests?status=all", **self.auth_headers(self.admin)).json()

        self.assertEqual([r["id"] for r in pending], [self.request_id])
        self.assertEqual(pending[0]["owner_email"], "opreq-member@example.com")
        self.assertEqual({r["id"] for r in everything}, {self.request_id, other_id})
        self.assertEqual(
            self.client.get("/operator-requests?status=nope", **self.auth_headers(self.admin)).status_code, 400
        )

    def test_a_direct_grant_closes_the_pending_request(self):
        self.client.put(
            f"/owners/{self.member['id']}", {"role": "operator"}, format="json", **self.auth_headers(self.admin)
        )

        closed = OperatorRequest.objects.get(pk=self.request_id)
        self.assertEqual(closed.status, "approved")
        self.assertEqual(str(closed.decided_by_id), self.admin["id"])
