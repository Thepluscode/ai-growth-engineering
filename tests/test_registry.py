import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering.models import ExperimentSpec
from ai_growth_engineering.registry import (
    add_experiment, record_experiment_result, record_sourcing_run, scoreboard,
    seed_prospects, sourcing_funnel,
)
from ai_growth_engineering.storage import connect, init_db


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
            "Acme,https://acme.test,A,MD,test,https://acme.test,qualified_batch_01\n"
            "Unreviewed,https://u.test,B,MD,test,https://u.test,research\n"
            "Wrong ICP,https://wrong.test,B,MD,test,https://wrong.test,disqualified_market_fit\n",
            encoding="utf-8",
        )
        seed_prospects(self.db, str(csv_path))
        values = scoreboard(self.db)
        # `research` is NOT qualified. This assertion used to read 1 against a single
        # `research` row, which encoded the defect as the expectation.
        self.assertEqual(values["qualified_prospects"], 1)
        self.assertEqual(values["unreviewed_prospects"], 1)
        self.assertEqual(values["paying_customers"], 0)

    def test_reseeding_updates_a_disqualified_prospect(self):
        csv_path = Path(self.tmp.name) / "prospects.csv"
        csv_path.write_text(
            "company,website,priority,target_roles,evidence,source_url,status\n"
            "Acme,https://acme.test,A,MD,test,https://acme.test,qualified_batch_01\n",
            encoding="utf-8",
        )
        seed_prospects(self.db, str(csv_path))
        self.assertEqual(scoreboard(self.db)["qualified_prospects"], 1)

        csv_path.write_text(
            "company,website,priority,target_roles,evidence,source_url,status\n"
            "Acme,https://acme.test,A,MD,verified,https://acme.test,disqualified_market_fit\n",
            encoding="utf-8",
        )
        seed_prospects(self.db, str(csv_path))
        self.assertEqual(scoreboard(self.db)["qualified_prospects"], 0)


