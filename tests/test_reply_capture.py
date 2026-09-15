"""Reply capture on synthetic Gmail-shaped messages. Capture only proposes; every write to events or
evidence goes through an explicit, item-by-item approval, and never ahead of its verifiable send."""
from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering.buyer_truth import buyer_evidence
from ai_growth_engineering.funnel_events import effective_events, event_id_for, record_event
from ai_growth_engineering.marketing_engineer import render_status, status_report
from ai_growth_engineering.reply_capture import (
    ReplyCaptureError, approve, candidate, candidate_id_for, capture, check, check_plan, gmail_messages,
    import_outbound_sends, link_outbound, reject, review,
)
from ai_growth_engineering.revenue_loop import compute_metrics, diagnose_funnel, money_graph_for_entity, totals
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

    def outcomes(self):
        """Everything recorded after the send: replies, bounces."""
        return [e for e in effective_events(self.db) if e["event_type"] != "message_sent"]

    def sends(self):
        return [e for e in effective_events(self.db) if e["event_type"] == "message_sent"]


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
        import_outbound_sends(self.db, "EXP-ACQ-0006")
        approve(self.db, self.get("m1")["candidate_id"])
        self.assertEqual([(e["event_type"], e["company"]) for e in self.outcomes()], [("message_bounced", "Beta Ltd")])
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
        import_outbound_sends(self.db, "EXP-ACQ-0006")
        self.run_capture(message("m1", "t-acme", "buyer@acme.test", INTERESTED))
        self.cid = self.get("m1")["candidate_id"]

    def test_the_reply_event_can_be_approved_without_any_evidence(self):
        approve(self.db, self.cid, items=["event"])
        [event] = self.outcomes()
        self.assertEqual((event["event_type"], event["source"], event["source_record_id"], event["metadata"]["source_thread_id"]),
                         ("reply_received", "gmail", "m1", "t-acme"))
        self.assertEqual(event["metadata"]["answers_send_event_id"], event_id_for("gmail", "out-1", "message_sent"))
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
        self.assertEqual(self.outcomes(), [])
        result = approve(self.db, self.cid, items=["event", "E2"])
        reject(self.db, self.cid, items=["meaningful", "E1"], reason="interest alone is not a qualified conversation")
        [evidence] = buyer_evidence(self.db)
        self.assertEqual((evidence["category"], evidence["source"], evidence["source_record_id"], evidence["source_event_id"]),
                         ("BUYING_CRITERION", "gmail", "m1", result["approved"]["event"]))
        self.assertEqual([e["event_type"] for e in self.outcomes()], ["reply_received"])
        with self.assertRaises(ReplyCaptureError):
            approve(self.db, self.cid, items=["E1"])

    def test_a_rejected_candidate_never_comes_back(self):
        reject(self.db, self.cid, reason="not a buyer reply")
        self.assertEqual(self.run_capture(message("m1", "t-acme", "buyer@acme.test", INTERESTED)), {"already_captured": 1})
        self.assertEqual((review(self.db)["pending"], self.outcomes(), buyer_evidence(self.db)), ([], [], []))

    def test_status_counts_pending_reviews_as_nothing_else(self):
        report = status_report(self.db, as_of="2026-09-15")
        self.assertEqual((report["pending_reply_reviews"], report["totals"].get("reply_received", 0)), (1, 0))
        self.assertIn("[PENDING REVIEW] 1 reply candidate(s)", render_status(report))


