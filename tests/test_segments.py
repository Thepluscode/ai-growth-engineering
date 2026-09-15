"""Segment performance and target / offer / route decisions. Expected values are hard-coded; the
evidence policy's thresholds are asserted at their boundaries, not read back from the policy."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering import registries
from ai_growth_engineering.buyer_truth import buyer_evidence, interpret, record_commercial_evidence
from ai_growth_engineering.funnel_events import record_event
from ai_growth_engineering.marketing_engineer import linked_events, recommend_next_experiment, render_status, status_report
from ai_growth_engineering.segments import (
    compare_segments, evidence_state, load_registry, recommend_acquisition_route, recommend_offer,
    recommend_target_segment, segment_performance,
)
from ai_growth_engineering.storage import init_db

AS_OF = "2026-09-15"


class SegmentCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)
        self.n = 0
        registries.add(self.db, "offers", {"offer_id": "OFF-A", "buyer": "b", "problem": "p", "outcome": "o",
                                           "price_pence": 120_000})
        registries.add(self.db, "offers", {"offer_id": "OFF-B", "buyer": "b", "problem": "p", "outcome": "o"})
        registries.add(self.db, "audiences", {"audience_id": "AUD-C", "audience_type": "cold", "source": "list"})
        for campaign, icp, offer in (("CMP-A", "Founders", "OFF-A"), ("CMP-B", "Founders", "OFF-B"),
                                     ("CMP-OPS", "Ops leads", "OFF-B")):
            registries.add(self.db, "campaigns", {"campaign_id": campaign, "channel": "email", "icp": icp,
                                                  "objective": "meeting_rate", "status": "active", "offer_id": offer,
                                                  "experiment_id": "EXP-ACQ-0009", "audience_id": "AUD-C"})

    def ev(self, event_type, company, **kw):
        self.n += 1
        values = {"event_type": event_type, "company": company, "occurred_at": "2026-08-01", "source": "test",
                  "source_record_id": f"r{self.n}", "provenance": "operator_recorded"}
        values.update(kw)
        return record_event(self.db, values)["event_id"]

    def buyers(self, prefix, n, *, campaign="CMP-A", channel="email", route="named_buyer", role="CEO",
               experiment="EXP-ACQ-0009", at="2026-08-01", kind="message_sent"):
        companies = [f"{prefix}{i}" for i in range(n)]
        metadata = {"role": role, "recipient_class": route} if kind == "message_sent" else {}
        for company in companies:
            self.ev(kind, company, campaign_id=campaign, channel=channel, experiment_id=experiment, occurred_at=at,
                    metadata=metadata)
        return companies

    def reach(self, companies, *event_types, **kw):
        for company in companies:
            for event_type in event_types:
                self.ev(event_type, company, occurred_at="2026-08-10", **kw)

    def perf(self, dimension, **kw):
        return segment_performance(linked_events(self.db), buyer_evidence(self.db), dimension, as_of=AS_OF,
                                   registry=load_registry(self.db), **kw)


class SegmentPerformanceTests(SegmentCase):
    def test_segments_come_only_from_recorded_fields_and_unknown_stays_unknown(self):
        self.buyers("a", 3, role="Head of Sales")
        self.ev("message_sent", "loose", channel="email")
        icp = self.perf("icp")
        self.assertEqual({s["value"]: s["counts"]["delivered"] for s in icp["segments"]}, {"Founders": 3, "UNKNOWN": 1})
        self.assertEqual({s["value"] for s in self.perf("price")["segments"]}, {"£1,200.00", "UNKNOWN"})
        self.assertEqual({s["value"] for s in self.perf("buyer_role")["segments"]}, {"Head of Sales", "UNKNOWN"})
        self.assertEqual(icp["not_recorded_dimensions"], ["company_type", "company_size", "geography", "buyer_seniority"])
        with self.assertRaises(ValueError):
            self.perf("geography")

    def test_a_missing_denominator_is_never_zero_and_fresh_sends_are_not_refusals(self):
        self.buyers("old", 5)
        self.buyers("new", 5, at="2026-09-10")
        [segment] = self.perf("icp")["segments"]
        rates = segment["rates"]
        self.assertEqual((rates["reply_rate"]["value"], rates["reply_rate"]["denominator"], rates["reply_rate"]["status"]),
                         (0.0, 5, "INSUFFICIENT_DATA"))
        self.assertEqual((rates["meeting_rate"]["value"], rates["meeting_rate"]["status"]), (None, "NOT_DERIVABLE"))
        self.assertEqual(rates["acceptance_rate"]["status"], "NOT_DERIVABLE")
        self.assertEqual(segment["economics"]["cac"]["status"], "NOT_DERIVABLE")
        self.assertIn("not per buyer_role", self.perf("buyer_role")["segments"][0]["economics"]["cac"]["reason"])

    def test_spend_reaches_a_segment_only_through_the_campaign_record(self):
        buyers = self.buyers("p", 3)
        self.reach(buyers[:1], "customer_won")
        self.ev("spend_recorded", "", campaign_id="CMP-A", value_pence=150_000, currency="GBP")
        [segment] = self.perf("campaign")["segments"]
        self.assertEqual(segment["economics"]["cac"]["value"], 150_000)

    def test_evidence_state_follows_the_declared_policy_and_one_customer_never_promotes(self):
        counts = {"delivered": 100, "matured_delivered": 100, "exposures": 100, "qualified_replies": 5, "customers": 0}
        self.assertEqual(evidence_state(counts), "DECISION_WORTHY")
        self.assertEqual(evidence_state({**counts, "qualified_replies": 4}), "DESCRIPTIVE")
        self.assertEqual(evidence_state({**counts, "matured_delivered": 99}), "DESCRIPTIVE")
        self.assertEqual(evidence_state({**counts, "delivered": 0}), "NO_DATA")
        paid = self.buyers("x", 5)
        self.reach(paid[:1], "payment_received", value_pence=150_000, currency="GBP")
        self.assertEqual(self.perf("icp")["segments"][0]["state"], "EARLY_SIGNAL")
        self.buyers("y", 24)
        self.assertEqual(self.perf("icp")["segments"][0]["state"], "EARLY_SIGNAL")
        self.buyers("z", 1)
        self.assertEqual(self.perf("icp")["segments"][0]["state"], "DESCRIPTIVE")

    def test_segment_truth_counts_organisations_and_withholds_a_thin_top_problem(self):
        buyers = self.buyers("t", 3)

        def say(company, statement):
            self.n += 1
            result = record_commercial_evidence(self.db, statement=statement, categories=("PROBLEM_STATED",),
                                                source="test", source_record_id=f"s{self.n}",
                                                occurred_at="2026-08-12", company=company)
            interpret(self.db, result["link_ids"][0], theme="traceability", interpretation="i", confidence=0.3,
                      interpreted_by="founder")

        for n in range(3):
            say(buyers[0], f"We cannot trace agent decisions, case {n}.")
        problems = self.perf("icp")["segments"][0]["buyer_truth"]["problems"]
        self.assertEqual((problems["organisations"], problems["top"]), (1, None))
        say(buyers[1], "We cannot trace agent decisions either.")
        top = self.perf("icp")["segments"][0]["buyer_truth"]["problems"]["top"]
        self.assertEqual((top["theme"], top["organisations"]), ("traceability", 2))


class ComparisonTests(SegmentCase):
    def test_more_replies_never_beats_more_customers_and_tiny_samples_decide_nothing(self):
        sales, ceo = self.buyers("s", 5, role="Head of Sales"), self.buyers("c", 5, role="CEO")
        self.reach(ceo[:1], "reply_meaningful", "meeting_held", "proposal_sent")
        self.reach(ceo[:1], "payment_received", value_pence=150_000, currency="GBP")
        self.reach(sales, "reply_received")
        tiny = compare_segments(self.perf("buyer_role"))
        self.assertEqual((tiny["ranked"], tiny["verdict"]["state"]), (["CEO", "Head of Sales"], "NOT_ENOUGH_EVIDENCE"))
        self.buyers("s2", 35, role="Head of Sales")
        self.buyers("c2", 35, role="CEO")
        verdict = compare_segments(self.perf("buyer_role"))["verdict"]
        self.assertEqual((verdict["state"], verdict["leader"], verdict["decided_on"], verdict["strength"]),
                         ("DESCRIPTIVE_LEAD", "CEO", "observed_revenue_pence", "DESCRIPTIVE"))
        self.assertIn("currently favours CEO", verdict["statement"])

    def test_a_cross_experiment_route_comparison_discloses_its_confounds(self):
        self.buyers("e", 3, route="role_inbox", experiment="EXP-ACQ-0001")
        self.buyers("l", 4, channel="linkedin", kind="invitation_sent", experiment="EXP-ACQ-0003", at="2026-09-01")
        comparison = compare_segments(self.perf("acquisition_route"))
        self.assertTrue(comparison["cross_experiment"])
        self.assertEqual(comparison["verdict"]["state"], "NOT_ENOUGH_EVIDENCE")
        self.assertIn("differ only in access", comparison["verdict"]["reason"])
        self.assertEqual({s["value"] for s in comparison["segments"]}, {"email/role_inbox", "linkedin/named_buyer_connection"})
        self.assertEqual({c["attribute"] for c in comparison["confounds"]}, {"experiment", "period", "cross_experiment"})

    def test_one_experiment_never_absorbs_another_experiments_exposure_of_the_same_buyer(self):
        # Regression: first-exposure assignment moved 31 real invitations into an earlier email segment.
        self.buyers("both", 2, route="role_inbox", experiment="EXP-ACQ-0001", at="2026-08-01")
        self.buyers("both", 2, channel="linkedin", kind="invitation_sent", experiment="EXP-ACQ-0003", at="2026-08-20")
        self.ev("payment_received", "both0", occurred_at="2026-09-01", value_pence=150_000, currency="GBP")
        performance = self.perf("acquisition_route")
        counts = {s["value"]: (s["counts"]["delivered"], s["counts"]["observed_revenue_pence"]) for s in performance["segments"]}
        self.assertEqual(counts, {"email/role_inbox": (2, 0), "linkedin/named_buyer_connection": (2, 150_000)})
        self.assertEqual(performance["overlapping_buyers"], 2)
        self.assertIn("overlap", {c["attribute"] for c in compare_segments(performance)["confounds"]})

    def test_an_offer_shown_to_a_different_audience_is_not_comparable(self):
        self.buyers("f", 40, campaign="CMP-A")
        self.buyers("o", 40, campaign="CMP-OPS")
        self.assertEqual(recommend_offer(self.db, as_of=AS_OF)["recommended"], "NOT_COMPARABLE")

    def test_offers_seen_by_the_same_buyer_context_are_compared(self):
        offer_a = self.buyers("a", 40, campaign="CMP-A")
        self.buyers("b", 40, campaign="CMP-B")
        self.reach(offer_a[:4], "reply_meaningful", "meeting_held", "proposal_sent")
        rec = recommend_offer(self.db, as_of=AS_OF)
        self.assertEqual((rec["recommended"], rec["evidence_strength"], rec["context"]),
                         ("OFF-A", "DESCRIPTIVE", {"icp": "Founders", "audience_type": "cold"}))

    def test_access_that_downstream_evidence_contradicts_is_disclosed(self):
        email = self.buyers("e", 35)
        for i in range(25):
            self.ev("message_bounced", f"eb{i}", channel="email", campaign_id="CMP-A", experiment_id="EXP-ACQ-0009",
                    metadata={"recipient_class": "named_buyer"})
        self.reach(email[:5], "reply_meaningful")
        self.reach(email[:2], "meeting_held")
        invited = self.buyers("l", 40, channel="linkedin", kind="invitation_sent")
        self.reach(invited[:30], "invitation_accepted")
        self.reach(invited[:1], "reply_meaningful")
        rec = recommend_acquisition_route(self.db, as_of=AS_OF)
        self.assertEqual((rec["recommended"], rec["evidence_strength"]), ("email/named_buyer", "DESCRIPTIVE"))
        self.assertIn("linkedin/named_buyer_connection leads on access", rec["access_vs_downstream"])


class DecisionTests(SegmentCase):
    def test_a_target_is_recommended_only_when_the_policy_allows(self):
        ceo = self.buyers("c", 5, role="CEO")
        self.buyers("s", 5, role="Head of Sales")
        self.reach(ceo[:3], "reply_meaningful")
        thin = recommend_target_segment(self.db, as_of=AS_OF)
        self.assertEqual((thin["recommended"], thin["best_early_signal"]["value"]), ("NOT_ENOUGH_EVIDENCE", "CEO"))
        self.buyers("c2", 35, role="CEO")
        self.buyers("s2", 35, role="Head of Sales")
        rec = recommend_target_segment(self.db, as_of=AS_OF)
        self.assertEqual((rec["recommended"], rec["dimension"], rec["evidence_strength"]), ("CEO", "buyer_role", "DESCRIPTIVE"))
        self.assertEqual(rec["commercial_performance"]["qualified_replies"], 3)
        self.assertIn("survives", rec["main_uncertainty"])

    def test_a_clear_target_with_an_unclear_offer_proposes_testing_only_the_offer(self):
        ceo = self.buyers("c", 110, role="CEO")
        self.buyers("s", 110, role="Head of Sales")
        self.reach(ceo[:6], "reply_meaningful", "meeting_held")
        self.assertEqual(recommend_target_segment(self.db, as_of=AS_OF)["evidence_strength"], "DECISION_WORTHY")
        preferred = recommend_next_experiment(self.db, as_of=AS_OF)["preferred"]
        self.assertEqual((preferred["status"], preferred["single_variable"]), ("PROPOSED_NEEDS_CONTRACT", "offer"))
        self.assertIn("buyer_role = CEO", preferred["hypothesis"])

    def test_status_shows_decisions_only_with_exposure_and_never_a_fake_ranking(self):
        self.assertNotIn("TARGET / OFFER / ROUTE", render_status(status_report(self.db, as_of=AS_OF)))
        self.buyers("a", 3)
        text = render_status(status_report(self.db, as_of=AS_OF))
        self.assertIn("who to target: NOT_ENOUGH_EVIDENCE", text)
        self.assertIn("best offer: NOT_ENOUGH_EVIDENCE — only one offer observed (OFF-A)", text)


if __name__ == "__main__":
    unittest.main()