class QualifiedStatusSemanticsTests(unittest.TestCase):
    """Qualification must be asserted, never inherited from not being disqualified.

    `qualified_prospects` read `NOT LIKE 'disqualified%'`, so an unreviewed import
    incremented a VERIFIED number with nobody deciding anything. These are the tests
    that would have caught it.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)

    def _seed(self, *statuses):
        csv_path = Path(self.tmp.name) / "p.csv"
        rows = "".join(
            f"Co{i},https://co{i}.test,B,MD,e,https://co{i}.test,{s}\n"
            for i, s in enumerate(statuses)
        )
        csv_path.write_text(
            "company,website,priority,target_roles,evidence,source_url,status\n" + rows,
            encoding="utf-8",
        )
        seed_prospects(self.db, str(csv_path))
        return scoreboard(self.db)

    def test_no_unreviewed_status_can_inflate_the_qualified_count(self):
        limbo = ("candidate", "sourced_candidate_unqualified", "unreviewed", "researching",
                 "research", "ready_for_deep_research", "pending", "unknown", "borderline")
        values = self._seed(*limbo)
        self.assertEqual(values["qualified_prospects"], 0,
                         "an unreviewed prospect must never count as qualified")
        self.assertEqual(values["unreviewed_prospects"], len(limbo))

    def test_an_explicitly_qualified_prospect_counts(self):
        values = self._seed("qualified", "qualified_batch_02", "qualified_batch_06_replacement")
        self.assertEqual(values["qualified_prospects"], 3)
        self.assertEqual(values["unreviewed_prospects"], 0)

    def test_disqualified_counts_as_neither(self):
        values = self._seed("disqualified_market_fit", "disqualified_unreachable_by_email")
        self.assertEqual(values["qualified_prospects"], 0)
        self.assertEqual(values["unreviewed_prospects"], 0)

    def test_a_mixed_population_splits_three_ways_and_nothing_is_lost(self):
        values = self._seed("qualified_batch_02", "qualified_batch_03",
                            "candidate", "research",
                            "disqualified_market_fit")
        self.assertEqual(values["qualified_prospects"], 2)
        self.assertEqual(values["unreviewed_prospects"], 2)
        # Every row lands in exactly one bucket: a prospect cannot go missing.
        with connect(self.db) as con:
            total = con.execute("SELECT COUNT(*) FROM prospects").fetchone()[0]
            disq = con.execute(
                "SELECT COUNT(*) FROM prospects WHERE status LIKE 'disqualified%'"
            ).fetchone()[0]
        self.assertEqual(values["qualified_prospects"] + values["unreviewed_prospects"] + disq,
                         total)

    def test_seeding_the_40_sourced_candidates_moves_the_qualified_count_by_zero(self):
        """The concrete regression: importing Batch-02 must not manufacture validation."""
        before = self._seed("qualified_batch_02", "qualified_batch_03")["qualified_prospects"]
        after = self._seed("qualified_batch_02", "qualified_batch_03",
                           *["sourced_candidate_unqualified"] * 40)
        self.assertEqual(after["qualified_prospects"], before)
        self.assertEqual(after["unreviewed_prospects"], 40)


if __name__ == "__main__":
    unittest.main()


class SourcingFunnelTests(unittest.TestCase):
    """Denominators must stay attached to the cohort they were measured on."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)

    def _run(self, **kw):
        base = dict(run_id="BATCH-02", ran_at="2026-09-08", source="companies_house",
                    raw_candidates=316, website_evidenced=40, qualified=10,
                    borderline=10, rejected=20, identity_resolved=7)
        base.update(kw)
        return record_sourcing_run(self.db, base)

    def test_each_step_divides_by_the_stage_above_it(self):
        steps = {s["key"]: s for s in self._run()["steps"]}
        self.assertEqual(steps["website_evidence_rate"]["denominator"], 316)
        self.assertEqual(steps["qualification_rate"]["denominator"], 40)
        self.assertEqual(steps["identity_rate"]["denominator"], 10)
        self.assertAlmostEqual(steps["qualification_rate"]["rate"], 0.25)

    def test_nothing_asked_is_not_a_rate_of_zero(self):
        steps = {s["key"]: s for s in self._run(
            raw_candidates=0, website_evidenced=0, qualified=0,
            borderline=0, rejected=0, identity_resolved=0)["steps"]}
        for key in ("website_evidence_rate", "qualification_rate", "identity_rate"):
            self.assertIsNone(steps[key]["rate"], f"{key} must be None, never 0.0")
            self.assertFalse(steps[key]["observed"])

    def test_a_measured_zero_is_distinguishable_from_an_unasked_one(self):
        steps = {s["key"]: s for s in self._run(
            qualified=0, borderline=15, rejected=25, identity_resolved=0)["steps"]}
        self.assertEqual(steps["qualification_rate"]["rate"], 0.0)
        self.assertTrue(steps["qualification_rate"]["observed"])
        self.assertIsNone(steps["identity_rate"]["rate"])

    def test_borderline_is_never_counted_as_qualified(self):
        run = self._run()
        self.assertEqual(run["counts"]["qualified"], 10)
        self.assertEqual(run["counts"]["borderline"], 10)
        steps = {s["key"]: s for s in run["steps"]}
        self.assertEqual(steps["qualification_rate"]["numerator"], 10)

    def test_a_classification_that_does_not_account_for_every_candidate_is_refused(self):
        with self.assertRaises(ValueError):
            self._run(qualified=10, borderline=10, rejected=5)

    def test_identity_cannot_exceed_qualified_and_evidenced_cannot_exceed_raw(self):
        with self.assertRaises(ValueError):
            self._run(identity_resolved=11)
        with self.assertRaises(ValueError):
            self._run(raw_candidates=10, website_evidenced=40)

    def test_the_compound_rate_spans_register_to_identity(self):
        self.assertAlmostEqual(self._run()["compound_rate"], 7 / 316)

    def test_no_run_reports_nothing_rather_than_zero(self):
        empty = sourcing_funnel(self.db)
        self.assertIsNone(empty["run_id"])
        self.assertIsNone(empty["compound_rate"])
        self.assertEqual(empty["steps"], [])
