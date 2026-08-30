from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering.outbound_workbench import (
    WorkbenchError,
    approve_draft,
    create_draft,
    record_manual_send,
    record_meaningful_reply,
    workbench_state,
)
from ai_growth_engineering.registry import reply_rate_by_route, scoreboard
from ai_growth_engineering.signal_intelligence import add_intent_signal, intelligence_state
from ai_growth_engineering.storage import connect, init_db


VALID = {
    "prospect_id": 1,
    "recipient_identity": "founder@example.com",
    "recipient_class": "named_buyer",
    "channel": "email",
    "observation": "Your managed-security pages route assessment demand into the general enquiry form.",
    "economic_hypothesis": "That shared path may be suppressing qualified conversations rather than traffic being the constraint.",
    "cta": "Want me to send the one-page experiment map?",
    "metric": "qualified_conversation_rate",
    "source_url": "https://example.com/managed-security",
}


class OutboundWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)
        with connect(self.db) as con:
            con.execute(
                """INSERT INTO prospects(
                     id, company, website, priority, target_roles, evidence, source_url, status
                   ) VALUES (1, 'Acme Security', 'https://example.com', 'A', 'Founder',
                             'UK managed security provider', 'https://example.com', 'qualified')"""
            )

    def test_draft_persists_teardown_and_separates_message_parts(self):
        draft = create_draft(self.db, VALID)
        self.assertEqual(draft["status"], "pending_approval")
        self.assertEqual(
            draft["message"],
            f"{VALID['observation']}\n\n{VALID['economic_hypothesis']}\n\n{VALID['cta']}",
        )
        with connect(self.db) as con:
            teardown = con.execute("SELECT * FROM teardowns").fetchone()
        self.assertEqual(teardown["observation"], VALID["observation"])
        self.assertEqual(teardown["hypothesis"], VALID["economic_hypothesis"])

    def test_approval_is_required_before_a_send_can_be_recorded(self):
        draft = create_draft(self.db, VALID)
        with self.assertRaisesRegex(WorkbenchError, "Approve the draft"):
            record_manual_send(self.db, draft["id"])
        self.assertEqual(scoreboard(self.db)["outreach_sent"], 0)

    def test_approved_manual_send_and_reply_update_real_metrics(self):
        draft = create_draft(self.db, VALID)
        approved = approve_draft(self.db, draft["id"])
        self.assertEqual(approved["status"], "approved")
        sent = record_manual_send(self.db, draft["id"])
        self.assertEqual(sent["status"], "sent")
        self.assertEqual(scoreboard(self.db)["outreach_sent"], 1)
        self.assertEqual(
            reply_rate_by_route(self.db)["email/named_buyer"],
            {"sent": 1, "replies": 0},
        )
        replied = record_meaningful_reply(self.db, draft["id"])
        self.assertEqual(replied["status"], "replied")
        self.assertEqual(scoreboard(self.db)["meaningful_responses"], 1)

    def test_suppression_is_rechecked_after_approval(self):
        draft = create_draft(self.db, VALID)
        approve_draft(self.db, draft["id"])
        with connect(self.db) as con:
            con.execute(
                "INSERT INTO suppression(identity, reason) VALUES (?, ?)",
                (VALID["recipient_identity"], "opt_out"),
            )
        with self.assertRaisesRegex(WorkbenchError, "suppressed"):
            record_manual_send(self.db, draft["id"])
        self.assertEqual(scoreboard(self.db)["outreach_sent"], 0)

    def test_high_friction_cta_is_rejected(self):
        values = {**VALID, "cta": "Can you book a call on my calendar link?"}
        with self.assertRaisesRegex(WorkbenchError, "high-friction"):
            create_draft(self.db, values)

    def test_disqualified_prospect_is_neither_listed_nor_actionable(self):
        with connect(self.db) as con:
            con.execute("UPDATE prospects SET status = 'disqualified_market_fit' WHERE id = 1")
        self.assertEqual(workbench_state(self.db)["prospects"], [])
        with self.assertRaisesRegex(WorkbenchError, "Disqualified"):
            create_draft(self.db, VALID)

    def test_active_duplicate_is_blocked(self):
        create_draft(self.db, VALID)
        with self.assertRaisesRegex(WorkbenchError, "Active draft"):
            create_draft(self.db, VALID)

    def test_profile_identity_preserves_case(self):
        identity = "https://network.example/in/CaseSensitiveBuyer"
        draft = create_draft(
            self.db,
            {**VALID, "recipient_identity": identity, "channel": "linkedin"},
        )
        self.assertEqual(draft["recipient_identity"], identity)

    def test_signal_to_draft_to_reply_lineage_is_preserved(self):
        signal = add_intent_signal(
            self.db,
            {
                "prospect_id": 1,
                "signal_type": "website_change",
                "source_url": "https://example.com/offer",
                "observed_fact": "The company published a new assessment route on its public offer page.",
                "commercial_interpretation": "The new route may indicate an active attempt to improve qualified demand capture.",
                "observed_at": "2026-08-29",
                "confidence": 0.9,
                "strength": 4,
                "freshness_half_life_days": 30,
            },
        )
        draft = create_draft(self.db, {**VALID, "signal_ids": [signal["signal_id"]]})
        self.assertEqual(draft["signal_ids"], [signal["signal_id"]])
        approve_draft(self.db, draft["id"])
        record_manual_send(self.db, draft["id"])
        record_meaningful_reply(self.db, draft["id"])
        lineage = intelligence_state(self.db)["lineage"][signal["signal_id"]][0]
        self.assertEqual(lineage["draft_status"], "replied")
        self.assertEqual(lineage["meaningful_reply"], 1)

    def test_draft_rejects_a_signal_from_another_prospect(self):
        with connect(self.db) as con:
            con.execute(
                """INSERT INTO prospects(
                     id, company, website, priority, target_roles, evidence, source_url, status
                   ) VALUES (2, 'Other Company', 'https://other.example', 'A', 'Founder',
                             'Public B2B offer', 'https://other.example', 'qualified')"""
            )
        signal = add_intent_signal(
            self.db,
            {
                "prospect_id": 2,
                "signal_type": "hiring",
                "source_url": "https://other.example/jobs",
                "observed_fact": "The company published a commercial operations vacancy on its careers page.",
                "commercial_interpretation": "The role may indicate planned investment in commercial systems and measurement.",
                "observed_at": "2026-08-29",
                "confidence": 0.8,
                "strength": 3,
                "freshness_half_life_days": 20,
            },
        )
        with self.assertRaisesRegex(WorkbenchError, "selected prospect"):
            create_draft(self.db, {**VALID, "signal_ids": [signal["signal_id"]]})


if __name__ == "__main__":
    unittest.main()
