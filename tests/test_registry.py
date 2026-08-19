import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering.models import ExperimentSpec
from ai_growth_engineering.registry import add_experiment, record_experiment_result, scoreboard, seed_prospects
from ai_growth_engineering.storage import init_db


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_experiment_decisions(self):
        add_experiment(self.db, ExperimentSpec("EXP-ACQ-0001", "test", "reply", 0.10, 0.05, 50))
        self.assertEqual(record_experiment_result(self.db, "EXP-ACQ-0001", 49, 0.20), "preregistered")
        self.assertEqual(record_experiment_result(self.db, "EXP-ACQ-0001", 50, 0.12), "keep")

    def test_experiment_id_namespace_is_enforced(self):
        for eid in ("EXP-ACQ-0002", "EXP-CREATIVE-0001", "EXP-PAID-0001", "EXP-CRO-0001"):
            ExperimentSpec(eid, "h", "m", 0.10, 0.05, 50).validate()
        for eid in ("EXP-BANANA-0001", "EXP-0001", "ACQ-0001", "EXP-ACQ-X", "EXP-ACQ-01"):
            with self.assertRaises(ValueError):
                ExperimentSpec(eid, "h", "m", 0.10, 0.05, 50).validate()

    def test_seed_and_scoreboard(self):
        csv_path = Path(self.tmp.name) / "prospects.csv"
        csv_path.write_text(
            "company,website,priority,target_roles,evidence,source_url,status\n"
            "Acme,https://acme.test,A,MD,test,https://acme.test,research\n"
            "Wrong ICP,https://wrong.test,B,MD,test,https://wrong.test,disqualified_market_fit\n",
            encoding="utf-8",
        )
        seed_prospects(self.db, str(csv_path))
        values = scoreboard(self.db)
        self.assertEqual(values["qualified_prospects"], 1)
        self.assertEqual(values["paying_customers"], 0)


if __name__ == "__main__":
    unittest.main()