class SendLineageTests(ReplyCaptureCase):
    def test_each_verified_send_becomes_one_event_with_its_lineage_and_timestamp(self):
        self.assertEqual(import_outbound_sends(self.db, "EXP-ACQ-0006"),
                         {"experiment_id": "EXP-ACQ-0006", "linked": 3, "inserted": 3, "already_present": 0, "refused": []})
        by_company = {e["company"]: e for e in self.sends()}
        acme = by_company["Acme Ltd"]
        self.assertEqual((acme["source"], acme["source_record_id"], acme["occurred_at"], acme["experiment_id"],
                          acme["campaign_id"], acme["channel"], acme["provenance"]),
                         ("gmail", "out-1", "2026-09-08T07:00:00+00:00", "EXP-ACQ-0006", "CMP-6", "email", "platform_export"))
        self.assertEqual((acme["metadata"]["source_thread_id"], acme["metadata"]["recipient_class"],
                          by_company["Beta Ltd"]["metadata"]["recipient_class"]), ("t-acme", "named_buyer", "role_inbox"))
        self.assertEqual(import_outbound_sends(self.db, "EXP-ACQ-0006")["inserted"], 0)
        self.assertEqual(len(self.sends()), 3)

    def test_a_bounce_is_an_attempt_not_a_delivery_and_never_a_reply(self):
        import_outbound_sends(self.db, "EXP-ACQ-0006")
        self.run_capture(message("b1", "t-beta", "mailer-daemon@googlemail.com", "Address not found.",
                                 subject="Delivery Status Notification (Failure)", date="2026-09-08T07:01:30Z"))
        approve(self.db, self.get("b1")["candidate_id"])
        events = [e for e in effective_events(self.db) if e["experiment_id"] == "EXP-ACQ-0006"]
        self.assertEqual(sorted(e["event_type"] for e in events), ["message_bounced", "message_sent", "message_sent", "message_sent"])
        diagnosis = diagnose_funnel(events, "outbound", as_of="2026-09-30")
        self.assertEqual((diagnosis["stages"][0]["count"], diagnosis["attempts_not_exposure"]), (2, 1))
        self.assertEqual((totals(events)["message_sent"], totals(events)["delivered_messages"]), (3, 2))
        self.assertEqual(compute_metrics(events)["metrics"]["reply_rate"]["denominator"], 2)

    def test_a_send_without_its_source_message_is_never_created(self):
        with self.assertRaises(ReplyCaptureError) as caught:
            link_outbound(self.db, [{"thread_id": "t-x", "recipient": "info@waterworx.test", "company": "Waterworx",
                                     "experiment_id": "EXP-ACQ-0006", "sent_at": "2026-09-08T08:27:20Z"}])
        self.assertEqual(caught.exception.code, "outbound_incomplete")
        with self.assertRaises(ReplyCaptureError) as caught:
            import_outbound_sends(self.db, "EXP-ACQ-0099")
        self.assertEqual(caught.exception.code, "no_linked_sends")
        self.assertEqual(effective_events(self.db), [])

    def test_a_reply_traces_to_its_recorded_send_and_never_enters_before_it(self):
        self.run_capture(message("m1", "t-acme", "buyer@acme.test", INTERESTED))
        cid = self.get("m1")["candidate_id"]
        with self.assertRaises(ReplyCaptureError) as caught:
            approve(self.db, cid, items=["event"])
        self.assertEqual(caught.exception.code, "upstream_send_missing")
        self.assertEqual(effective_events(self.db), [])
        import_outbound_sends(self.db, "EXP-ACQ-0006")
        approve(self.db, cid, items=["event"])
        chain = money_graph_for_entity(effective_events(self.db), "Acme Ltd")["chain"]
        self.assertEqual([c["event_type"] for c in chain], ["message_sent", "reply_received"])
        [reply] = self.outcomes()
        self.assertEqual(reply["metadata"]["answers_send_event_id"], chain[0]["event_id"])

    def test_ambiguous_send_lineage_is_refused(self):
        link_outbound(self.db, [{"message_id": "out-5", "thread_id": "t-acme-2", "recipient": "buyer@acme.test",
                                 "company": "Acme Holdings", "experiment_id": "EXP-ACQ-0006", "sent_at": "2026-09-08T07:05:00Z"}])
        result = import_outbound_sends(self.db, "EXP-ACQ-0006")
        self.assertEqual(sorted((r["message_id"], r["code"]) for r in result["refused"]),
                         [("out-1", "ambiguous_lineage"), ("out-5", "ambiguous_lineage")])
        self.assertEqual({e["company"] for e in self.sends()}, {"Beta Ltd", "Gamma Ltd"})

    def test_a_claimed_total_is_not_an_input_and_a_buyer_is_never_counted_twice(self):
        # The historical claim (22 sends) cannot be passed in: only linked, verified messages import.
        self.assertEqual(set(inspect.signature(import_outbound_sends).parameters), {"db_path", "experiment_id"})
        record_event(self.db, {"event_type": "message_sent", "company": "Beta Ltd", "experiment_id": "EXP-ACQ-0006",
                               "source": "outreach_csv", "source_record_id": "log-beta", "occurred_at": "2026-09-08",
                               "provenance": "system_import"})
        result = import_outbound_sends(self.db, "EXP-ACQ-0006")
        self.assertEqual((result["linked"], result["inserted"], [r["code"] for r in result["refused"]]),
                         (3, 2, ["recorded_from_other_source"]))
        self.assertEqual(sorted(e["company"] for e in self.sends()), ["Acme Ltd", "Beta Ltd", "Gamma Ltd"])


