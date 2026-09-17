"""Reply evidence cannot be removed, and a pending reply blocks only the experiment it belongs to.

reply_candidates and reply_checks were append-only for UPDATE but not for DELETE: deleting a pending
candidate would have cleared the review gate, and deleting a check would have changed whether a
post-window check ever ran. A pending review is resolved by a decision, never by removing it.

A pending candidate also blocked every experiment that shared either its thread or its sender. One
mailbox contacted by two experiments meant a reply in one experiment's thread held up the other.
Thread lineage now decides; the sender is a fallback only for a reply outside every known thread.
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering.reply_capture import capture, check, gmail_messages, link_outbound, review
from ai_growth_engineering.staged_verdict import _review_state
from ai_growth_engineering.storage import init_db

MAILBOX = "founder@example.test"
BODY = "We are interested, but we'd need to understand exactly what the deliverable contains before booking time."


def message(mid, thread, sender, date="2026-09-10T09:00:00Z"):
    return {"id": mid, "threadId": thread, "sender": sender, "toRecipients": [MAILBOX], "subject": "Re: diary",
            "date": date, "labelIds": ["INBOX"], "snippet": BODY[:60], "plaintextBody": BODY}


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)
        # One shared mailbox, contacted by two experiments in two different threads.
        link_outbound(self.db, [
            {"message_id": "a-1", "thread_id": "t-a", "recipient": "shared@gamma.test", "company": "Gamma Ltd",
             "experiment_id": "EXP-ACQ-0006", "sent_at": "2026-09-08T07:00:00Z"},
            {"message_id": "b-1", "thread_id": "t-b", "recipient": "shared@gamma.test", "company": "Gamma Group",
             "experiment_id": "EXP-ACQ-0001", "sent_at": "2026-08-19T16:00:00Z"},
            {"message_id": "a-2", "thread_id": "t-a2", "recipient": "buyer@acme.test", "company": "Acme Ltd",
             "experiment_id": "EXP-ACQ-0006", "sent_at": "2026-09-08T07:01:00Z"},
        ])

    def capture(self, *messages):
        return capture(self.db, gmail_messages({"threads": [{"id": m["threadId"], "messages": [m]} for m in messages]}),
                       mailbox=MAILBOX)

    def pending(self, experiment):
        return _review_state(self.db, experiment)[0]

    def sql(self, statement):
        con = sqlite3.connect(self.db)
        try:
            con.execute(statement)
            con.commit()
        finally:
            con.rollback()
            con.close()


class DeletionIsRefused(Case):
    def test_a_pending_reply_candidate_cannot_be_deleted(self):
        self.capture(message("m1", "t-a2", "buyer@acme.test"))
        self.assertEqual(self.pending("EXP-ACQ-0006"), 1)
        with self.assertRaises(sqlite3.DatabaseError) as ctx:
            self.sql("DELETE FROM reply_candidates")
        self.assertIn("append-only", str(ctx.exception))
        self.assertEqual(self.pending("EXP-ACQ-0006"), 1, "the review gate must still hold")

    def test_a_reply_check_cannot_be_deleted(self):
        check(self.db, "EXP-ACQ-0006", {"threads": []}, mailbox=MAILBOX)
        self.assertIsNotNone(_review_state(self.db, "EXP-ACQ-0006")[2])
        with self.assertRaises(sqlite3.DatabaseError) as ctx:
            self.sql("DELETE FROM reply_checks")
        self.assertIn("append-only", str(ctx.exception))
        self.assertIsNotNone(_review_state(self.db, "EXP-ACQ-0006")[2])

    def test_updates_stay_refused_and_appends_still_work(self):
        """The positive twin: the triggers block removal, not recording."""
        self.capture(message("m1", "t-a2", "buyer@acme.test"))
        self.capture(message("m2", "t-a", "shared@gamma.test"))
        self.assertEqual(review(self.db)["captured"], 2)
        with self.assertRaises(sqlite3.DatabaseError):
            self.sql("UPDATE reply_candidates SET kind = 'AUTOMATED'")


class PendingReviewScope(Case):
    def test_a_reply_in_another_experiments_thread_does_not_block_this_one(self):
        """The reproduced case: the shared mailbox answers experiment B's thread."""
        self.capture(message("m1", "t-b", "shared@gamma.test"))
        self.assertEqual(self.pending("EXP-ACQ-0001"), 1)
        self.assertEqual(self.pending("EXP-ACQ-0006"), 0)

    def test_a_reply_in_this_experiments_thread_blocks_only_this_one(self):
        self.capture(message("m1", "t-a", "shared@gamma.test"))
        self.assertEqual(self.pending("EXP-ACQ-0006"), 1)
        self.assertEqual(self.pending("EXP-ACQ-0001"), 0)

    def test_a_reply_outside_every_known_thread_falls_back_to_the_sender(self):
        """No thread lineage: a sender both experiments contacted blocks both, rather than neither."""
        self.capture(message("m1", "t-new", "shared@gamma.test"))
        self.assertEqual((self.pending("EXP-ACQ-0006"), self.pending("EXP-ACQ-0001")), (1, 1))

    def test_a_sender_only_one_experiment_contacted_blocks_only_that_one(self):
        self.capture(message("m1", "t-new", "buyer@acme.test"))
        self.assertEqual((self.pending("EXP-ACQ-0006"), self.pending("EXP-ACQ-0001")), (1, 0))


if __name__ == "__main__":
    unittest.main()
