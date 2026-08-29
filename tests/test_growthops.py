from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from ai_growth_engineering.growthops import command_center_state
from ai_growth_engineering.storage import connect, init_db


class GrowthOpsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)

    def test_empty_state_proposes_contact_without_external_authority(self):
        state = command_center_state(self.db, today=date(2026, 8, 29))
        self.assertEqual(state["status"]["label"], "CONTACT FREEZE")
        self.assertFalse(state["recommendation"]["executable"])
        self.assertEqual(state["authority"]["mode"], "PROPOSE_ONLY")
        self.assertIn("contact a customer or prospect", state["authority"]["human_approval_required"])

    def test_stale_external_contact_activates_freeze(self):
        with connect(self.db) as con:
            con.execute(
                "INSERT INTO outreach(company, sent_at, stage) VALUES ('Acme', '2026-08-20', 'sent_awaiting_reply')"
            )
        state = command_center_state(self.db, today=date(2026, 8, 29))
        self.assertTrue(state["freshness"]["contact_freeze"])
        self.assertEqual(state["freshness"]["days_since_external_contact"], 9)
        self.assertEqual(state["recommendation"]["primary_metric"], "external_contact_date")

    def test_current_contact_with_no_reply_identifies_access_constraint(self):
        with connect(self.db) as con:
            con.execute(
                """INSERT INTO outreach(company, sent_at, stage, channel, recipient_class)
                   VALUES ('Acme', '2026-08-28', 'sent_awaiting_reply', 'email', 'named_buyer')"""
            )
        state = command_center_state(self.db, today=date(2026, 8, 29))
        self.assertEqual(state["status"]["label"], "ACCESS CONSTRAINT")
        self.assertEqual(state["routes"][0]["route"], "email/named_buyer")
        self.assertEqual(state["routes"][0]["reply_rate"], 0)

    def test_paid_customer_moves_attention_to_delivery_evidence(self):
        with connect(self.db) as con:
            con.execute(
                """INSERT INTO outreach(
                     company, sent_at, meaningful_reply, discovery, proposal, paid, stage
                   ) VALUES ('Acme', '2026-08-29', 1, 1, 1, 1, 'sent_awaiting_reply')"""
            )
        state = command_center_state(self.db, today=date(2026, 8, 29))
        self.assertEqual(state["status"]["level"], "green")
        self.assertEqual(state["recommendation"]["primary_metric"], "customer_outcome_and_margin")

    def test_malformed_opportunity_is_visible_but_never_eligible(self):
        with connect(self.db) as con:
            con.execute(
                """INSERT INTO product_opportunities(
                     product_opportunity_id, buyer, problem, evidence_ids, evidence_count, status
                   ) VALUES ('OPP-BROKEN', 'Buyer', 'Problem', 'EV-1', 2, 'research')"""
            )
        state = command_center_state(self.db, today=date(2026, 8, 29))
        opportunity = state["opportunities"][0]
        self.assertFalse(opportunity["eligible"])
        self.assertEqual(opportunity["status"], "invalid")
        self.assertEqual(opportunity["missing"], ["registry_contract_error"])


if __name__ == "__main__":
    unittest.main()