class ReplyCheckTests(ReplyCaptureCase):
    def setUp(self):
        super().setUp()
        import_outbound_sends(self.db, "EXP-ACQ-0006")
        self.payload = {"threads": [
            {"id": "t-acme", "messages": [message("r1", "t-acme", "buyer@acme.test", INTERESTED)]},
            {"id": "t-beta", "messages": [message("r2", "t-beta", "mailer-daemon@googlemail.com", "Address not found.",
                                                   subject="Delivery Status Notification (Failure)", labels=("TRASH",))]},
            {"id": "t-gamma-1", "messages": [message("r3", "t-gamma-1", "shared@gamma.test", "I am out of the office until Monday.",
                                                      subject="Automatic reply", labels=("TRASH",))]},
            {"id": "t-news", "messages": [message("r4", "t-news", "newsletter@shop.test", "Our autumn sale starts now.")]},
            {"id": "t-gamma-2", "messages": [message("r5", "t-gamma-2", "shared@gamma.test", INTERESTED)]},
            {"id": "t-early", "messages": [message("r6", "t-early", "buyer@acme.test", INTERESTED, date="2026-09-01T09:00:00Z")]},
            {"id": "t-snip", "messages": [message("r7", "t-snip", "info@beta.test", INTERESTED, snippet_only=True)]},
        ]}

    def run_check(self):
        return check(self.db, "EXP-ACQ-0006", self.payload, mailbox=MAILBOX)

    def test_only_governed_mail_in_the_window_is_checked_and_trash_counts(self):
        plan = check_plan(self.db, "EXP-ACQ-0006")
        self.assertEqual((plan["governed_threads"], plan["recipients"]), (["t-acme", "t-beta", "t-gamma-1"], 3))
        self.assertTrue(all(s["include_trash"] and "after:2026/09/08" in s["query"] for s in plan["searches"]))
        summary = self.run_check()
        self.assertEqual((summary["threads_checked"], summary["out_of_scope_dropped"], summary["needs_full_body"]),
                         (3, 3, ["r7"]))
        self.assertEqual((summary["bounces"], summary["automated"], summary["buyer_reply_candidates"]), (1, 1, 1))
        self.assertEqual({c["kind"] for c in (self.get("r2"), self.get("r3"))}, {"BOUNCE", "OUT_OF_OFFICE"})
        with self.assertRaises(ReplyCaptureError):
            self.get("r5")

    def test_a_check_writes_candidates_only_and_a_rerun_adds_nothing(self):
        before = self.sends()
        summary = self.run_check()
        self.assertEqual((summary["canonical_writes"], summary["pending_review"], summary["real_buyer_replies"]), (0, 2, 1))
        self.assertEqual((self.sends(), self.outcomes(), buyer_evidence(self.db)), (before, [], []))
        approve(self.db, self.get("r1")["candidate_id"], items=["event"])
        reject(self.db, self.get("r2")["candidate_id"], reason="checked in the review")
        again = self.run_check()
        self.assertEqual((again["already_processed"], again["new_candidates"], review(self.db)["captured"]), (3, {}, 3))
        self.assertEqual([e["event_type"] for e in self.outcomes()], ["reply_received"])

    def test_a_check_that_would_change_canonical_stores_is_refused(self):
        from ai_growth_engineering import reply_capture

        original = reply_capture.capture

        def writing_capture(db_path, messages, *, mailbox):
            record_event(db_path, {"event_type": "reply_received", "company": "Acme Ltd", "experiment_id": "EXP-ACQ-0006",
                                   "source": "gmail", "source_record_id": "sneaky", "occurred_at": "2026-09-10",
                                   "provenance": "platform_export"})
            return original(db_path, messages, mailbox=mailbox)

        reply_capture.capture = writing_capture
        self.addCleanup(setattr, reply_capture, "capture", original)
        with self.assertRaises(ReplyCaptureError) as caught:
            self.run_check()
        self.assertEqual(caught.exception.code, "canonical_write_during_check")


if __name__ == "__main__":
    unittest.main()
