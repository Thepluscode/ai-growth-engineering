"""The revenue loop: append-only events, deterministic metrics, attribution, money graph,
evaluation and the next experiment. Every expected number is hard-coded, never recomputed
from the code under test."""
from __future__ import annotations

import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering.execution import freeze_execution_cohort, record_invitation
from ai_growth_engineering.funnel_events import (
    EventError, correct_event, effective_events, import_invitations, import_outreach_csv, record_event,
)
from ai_growth_engineering import registries
from ai_growth_engineering.marketing_engineer import (
    RECOMMENDATION_FIELDS, _keep_constant, campaign_graph, customer_graph, evaluate, next_experiment_card,
    recommend_next_experiment, render_card, render_status, status_report,
)
from ai_growth_engineering.models import ExperimentSpec
from ai_growth_engineering.registry import add_experiment, set_execution_mode
from ai_growth_engineering.revenue_loop import (
    attribute, compute_metrics, diagnose_funnel, funnel, money_graph_for_campaign, money_graph_for_entity,
)
from ai_growth_engineering.signal_intelligence import add_identity
from ai_growth_engineering.storage import connect, init_db


class StoreCase(unittest.TestCase):
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
        return record_event(self.db, values)

    def many(self, count, event_type, **kw):
        for i in range(count):
            self.ev(event_type, **{"company": f"buyer-{event_type}-{i}", **kw})

    def freeze_supply(self, cohort_id):
        with connect(self.db) as con:
            con.execute("INSERT INTO prospects(id, company, status) VALUES (1, 'Acme', 'qualified_batch_01')")
        url = "https://www.linkedin.com/in/acme-md"
        add_identity(self.db, {"prospect_id": 1, "identity_type": "linkedin", "value": url,
                               "provider": "test", "verification_status": "observed_published",
                               "source_url": url, "observed_at": "2026-09-01T00:00:00+00:00",
                               "confidence": 0.8})
        freeze_execution_cohort(self.db, cohort_id)

    def experiment(self, experiment_id, **kw):
        add_experiment(self.db, ExperimentSpec(
            experiment_id=experiment_id, hypothesis=f"{experiment_id} hypothesis",
            primary_metric=kw.pop("primary_metric", "accept_rate"), success_threshold=0.5,
            review_threshold=0.2, minimum_sample=30, **kw))


