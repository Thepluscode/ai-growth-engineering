"""When something happened in the world is observed, never assumed.

`recorded_at = now` is true by definition: the row is being written now. `occurred_at = now`
is a claim about the outside world, and making it because the operator left a field blank is
fabrication. On 2026-09-16 it re-dated a LinkedIn invitation by a day while an acceptance was
being recorded, and the maturity window moved with it.

Every writer of an external fact therefore takes the observed time, keeps the one already on
file, or refuses.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering.execution import ExecutionError, freeze_execution_cohort, record_invitation
from ai_growth_engineering.outbound_workbench import (
    WorkbenchError, approve_draft, create_draft, record_manual_send, record_meaningful_reply,
)
from ai_growth_engineering.signal_intelligence import add_identity
from ai_growth_engineering.storage import connect, init_db

SENT = "2026-09-15"
LATER = "2026-09-16T05:50:47+00:00"


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)

    def one(self, sql, *params):
        with connect(self.db) as con:
            return con.execute(sql, params).fetchone()


class InvitationTime(Case):
    def setUp(self):
        super().setUp()
        with connect(self.db) as con:
            con.execute("""INSERT INTO prospects(id, company, website, priority, target_roles, evidence,
                           source_url, status) VALUES (63, 'Acme', 'https://acme.test', 'B', 'MD', 'e',
                           'https://acme.test/about', 'qualified_batch_07')""")
        add_identity(self.db, {"prospect_id": 63, "identity_type": "linkedin",
                               "value": "https://uk.linkedin.com/in/example-buyer-63", "provider": "test",
                               "verification_status": "observed_published", "source_url": "https://acme.test",
                               "observed_at": "2026-09-08T09:00:00+00:00", "confidence": 0.8})
        freeze_execution_cohort(self.db, "C1")

    def submitted_at(self):
        return self.one("SELECT submitted_at FROM invitations WHERE cohort_id='C1' AND prospect_id=63")[0]

    def test_recording_an_acceptance_keeps_the_submission_date_on_file(self):
        """The 2026-09-16 defect, exactly: an acceptance must not re-date the invitation."""
        record_invitation(self.db, "C1", 63, {"outcome": "pending", "submitted_at": SENT})
        record_invitation(self.db, "C1", 63, {"outcome": "accepted", "accepted_at": LATER})
        self.assertEqual(self.submitted_at(), SENT)

    def test_a_first_submission_without_a_date_is_refused(self):
        with self.assertRaises(ExecutionError) as ctx:
            record_invitation(self.db, "C1", 63, {"outcome": "pending"})
        self.assertEqual(ctx.exception.code, "submission_needs_timestamp")
        self.assertEqual(self.submitted_at() or "", "")

    def test_an_explicit_new_date_is_honoured(self):
        record_invitation(self.db, "C1", 63, {"outcome": "pending", "submitted_at": SENT})
        record_invitation(self.db, "C1", 63, {"outcome": "pending", "submitted_at": "2026-09-14"})
        self.assertEqual(self.submitted_at(), "2026-09-14")

    def test_a_malformed_date_is_refused(self):
        with self.assertRaises(ExecutionError) as ctx:
            record_invitation(self.db, "C1", 63, {"outcome": "pending", "submitted_at": "yesterday"})
        self.assertEqual(ctx.exception.code, "invalid_timestamp")

    def test_an_unsent_invitation_carries_no_submission_date(self):
        record_invitation(self.db, "C1", 63, {"outcome": "not_submitted"})
        self.assertEqual(self.submitted_at() or "", "")


class OutreachRecordTime(Case):
    def run_cli(self, *extra):
        from ai_growth_engineering.cli import build_parser

        args = build_parser().parse_args(["outreach-record", "--db", self.db, "--company", "Acme",
                                          "--identity", "info@acme.test", *extra])
        args.func(args)

    def test_the_send_date_is_required(self):
        with self.assertRaises(SystemExit):
            self.run_cli()
        self.assertEqual(self.one("SELECT COUNT(*) FROM outreach")[0], 0)

    def test_the_observed_send_date_is_stored_exactly(self):
        self.run_cli("--sent-at", SENT)
        self.assertEqual(self.one("SELECT sent_at FROM outreach")[0], SENT)

    def test_a_malformed_send_date_is_refused(self):
        with self.assertRaises(SystemExit):
            self.run_cli("--sent-at", "last tuesday")
        self.assertEqual(self.one("SELECT COUNT(*) FROM outreach")[0], 0)


class WorkbenchTime(Case):
    def setUp(self):
        super().setUp()
        with connect(self.db) as con:
            con.execute("""INSERT INTO prospects(id, company, website, priority, target_roles, evidence,
                           source_url, status) VALUES (1, 'Acme', 'https://example.com', 'A', 'Founder',
                           'e', 'https://example.com', 'qualified')""")
        self.draft = create_draft(self.db, {
            "prospect_id": 1, "recipient_identity": "founder@example.com", "recipient_class": "named_buyer",
            "channel": "email",
            "observation": "Your managed-security pages route assessment demand into the general enquiry form.",
            "economic_hypothesis": "That shared path may be suppressing qualified conversations rather than "
                                   "traffic being the constraint.",
            "cta": "Want me to send the one-page experiment map?", "metric": "qualified_conversation_rate",
            "source_url": "https://example.com/managed-security"})["id"]
        approve_draft(self.db, self.draft)

    def test_a_manual_send_needs_the_time_it_was_sent(self):
        with self.assertRaises(WorkbenchError) as ctx:
            record_manual_send(self.db, self.draft, "")
        self.assertEqual(ctx.exception.code, "observed_time_required")
        self.assertEqual(self.one("SELECT COUNT(*) FROM outreach")[0], 0)

    def test_the_manual_send_time_is_stored_exactly(self):
        record_manual_send(self.db, self.draft, SENT)
        self.assertEqual(self.one("SELECT sent_at FROM outreach")[0], SENT)
        self.assertEqual(self.one("SELECT sent_at FROM outbound_drafts WHERE id=?", self.draft)[0], SENT)

    def test_a_reply_needs_the_time_it_arrived(self):
        record_manual_send(self.db, self.draft, SENT)
        with self.assertRaises(WorkbenchError) as ctx:
            record_meaningful_reply(self.db, self.draft, "")
        self.assertEqual(ctx.exception.code, "observed_time_required")

    def test_the_reply_time_is_stored_exactly(self):
        record_manual_send(self.db, self.draft, SENT)
        record_meaningful_reply(self.db, self.draft, LATER)
        self.assertEqual(self.one("SELECT replied_at FROM outbound_drafts WHERE id=?", self.draft)[0], LATER)

    def test_a_reply_before_its_send_is_refused(self):
        record_manual_send(self.db, self.draft, SENT)
        with self.assertRaises(WorkbenchError):
            record_meaningful_reply(self.db, self.draft, "2026-09-01")


if __name__ == "__main__":
    unittest.main()
