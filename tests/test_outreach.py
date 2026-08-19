import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from ai_growth_engineering.cli import cmd_outreach_record, cmd_suppress
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
