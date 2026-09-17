"""A preregistered experiment can be held until another experiment's verdict is mature.

EXP-ACQ-0007 was frozen on 2026-09-16 while the founder's standing sequence says no demand-gen
experiment runs before EXP-ACQ-0006's verdict (on or after 2026-09-22). Nothing in the store
said so: the order lived in memory and prose. The gate makes it a refusal.

    BLOCK    appended with its dependency and reason
    blocked  no canonical event, no linked send and no active campaign for the experiment
    RELEASE  appended only when the dependency's own staged verdict is past NOT_READY
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering import registries
from ai_growth_engineering.execution_gate import (
    GateError, block_experiment, execution_status, release_experiment,
)
from ai_growth_engineering.funnel_events import EventError, record_event
from ai_growth_engineering.models import ExperimentSpec
from ai_growth_engineering.registry import add_experiment
from ai_growth_engineering.reply_capture import (
    ReplyCaptureError, check, import_outbound_sends, link_outbound,
)
from ai_growth_engineering.storage import init_db

GATED, DEP = "EXP-ACQ-0017", "EXP-ACQ-0016"
MAILBOX = "founder@example.test"
RULES = {
    "experiment_id": DEP, "judge_not_before": "2026-09-10", "demand_exposure_counted": False,
    "access": {"min_desk_eligible": 30, "min_named_buyers": 20, "min_verified_access_accounts": 15,
               "preferred_direct": 10, "min_clean_delivery_rate": 0.70, "min_observed_for_rate": 10},
    "demand": {"min_clean_deliveries": 30, "min_replies": 5, "min_pain_conversations": 3, "min_proposals": 2,
               "min_paid_partners": 1},
    "research_snapshot": {"desk_eligible": 38, "named_buyers": 15, "direct_access_companies": [],
                          "sends_claimed": 3},
    "response_mapping": {"routing": ["AUTHORITY_SIGNAL"], "demand": ["PROBLEM_STATED"]},
    "next_actions": {"no_human_replies": "change the route", "routing_without_demand": "count routes"},
}


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)
        add_experiment(self.db, ExperimentSpec(GATED, "h", "m", 0.10, 0.05, 30))
        self.rules = Path(self.tmp.name) / "gates.json"
        self.rules.write_text(json.dumps(RULES), encoding="utf-8")
        link_outbound(self.db, [{"message_id": f"d{i}", "thread_id": f"dt{i}", "recipient": f"x{i}@c{i}.test",
                                 "company": f"Dep {i}", "experiment_id": DEP, "sent_at": "2026-09-01T09:00:00Z"}
                                for i in range(3)])
        import_outbound_sends(self.db, DEP)

    def block(self):
        return block_experiment(self.db, GATED, depends_on=DEP, rules_path=str(self.rules),
                                reason="founder sequence: no demand-gen test before the dependency's verdict")

    def send(self, experiment=GATED, n=1):
        return record_event(self.db, {"event_type": "message_sent", "company": f"Co {n}", "experiment_id": experiment,
                                      "occurred_at": "2026-09-20", "source": "t", "source_record_id": f"s{n}",
                                      "provenance": "operator_recorded"})


class Blocking(Case):
    def test_a_blocked_experiment_reports_its_dependency(self):
        self.block()
        status = execution_status(self.db, GATED)
        self.assertEqual((status["status"], status["blocked_by"]), ("PREREGISTERED_BLOCKED", [DEP]))

    def test_an_unblocked_experiment_is_executable(self):
        self.assertEqual(execution_status(self.db, GATED)["status"], "EXECUTABLE")

    def test_no_event_can_be_attributed_to_a_blocked_experiment(self):
        self.block()
        with self.assertRaises(EventError) as ctx:
            self.send()
        self.assertEqual(ctx.exception.code, "experiment_blocked")
        self.assertIn(DEP, str(ctx.exception))

    def test_other_experiments_are_not_held(self):
        self.block()
        self.assertTrue(self.send(experiment="EXP-ACQ-0018")["inserted"])

    def test_a_send_cannot_be_linked_to_a_blocked_experiment(self):
        self.block()
        with self.assertRaises(ReplyCaptureError) as ctx:
            link_outbound(self.db, [{"message_id": "g1", "thread_id": "gt1", "recipient": "a@b.test",
                                     "company": "Gated Co", "experiment_id": GATED,
                                     "sent_at": "2026-09-20T09:00:00Z"}])
        self.assertEqual(ctx.exception.code, "experiment_blocked")

    def test_a_campaign_cannot_be_activated_for_a_blocked_experiment(self):
        self.block()
        base = {"campaign_id": "CMP-G", "channel": "email", "icp": "x", "objective": "qualified_reply_rate",
                "offer_id": "", "experiment_id": GATED}
        with self.assertRaises(ValueError) as ctx:
            registries.add(self.db, "campaigns", dict(base, status="active"))
        self.assertIn("PREREGISTERED_BLOCKED", str(ctx.exception))
        registries.add(self.db, "campaigns", dict(base, status="planned"))  # declaring it is not running it

    def test_a_block_needs_a_reason_and_an_existing_rules_file(self):
        with self.assertRaises(GateError):
            block_experiment(self.db, GATED, depends_on=DEP, rules_path=str(self.rules), reason=" ")
        with self.assertRaises(GateError):
            block_experiment(self.db, GATED, depends_on=DEP, rules_path=str(self.rules) + ".missing", reason="r")
        with self.assertRaises(GateError):
            block_experiment(self.db, "EXP-ACQ-9999", depends_on=DEP, rules_path=str(self.rules), reason="r")

    def test_the_gate_ledger_is_append_only(self):
        self.block()
        con = sqlite3.connect(self.db)
        try:
            for sql in ("DELETE FROM experiment_gates", "UPDATE experiment_gates SET action = 'RELEASE'"):
                with self.assertRaises(sqlite3.DatabaseError):
                    con.execute(sql)
        finally:
            con.rollback()
            con.close()


class Release(Case):
    def test_release_before_the_dependency_matures_is_refused(self):
        self.block()
        with self.assertRaises(GateError) as ctx:
            release_experiment(self.db, GATED, depends_on=DEP, as_of="2026-09-05", released_by="founder")
        self.assertIn("NOT_READY", str(ctx.exception))
        self.assertEqual(execution_status(self.db, GATED)["status"], "PREREGISTERED_BLOCKED")

    def test_release_after_the_window_without_a_reply_check_is_refused(self):
        self.block()
        with self.assertRaises(GateError):
            release_experiment(self.db, GATED, depends_on=DEP, as_of="2026-09-20", released_by="founder")

    def test_a_mature_verdict_releases_the_gate_and_records_it(self):
        self.block()
        check(self.db, DEP, {"threads": []}, mailbox=MAILBOX)
        result = release_experiment(self.db, GATED, depends_on=DEP, as_of="2026-09-20", released_by="founder")
        self.assertNotEqual(result["dependency_status"], "NOT_READY")
        status = execution_status(self.db, GATED)
        self.assertEqual((status["status"], status["blocked_by"]), ("EXECUTABLE", []))
        self.assertTrue(self.send()["inserted"])

    def test_a_release_without_a_block_is_refused(self):
        with self.assertRaises(GateError):
            release_experiment(self.db, GATED, depends_on=DEP, as_of="2026-09-20", released_by="founder")


if __name__ == "__main__":
    unittest.main()
