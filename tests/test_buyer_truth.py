"""Buyer truth: observed statements linked to buyers, events and money. Every expected value is
hard-coded; nothing is recomputed from the code under test."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering.buyer_truth import (
    BuyerTruthError, buyer_evidence, buyer_truth, interpret, problem_revenue, record_commercial_evidence,
)
from ai_growth_engineering.funnel_events import effective_events, record_event
from ai_growth_engineering.marketing_engineer import (
    customer_graph, recommend_next_experiment, render_customer, render_status, status_report,
)
from ai_growth_engineering.registry import seed_registries
from ai_growth_engineering.storage import connect, init_db

PROBLEM = "Security cannot reconstruct why the agent approved actions."
OBJECTION = "We cannot give an outside party production access."


class BuyerTruthCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)
        self.n = 0

    def ev(self, event_type, **kw):
        self.n += 1
        values = {"event_type": event_type, "occurred_at": "2026-09-01", "source": "test",
                  "source_record_id": f"r{self.n}", "provenance": "operator_recorded"}
        values.update(kw)
        return record_event(self.db, values)["event_id"]

    def say(self, statement=PROBLEM, categories=("PROBLEM_STATED",), theme="", **kw):
        self.n += 1
        values = {"statement": statement, "categories": categories, "source": "test", "source_record_id": f"s{self.n}",
                  "occurred_at": "2026-09-02", "company": "Acme Ltd"}
        values.update(kw)
        result = record_commercial_evidence(self.db, **values)
        if theme:
            for link_id in result["link_ids"]:
                interpret(self.db, link_id, theme=theme, interpretation=f"reads as {theme}", confidence=0.3,
                          interpreted_by="founder")
        return result


class DurabilityTests(unittest.TestCase):
    def test_a_rebuilt_store_restores_the_retrospective_variable(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "rebuilt.db")
            init_db(db)
            seeds = str(Path(__file__).resolve().parent.parent / "seeds" / "registries.json")
            self.assertEqual(seed_registries(db, seeds).get("experiments"), 1)
            self.assertIsNone(seed_registries(db, seeds).get("experiments"))
            with connect(db) as con:
                row = dict(con.execute("SELECT * FROM experiments WHERE experiment_id = 'EXP-ACQ-0003'").fetchone())
        self.assertEqual((row["variable"], row["variable_metadata_source"], row["execution_mode"], row["minimum_sample"]),
                         ("recipient_route", "retrospective_from_preregistration", "DESCRIPTIVE_FROZEN_COHORT", 51))
        self.assertIn("Retrospective metadata only", row["variable_metadata_note"])
        self.assertIn("unchanged", row["variable_metadata_note"])


class CommercialEvidenceTests(BuyerTruthCase):
    def test_a_reply_yields_only_the_evidence_its_words_support(self):
        reply = self.ev("reply_received", company="Acme Ltd", experiment_id="EXP-ACQ-0009", campaign_id="CMP-1")
        result = self.say("Interesting, but this is handled by our compliance team.",
                          ("AUTHORITY_SIGNAL", "REASON_FOR_REJECTION"), source_event_id=reply)
        evidence = buyer_evidence(self.db)
        self.assertEqual(sorted(i["category"] for i in evidence), ["AUTHORITY_SIGNAL", "REASON_FOR_REJECTION"])
        self.assertEqual({(i["evidence_id"], i["experiment_id"], i["campaign_id"], i["source_event_id"]) for i in evidence},
                         {(result["evidence_id"], "EXP-ACQ-0009", "CMP-1", reply)})
        truth = buyer_truth(evidence, effective_events(self.db), "acme ltd")
        self.assertEqual(truth["not_observed"], ["PROBLEM_STATED", "OBJECTION", "BUYING_CRITERION", "REASON_FOR_PURCHASE"])
        self.assertIsNone(truth["willingness_to_pay"]["strongest"])
        self.assertEqual([e["event_type"] for e in effective_events(self.db)], ["reply_received"])
        with connect(self.db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 1)

    def test_what_a_statement_cannot_establish_is_refused(self):
        reply = self.ev("reply_received", company="Acme Ltd", experiment_id="EXP-ACQ-0009")
        invite = self.ev("invitation_sent", company="Acme Ltd")
        cases = {
            "not_an_observation": {"statement": "Thanks.", "categories": ("PAIN_CONFIRMED",)},
            "category_required": {"categories": ()},
            "unknown_category": {"categories": ("VIBES",)},
            "missing_source": {"source_record_id": " "},
            "buyer_required": {"company": ""},
            "event_not_found": {"source_event_id": "EVT-missing"},
            "not_a_conversation": {"source_event_id": invite},
            "buyer_mismatch": {"source_event_id": reply, "company": "Other Ltd"},
            "lineage_conflict": {"source_event_id": reply, "experiment_id": "EXP-ACQ-0008"},
            "no_purchase": {"categories": ("REASON_FOR_PURCHASE",)},
        }
        for code, change in cases.items():
            with self.subTest(code), self.assertRaises(BuyerTruthError) as caught:
                self.say(**change)
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(buyer_evidence(self.db), [])

    def test_the_observation_is_never_rewritten_and_readings_append(self):
        result = self.say()
        [link] = result["link_ids"]
        con = sqlite3.connect(self.db, isolation_level=None)
        self.addCleanup(con.close)
        for sql, arg in (("UPDATE evidence SET statement = 'rewritten' WHERE evidence_id = ?", result["evidence_id"]),
                         ("UPDATE commercial_evidence SET category = 'OBJECTION' WHERE link_id = ?", link),
                         ("DELETE FROM commercial_evidence WHERE link_id = ?", link)):
            with self.assertRaises(sqlite3.DatabaseError):
                con.execute(sql, (arg,))
        interpret(self.db, link, theme="agent-traceability", interpretation="first", confidence=0.4, interpreted_by="founder")
        interpret(self.db, link, theme="audit-evidence", interpretation="second", confidence=0.6, interpreted_by="founder")
        with self.assertRaises(sqlite3.DatabaseError):
            con.execute("DELETE FROM evidence_interpretations")
        with self.assertRaises(BuyerTruthError):
            interpret(self.db, link, theme="Not A Slug", interpretation="x", confidence=0.5, interpreted_by="founder")
        [item] = buyer_evidence(self.db)
        self.assertEqual((item["observation"], item["interpretation"]["theme"], item["interpretation_history"]),
                         (PROBLEM, "audit-evidence", 2))

    def test_a_meeting_is_evidence_only_of_what_was_observed_in_it(self):
        meeting = self.ev("meeting_held", company="Acme Ltd")
        self.assertEqual(buyer_evidence(self.db), [])
        for n, (statement, category) in enumerate(((PROBLEM, "PROBLEM_STATED"), (OBJECTION, "OBJECTION"),
                                                   ("It must work from exported evidence only.", "BUYING_CRITERION"))):
            self.say(statement, (category,), source="meeting-notes", source_record_id=f"notes-1#{n}",
                     source_event_id=meeting)
        evidence = buyer_evidence(self.db)
        self.assertEqual(sorted(i["category"] for i in evidence), ["BUYING_CRITERION", "OBJECTION", "PROBLEM_STATED"])
        self.assertEqual(len({i["evidence_id"] for i in evidence}), 3)

    def test_willingness_to_pay_is_a_ladder_where_behaviour_outranks_words(self):
        self.say("We could probably find money for this.", ("WILLINGNESS_TO_PAY_STATED",))
        self.say("Our budget for this quarter is already set.", ("BUDGET_SIGNAL",))

        def ladder():
            return buyer_truth(buyer_evidence(self.db), effective_events(self.db), "acme ltd")["willingness_to_pay"]

        self.assertEqual(ladder()["strongest"], "budget_discussed")
        self.ev("payment_received", company="Acme Ltd", value_pence=150_000, currency="GBP")
        self.assertEqual(ladder()["strongest"], "payment_received")
        self.assertEqual([r["rung"] for r in ladder()["rungs"] if r["observed"]],
                         ["payment_received", "budget_discussed", "willingness_to_pay_stated"])

    def test_synthetic_evidence_never_counts(self):
        self.say(provenance="synthetic_fixture")
        self.assertEqual(buyer_evidence(self.db), [])
        self.assertEqual(len(buyer_evidence(self.db, include_synthetic=True)), 1)
        self.assertNotIn("BUYER TRUTH", render_status(status_report(self.db, as_of="2026-09-15")))


class TruthToMoneyTests(BuyerTruthCase):
    def test_one_buyer_is_buyer_truth_and_only_independent_organisations_generalise(self):
        def level():
            view = problem_revenue(buyer_evidence(self.db), [])[0]["scope"]
            return view["level"], view["confidence"]

        self.say(person_id="p1", theme="agent-traceability")
        self.assertEqual(level(), ("BUYER", "LOW"))
        self.say(person_id="p2", theme="agent-traceability")
        self.assertEqual(level(), ("ORGANISATION", "LOW"))
        self.say(company="Beta Ltd", theme="agent-traceability")
        self.assertEqual(level(), ("CROSS_ORGANISATION", "LOW"))
        self.say(company="Gamma Ltd", theme="agent-traceability")
        self.assertEqual(level(), ("SEGMENT_CANDIDATE", "MEDIUM"))

    def test_the_money_graph_shows_what_the_customer_said_and_what_was_never_said(self):
        self.ev("message_sent", company="Acme Ltd", campaign_id="CMP-1", channel="email", occurred_at="2026-08-01")
        meeting = self.ev("meeting_held", company="Acme Ltd", occurred_at="2026-08-10")
        problem = self.say(PROBLEM, source_event_id=meeting, theme="agent-traceability")
        objection = self.say(OBJECTION, ("OBJECTION",), source_event_id=meeting)
        self.ev("payment_received", company="Acme Ltd", value_pence=150_000, currency="GBP", occurred_at="2026-09-01")
        graph = customer_graph(self.db, "Acme Ltd")
        truth = graph["buyer_truth"]
        self.assertEqual(truth["observed"]["PROBLEM_STATED"][0]["evidence_id"], problem["evidence_id"])
        self.assertEqual(truth["observed"]["OBJECTION"][0]["evidence_id"], objection["evidence_id"])
        self.assertEqual(truth["not_observed"], ["BUYING_CRITERION", "REASON_FOR_PURCHASE"])
        self.assertEqual(truth["interpreted_problems"][0]["scope"]["reason"], "one buyer")
        text = render_customer(graph)
        self.assertIn("REASON FOR PURCHASE\n  NOT OBSERVED", text)
        self.assertIn(problem["evidence_id"], text)
        self.assertIn("£1,500.00", text)
        self.assertIn("BUYER TRUTH", render_status(status_report(self.db, as_of="2026-09-15")))

    def test_a_problem_traces_forward_to_meetings_proposals_customers_and_revenue(self):
        for company in ("A1", "A2", "A3", "A4"):
            self.say(company=company, theme="agent-traceability")
        for company in ("A1", "A2", "A3"):
            self.ev("reply_meaningful", company=company)
        for company in ("A1", "A2"):
            self.ev("meeting_held", company=company)
            self.ev("proposal_sent", company=company, value_pence=300_000, currency="GBP")
        self.ev("payment_received", company="A1", value_pence=150_000, currency="GBP")
        self.ev("meeting_held", company="Unrelated")
        [view] = problem_revenue(buyer_evidence(self.db), effective_events(self.db))
        self.assertEqual({k: view[k] for k in ("buyers_stating", "qualified_conversations", "meetings", "proposals",
                                               "customers", "observed_revenue_pence")},
                         {"buyers_stating": 4, "qualified_conversations": 3, "meetings": 2, "proposals": 2,
                          "customers": 1, "observed_revenue_pence": 150_000})

    def test_an_objection_that_stalls_proposals_becomes_the_one_next_test(self):
        for i in range(50):
            self.ev("message_sent", company=f"m{i}", experiment_id="EXP-ACQ-0007", occurred_at="2026-08-01")
        self.ev("proposal_sent", company="B3", value_pence=300_000, currency="GBP")
        self.say(OBJECTION, ("OBJECTION",), company="B3", theme="production-access")
        self.ev("payment_received", company="B3", value_pence=300_000, currency="GBP")
        self.ev("proposal_sent", company="B1", value_pence=300_000, currency="GBP")
        self.say(OBJECTION, ("OBJECTION",), company="B1", theme="production-access")
        # One stalled organisation is one buyer's view: the funnel leak still leads.
        self.assertEqual(recommend_next_experiment(self.db, as_of="2026-09-15")["preferred"]["single_variable"], "cta")
        self.ev("proposal_sent", company="B2", value_pence=300_000, currency="GBP")
        self.say(OBJECTION, ("OBJECTION",), company="B2", theme="production-access")
        rec = recommend_next_experiment(self.db, as_of="2026-09-15")
        preferred = rec["preferred"]
        self.assertEqual((preferred["status"], preferred["single_variable"], preferred["primary_metric"]),
                         ("PROPOSED_NEEDS_CONTRACT", "offer", "close_rate"))
        self.assertIn("production-access", preferred["hypothesis"])
        self.assertIn("does not invent", preferred["variant"])
        self.assertEqual(len(preferred["evidence"]), 2)
        self.assertIn(("PROPOSED_NEEDS_CONTRACT", "cta"), {(a["status"], a.get("single_variable")) for a in rec["alternatives"]})


if __name__ == "__main__":
    unittest.main()
