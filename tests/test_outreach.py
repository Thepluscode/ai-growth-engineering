import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from ai_growth_engineering.cli import cmd_outreach_record, cmd_suppress
from ai_growth_engineering.registry import import_outreach, scoreboard
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