class EventLogTests(StoreCase):
    def test_the_log_refuses_update_and_delete(self):
        event_id = self.ev("message_sent", company="Acme")["event_id"]
        # Autocommit, so the refused statement leaves no open transaction locking the store.
        con = sqlite3.connect(self.db, isolation_level=None)
        self.addCleanup(con.close)
        for sql in ("UPDATE funnel_events SET company = 'Other' WHERE event_id = ?",
                    "DELETE FROM funnel_events WHERE event_id = ?"):
            with self.assertRaisesRegex(sqlite3.DatabaseError, "append-only"):
                con.execute(sql, (event_id,))
        self.assertEqual(effective_events(self.db)[0]["company"], "Acme")

    def test_the_same_source_record_is_logged_once(self):
        first = self.ev("message_sent", company="Acme", source_record_id="send-1")
        again = self.ev("message_sent", company="Acme", source_record_id="send-1")
        self.assertEqual((first["inserted"], again["inserted"]), (True, False))
        self.assertEqual(len(effective_events(self.db)), 1)

    def test_a_correction_voids_an_event_without_rewriting_it(self):
        keep = self.ev("message_sent", company="Acme")["event_id"]
        wrong = self.ev("reply_meaningful", company="Acme")["event_id"]
        correct_event(self.db, wrong, "reply was an out-of-office")
        self.assertEqual([e["event_id"] for e in effective_events(self.db)], [keep])
        with connect(self.db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM funnel_events").fetchone()[0], 3)
            self.assertIsNotNone(con.execute("SELECT 1 FROM funnel_events WHERE event_id = ?", (wrong,)).fetchone())

    def test_corrections_cannot_be_stacked_reused_or_unexplained(self):
        wrong = self.ev("reply_meaningful", company="Acme", source_record_id="reply-1")["event_id"]
        with self.assertRaises(EventError) as ctx:
            correct_event(self.db, wrong, "  ")
        self.assertEqual(ctx.exception.code, "reason_required")
        correction = correct_event(self.db, wrong, "duplicate")["event_id"]
        for target, code in ((wrong, "already_corrected"), (correction, "correction_of_correction")):
            with self.assertRaises(EventError) as ctx:
                correct_event(self.db, target, "again")
            self.assertEqual(ctx.exception.code, code)
        with self.assertRaises(EventError) as ctx:
            self.ev("reply_meaningful", company="Acme", source_record_id="reply-1")
        self.assertEqual(ctx.exception.code, "voided_event_reused")

    def test_malformed_events_are_refused(self):
        cases = [
            ({"event_type": "sale"}, "unknown_event_type"),
            ({"event_type": "message_sent", "company": "A", "source": ""}, "missing_source"),
            ({"event_type": "message_sent", "company": "A", "provenance": "guess"}, "invalid_provenance"),
            ({"event_type": "click", "value_pence": 100, "currency": "GBP"}, "value_not_allowed"),
            ({"event_type": "payment_received", "company": "A", "value_pence": 100}, "currency_required"),
            ({"event_type": "payment_received", "company": "A", "value_pence": -5, "currency": "GBP"},
             "negative_value"),
            ({"event_type": "reply_meaningful", "company": "A", "quantity": 3}, "quantity_not_allowed"),
            ({"event_type": "meeting_booked"}, "entity_required"),
            ({"event_type": "message_sent", "company": "A", "occurred_at": "last week"}, "invalid_occurred_at"),
        ]
        for overrides, code in cases:
            with self.subTest(code=code), self.assertRaises(EventError) as ctx:
                self.ev(**overrides)
            self.assertEqual(ctx.exception.code, code)

    def test_synthetic_fixtures_never_count_as_market_evidence(self):
        self.ev("payment_received", company="Demo", value_pence=500_000, currency="GBP",
                provenance="synthetic_fixture")
        self.assertEqual(effective_events(self.db), [])
        self.assertEqual(len(effective_events(self.db, include_synthetic=True)), 1)
        self.assertEqual(status_report(self.db)["totals"]["revenue_pence"], 0)


class MetricsTests(StoreCase):
    def test_the_worked_example_reproduces_every_number_in_the_brief(self):
        self.ev("spend_recorded", value_pence=100_000, currency="GBP", campaign_id="CMP-1")
        self.ev("impression", quantity=200_000, campaign_id="CMP-1")
        self.ev("click", quantity=4_000, campaign_id="CMP-1")
        for event_type, count in (("lead_created", 120), ("lead_qualified", 24), ("meeting_booked", 10),
                                  ("proposal_sent", 4), ("customer_won", 2)):
            self.many(count, event_type, campaign_id="CMP-1")
        for i in range(2):
            self.ev("payment_received", company=f"customer-{i}", value_pence=600_000, currency="GBP",
                    campaign_id="CMP-1")
        metrics = compute_metrics(effective_events(self.db))["metrics"]
        expected = {"cpm": 500, "ctr": 0.02, "cpc": 25, "lead_cvr": 0.03, "cpl": 833,
                    "qualified_cpl": 4_167, "cost_per_meeting": 10_000, "cac": 50_000, "roas": 12.0}
        self.assertEqual({k: metrics[k]["value"] for k in expected}, expected)
        self.assertEqual(metrics["cpl"]["definition"], "spend / leads")

    def test_unasked_and_unfunded_are_not_zero(self):
        self.many(3, "message_sent")
        metrics = compute_metrics(effective_events(self.db))["metrics"]
        self.assertEqual(metrics["meaningful_reply_rate"]["value"], 0.0)
        self.assertIsNone(metrics["reply_to_meeting_rate"]["value"])
        self.assertEqual(metrics["reply_to_meeting_rate"]["reason"], "denominator_zero")
        self.assertIsNone(metrics["cac"]["value"])
        self.assertEqual(metrics["cac"]["reason"], "spend_not_recorded")

    def test_recorded_zero_spend_is_a_real_zero(self):
        self.ev("spend_recorded", value_pence=0)
        self.ev("lead_created", company="A")
        self.assertEqual(compute_metrics(effective_events(self.db))["metrics"]["cpl"]["value"], 0)

    def test_funnel_reports_count_conversion_and_drop_off(self):
        self.many(10, "message_sent")
        self.many(2, "reply_meaningful")
        steps = funnel(effective_events(self.db), "outbound")
        self.assertEqual([s["count"] for s in steps[:3]], [10, 2, 0])
        self.assertEqual((steps[1]["conversion_from_previous"], steps[1]["drop_off"]), (0.2, 8))
        self.assertEqual(steps[2]["conversion_from_previous"], 0.0)
        self.assertIsNone(steps[3]["conversion_from_previous"])

    def test_money_in_two_currencies_is_not_summed(self):
        self.ev("payment_received", company="A", value_pence=100, currency="GBP")
        self.ev("payment_received", company="B", value_pence=100, currency="USD")
        with self.assertRaisesRegex(ValueError, "currencies"):
            compute_metrics(effective_events(self.db))


class AttributionTests(StoreCase):
    def journey(self):
        for day, campaign in (("2026-09-01", "C1"), ("2026-09-03", "C2"), ("2026-09-05", "C3")):
            self.ev("message_sent", company="Acme", occurred_at=day, campaign_id=campaign,
                    experiment_id="EXP-ACQ-0009", arm="variant")
        self.ev("message_sent", company="Acme", occurred_at="2026-09-20", campaign_id="C4")
        self.ev("meeting_booked", company="Acme", occurred_at="2026-09-07")
        self.ev("proposal_sent", company="Acme", occurred_at="2026-09-08", value_pence=300_000, currency="GBP")
        self.ev("customer_won", company="Acme", occurred_at="2026-09-10")
        self.ev("payment_received", company="Acme", occurred_at="2026-09-10", value_pence=1_000, currency="GBP")
        return effective_events(self.db)

    def test_each_model_assigns_whole_pence_that_sum_to_the_payment(self):
        events = self.journey()
        shares = {m: attribute(events, m)[0]["attributed_pence"] for m in ("first_touch", "last_touch", "linear")}
        self.assertEqual(shares, {"first_touch": [1_000, 0, 0], "last_touch": [0, 0, 1_000],
                                  "linear": [333, 333, 334]})
        linear = attribute(events, "linear")[0]
        self.assertEqual([t["campaign_id"] for t in linear["touchpoints"]], ["C1", "C2", "C3"])
        self.assertEqual(linear["unattributed_pence"], 0)

    def test_a_payment_with_no_touch_is_unattributed_not_guessed(self):
        self.ev("payment_received", company="Walk-in", value_pence=5_000, currency="GBP")
        record = attribute(effective_events(self.db), "linear")[0]
        self.assertEqual((record["touchpoints"], record["unattributed_pence"]), ([], 5_000))

    def test_the_money_graph_traces_a_pound_back_to_campaign_and_arm(self):
        events = self.journey()
        graph = money_graph_for_entity(events, "Acme")
        self.assertEqual([s["event_type"] for s in graph["chain"]][:4], ["message_sent"] * 3 + ["meeting_booked"])
        self.assertEqual(graph["revenue_pence"], 1_000)
        self.assertIn(("EXP-ACQ-0009", "variant"), graph["experiments"])
        campaign = money_graph_for_campaign(events, "C1")
        self.assertEqual((campaign["customers"], campaign["pipeline_pence"]), (["acme"], 300_000))
        self.assertEqual(campaign["attributed_revenue_pence"], {"first_touch": 1_000, "last_touch": 0, "linear": 333})
        self.assertIsNone(campaign["roas"]["linear"])


class EvaluatorTests(StoreCase):
    def test_attention_and_buyer_quality_are_separated(self):
        for creative, clicks, leads, qualified in (("Creative A", 42, 25, 2), ("Creative B", 21, 13, 4)):
            self.ev("impression", quantity=1_000, creative_id=creative, experiment_id="EXP-PAID-0001")
            self.ev("click", quantity=clicks, creative_id=creative, experiment_id="EXP-PAID-0001")
            self.many(leads, "lead_created", creative_id=creative, experiment_id="EXP-PAID-0001")
            self.many(qualified, "lead_qualified", creative_id=creative, experiment_id="EXP-PAID-0001")
        finding = next(f for f in evaluate(effective_events(self.db)) if f["kind"] == "attention_vs_quality")
        self.assertIn("Creative A wins attention; Creative B wins buyer quality", finding["interpretation"])
        self.assertEqual((finding["proposed_test_variable"], finding["primary_metric"]), ("hook", "qualified_lead_rate"))
        for key in ("observation", "evidence", "interpretation", "proposed_action", "why_not_other_metric"):
            self.assertTrue(finding[key], key)

    def test_zero_below_the_minimum_is_not_a_rejection(self):
        self.many(10, "message_sent", experiment_id="EXP-ACQ-0009")
        [finding] = evaluate(effective_events(self.db))
        self.assertEqual(finding["kind"], "unmeasured_not_rejected")
        self.assertIsNone(finding["proposed_test_variable"])

    def test_a_measured_zero_through_shared_inboxes_points_at_the_route(self):
        self.many(48, "message_sent", experiment_id="EXP-ACQ-0009", metadata={"recipient_class": "role_inbox"})
        self.many(2, "message_sent", experiment_id="EXP-ACQ-0009", metadata={"recipient_class": "named_buyer"})
        [finding] = evaluate(effective_events(self.db))
        self.assertEqual((finding["kind"], finding["proposed_test_variable"]), ("leak", "recipient_route"))
        self.assertEqual(finding["evidence"]["by_recipient_class"], {"role_inbox": 48, "named_buyer": 2})

    def test_an_experiments_own_minimum_sample_decides_whether_a_zero_is_measured(self):
        self.many(40, "message_sent", experiment_id="EXP-ACQ-0009")
        events = effective_events(self.db)
        self.assertEqual(evaluate(events)[0]["kind"], "leak")
        self.assertEqual(evaluate(events, minimums={"EXP-ACQ-0009": 51})[0]["kind"], "unmeasured_not_rejected")

    def test_experiments_are_never_pooled(self):
        self.many(20, "message_sent", experiment_id="EXP-ACQ-0008")
        self.many(20, "message_sent", experiment_id="EXP-ACQ-0009")
        kinds = {f["experiment_id"]: f["kind"] for f in evaluate(effective_events(self.db))}
        self.assertEqual(kinds, {"EXP-ACQ-0008": "unmeasured_not_rejected",
                                 "EXP-ACQ-0009": "unmeasured_not_rejected"})


class RecommendationTests(StoreCase):
    def test_a_frozen_unrun_experiment_is_preferred_over_designing_a_new_one(self):
        self.experiment("EXP-ACQ-0008", primary_metric="meaningful_reply_rate")
        self.experiment("EXP-ACQ-0009", channel="linkedin/named_buyer", control="email",
                        variant="linkedin", variable="channel")
        self.freeze_supply("EXP-ACQ-0009")
        self.many(50, "message_sent", experiment_id="EXP-ACQ-0007", metadata={"recipient_class": "role_inbox"})
        rec = recommend_next_experiment(self.db)
        preferred = rec["preferred"]
        self.assertEqual((preferred["status"], preferred["experiment_id"]), ("PREREGISTERED_UNRUN", "EXP-ACQ-0009"))
        self.assertEqual(set(preferred), set(RECOMMENDATION_FIELDS))
        for field in RECOMMENDATION_FIELDS:
            if field != "previous_experiments":
                self.assertTrue(preferred[field], field)
        self.assertEqual(preferred["single_variable"], "channel")
        statuses = {(a["status"], a.get("experiment_id")) for a in rec["alternatives"]}
        self.assertIn(("PREREGISTERED_BLOCKED", "EXP-ACQ-0008"), statuses)
        self.assertIn(("PROPOSED_NEEDS_CONTRACT", None), statuses)

    def test_without_a_runnable_experiment_a_leak_becomes_a_proposal_that_invents_nothing(self):
        self.many(50, "message_sent", experiment_id="EXP-ACQ-0007")
        preferred = recommend_next_experiment(self.db)["preferred"]
        self.assertEqual((preferred["status"], preferred["single_variable"]), ("PROPOSED_NEEDS_CONTRACT", "cta"))
        self.assertIn("does not invent", preferred["variant"])

    def test_with_nothing_observed_there_is_no_basis_for_a_test(self):
        self.assertEqual(recommend_next_experiment(self.db)["preferred"]["status"], "NO_BASIS")


class AdapterTests(StoreCase):
    def test_a_send_log_becomes_events_exactly_once(self):
        path = Path(self.tmp.name) / "outreach.csv"
        fields = ["date_first_contact", "company", "recipient", "role", "recipient_class", "channel",
                  "stage", "message_variant", "meaningful_reply"]
        rows = [
            ["2026-08-19", "Alpha", "A. Person", "CEO", "named_buyer", "email", "sent_awaiting_reply", "V1", "yes"],
            ["2026-08-19", "Beta", "B. Person", "MD", "role_inbox", "email", "bounced", "V1", ""],
            ["", "Gamma", "C. Person", "MD", "role_inbox", "email", "sent_awaiting_reply", "V1", ""],
        ]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(fields)
            writer.writerows(rows)
        first = import_outreach_csv(self.db, str(path), experiment_id="EXP-ACQ-0009", campaign_id="CMP-1")
        self.assertEqual(first, {"inserted": 3, "already_present": 0, "incomplete_rows": 1})
        self.assertEqual(import_outreach_csv(self.db, str(path), experiment_id="EXP-ACQ-0009",
                                             campaign_id="CMP-1")["inserted"], 0)
        events = {e["event_type"]: e for e in effective_events(self.db)}
        self.assertEqual(set(events), {"message_sent", "message_bounced", "reply_meaningful"})
        self.assertTrue(events["reply_meaningful"]["metadata"]["occurred_at_is_send_date"])
        self.assertEqual(events["message_sent"]["creative_id"], "V1")
        with self.assertRaises(EventError):
            import_outreach_csv(self.db, str(path), experiment_id=" ")

    def test_a_withdrawn_acceptance_is_corrected_not_left_standing(self):
        self.freeze_supply("EXP-ACQ-0009")
        record_invitation(self.db, "EXP-ACQ-0009", 1,
                          {"outcome": "accepted", "submitted_at": "2026-09-15", "accepted_at": "2026-09-16"})
        self.assertEqual(import_invitations(self.db, "EXP-ACQ-0009")["inserted"], 2)
        record_invitation(self.db, "EXP-ACQ-0009", 1, {"outcome": "withdrawn", "submitted_at": "2026-09-15"})
        self.assertEqual(import_invitations(self.db, "EXP-ACQ-0009")["corrected"], 1)
        self.assertEqual([e["event_type"] for e in effective_events(self.db)], ["invitation_sent"])


    def test_an_undeliverable_invitation_is_an_attempt_never_an_exposure(self):
        self.freeze_supply("EXP-ACQ-0009")
        record_invitation(self.db, "EXP-ACQ-0009", 1, {"outcome": "pending", "submitted_at": "2026-09-15"})
        import_invitations(self.db, "EXP-ACQ-0009")
        record_invitation(self.db, "EXP-ACQ-0009", 1, {"outcome": "undeliverable", "submitted_at": "2026-09-15"})
        self.assertEqual(import_invitations(self.db, "EXP-ACQ-0009")["corrected"], 1)
        events = effective_events(self.db)
        self.assertEqual([e["event_type"] for e in events], ["invitation_undeliverable"])
        diag = diagnose_funnel(events, "invitation", as_of="2026-10-30")
        self.assertEqual((diag["stages"][0]["count"], diag["attempts_not_exposure"]), (0, 1))


class DiagnosisTests(StoreCase):
    def invitations(self, count, occurred_at, prefix="c"):
        for i in range(count):
            self.ev("invitation_sent", company=f"{prefix}{i}", occurred_at=occurred_at)

    def transition(self, diag, stage):
        return next(s["transition"] for s in diag["stages"] if s["stage"] == stage)

    def test_a_later_stage_implies_the_earlier_ones_and_an_orphan_is_never_counted(self):
        self.invitations(40, "2026-08-01")
        for i in range(10):
            self.ev("invitation_accepted", company=f"c{i}", occurred_at="2026-08-03")
        for company in ("c0", "c1"):
            self.ev("reply_received", company=company, occurred_at="2026-08-04")
        self.ev("meeting_booked", company="c5", occurred_at="2026-08-06")  # no reply logged
        self.ev("meeting_booked", company="stranger", occurred_at="2026-08-06")
        diag = diagnose_funnel(effective_events(self.db), "invitation", as_of="2026-09-15")
        self.assertEqual([s["count"] for s in diag["stages"]], [40, 10, 3, 1, 1, 0, 0, 0])
        self.assertEqual(diag["unlinked_events"], 1)
        accept = self.transition(diag, "invitation_accepted")
        self.assertEqual((accept["numerator"], accept["denominator"], accept["status"]), (10, 40, "MEASURED"))
        self.assertEqual(self.transition(diag, "reply_received")["status"], "INSUFFICIENT_DATA")
        self.assertEqual(self.transition(diag, "customer_won")["status"], "NOT_REACHED")
        self.assertIsNone(self.transition(diag, "customer_won")["rate"])
        # 0 of 1 meeting is a lower rate, but only acceptance is measurable: it is the constraint.
        c = diag["constraint"]
        self.assertEqual((c["to"], c["rate"], c["confidence"], c["is_leak"]),
                         ("invitation_accepted", 0.25, "MEDIUM", True))
        self.assertEqual(c["reason"], "40 delivered observed")

    def test_exposures_inside_the_response_window_are_in_flight_not_declined(self):
        self.invitations(7, "2026-08-20", prefix="old")
        self.invitations(27, "2026-09-15", prefix="new")
        self.ev("invitation_accepted", company="new0", occurred_at="2026-09-15")
        diag = diagnose_funnel(effective_events(self.db), "invitation", as_of="2026-09-16")
        accept = self.transition(diag, "invitation_accepted")
        self.assertEqual((accept["numerator"], accept["denominator"], accept["in_flight"], accept["early_responses"]),
                         (0, 7, 27, 1))
        self.assertEqual(accept["status"], "INSUFFICIENT_DATA")
        self.assertEqual(diag["constraint"]["reason"], "only 7 delivered observed")
        self.assertEqual(self.transition(diagnose_funnel(effective_events(self.db), "invitation", as_of="2026-08-21"),
                                         "invitation_accepted")["status"], "IN_FLIGHT")

    def test_a_leak_needs_the_minimum_matured_sample(self):
        self.invitations(29, "2026-08-01")
        events = effective_events(self.db)
        below = diagnose_funnel(events, "invitation", as_of="2026-09-15")["constraint"]
        self.assertEqual((below["is_leak"], below["confidence"]), (False, "LOW"))
        self.ev("invitation_sent", company="c29", occurred_at="2026-08-01")
        at = diagnose_funnel(effective_events(self.db), "invitation", as_of="2026-09-15")["constraint"]
        self.assertEqual((at["is_leak"], at["confidence"], at["denominator"]), (True, "MEDIUM", 30))

    def test_a_descriptive_execution_never_claims_its_preregistered_threshold(self):
        self.experiment("EXP-ACQ-0009", channel="linkedin")
        for bad in (("EXP-ACQ-0009", "EXPLORATORY", "why"), ("EXP-ACQ-0009", "DESCRIPTIVE_FROZEN_COHORT", " "),
                    ("EXP-ACQ-0404", "DESCRIPTIVE_FROZEN_COHORT", "why")):
            with self.assertRaises(ValueError):
                set_execution_mode(self.db, *bad)
        set_execution_mode(self.db, "EXP-ACQ-0009", "DESCRIPTIVE_FROZEN_COHORT", "cohort frozen below minimum")
        self.freeze_supply("EXP-ACQ-0009")
        for c in ("c0", "c1", "c2"):
            self.ev("invitation_sent", company=c, occurred_at="2026-09-01", experiment_id="EXP-ACQ-0009",
                    source_record_id=f"x-{c}")
        report = status_report(self.db, as_of="2026-09-20")
        rule = report["recommendation"]["preferred"]["sample_and_stopping_rule"]
        self.assertIn("is not claimed", rule)
        text = render_status(report)
        self.assertIn("DESCRIPTIVE_FROZEN_COHORT", text)
        self.assertIn("Verdict: DESCRIPTIVE_INCONCLUSIVE", text)


class CommercialModelTests(StoreCase):
    def register(self, campaign_id="CMP-1", experiment_id="EXP-ACQ-0009", **kw):
        registries.add(self.db, "campaigns", {
            "campaign_id": campaign_id, "channel": "email", "icp": "Founders of 20-200 person firms",
            "objective": "meeting_rate", "status": "active", "offer_id": "OFF-1",
            "experiment_id": experiment_id, "audience_id": "AUD-1", **kw})

    def fixture(self):
        registries.add(self.db, "offers", {"offer_id": "OFF-1", "buyer": "Founder", "problem": "no pipeline",
                                           "outcome": "a diagnosed leak", "price_pence": 120_000})
        registries.add(self.db, "audiences", {"audience_id": "AUD-1", "audience_type": "cold", "source": "list"})
        registries.add(self.db, "creatives", {"creative_id": "CR-1", "buyer": "Founder", "problem": "no pipeline",
                                              "hook": "I noticed", "body": "I'd test", "campaign_id": "CMP-1"})
        self.register()
        exp = {"experiment_id": "EXP-ACQ-0009", "channel": "email"}
        for company in ("a", "b", "c"):
            self.ev("message_sent", company=company, creative_id="CR-1", occurred_at="2026-08-01", **exp)
        self.ev("meeting_booked", company="a", occurred_at="2026-08-05", **exp)
        self.ev("proposal_sent", company="a", occurred_at="2026-08-06", value_pence=500_000, currency="GBP", **exp)
        self.ev("customer_won", company="a", occurred_at="2026-08-07", **exp)
        self.ev("payment_received", company="a", occurred_at="2026-08-08", value_pence=300_000, currency="GBP", **exp)
        self.ev("spend_recorded", campaign_id="CMP-1", occurred_at="2026-08-01", value_pence=150_000, currency="GBP")

    def test_closed_vocabularies_refuse_free_text(self):
        with self.assertRaisesRegex(ValueError, "audience_type"):
            registries.add(self.db, "audiences", {"audience_id": "AUD-2", "audience_type": "warm", "source": "x"})
        with self.assertRaisesRegex(ValueError, "status"):
            self.register(campaign_id="CMP-9", status="live")

    def test_a_campaign_traces_every_count_and_pound_to_events(self):
        self.fixture()
        graph = campaign_graph(self.db, "CMP-1")
        self.assertEqual((graph["offer"]["offer_id"], graph["audience"]["audience_type"]), ("OFF-1", "cold"))
        self.assertEqual([c["creative_id"] for c in graph["creatives"]], ["CR-1"])
        counts = graph["counts"]
        self.assertEqual((counts["message_sent"], counts["meeting_booked"], counts["proposal_sent"],
                          counts["customer_won"]), (3, 1, 1, 1))
        self.assertEqual(len(graph["trace"]["message_sent"]), 3)
        self.assertEqual(graph["events_linked_by_experiment"], 7)
        self.assertEqual((graph["spend_pence"], graph["cac_pence"], graph["customers"]), (150_000, 150_000, ["a"]))
        self.assertEqual((graph["attributed_revenue_pence"]["linear"], graph["roas"]["linear"]), (300_000, 2.0))
        self.assertAlmostEqual(graph["pipeline_roas"], 500_000 / 150_000)
        with self.assertRaises(ValueError):
            campaign_graph(self.db, "CMP-404")

    def test_an_experiment_with_two_campaigns_links_nothing_by_guess(self):
        self.fixture()
        self.register(campaign_id="CMP-2")
        self.assertEqual(campaign_graph(self.db, "CMP-1")["counts"]["message_sent"], 0)

    def test_a_customer_traces_back_to_icp_offer_creative_and_channel(self):
        self.fixture()
        graph = customer_graph(self.db, "A")
        self.assertEqual((graph["icp"], graph["channels"], graph["campaigns"]),
                         (["Founders of 20-200 person firms"], ["email"], ["CMP-1"]))
        self.assertEqual([o["offer_id"] for o in graph["offers"]], ["OFF-1"])
        self.assertEqual([c["creative_id"] for c in graph["creatives"]], ["CR-1"])
        self.assertEqual(graph["revenue_pence"], 300_000)

    def test_the_card_names_one_test_and_keeps_the_rest_fixed_from_records(self):
        registries.add(self.db, "offers", {"offer_id": "OFF-1", "buyer": "Founder", "problem": "no pipeline",
                                           "outcome": "a diagnosed leak", "price_pence": 120_000})
        registries.add(self.db, "creatives", {"creative_id": "CR-7", "buyer": "Founder", "problem": "p",
                                              "hook": "h", "body": "I'd test", "campaign_id": "CMP-7"})
        self.register(campaign_id="CMP-7", experiment_id="EXP-ACQ-0007")
        for i in range(50):
            self.ev("message_sent", company=f"b{i}", occurred_at="2026-08-01", experiment_id="EXP-ACQ-0007")
        card = next_experiment_card(self.db, as_of="2026-09-15")
        self.assertEqual((card["status"], card["campaign_id"], card["variable"]),
                         ("PROPOSED_NEEDS_CONTRACT", "CMP-7", "cta"))
        self.assertEqual(card["current_constraint"], "Delivered → Replies")
        self.assertEqual(card["evidence"][:3], ["50 delivered", "0 replies", "0.0% conversion"])
        self.assertEqual(card["keep_constant"], {
            "ICP": "Founders of 20-200 person firms", "offer": "OFF-1 — a diagnosed leak",
            "message body": "I'd test", "channel": "email", "price": "£1,200.00"})
        text = render_card(card)
        for title in ("CURRENT CONSTRAINT", "EVIDENCE", "HIGHEST-VALUE UNCERTAINTY", "NEXT TEST",
                      "PRIMARY METRIC", "KEEP CONSTANT", "KILL CONDITION"):
            self.assertIn(f"\n{title}\n", text)

    def test_the_variable_under_test_is_released_and_an_unpriced_offer_is_not_free(self):
        offer = {"offer_id": "OFF-0", "outcome": "o", "price_pence": 0}
        kept = _keep_constant({"icp": "i", "channel": "c"}, offer, None, "offer")
        self.assertEqual(kept, {"ICP": "i", "message body": "not recorded", "channel": "c", "price": "not recorded"})

    def test_with_nothing_observed_the_card_still_renders_without_inventing(self):
        card = next_experiment_card(self.db, as_of="2026-09-15")
        self.assertEqual(card["status"], "NO_BASIS")
        self.assertIn("KILL CONDITION", render_card(card))


class ExperimentVariableTests(unittest.TestCase):
    def spec(self, **kw):
        return ExperimentSpec(experiment_id="EXP-PAID-0002", hypothesis="h", primary_metric="ctr",
                              success_threshold=0.1, review_threshold=0.05, minimum_sample=10, **kw)

    def test_a_control_and_variant_must_name_exactly_one_variable(self):
        with self.assertRaisesRegex(ValueError, "single variable"):
            self.spec(control="a", variant="b").validate()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.spec(control="a", variant="b", variable="hook and cta").validate()
        self.spec(control="a", variant="b", variable="hook").validate()


class StatusTests(StoreCase):
    def test_status_answers_the_eight_questions_and_labels_each_kind_of_claim(self):
        self.many(3, "message_sent", experiment_id="EXP-ACQ-0009")
        text = render_status(status_report(self.db))
        for number in range(1, 9):
            self.assertIn(f"\n{number}. ", text)
        for label in ("[OBSERVED]", "[DERIVED", "[INTERPRETATION", "[RECOMMENDATION"):
            self.assertIn(label, text)
        self.assertIn("Spend not recorded", text)


if __name__ == "__main__":
    unittest.main()
