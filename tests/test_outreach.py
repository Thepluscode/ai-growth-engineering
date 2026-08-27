import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from ai_growth_engineering.cli import cmd_outreach_record, cmd_suppress
from ai_growth_engineering.registry import (
    import_outreach,
    parse_recipient_class,
    reply_rate_by_recipient_class,
    scoreboard,
)
from ai_growth_engineering.storage import connect, init_db


class OutreachTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_suppression_blocks_send_record(self):
        cmd_suppress(Namespace(db=self.db, identity="person@example.com", reason="opt_out"))
        args = Namespace(
            db=self.db,
            company="Acme",
            identity="person@example.com",
            meaningful_reply=False,
            discovery=False,
            diagnostic_proposed=False,
            proposal=False,
            paid=False,
            collected_revenue=0.0,
            notes="",
        )
        with self.assertRaises(SystemExit):
            cmd_outreach_record(args)
        with connect(self.db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM outreach").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()


class BouncedSendsTests(unittest.TestCase):
    """A send that bounced never reached anyone.

    Counting it inflates the denominator every threshold is measured against, which
    would let an experiment reach its minimum sample on messages nobody received.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)
        self.csv = Path(self.tmp.name) / "outreach.csv"
        self.csv.write_text(
            "date_first_contact,company,stage,meaningful_reply,notes\n"
            "2026-08-19,Delivered A,sent_awaiting_reply,,ok\n"
            "2026-08-19,Delivered B,sent_awaiting_reply,,ok\n"
            "2026-08-19,Dead Address,bounced,,address not found\n"
            "2026-08-19,Misrouted,misrouted_support_queue,,logged as a ticket\n",
            encoding="utf-8",
        )

    def test_bounced_sends_do_not_count_toward_the_sample(self):
        import_outreach(self.db, str(self.csv))
        values = scoreboard(self.db)
        # 4 rows imported, 3 actually delivered.
        self.assertEqual(values["outreach_sent"], 3)

    def test_the_bounce_is_still_recorded_not_discarded(self):
        # Losing the row would hide the addressing problem that caused it.
        import_outreach(self.db, str(self.csv))
        with connect(self.db) as con:
            stages = {r["company"]: r["stage"] for r in con.execute(
                "SELECT company, stage FROM outreach")}
        self.assertEqual(stages["Dead Address"], "bounced")
        self.assertEqual(len(stages), 4)

    def test_a_misrouted_send_still_counts_as_delivered(self):
        # It arrived; it went to the wrong queue. That is a targeting problem,
        # not a delivery one, and conflating them hides both.
        import_outreach(self.db, str(self.csv))
        with connect(self.db) as con:
            stage = con.execute(
                "SELECT stage FROM outreach WHERE company='Misrouted'").fetchone()["stage"]
        self.assertEqual(stage, "misrouted_support_queue")
        self.assertEqual(scoreboard(self.db)["outreach_sent"], 3)

    def test_a_legacy_row_without_a_stage_counts_as_delivered(self):
        # Rows imported before the column existed must not silently vanish.
        with connect(self.db) as con:
            con.execute("INSERT INTO outreach(company, sent_at) VALUES ('Legacy','2026-08-01')")
        self.assertEqual(scoreboard(self.db)["outreach_sent"], 1)


class RecipientClassTests(unittest.TestCase):
    """EXP-ACQ-0001 concluded REVIEW on 0/50 without recording who received the mail.

    48 went to a shared inbox and 2 to a named buyer. The blended 0% answered a
    question nobody asked, and the route that mattered was never tested. These tests
    exist so the same result cannot be produced again without the split being visible.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)
        self.csv = Path(self.tmp.name) / "outreach.csv"
        self.csv.write_text(
            "date_first_contact,company,stage,recipient_class,meaningful_reply,notes\n"
            "2026-08-19,Named A,sent_awaiting_reply,named_buyer,yes,replied\n"
            "2026-08-19,Named B,sent_awaiting_reply,named_buyer,,no reply\n"
            "2026-08-19,Role A,sent_awaiting_reply,role_inbox,,no reply\n"
            "2026-08-19,Role B,sent_awaiting_reply,role_inbox,,no reply\n"
            "2026-08-19,Role C,sent_awaiting_reply,role_inbox,,no reply\n"
            "2026-08-19,Dead,bounced,named_buyer,,address not found\n",
            encoding="utf-8",
        )

    def test_each_class_reports_its_own_sent_and_replies(self):
        import_outreach(self.db, str(self.csv))
        split = reply_rate_by_recipient_class(self.db)
        # Hardcoded, not derived from the CSV: a count computed from the same source
        # would pass with the split broken.
        self.assertEqual(split["named_buyer"], {"sent": 2, "replies": 1})
        self.assertEqual(split["role_inbox"], {"sent": 3, "replies": 0})

    def test_the_blended_rate_hides_what_the_split_shows(self):
        # The regression this whole column exists for. Blended: 1 reply / 5 delivered
        # = 20%, which describes neither route. Split: 50% and 0%.
        import_outreach(self.db, str(self.csv))
        split = reply_rate_by_recipient_class(self.db)
        self.assertEqual(scoreboard(self.db)["outreach_sent"], 5)
        self.assertEqual(scoreboard(self.db)["meaningful_responses"], 1)
        self.assertNotEqual(
            split["named_buyer"]["replies"] / split["named_buyer"]["sent"],
            split["role_inbox"]["replies"] / max(split["role_inbox"]["sent"], 1),
        )

    def test_a_bounce_is_excluded_from_its_class(self):
        # Same rule as the scoreboard: a message that did not arrive is not a send.
        # Counting it would let a class reach a minimum sample on nothing.
        # Three named_buyer rows exist; one bounced, so the class reports two.
        import_outreach(self.db, str(self.csv))
        self.assertEqual(reply_rate_by_recipient_class(self.db)["named_buyer"]["sent"], 2)

    def test_a_legacy_row_is_unclassified_not_assigned_to_a_class(self):
        # Rows written before the column existed must not be silently absorbed into
        # either route; "we do not know who read it" is the honest answer.
        with connect(self.db) as con:
            con.execute("INSERT INTO outreach(company, sent_at) VALUES ('Legacy','2026-08-01')")
        split = reply_rate_by_recipient_class(self.db)
        self.assertEqual(split["unclassified"]["sent"], 1)
        self.assertEqual(split["named_buyer"]["sent"], 0)
        self.assertEqual(split["role_inbox"]["sent"], 0)

    def test_a_class_with_no_sends_is_zero_not_an_error(self):
        split = reply_rate_by_recipient_class(self.db)
        self.assertEqual(split["named_buyer"], {"sent": 0, "replies": 0})

    def test_an_unknown_class_raises_rather_than_defaulting(self):
        # A silent fallback turns a typo into a class of sends nobody can find again.
        bad = Path(self.tmp.name) / "bad.csv"
        bad.write_text(
            "date_first_contact,company,stage,recipient_class,meaningful_reply,notes\n"
            "2026-08-19,Typo,sent_awaiting_reply,named-buyerr,,\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as caught:
            import_outreach(self.db, str(bad))
        self.assertIn("named-buyerr", str(caught.exception))
        self.assertIn("Typo", str(caught.exception))

    def test_a_hyphen_and_stray_case_are_accepted_not_rejected(self):
        # named-buyer and Named_Buyer mean the same thing to a human writing a CSV.
        self.assertEqual(parse_recipient_class("Named-Buyer"), "named_buyer")
        self.assertEqual(parse_recipient_class(" ROLE_INBOX "), "role_inbox")

    def test_a_missing_or_empty_value_is_unclassified(self):
        self.assertEqual(parse_recipient_class(None), "unclassified")
        self.assertEqual(parse_recipient_class(""), "unclassified")
        self.assertEqual(parse_recipient_class("   "), "unclassified")


class RecipientClassMigrationTests(unittest.TestCase):
    def test_a_database_built_before_the_column_gains_it(self):
        # The store under .age/ is rebuildable, but a developer's existing copy is not,
        # and an ALTER that never runs reads exactly like a column that was never added.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = str(Path(tmp.name) / "old.db")
        with connect(db) as con:
            con.execute(
                "CREATE TABLE outreach (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "company TEXT NOT NULL, sent_at TEXT, meaningful_reply INTEGER NOT NULL DEFAULT 0, "
                "discovery INTEGER NOT NULL DEFAULT 0, diagnostic_proposed INTEGER NOT NULL DEFAULT 0, "
                "proposal INTEGER NOT NULL DEFAULT 0, paid INTEGER NOT NULL DEFAULT 0, "
                "collected_revenue_pence INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '')"
            )
            con.execute("INSERT INTO outreach(company, sent_at) VALUES ('Old','2026-08-01')")
        init_db(db)
        with connect(db) as con:
            columns = {r["name"] for r in con.execute("PRAGMA table_info(outreach)")}
        self.assertIn("recipient_class", columns)
        self.assertEqual(reply_rate_by_recipient_class(db)["unclassified"]["sent"], 1)
