"""An experiment's sample is counted from the event log; a typed number may not contradict it.

`age experiment-result` took --sample-size and --observed-value as free numbers and wrote them onto
the experiment, where the Marketing Engineer printed them under OBSERVED. Nothing compared the
typed sample with the exposures the log held. EXP-ACQ-0003 shows the other side of the same gap:
its row says n=0 while the log holds 34 delivered invitations.

Now:
  * the sample is COMPUTED from delivered exposures whenever the experiment has events, and a typed
    sample that disagrees is refused;
  * a sample for an experiment with no events is accepted as MANUAL_ANNOTATION, and the observed
    value is always recorded as MANUAL_ANNOTATION — it is typed, not derived;
  * `age reconcile` compares every stored figure with the log, and `--record` appends the
    disagreements to an append-only ledger, so history is annotated rather than rewritten.
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering.funnel_events import record_event
from ai_growth_engineering.models import ExperimentSpec
from ai_growth_engineering.registry import (
    add_experiment, canonical_sample, declare_trust_not_applicable, reconcile_experiments,
    record_experiment_result, record_reconciliations,
)
from ai_growth_engineering.storage import connect, init_db

EXP = "EXP-ACQ-0009"


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)
        add_experiment(self.db, ExperimentSpec(EXP, "h", "reply_rate", 0.10, 0.05, 3))
        declare_trust_not_applicable(self.db, EXP, "fixture: trust not under test here")
        self.n = 0

    def ev(self, event_type, company, experiment=EXP, **kw):
        self.n += 1
        values = {"event_type": event_type, "company": company, "experiment_id": experiment,
                  "occurred_at": "2026-09-01", "source": "t", "source_record_id": f"r{self.n}",
                  "provenance": "operator_recorded"}
        values.update(kw)
        record_event(self.db, values)

    def row(self, experiment=EXP):
        with connect(self.db) as con:
            return dict(con.execute("SELECT * FROM experiments WHERE experiment_id = ?", (experiment,)).fetchone())

    def status(self, experiment=EXP):
        return {r["metric"]: r for r in reconcile_experiments(self.db) if r["experiment_id"] == experiment}


class CanonicalSample(Case):
    def test_delivered_sends_and_invitations_count_once_per_buyer(self):
        for company in ("A", "B", "C"):
            self.ev("message_sent", company)
        self.ev("message_sent", "A")  # a second touch to the same buyer
        self.ev("message_bounced", "C")
        self.ev("invitation_sent", "D")
        self.ev("invitation_undeliverable", "E")
        self.ev("message_sent", "F", experiment="EXP-ACQ-0010")
        self.ev("message_sent", "G", provenance="synthetic_fixture")
        self.assertEqual(canonical_sample(self.db, EXP), 3)  # A, B, D

    def test_an_experiment_with_no_events_has_no_computed_sample(self):
        self.assertIsNone(canonical_sample(self.db, EXP))


class ResultRecording(Case):
    def test_a_typed_sample_that_contradicts_the_log_is_refused(self):
        for company in ("A", "B", "C"):
            self.ev("message_sent", company)
        with self.assertRaises(ValueError) as ctx:
            record_experiment_result(self.db, EXP, 50, 0.20)
        self.assertIn("event log", str(ctx.exception))
        self.assertEqual((self.row()["sample_size"], self.row()["observed_value"]), (0, None))

    def test_a_sample_that_matches_the_log_is_recorded_as_computed(self):
        for company in ("A", "B", "C"):
            self.ev("message_sent", company)
        self.assertEqual(record_experiment_result(self.db, EXP, 3, 0.34), "keep")
        row = self.row()
        self.assertEqual((row["sample_basis"], row["observed_value_basis"]), ("COMPUTED", "MANUAL_ANNOTATION"))

    def test_a_sample_for_an_experiment_with_no_events_is_labelled_manual(self):
        record_experiment_result(self.db, EXP, 3, 0.34)
        self.assertEqual(self.row()["sample_basis"], "MANUAL_ANNOTATION")

    def test_the_command_prints_a_refusal_instead_of_a_traceback(self):
        from ai_growth_engineering.cli import build_parser

        self.ev("message_sent", "A")
        args = build_parser().parse_args(["experiment-result", "--db", self.db, "--experiment-id", EXP,
                                          "--sample-size", "9", "--observed-value", "0.2"])
        with self.assertRaises(SystemExit) as ctx:
            args.func(args)
        self.assertIn("REFUSED", str(ctx.exception))


class Reconciliation(Case):
    def test_a_row_that_never_recorded_its_exposures_is_not_recorded(self):
        """The EXP-ACQ-0003 shape: n=0 on the row, deliveries in the log."""
        for company in ("A", "B"):
            self.ev("invitation_sent", company)
        row = self.status()["sample_size"]
        self.assertEqual((row["status"], row["stored_value"], row["computed_value"]), ("NOT_RECORDED", 0, 2))

    def test_a_matching_row_is_a_match(self):
        for company in ("A", "B", "C"):
            self.ev("message_sent", company)
        record_experiment_result(self.db, EXP, 3, 0.1)
        self.assertEqual(self.status()["sample_size"]["status"], "MATCH")

    def test_history_written_before_the_rule_is_reported_as_diverged(self):
        self.ev("message_sent", "A")
        with connect(self.db) as con:
            con.execute("UPDATE experiments SET sample_size = 50, observed_value = 0.0 WHERE experiment_id = ?", (EXP,))
        row = self.status()["sample_size"]
        self.assertEqual((row["status"], row["stored_value"], row["computed_value"]), ("DIVERGED", 50, 1))

    def test_without_events_a_stored_sample_is_not_derivable(self):
        record_experiment_result(self.db, EXP, 3, 0.1)
        self.assertEqual(self.status()["sample_size"]["status"], "NOT_DERIVABLE")

    def test_the_observed_value_is_always_an_annotation(self):
        record_experiment_result(self.db, EXP, 3, 0.1)
        self.assertEqual(self.status()["observed_value"]["status"], "MANUAL_ANNOTATION")

    def test_recording_appends_disagreements_once_and_never_rewrites_the_experiment(self):
        self.ev("invitation_sent", "A")
        before = self.row()
        self.assertEqual(record_reconciliations(self.db, recorded_by="test"), 1)
        self.assertEqual(record_reconciliations(self.db, recorded_by="test"), 0, "an unchanged disagreement is recorded once")
        self.assertEqual(self.row(), before)
        with connect(self.db) as con:
            rows = [dict(r) for r in con.execute("SELECT * FROM metric_reconciliations")]
        self.assertEqual([(r["experiment_id"], r["metric"], r["status"], r["stored_value"], r["computed_value"])
                          for r in rows], [(EXP, "sample_size", "NOT_RECORDED", "0", "1")])

    def test_the_ledger_is_append_only(self):
        self.ev("invitation_sent", "A")
        record_reconciliations(self.db, recorded_by="test")
        con = sqlite3.connect(self.db)
        try:
            for sql in ("DELETE FROM metric_reconciliations", "UPDATE metric_reconciliations SET status = 'MATCH'"):
                with self.assertRaises(sqlite3.DatabaseError):
                    con.execute(sql)
        finally:
            con.rollback()
            con.close()


class Reporting(Case):
    def test_a_concluded_experiment_reports_its_computed_sample_and_labels_the_typed_value(self):
        from ai_growth_engineering.marketing_engineer import learned_line

        for company in ("A", "B", "C"):
            self.ev("message_sent", company)
        record_experiment_result(self.db, EXP, 3, 0.0)
        line = learned_line(self.db, {"experiment_id": EXP, "decision": "review", "sample_size": 3,
                                      "primary_metric": "reply_rate", "observed_value": 0.0})
        self.assertIn("n=3 [COMPUTED]", line)
        self.assertIn("reply_rate=0.0 [MANUAL_ANNOTATION]", line)

    def test_a_disagreement_is_shown_not_hidden(self):
        from ai_growth_engineering.marketing_engineer import learned_line

        self.ev("message_sent", "A")
        line = learned_line(self.db, {"experiment_id": EXP, "decision": "review", "sample_size": 50,
                                      "primary_metric": "reply_rate", "observed_value": 0.0})
        self.assertIn("n=1 [COMPUTED]", line)
        self.assertIn("recorded n=50 disagrees", line)


if __name__ == "__main__":
    unittest.main()
