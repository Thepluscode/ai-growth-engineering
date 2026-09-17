"""A recipient class that reaches a denominator must have been observed, not guessed.

The gmail send import classified every recipient from a 16-word list of mailbox names, and that
guess fed the named-buyer denominator of a preregistered DEMAND gate. `first.last@` became a
named buyer by default. An inference may still PROPOSE a class; only an operator-recorded class
or a person's review can establish one.

    observed   named_buyer | role_inbox | other
    UNKNOWN    nothing recorded, or only a proposal
    INFERRED_LEGACY   written before this rule, on the word-list basis
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering.funnel_events import (
    EventError, effective_events, recipient_class, record_event, review_recipient_class,
)
from ai_growth_engineering.reply_capture import import_outbound_sends, link_outbound
from ai_growth_engineering.storage import connect, init_db

LEGACY_BASIS = "recipient address local part"


class Classification(unittest.TestCase):
    def test_an_operator_recorded_class_is_observed(self):
        for value in ("named_buyer", "role_inbox", "other"):
            self.assertEqual(recipient_class({"recipient_class": value}), value)

    def test_a_word_list_class_written_before_the_rule_is_inferred_legacy(self):
        self.assertEqual(recipient_class({"recipient_class": "named_buyer", "recipient_class_basis": LEGACY_BASIS}),
                         "INFERRED_LEGACY")

    def test_a_proposal_alone_is_unknown(self):
        self.assertEqual(recipient_class({"recipient_class": "UNKNOWN", "recipient_class_proposed": "named_buyer"}),
                         "UNKNOWN")

    def test_absent_blank_and_unrecognised_classes_are_unknown(self):
        for meta in ({}, None, {"recipient_class": ""}, {"recipient_class": "unclassified"},
                     {"recipient_class": "vip"}):
            self.assertEqual(recipient_class(meta), "UNKNOWN", meta)

    def test_a_review_outranks_the_inference(self):
        meta = {"recipient_class": "named_buyer", "recipient_class_basis": LEGACY_BASIS,
                "recipient_class_review": "role_inbox"}
        self.assertEqual(recipient_class(meta), "role_inbox")


class Case(unittest.TestCase):
    EXP = "EXP-ACQ-0009"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)
        link_outbound(self.db, [
            {"message_id": "m1", "thread_id": "t1", "recipient": "first.last@acme.test", "company": "Acme",
             "experiment_id": self.EXP, "sent_at": "2026-09-01T09:00:00Z"},
            {"message_id": "m2", "thread_id": "t2", "recipient": "info@beta.test", "company": "Beta",
             "experiment_id": self.EXP, "sent_at": "2026-09-01T09:00:00Z"}])
        import_outbound_sends(self.db, self.EXP)

    def sends(self):
        return {e["company"]: e for e in effective_events(self.db) if e["event_type"] == "message_sent"}


class SendImportOnlyProposes(Case):
    def test_the_import_records_unknown_with_a_labelled_proposal(self):
        sends = self.sends()
        acme, beta = sends["Acme"]["metadata"], sends["Beta"]["metadata"]
        self.assertEqual((acme["recipient_class"], acme["recipient_class_proposed"]), ("UNKNOWN", "named_buyer"))
        self.assertEqual((beta["recipient_class"], beta["recipient_class_proposed"]), ("UNKNOWN", "role_inbox"))
        self.assertIn("not observed", acme["recipient_class_basis"])
        self.assertEqual({recipient_class(e["metadata"]) for e in sends.values()}, {"UNKNOWN"})


class Review(Case):
    def test_a_reviewed_class_is_observed(self):
        event = self.sends()["Acme"]["event_id"]
        review_recipient_class(self.db, event, "named_buyer", reason="signature names the MD; mailbox is personal")
        self.assertEqual(recipient_class(self.sends()["Acme"]["metadata"]), "named_buyer")

    def test_the_latest_review_wins(self):
        event = self.sends()["Acme"]["event_id"]
        review_recipient_class(self.db, event, "named_buyer", reason="first read")
        review_recipient_class(self.db, event, "role_inbox", reason="it is a shared sales mailbox")
        self.assertEqual(recipient_class(self.sends()["Acme"]["metadata"]), "role_inbox")

    def test_a_review_needs_a_reason_and_a_known_class_and_event(self):
        event = self.sends()["Acme"]["event_id"]
        for args in ((event, "named_buyer", ""), (event, "INFERRED_LEGACY", "x"), (event, "vip", "x"),
                     ("EVT-0000000000000000", "named_buyer", "x")):
            with self.assertRaises(EventError, msg=args):
                review_recipient_class(self.db, *args[:2], reason=args[2])

    def test_reviews_are_append_only(self):
        review_recipient_class(self.db, self.sends()["Acme"]["event_id"], "named_buyer", reason="r")
        con = sqlite3.connect(self.db)
        self.addCleanup(con.close)
        for sql in ("DELETE FROM recipient_class_reviews", "UPDATE recipient_class_reviews SET recipient_class='other'"):
            with self.assertRaises(sqlite3.DatabaseError):
                con.execute(sql)


class Denominators(Case):
    def rules(self):
        return {
            "experiment_id": self.EXP, "judge_not_before": "2026-09-10", "demand_exposure_counted": True,
            "access": {"min_desk_eligible": 1, "min_named_buyers": 1, "min_verified_access_accounts": 1,
                       "preferred_direct": 1, "min_clean_delivery_rate": 0.7, "min_observed_for_rate": 10},
            "demand": {"min_clean_deliveries": 1, "min_replies": 1, "min_pain_conversations": 1, "min_proposals": 1,
                       "min_paid_partners": 1},
            "research_snapshot": {"desk_eligible": 2, "named_buyers": 1, "direct_access_companies": [],
                                  "sends_claimed": 2},
            "response_mapping": {"routing": [], "demand": []},
            "next_actions": {"no_human_replies": "n", "routing_without_demand": "r"},
        }

    def clean(self):
        from ai_growth_engineering.staged_verdict import verdict

        return verdict(self.db, self.rules(), as_of="2026-09-20")["clean_deliveries_to_named_buyers"]

    def test_an_unreviewed_proposal_is_not_a_clean_named_buyer_delivery(self):
        self.assertEqual(self.clean(), 0)

    def test_a_reviewed_named_buyer_is_counted(self):
        review_recipient_class(self.db, self.sends()["Acme"]["event_id"], "named_buyer", reason="verified")
        self.assertEqual(self.clean(), 1)

    def test_a_legacy_word_list_class_is_not_counted_until_reviewed(self):
        record_event(self.db, {"event_type": "message_sent", "company": "Gamma", "experiment_id": self.EXP,
                               "occurred_at": "2026-09-01", "source": "legacy", "source_record_id": "g1",
                               "provenance": "platform_export",
                               "metadata": {"recipient_class": "named_buyer", "recipient_class_basis": LEGACY_BASIS}})
        self.assertEqual(self.clean(), 0)

    def test_segments_do_not_file_an_inference_under_named_buyer(self):
        from ai_growth_engineering.segments import _attributes

        route = _attributes(self.sends()["Acme"], {"campaigns": {}, "offers": {}, "audiences": {}})["recipient_route"]
        self.assertEqual(route, "UNKNOWN")

    def test_the_marketing_engineer_does_not_read_an_inference_as_a_route(self):
        from ai_growth_engineering.marketing_engineer import _recipient_classes

        self.assertEqual(_recipient_classes(list(self.sends().values())), {"UNKNOWN": 2})


class Recommendation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)

    def many(self, n, metadata):
        for i in range(n):
            record_event(self.db, {"event_type": "message_sent", "company": f"C{i}", "experiment_id": "EXP-ACQ-0009",
                                   "occurred_at": "2026-08-01", "source": "t", "source_record_id": f"r{i}",
                                   "provenance": "operator_recorded", "metadata": metadata})

    def variable(self):
        from ai_growth_engineering.marketing_engineer import evaluate

        [finding] = evaluate(effective_events(self.db))
        return finding["proposed_test_variable"]

    def test_observed_shared_inboxes_redirect_the_next_test_to_the_route(self):
        self.many(50, {"recipient_class": "role_inbox"})
        self.assertEqual(self.variable(), "recipient_route")

    def test_guessed_shared_inboxes_do_not(self):
        self.many(50, {"recipient_class": "role_inbox", "recipient_class_basis": LEGACY_BASIS})
        self.assertNotEqual(self.variable(), "recipient_route")


if __name__ == "__main__":
    unittest.main()
