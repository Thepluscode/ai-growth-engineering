"""Reply capture on synthetic Gmail-shaped messages. Capture only proposes; every write to events or
evidence goes through an explicit, item-by-item approval."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering.buyer_truth import buyer_evidence
from ai_growth_engineering.funnel_events import effective_events
from ai_growth_engineering.marketing_engineer import render_status, status_report
from ai_growth_engineering.reply_capture import (
    ReplyCaptureError, approve, candidate, candidate_id_for, capture, gmail_messages, link_outbound, reject, review,
)
from ai_growth_engineering.storage import connect, init_db

MAILBOX = "founder@example.test"
INTERESTED = "We are interested, but we'd need to understand exactly what the deliverable contains before booking time."


def message(mid, thread, sender, body, *, subject="Re: Who handles the diary?", date="2026-09-10T09:00:00Z",
            labels=("INBOX",), snippet_only=False):
    m = {"id": mid, "threadId": thread, "sender": sender, "toRecipients": [MAILBOX], "subject": subject, "date": date,
         "labelIds": list(labels), "snippet": body[:60]}
    if not snippet_only:
        m["plaintextBody"] = body
    return m


class ReplyCaptureCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)
        link_outbound(self.db, [
            {"message_id": "out-1", "thread_id": "t-acme", "recipient": "Jane <buyer@acme.test>", "company": "Acme Ltd",
             "experiment_id": "EXP-ACQ-0006", "campaign_id": "CMP-6", "sent_at": "2026-09-08T07:00:00Z"},
            {"message_id": "out-2", "thread_id": "t-beta", "recipient": "info@beta.test", "company": "Beta Ltd",
             "experiment_id": "EXP-ACQ-0006", "sent_at": "2026-09-08T07:01:00Z"},
            {"message_id": "out-3", "thread_id": "t-gamma-1", "recipient": "shared@gamma.test", "company": "Gamma Ltd",
             "experiment_id": "EXP-ACQ-0006", "sent_at": "2026-09-08T07:02:00Z"},
            {"message_id": "out-4", "thread_id": "t-gamma-2", "recipient": "shared@gamma.test", "company": "Gamma Group",
             "experiment_id": "EXP-ACQ-0001", "sent_at": "2026-08-19T16:00:00Z"},
        ])

    def run_capture(self, *messages):
        return capture(self.db, gmail_messages({"threads": [{"id": m["threadId"], "messages": [m]} for m in messages]}),
                       mailbox=MAILBOX)

    def get(self, mid):
        return candidate(self.db, candidate_id_for("gmail", mid))

    def items(self, mid):
        return {p["item"]: p for p in self.get(mid)["proposals"]}


class CaptureTests(ReplyCaptureCase):
    def test_a_reply_becomes_a_candidate_and_nothing_is_recorded_before_approval(self):
        body = INTERESTED + "\n\nOn Tue, 8 Sept 2026 at 08:17, Founder <founder@example.test> wrote:\n> Who handles the diary?"
        self.run_capture(message("m1", "t-acme", "Jane <buyer@acme.test>", body))
        c = self.get("m1")
        self.assertEqual((c["kind"], c["match_state"], c["match_method"], c["match_confidence"], c["company"],
                          c["experiment_id"], c["campaign_id"]),
                         ("BUYER_REPLY", "MATCHED", "thread_lineage", "HIGH", "Acme Ltd", "EXP-ACQ-0006", "CMP-6"))
        items = self.items("m1")
        self.assertTrue(items["event"]["proposed"] and items["meaningful"]["proposed"])
        self.assertEqual([(items[k]["category"], items[k]["text"]) for k in ("E1", "E2")],
                         [("REASON_FOR_INTEREST", "We are interested"),
                          ("BUYING_CRITERION", "we'd need to understand exactly what the deliverable contains before booking time.")])
        for item in ("E1", "E2"):
            self.assertIn(items[item]["text"], body)
        self.assertNotIn("Who handles the diary", c["body"])
        self.assertEqual((effective_events(self.db), buyer_evidence(self.db)), ([], []))
        with connect(self.db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 0)

    def test_an_acknowledgement_proposes_a_reply_and_no_evidence(self):
        self.run_capture(message("m1", "t-acme", "buyer@acme.test", "Thanks."))
        items = self.items("m1")
        self.assertEqual(set(items), {"event", "meaningful"})
        self.assertEqual((items["meaningful"]["proposed"], items["meaningful"]["reason"]), (False, "an acknowledgement"))

    def test_out_of_office_and_gateway_mail_are_never_buyer_replies(self):
        self.run_capture(message("m1", "t-acme", "buyer@acme.test", "I am out of the office until Monday.",
                                 subject="Automatic reply: Who handles the diary?"),
                         message("m2", "t-beta", "info@beta.test", "Thank you for contacting us. A ticket has been created."))
        self.assertEqual((self.get("m1")["kind"], self.get("m2")["kind"]), ("OUT_OF_OFFICE", "AUTOMATED"))
        self.assertEqual((self.get("m1")["proposals"], review(self.db)["pending"]), ([], []))

    def test_a_bounce_maps_to_the_bounce_event_not_a_reply(self):
        bounce = message("m1", "t-beta", "mailer-daemon@googlemail.com", "Your message wasn't delivered to info@beta.test.",
                         subject="Delivery Status Notification (Failure)")
        self.run_capture(bounce)
        self.assertEqual((self.get("m1")["kind"], list(self.items("m1"))), ("BOUNCE", ["bounce"]))
        approve(self.db, self.get("m1")["candidate_id"])
        self.assertEqual([(e["event_type"], e["company"]) for e in effective_events(self.db)], [("message_bounced", "Beta Ltd")])
        self.run_capture(message("m2", "t-beta", "mailer-daemon@googlemail.com", "Still undelivered.",
                                 subject="Delivery Status Notification (Failure)"))
        self.assertEqual(self.get("m2")["proposals"], [])

    def test_unknown_and_ambiguous_senders_are_never_guessed(self):
        self.run_capture(message("m1", "t-new", "stranger@elsewhere.test", INTERESTED),
                         message("m2", "t-new-2", "shared@gamma.test", INTERESTED),
                         message("m3", "t-new-3", "someone@acme.test", INTERESTED),
                         message("m4", "t-acme", "partner@other.test", INTERESTED))
        states = {mid: self.get(mid)["match_state"] for mid in ("m1", "m2", "m3", "m4")}
        self.assertEqual(states, {"m1": "UNMATCHED", "m2": "AMBIGUOUS", "m3": "UNMATCHED", "m4": "AMBIGUOUS"})
        self.assertIn("a domain alone never identifies a buyer", self.items("m3")["identity"]["reason"])
        with self.assertRaises(ReplyCaptureError) as caught:
            approve(self.db, self.get("m2")["candidate_id"], items=["identity"])
        self.assertEqual(caught.exception.code, "identity_unresolved")
        self.assertEqual(effective_events(self.db), [])

    def test_thread_lineage_names_the_buyer_and_a_colleague_at_the_same_domain_is_marked(self):
        self.run_capture(message("m1", "t-beta", "info@beta.test", INTERESTED),
                         message("m2", "t-acme", "ops@acme.test", INTERESTED))
        self.assertEqual((self.get("m1")["company"], self.get("m1")["match_confidence"]), ("Beta Ltd", "HIGH"))
        self.assertEqual((self.get("m2")["company"], self.get("m2")["match_method"], self.get("m2")["match_confidence"]),
                         ("Acme Ltd", "thread_lineage_same_domain", "MEDIUM"))

    def test_capturing_the_same_message_twice_is_idempotent(self):
        self.assertEqual(self.run_capture(message("m1", "t-acme", "buyer@acme.test", INTERESTED)),
                         {"buyer_reply_matched": 1})
        self.assertEqual(self.run_capture(message("m1", "t-acme", "buyer@acme.test", INTERESTED)), {"already_captured": 1})
        self.assertEqual(review(self.db)["captured"], 1)

    def test_quoted_or_repeated_words_are_one_observation_not_two(self):
        self.run_capture(message("m1", "t-acme", "buyer@acme.test", INTERESTED))
        self.run_capture(message("m2", "t-acme", "buyer@acme.test", "Thanks, that helps.\n\nOn Wed, 9 Sept 2026, Founder wrote:\n> "
                                 + INTERESTED, date="2026-09-11T09:00:00Z"),
                         message("m3", "t-acme", "buyer@acme.test", INTERESTED + " Our budget is set for this quarter.",
                                 date="2026-09-12T09:00:00Z"))
        self.assertEqual([k for k in self.items("m2") if k.startswith("E")], [])
        texts = {p["text"] for p in self.get("m3")["proposals"] if p["item"].startswith("E")}
        self.assertEqual(texts, {"Our budget is set for this quarter."})

    def test_a_negative_reply_and_a_stated_problem_are_proposed_as_what_they_say(self):
        self.run_capture(message("m1", "t-beta", "info@beta.test", "We already have this covered internally."),
                         message("m2", "t-acme", "buyer@acme.test", "Our dispatcher loses an hour a day re-planning callouts."))
        self.assertEqual([(p["category"], p["text"]) for k, p in self.items("m1").items() if k.startswith("E")],
                         [("REASON_FOR_REJECTION", "We already have this covered internally.")])
        self.assertEqual([p["category"] for k, p in self.items("m2").items() if k.startswith("E")], ["PROBLEM_STATED"])

    def test_a_snippet_is_never_cited_as_evidence(self):
        self.run_capture(message("m1", "t-acme", "buyer@acme.test", INTERESTED, snippet_only=True))
        self.assertEqual(self.items("m1")["evidence"]["proposed"], False)
        self.assertFalse(any(k.startswith("E") for k in self.items("m1")))


class ApprovalTests(ReplyCaptureCase):
    def setUp(self):
        super().setUp()
        self.run_capture(message("m1", "t-acme", "buyer@acme.test", INTERESTED))
        self.cid = self.get("m1")["candidate_id"]

    def test_the_reply_event_can_be_approved_without_any_evidence(self):
        approve(self.db, self.cid, items=["event"])
        [event] = effective_events(self.db)
        self.assertEqual((event["event_type"], event["source"], event["source_record_id"], event["metadata"]["source_thread_id"]),
                         ("reply_received", "gmail", "m1", "t-acme"))
        self.assertEqual(buyer_evidence(self.db), [])
        self.assertEqual(review(self.db)["pending"][0]["pending"], ["meaningful", "E1", "E2"])
        reject(self.db, self.cid, reason="read in full; nothing more established")
        self.assertEqual(review(self.db)["pending"], [])

    def test_approval_is_item_by_item_and_evidence_needs_the_reply_first(self):
        for items, code in ((["E1"], "event_first"), (["event", "identity"], "unknown_item")):
            with self.assertRaises(ReplyCaptureError) as caught:
                approve(self.db, self.cid, items=items)
            self.assertEqual(caught.exception.code, code)
        with self.assertRaises(ReplyCaptureError) as caught:
            approve(self.db, self.cid, items=["event", "E2"], texts={"E2": "we need a cheaper option"})
        self.assertEqual(caught.exception.code, "text_not_in_reply")
        self.assertEqual(effective_events(self.db), [])
        result = approve(self.db, self.cid, items=["event", "E2"])
        reject(self.db, self.cid, items=["meaningful", "E1"], reason="interest alone is not a qualified conversation")
        [evidence] = buyer_evidence(self.db)
        self.assertEqual((evidence["category"], evidence["source"], evidence["source_record_id"], evidence["source_event_id"]),
                         ("BUYING_CRITERION", "gmail", "m1", result["approved"]["event"]))
        self.assertEqual([e["event_type"] for e in effective_events(self.db)], ["reply_received"])
        with self.assertRaises(ReplyCaptureError):
            approve(self.db, self.cid, items=["E1"])

    def test_a_rejected_candidate_never_comes_back(self):
        reject(self.db, self.cid, reason="not a buyer reply")
        self.assertEqual(self.run_capture(message("m1", "t-acme", "buyer@acme.test", INTERESTED)), {"already_captured": 1})
        self.assertEqual((review(self.db)["pending"], effective_events(self.db), buyer_evidence(self.db)), ([], [], []))

    def test_status_counts_pending_reviews_as_nothing_else(self):
        report = status_report(self.db, as_of="2026-09-15")
        self.assertEqual((report["pending_reply_reviews"], report["events"]), (1, 0))
        self.assertIn("[PENDING REVIEW] 1 reply candidate(s)", render_status(report))


if __name__ == "__main__":
    unittest.main()
