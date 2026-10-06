"""The demand funnel keeps access, response and truth apart, per market and per message variant.
Expected counts are hard-coded from what each case records."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering import registries
from ai_growth_engineering.buyer_truth import record_commercial_evidence
from ai_growth_engineering.demand_funnel import classify, gate, render, report
from ai_growth_engineering.funnel_events import record_event
from ai_growth_engineering.marketer import MarketerError, market_context
from ai_growth_engineering.storage import init_db
from ai_growth_engineering.weekly_cycle import readout

AT = "2026-10-05T10:00:00+00:00"


class Funnel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)
        registries.add(self.db, "offers", {"offer_id": "OFF", "buyer": "b", "problem": "p", "outcome": "o",
                                           "price_pence": 0, "proof": "", "cta": "reply"})
        for market, status in (("MKT-PAY", "active"), ("MKT-OLD", "parked")):
            registries.add(self.db, "markets", {"market_id": market, "hypothesis": "h", "status": status,
                                                "offer_id": "OFF"})
        for exp, market, protocol in (("EXP-D", "MKT-PAY", "discovery-v1"), ("EXP-O", "MKT-PAY", "offer-v1"),
                                      ("EXP-OLD", "MKT-OLD", "offer-v1")):
            registries.add(self.db, "market_experiments", {
                "link_id": f"L-{exp}", "market_id": market, "experiment_id": exp, "layer": "DEMAND",
                "protocol": protocol, "exposure_event": "message_sent", "positive_event": "reply_meaningful"})
        self.n = 0

    def event(self, event_type, company, exp, recipient_class="named_buyer", value=0):
        self.n += 1
        record_event(self.db, {"event_type": event_type, "company": company, "experiment_id": exp,
                               "source": "t", "source_record_id": f"r{self.n}", "provenance": "operator_recorded",
                               "occurred_at": AT, "value_pence": value,
                               "metadata": {"recipient_class": recipient_class}})

    def market(self, data, market_id="MKT-PAY"):
        return next(m for m in data["markets"] if m["market_id"] == market_id)

    def test_access_and_response_are_counted_apart_and_variants_are_not_pooled(self):
        for co in ("a", "b", "c"):
            self.event("message_sent", co, "EXP-D")
        self.event("message_bounced", "c", "EXP-D")              # attempted, never delivered
        self.event("reply_meaningful", "a", "EXP-D")              # a reply proves delivery
        self.event("message_delivered", "b", "EXP-D")
        for co in ("d", "f"):
            self.event("message_sent", co, "EXP-O")
        self.event("message_delivered", "d", "EXP-O")
        self.event("message_sent", "e", "EXP-O", recipient_class="role_inbox")
        self.event("message_delivered", "e", "EXP-O", recipient_class="role_inbox")
        self.event("message_sent", "x", "EXP-OLD")              # parked market: not this cycle
        m = self.market(report(self.db))
        self.assertEqual((m["messages_attempted"], m["messages_delivered"], m["attempted_delivery_unverified"],
                          m["delivered_to_named_buyers"], m["meaningful_replies"]), (6, 4, 1, 3, 1))
        variants = {v["protocol"]: v for v in m["variants"]}
        self.assertEqual((variants["discovery-v1"]["delivered_to_named_buyers"],
                          variants["discovery-v1"]["meaningful_replies"]), (2, 1))
        self.assertEqual((variants["offer-v1"]["delivered_to_named_buyers"],
                          variants["offer-v1"]["meaningful_replies"]), (1, 0))
        self.assertIsNone(variants["discovery-v1"]["primary_rate"], "no rate below the minimum sample")
        self.assertEqual(report(self.db, min_delivered=2)["markets"][0]["variants"][0]["primary_rate"], 0.5)
        self.assertEqual([x["market_id"] for x in report(self.db)["markets"]], ["MKT-PAY"])
        self.assertEqual([x["market_id"] for x in readout(self.db)["markets"]], ["MKT-PAY"])

    def test_a_send_without_delivery_evidence_is_never_a_delivery(self):
        for co in ("a", "b"):
            self.event("message_sent", co, "EXP-O")
        m = self.market(report(self.db))
        self.assertEqual((m["messages_attempted"], m["attempted_delivery_unverified"],
                          m["delivered_to_named_buyers"]), (2, 2, 0))

    def test_evidence_gates(self):
        self.assertEqual([gate(n) for n in (0, 4, 5, 9, 10, 15, 29, 30)],
                         ["BELOW_FIRST_GATE", "BELOW_FIRST_GATE", "ROUTE_MECHANICS_REVIEW", "ROUTE_MECHANICS_REVIEW",
                          "CATASTROPHIC_MISMATCH_CHECK", "DIRECTIONAL_ENGAGEMENT_AND_PAIN",
                          "DIRECTIONAL_ENGAGEMENT_AND_PAIN", "COMPARISON_ALLOWED"])

    def test_replies_alone_never_raise_the_thesis_above_access_inconclusive(self):
        for co in ("a", "b"):
            self.event("message_sent", co, "EXP-D")
            self.event("reply_meaningful", co, "EXP-D")
        self.assertEqual(self.market(report(self.db))["thesis_state"], "ACCESS_INCONCLUSIVE")

    def test_recorded_pain_confirms_the_thesis_and_spend_outranks_it(self):
        self.event("message_sent", "a", "EXP-D")
        self.event("meeting_held", "a", "EXP-D")
        record_commercial_evidence(
            self.db, statement="Three analysts spend every morning chasing settlement exceptions by hand",
            categories=["PAIN_CONFIRMED"], source="call-notes", source_record_id="call-1", occurred_at=AT,
            company="a", experiment_id="EXP-D")
        m = self.market(report(self.db))
        self.assertEqual((m["pain_confirmations"], m["thesis_state"]), (1, "PAIN_CONFIRMED"))
        record_commercial_evidence(
            self.db, statement="We pay eighty thousand a year for the platform and still use Excel",
            categories=["BUDGET_SIGNAL"], source="call-notes", source_record_id="call-1b", occurred_at=AT,
            company="a", experiment_id="EXP-D")
        self.assertEqual(self.market(report(self.db))["thesis_state"], "SPEND_CONFIRMED")

    def test_classification_ladder(self):
        zero = {k: 0 for k in ("paid_commitments", "solution_requests", "spend_confirmations",
                               "pain_confirmations", "discovery_conversations")}
        self.assertEqual(classify(zero), "ACCESS_INCONCLUSIVE")
        self.assertEqual(classify({**zero, "discovery_conversations": 4}), "ACCESS_INCONCLUSIVE")
        self.assertEqual(classify({**zero, "discovery_conversations": 5}), "PAIN_NOT_CONFIRMED")
        self.assertEqual(classify({**zero, "solution_requests": 1}), "PAID_TEST_REQUESTED")
        self.assertEqual(classify({**zero, "paid_commitments": 1, "pain_confirmations": 1}), "PAID_COMMITMENT")
        self.assertEqual(classify({**zero, "pain_confirmations": 3}, status="stop_thesis"), "STOP_THESIS")

    def test_research_stages_are_unknown_without_an_evidence_set_and_gated_with_one(self):
        self.assertIsNone(self.market(report(self.db))["named_buyers"])
        self.assertIn("UNKNOWN", render(report(self.db)))
        full = {"market_id": "MKT-PAY", "company": "A", "person_name": "P", "role": "Head of Payments Ops",
                "evidence_trigger": "job ad", "evidence_quote": "q" * 25, "evidence_url": "https://a.example",
                "route_confidence": "medium", "route_searched": True, "route_found": True, "route_verified": True}
        rows = [full, {**full, "company": "B", "route_confidence": "low", "route_found": False, "route_verified": False},
                {**full, "company": "C", "person_name": ""},
                {**full, "company": "D", "evidence_trigger": ""}]
        m = self.market(report(self.db, rows))
        self.assertEqual((m["companies_researched"], m["qualified_companies"], m["named_buyers"],
                          m["verified_routes"], m["route_searched"], m["route_verified"],
                          m["route_unavailable"]), (4, 3, 2, 1, 2, 1, 1))

    def test_marketer_needs_a_variant_choice_and_refuses_a_parked_market(self):
        with self.assertRaises(MarketerError) as ctx:
            market_context(self.db, "MKT-PAY")
        self.assertEqual(ctx.exception.code, "variant_required")
        self.assertEqual(market_context(self.db, "MKT-PAY", "EXP-D")["protocol"], "discovery-v1")
        with self.assertRaises(MarketerError) as ctx:
            market_context(self.db, "MKT-PAY", "EXP-OLD")
        self.assertEqual(ctx.exception.code, "experiment_not_in_market")
        with self.assertRaises(MarketerError) as ctx:
            market_context(self.db, "MKT-OLD")
        self.assertEqual(ctx.exception.code, "market_not_active")


if __name__ == "__main__":
    unittest.main()
