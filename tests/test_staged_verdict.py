"""The staged verdict applies an experiment's own preregistered gates to canonical data. The rules
below are a synthetic protocol of the same shape; every expected value is hard-coded."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering.buyer_truth import interpret, record_commercial_evidence
from ai_growth_engineering.funnel_events import effective_events, record_event, review_recipient_class
from ai_growth_engineering.reply_capture import capture, check, gmail_messages, import_outbound_sends, link_outbound
from ai_growth_engineering.staged_verdict import render_verdict, verdict
from ai_growth_engineering.storage import init_db

EXP = "EXP-ACQ-0009"
MAILBOX = "founder@example.test"
RULES = {
    "experiment_id": EXP, "judge_not_before": "2026-09-10", "demand_exposure_counted": False,
    "access": {"min_desk_eligible": 30, "min_named_buyers": 20, "min_verified_access_accounts": 15, "preferred_direct": 10,
               "min_clean_delivery_rate": 0.70, "min_observed_for_rate": 10},
    "demand": {"min_clean_deliveries": 30, "min_replies": 5, "min_pain_conversations": 3, "min_proposals": 2,
               "min_paid_partners": 1},
    "research_snapshot": {"desk_eligible": 38, "named_buyers": 15, "direct_access_companies": ["Company 00"], "sends_claimed": 22},
    "response_mapping": {"routing": ["AUTHORITY_SIGNAL"],
                         "demand": ["PROBLEM_STATED", "PAIN_CONFIRMED", "REASON_FOR_INTEREST", "PROPOSAL_REQUESTED"]},
    "next_actions": {"no_human_replies": "change the route, not the product",
                     "routing_without_demand": "count confirmed routes toward the access gate"},
}


class VerdictCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)
        self.n = 0
        link_outbound(self.db, [{"message_id": f"m{i}", "thread_id": f"t{i}", "recipient": f"first.last@c{i}.test",
                                 "company": f"Company {i:02d}", "experiment_id": EXP, "sent_at": "2026-09-01T09:00:00Z"}
                                for i in range(21)])
        import_outbound_sends(self.db, EXP)
        record_event(self.db, {"event_type": "message_bounced", "company": "Company 20", "experiment_id": EXP,
                               "source": "gmail", "source_record_id": "bounce-20", "occurred_at": "2026-09-01T09:01:00Z",
                               "provenance": "platform_export"})

    def reply(self, i, *categories, theme=""):
        event = record_event(self.db, {"event_type": "reply_received", "company": f"Company {i:02d}", "experiment_id": EXP,
                                       "source": "gmail", "source_record_id": f"reply-{i}", "occurred_at": "2026-09-03T10:00:00Z",
                                       "provenance": "platform_export"})["event_id"]
        if categories:
            self.n += 1
            result = record_commercial_evidence(
                self.db, statement=f"Please speak to our office manager about case {i}.", categories=categories,
                source="gmail", source_record_id=f"reply-{i}", occurred_at="2026-09-03T10:00:00Z", provenance="platform_export",
                company=f"Company {i:02d}", source_event_id=event, experiment_id=EXP)
            if theme:
                for link in result["link_ids"]:
                    interpret(self.db, link, theme=theme, interpretation="reads as the theme", confidence=0.3, interpreted_by="founder")

    def checked(self):
        check(self.db, EXP, {"threads": []}, mailbox=MAILBOX)

    def run_verdict(self, as_of="2026-09-20", rules=RULES):
        return verdict(self.db, rules, as_of=as_of)


class MaturityTests(VerdictCase):
    def test_before_the_window_the_verdict_is_not_ready_and_silence_is_not_read(self):
        v = self.run_verdict(as_of="2026-09-05")
        self.assertEqual((v["status"], v["delivered_exposures"], v["matured_exposures"], v["immature_exposures"],
                          v["final_maturity_date"]), ("NOT_READY", 20, 0, 20, "2026-09-10"))
        self.assertIn("open until 2026-09-10", v["blockers"][0])

    def test_after_the_window_a_reply_check_must_run_before_any_verdict(self):
        v = self.run_verdict()
        self.assertEqual(v["status"], "NOT_READY")
        self.assertIn("no governed reply check has run on or after 2026-09-10", v["blockers"][0])
        self.checked()
        self.assertEqual(self.run_verdict()["status"], "NEGATIVE")

    def test_a_reply_waiting_in_review_blocks_the_verdict_and_counts_as_nothing(self):
        capture(self.db, gmail_messages({"threads": [{"id": "t2", "messages": [
            {"id": "in-2", "threadId": "t2", "sender": "first.last@c2.test", "toRecipients": [MAILBOX], "subject": "Re: diary",
             "date": "2026-09-04T09:00:00Z", "labelIds": ["INBOX"], "plaintextBody": "Happy to discuss this with you next week."}]}]}),
                mailbox=MAILBOX)
        self.checked()
        v = self.run_verdict()
        self.assertEqual((v["status"], v["human_replies"], v["pending_reviews"]), ("NOT_READY", 0, 1))
        self.assertIn("await review", v["blockers"][0])


class ResponseClassTests(VerdictCase):
    def test_no_response_is_a_configuration_result_never_a_disproven_problem(self):
        self.checked()
        v = self.run_verdict()
        self.assertEqual((v["attempted_sends"], v["delivery_failures"], v["delivered_exposures"], v["historically_claimed_sends"]),
                         (21, 1, 20, 22))
        self.assertEqual((v["status"], v["access_verdict"], v["demand_verdict"]), ("NEGATIVE", "FAILED", "NOT_ASKED"))
        self.assertEqual(v["commercial_interpretation"],
                         "The tested outreach configuration produced no observed buyer response in 20 delivered exposures.")
        self.assertIn("that the underlying problem is absent", v["what_this_does_not_establish"])
        self.assertEqual((v["failure_point"], v["next_decision"]), ("no_human_replies", "change the route, not the product"))
        text = render_verdict(v)
        self.assertIn("historical claim 22 sends; the canonical verified count is used", text)
        self.assertNotIn("disproven", text.lower())

    def test_automated_replies_are_excluded(self):
        capture(self.db, gmail_messages({"threads": [{"id": "t1", "messages": [
            {"id": "ooo-1", "threadId": "t1", "sender": "first.last@c1.test", "toRecipients": [MAILBOX],
             "subject": "Automatic reply: diary", "date": "2026-09-02T09:00:00Z", "labelIds": ["INBOX"],
             "plaintextBody": "I am out of the office until Monday."}]}]}), mailbox=MAILBOX)
        self.checked()
        v = self.run_verdict()
        self.assertEqual((v["automated_responses"], v["human_replies"], v["status"]), (1, 0, "NEGATIVE"))

    def test_routing_replies_are_access_evidence_with_no_demand_rate(self):
        for i in range(1, 5):
            self.reply(i, "AUTHORITY_SIGNAL")
        self.checked()
        v = self.run_verdict()
        self.assertEqual((v["human_replies"], v["response_classes"]["ROUTING_ONLY"], v["response_classes"]["DEMAND_SIGNAL"]), (4, 4, 0))
        self.assertEqual((v["rates"]["human_reply_rate"], v["rates"]["demand_signal_rate"]), (0.2, 0.0))
        self.assertEqual(v["commercial_interpretation"], "Access produced routing information but no observed demand evidence.")
        self.assertIn("verified-access accounts 5 < 15 (1 DIRECT from research, 4 route-confirmed by reply)", v["access_reasons"][1])
        self.assertEqual((v["status"], v["failure_point"]), ("MIXED", "routing_without_demand"))

    def test_demand_and_qualified_conversations_are_counted_by_the_protocols_definition(self):
        self.reply(1, "PROBLEM_STATED")
        record_event(self.db, {"event_type": "meeting_booked", "company": "Company 01", "experiment_id": EXP, "source": "manual",
                               "source_record_id": "meeting-1", "occurred_at": "2026-09-05", "provenance": "operator_recorded"})
        self.reply(2, "PROBLEM_STATED")
        self.reply(3)
        self.reply(4, "PROPOSAL_REQUESTED")
        self.reply(5, "REASON_FOR_INTEREST")
        self.checked()
        v = self.run_verdict()
        self.assertEqual(v["response_classes"], {"GENERAL_REPLY": 1, "ROUTING_ONLY": 0, "DEMAND_SIGNAL": 2, "QUALIFIED_CONVERSATION": 2})
        self.assertEqual((v["rates"]["human_reply_rate"], v["rates"]["demand_signal_rate"], v["rates"]["qualified_conversation_rate"]),
                         (0.25, 0.2, 0.1))
        self.assertIn("non-preregistered for this stage", v["commercial_interpretation"])
        self.assertEqual(v["failure_point"], "meetings_without_proposals")


class GateTests(VerdictCase):
    def test_the_preregistered_demand_gate_is_applied_to_the_metric_it_declared(self):
        for i in (1, 2):
            self.reply(i, "PROBLEM_STATED")
        self.reply(3, "PROPOSAL_REQUESTED")
        self.checked()
        stage_a = self.run_verdict()
        self.assertEqual((stage_a["demand_verdict"], stage_a["clean_deliveries_to_named_buyers"]), ("NOT_ASKED", 0))
        self.assertIn("0 clean deliveries to named buyers of 30 required: this stage's sends are access attempts", stage_a["demand_reasons"][0])
        counted = copy.deepcopy(RULES)
        counted["demand_exposure_counted"] = True
        counted["demand"]["min_clean_deliveries"] = 20
        # The import only proposes a class; unreviewed, no send is a clean named-buyer delivery.
        self.assertEqual(self.run_verdict(rules=counted)["clean_deliveries_to_named_buyers"], 0)
        for event in effective_events(self.db):
            if event["event_type"] == "message_sent" and event["company"] != "Company 20":
                review_recipient_class(self.db, event["event_id"], "named_buyer", reason="named mailbox, verified")
        full_cycle = self.run_verdict(rules=counted)
        self.assertEqual((full_cycle["demand_verdict"], full_cycle["clean_deliveries_to_named_buyers"]), ("KILL", 20))
        self.assertIn("replies 3 < 5; pain conversations 1 < 3; proposals 0 < 2", full_cycle["demand_reasons"][0])

    def test_approved_evidence_informs_the_verdict_and_reruns_are_identical(self):
        for i in (1, 2):
            self.reply(i, "PROBLEM_STATED", theme="diary-coordination")
        self.checked()
        first = self.run_verdict()
        self.assertEqual([(t["theme"], t["organisations"]) for t in first["buyer_truth"]], [("diary-coordination", 2)])
        self.assertEqual(self.run_verdict(), first)



OTHER = "EXP-ACQ-0010"
OTHER_RULES = {**copy.deepcopy(RULES), "experiment_id": OTHER}


class CrossExperimentIsolationTests(VerdictCase):
    """A verdict must read only its own experiment's records.

    Found by mutation: removing either `experiment_id` filter in
    `staged_verdict._responses` killed nothing, because every fixture here used a
    single experiment. A verdict silently computed over a neighbour's exposures and
    buyer evidence is wrong in exactly the way the cross-experiment leakage finding
    described — and nothing would have said so.
    """

    FIELDS = ("status", "delivered_exposures", "matured_exposures", "immature_exposures",
              "attempted_exposures", "human_replies", "route_confirmed", "failure_point",
              "commercial_interpretation", "next_decision", "uncertainty", "final_maturity_date")

    def seed_other(self):
        """Experiment B: louder than A on every axis the verdict reads.

        Replies land on companies A never contacted, so a leak cannot be mistaken for
        A's own data, and the demand categories are ones A has none of.
        """
        link_outbound(self.db, [
            {"message_id": f"o{i}", "thread_id": f"ot{i}", "recipient": f"first.last@o{i}.test",
             "company": f"Other Co {i:02d}", "experiment_id": OTHER, "sent_at": "2026-09-01T09:00:00Z"}
            for i in range(40)])
        import_outbound_sends(self.db, OTHER)
        for i in range(12):
            event = record_event(self.db, {
                "event_type": "reply_received", "company": f"Other Co {i:02d}", "experiment_id": OTHER,
                "source": "gmail", "source_record_id": f"other-reply-{i}",
                "occurred_at": "2026-09-03T10:00:00Z", "provenance": "platform_export"})["event_id"]
            record_commercial_evidence(
                self.db, statement=f"We have a real problem with this today, case {i}.",
                categories=("PROBLEM_STATED", "PAIN_CONFIRMED", "PROPOSAL_REQUESTED"),
                source="gmail", source_record_id=f"other-reply-{i}", occurred_at="2026-09-03T10:00:00Z",
                provenance="platform_export", company=f"Other Co {i:02d}", source_event_id=event,
                experiment_id=OTHER)

    def slice_of(self, v):
        return {k: v[k] for k in self.FIELDS if k in v}

    def test_experiment_bs_exposures_and_evidence_never_reach_as_verdict(self):
        self.checked()
        before = self.slice_of(self.run_verdict())
        self.assertEqual(before["delivered_exposures"], 20)   # floor: the fixture really ran

        self.seed_other()
        after = self.slice_of(self.run_verdict())

        self.assertEqual(after, before)
        # named explicitly, so a future field addition cannot quietly drop the count check
        self.assertEqual(after["delivered_exposures"], 20)
        self.assertEqual(after["human_replies"], before["human_replies"])

    def test_bs_data_is_visible_when_b_itself_is_judged(self):
        """Isolation, not an inert fixture: B must be loud when B is the subject."""
        self.seed_other()
        check(self.db, OTHER, {"threads": []}, mailbox=MAILBOX)
        b = self.run_verdict(rules=OTHER_RULES)
        self.assertEqual(b["delivered_exposures"], 40)
        self.assertEqual(b["human_replies"], 12)
        a = self.run_verdict()
        self.assertNotEqual(a["delivered_exposures"], b["delivered_exposures"])
        self.assertNotEqual(a["human_replies"], b["human_replies"])

    def test_bs_buyer_evidence_does_not_enter_as_interpretation(self):
        self.checked()
        before = self.run_verdict()
        self.seed_other()
        after = self.run_verdict()
        self.assertEqual(after["commercial_interpretation"], before["commercial_interpretation"])
        self.assertEqual(after["failure_point"], before["failure_point"])
        self.assertNotIn("demand evidence", after["commercial_interpretation"])


if __name__ == "__main__":
    unittest.main()
