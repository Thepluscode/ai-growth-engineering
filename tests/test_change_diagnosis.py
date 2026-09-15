"""Performance-change diagnosis on synthetic stores. Each case is one of the required diagnoses;
expected labels and values are hard-coded."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering import registries
from ai_growth_engineering.buyer_truth import interpret, record_commercial_evidence
from ai_growth_engineering.change_diagnosis import ChangeError, diagnose_change, render_change
from ai_growth_engineering.funnel_events import record_event
from ai_growth_engineering.marketing_engineer import recommend_next_experiment, render_status, status_report
from ai_growth_engineering.models import ExperimentSpec
from ai_growth_engineering.registry import add_experiment
from ai_growth_engineering.storage import init_db

AS_OF = "2026-09-30"
BASELINE = {"start": "2026-08-01", "end": "2026-08-07"}
COMPARISON = {"start": "2026-08-08", "end": "2026-08-14"}


class ChangeCase(unittest.TestCase):
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
        registries.add(self.db, "audiences", {"audience_id": "AUD-R", "audience_type": "retargeting", "source": "site"})
        for creative, hook, cta in (("CR-A", "I noticed a leak", "Want it?"), ("CR-B", "Your pipeline is stalling", "Want it?"),
                                    ("CR-C", "I noticed a leak", "Book a call")):
            registries.add(self.db, "creatives", {"creative_id": creative, "buyer": "b", "problem": "p", "hook": hook,
                                                  "body": "One bounded test.", "cta": cta})
        for campaign, icp, offer, audience in (("CMP-F", "Founders", "OFF-A", "AUD-C"), ("CMP-O", "Ops leads", "OFF-A", "AUD-C"),
                                               ("CMP-X", "Ops leads", "OFF-B", "AUD-R")):
            registries.add(self.db, "campaigns", {"campaign_id": campaign, "channel": "email", "icp": icp,
                                                  "objective": "reply_rate", "status": "active", "offer_id": offer,
                                                  "experiment_id": "EXP-ACQ-0009", "audience_id": audience})

    def ev(self, event_type, company="", **kw):
        self.n += 1
        values = {"event_type": event_type, "company": company, "occurred_at": "2026-08-01", "source": "test",
                  "source_record_id": f"r{self.n}", "provenance": "operator_recorded", "experiment_id": "EXP-ACQ-0009"}
        values.update(kw)
        return record_event(self.db, values)["event_id"]

    def cohort(self, prefix, n, at, *, replies=0, campaign="CMP-F", creative="CR-A", arm="", kind="message_sent",
               channel="email"):
        companies = [f"{prefix}{i}" for i in range(n)]
        metadata = {"recipient_class": "named_buyer"} if kind == "message_sent" else {}
        for i, company in enumerate(companies):
            self.ev(kind, company, occurred_at=at, campaign_id=campaign, creative_id=creative, arm=arm, channel=channel,
                    metadata=metadata)
            if i < replies:
                self.ev("reply_received", company, occurred_at=at, campaign_id=campaign, arm=arm)
        return companies

    def diagnose(self, baseline=BASELINE, comparison=COMPARISON, as_of=AS_OF):
        return diagnose_change(self.db, baseline, comparison, as_of=as_of)


class DiagnosisCaseTests(ChangeCase):
    def test_a_only_the_creative_changed(self):
        self.cohort("a", 60, "2026-08-02", replies=30, creative="CR-A")
        self.cohort("b", 60, "2026-08-09", replies=12, creative="CR-B")
        d = self.diagnose()
        self.assertEqual((d["classification"], d["comparison_state"], d["lead_change"]["metric"]),
                         ("POSSIBLE_CREATIVE_EFFECT", "CLEAN_COMPARISON", "reply_rate"))
        self.assertAlmostEqual(d["lead_change"]["absolute"], -0.30)
        self.assertAlmostEqual(d["lead_change"]["relative"], -0.60)
        self.assertEqual({c["input"] for c in d["what_changed"]}, {"creative", "hook"})
        self.assertTrue({"icp", "offer", "channel", "audience_type", "body", "cta"} <= set(d["what_stayed_constant"]))
        self.assertIn("plausible explanation", d["supported_interpretation"])
        self.assertTrue(any("caused" in claim for claim in d["unsupported_claims"]))
        self.assertEqual(d["next_test"]["variable"], "hook")
        self.assertIn("-30.0 percentage points, -60%", render_change(d))

    def test_b_the_icp_mix_shifted(self):
        self.cohort("f", 48, "2026-08-02", replies=24, campaign="CMP-F")
        self.cohort("o", 12, "2026-08-02", replies=2, campaign="CMP-O")
        self.cohort("g", 18, "2026-08-09", replies=9, campaign="CMP-F")
        self.cohort("p", 42, "2026-08-09", replies=4, campaign="CMP-O")
        d = self.diagnose()
        self.assertEqual((d["classification"], d["comparison_state"]), ("MIX_SHIFT", "PARTIALLY_CONFOUNDED"))
        self.assertIn("mix shift in icp (Founders 80%, Ops leads 20% → Ops leads 70%, Founders 30%)",
                      d["supported_interpretation"])
        self.assertEqual(d["next_test"]["variable"], "audience")

    def test_c_revenue_falls_while_ctr_improves_so_the_diagnosis_stays_near_revenue(self):
        for prefix, at, payments, clicks in (("a", "2026-08-02", 5, 200), ("b", "2026-08-09", 2, 320)):
            buyers = self.cohort(prefix, 60, at)
            for i, company in enumerate(buyers[:10]):
                for event_type in ("reply_meaningful", "meeting_held", "proposal_sent"):
                    self.ev(event_type, company, occurred_at=at, campaign_id="CMP-F")
                if i < payments:
                    self.ev("payment_received", company, occurred_at=at, value_pence=150_000, currency="GBP")
            self.ev("impression", occurred_at=at, campaign_id="CMP-F", quantity=10_000)
            self.ev("click", occurred_at=at, campaign_id="CMP-F", quantity=clicks)
        d = self.diagnose()
        by_metric = {x["metric"]: x for x in d["deltas"]}
        self.assertEqual((d["classification"], d["lead_change"]["metric"]), ("DETERIORATED", "observed_revenue_pence"))
        self.assertEqual((by_metric["ctr"]["direction"], by_metric["ctr"]["meaningful"]), ("improved", True))
        self.assertEqual(by_metric["close_rate"]["status"], "INSUFFICIENT_DATA")
        self.assertIn("Near the revenue transition: customers: 5 → 2", d["supported_interpretation"])
        self.assertIn("ctr moved the other way and did not carry through to revenue", d["supported_interpretation"])

    def test_d_arms_of_one_experiment_with_one_declared_variable_support_attribution(self):
        add_experiment(self.db, ExperimentSpec(experiment_id="EXP-ACQ-0009", hypothesis="h", primary_metric="reply_rate",
                                               success_threshold=0.3, review_threshold=0.1, minimum_sample=60,
                                               control="Want it?", variant="Book a call", variable="cta"))
        self.cohort("c", 60, "2026-08-02", replies=12, creative="CR-A", arm="control")
        self.cohort("v", 60, "2026-08-03", replies=30, creative="CR-C", arm="variant")
        d = self.diagnose({**BASELINE, "arm": "control"}, {**BASELINE, "arm": "variant"})
        self.assertEqual((d["classification"], d["controlled_by"]),
                         ("CONTROLLED_EFFECT", {"experiment_id": "EXP-ACQ-0009", "variable": "cta"}))
        self.assertIn("attributable to cta, within the limits of that experiment", d["supported_interpretation"])
        # An arm that also changed the hook is not controlled by a cta experiment.
        self.cohort("x", 60, "2026-08-04", replies=30, creative="CR-B", arm="variant2")
        self.assertEqual(self.diagnose({**BASELINE, "arm": "control"}, {**BASELINE, "arm": "variant2"})["classification"],
                         "POSSIBLE_CREATIVE_EFFECT")
        # The same numbers across two time windows are not a controlled result.
        self.cohort("w", 60, "2026-08-09", replies=30, creative="CR-C")
        self.assertEqual(self.diagnose(BASELINE, COMPARISON)["classification"], "POSSIBLE_CREATIVE_EFFECT")

    def test_e_outcomes_still_inside_the_response_window_are_insufficient_data(self):
        self.cohort("a", 60, "2026-09-20", replies=30)
        self.cohort("b", 60, "2026-09-24", replies=5)
        d = self.diagnose({"start": "2026-09-20", "end": "2026-09-22"}, {"start": "2026-09-23", "end": "2026-09-25"})
        self.assertEqual((d["classification"], d["baseline"]["maturity"], d["comparison"]["maturity"]),
                         ("INSUFFICIENT_DATA", "IMMATURE", "IMMATURE"))
        self.assertEqual(d["baseline"]["matures_between"], ["2026-10-04", "2026-10-04"])
        self.assertIsNone(d["next_test"]["variable"])

    def test_e2_tiny_mature_windows_are_insufficient_not_unchanged(self):
        # Regression: 0 -> 0 counts on a five-buyer window were read as a measured non-change.
        self.cohort("a", 45, "2026-08-02")
        self.cohort("b", 5, "2026-08-09")
        d = self.diagnose()
        self.assertEqual((d["classification"], d["comparison"]["maturity"]), ("INSUFFICIENT_DATA", "MATURE"))
        self.assertIn("no rate has 30+ observations in both windows", d["reason"])

    def test_f_everything_changed_at_once(self):
        self.cohort("a", 60, "2026-08-02", replies=30, campaign="CMP-F", creative="CR-A")
        self.cohort("b", 60, "2026-08-09", replies=10, campaign="CMP-X", creative="CR-B", kind="invitation_sent",
                    channel="linkedin")
        d = self.diagnose()
        self.assertEqual((d["classification"], d["comparison_state"]), ("MULTIPLE_CONFOUNDS", "HEAVILY_CONFOUNDED"))
        self.assertEqual((d["next_test"]["variable"], d["next_test"]["hold_constant"]),
                         ("recipient_route", ["ICP", "audience", "offer", "message"]))

    def test_g_no_meaningful_change_and_buyer_truth_never_becomes_the_market(self):
        base = self.cohort("a", 60, "2026-08-02", replies=30)
        comp = self.cohort("b", 60, "2026-08-09", replies=28)
        for company, theme in ((base[0], "roi-proof"), (comp[0], "production-access")):
            self.n += 1
            result = record_commercial_evidence(self.db, statement="We would need to see this first.",
                                                categories=("OBJECTION",), source="test", source_record_id=f"s{self.n}",
                                                occurred_at="2026-08-12", company=company)
            interpret(self.db, result["link_ids"][0], theme=theme, interpretation="i", confidence=0.3, interpreted_by="founder")
        d = self.diagnose()
        self.assertEqual(d["classification"], "NO_MEASURABLE_CHANGE")
        self.assertEqual(d["buyer_truth_change"]["OBJECTION"]["comparison"], {"production-access": 1})
        self.assertTrue(any(claim.startswith("The market changed") for claim in d["unsupported_claims"]))


class ChangeIntegrationTests(ChangeCase):
    def test_a_window_must_be_explicit_and_valid(self):
        with self.assertRaises(ChangeError):
            self.diagnose({"start": "2026-08-07", "end": "2026-08-01"}, COMPARISON)
        with self.assertRaises(ChangeError):
            self.diagnose({"start": "last week", "end": "2026-08-01"}, COMPARISON)

    def test_a_diagnosis_proposes_one_variable_and_the_status_shows_it(self):
        self.assertNotIn("WHY PERFORMANCE CHANGED", render_status(status_report(self.db, as_of="2026-08-28")))
        self.cohort("a", 60, "2026-08-02", replies=30, campaign="CMP-F", creative="CR-A")
        self.cohort("b", 60, "2026-08-09", replies=10, campaign="CMP-X", creative="CR-B", kind="invitation_sent",
                    channel="linkedin")
        preferred = recommend_next_experiment(self.db, as_of="2026-08-28")["preferred"]
        self.assertEqual((preferred["status"], preferred["single_variable"]), ("PROPOSED_NEEDS_CONTRACT", "recipient_route"))
        self.assertIn("two time windows are not two arms", preferred["sample_and_stopping_rule"])
        text = render_status(status_report(self.db, as_of="2026-08-28"))
        self.assertIn("WHY PERFORMANCE CHANGED  [", text)
        self.assertIn("MULTIPLE_CONFOUNDS (HEAVILY_CONFOUNDED)", text)


if __name__ == "__main__":
    unittest.main()
