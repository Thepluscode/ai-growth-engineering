from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering.execution import (
    ExecutionError, access_result, cohort, freeze_execution_cohort, record_invitation, wilson,
)
from ai_growth_engineering.registry import scoreboard
from ai_growth_engineering.signal_intelligence import add_identity
from ai_growth_engineering.storage import connect, init_db


NOW = "2026-09-08T09:00:00+00:00"


class LineageTests(unittest.TestCase):
    """No downstream state without admissible upstream lineage.

    Both halves of this invariant have already failed in this repository: a prospect
    became qualified by not being disqualified, and an identity was counted as supply
    while sitting on an account nobody had qualified.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)

    def _prospect(self, pid, company, status):
        with connect(self.db) as con:
            con.execute(
                """INSERT INTO prospects(id, company, website, priority, target_roles,
                                         evidence, source_url, status)
                   VALUES (?, ?, 'https://x.test', 'B', 'MD', ?, 'https://x.test/about', ?)""",
                (pid, company, "MULTI_DIRECTOR", status))

    def _identity(self, pid, url, confidence=0.8):
        add_identity(self.db, {"prospect_id": pid, "identity_type": "linkedin", "value": url,
                               "provider": "test", "verification_status": "observed_published",
                               "source_url": url, "observed_at": NOW, "confidence": confidence})

    def test_an_identity_on_an_unqualified_account_is_not_admitted(self):
        self._prospect(1, "Qualified Co", "qualified_batch_07")
        self._prospect(2, "Candidate Co", "sourced_candidate_unqualified")
        self._prospect(3, "Borderline Co", "borderline")
        self._prospect(4, "Research Co", "research")
        self._prospect(5, "Rejected Co", "disqualified_market_fit")
        for pid in (1, 2, 3, 4, 5):
            self._identity(pid, f"https://uk.linkedin.com/in/person{pid}")
        frozen = freeze_execution_cohort(self.db, "C1")
        self.assertEqual(frozen["size"], 1, "only the qualified account may enter the cohort")
        self.assertEqual(frozen["members"][0]["company"], "Qualified Co")

    def test_a_qualified_account_with_no_identity_is_not_admitted(self):
        self._prospect(1, "No Identity Co", "qualified_batch_07")
        self.assertEqual(freeze_execution_cohort(self.db, "C1")["size"], 0)

    def test_one_invitation_per_account_however_many_identities(self):
        self._prospect(1, "Two Directors Co", "qualified_batch_07")
        self._identity(1, "https://uk.linkedin.com/in/first", 0.6)
        self._identity(1, "https://uk.linkedin.com/in/second", 0.8)
        frozen = freeze_execution_cohort(self.db, "C1")
        self.assertEqual(frozen["size"], 1)
        # The stronger identity is the one frozen.
        self.assertEqual(frozen["members"][0]["identity_value"], "https://uk.linkedin.com/in/second")
        self.assertEqual(frozen["members"][0]["identity_sourcing"], "two_source")

    def test_an_account_outside_the_cohort_cannot_record_access(self):
        self._prospect(1, "In Co", "qualified_batch_07")
        self._identity(1, "https://uk.linkedin.com/in/in")
        self._prospect(2, "Out Co", "sourced_candidate_unqualified")
        freeze_execution_cohort(self.db, "C1")
        with self.assertRaises(ExecutionError) as ctx:
            record_invitation(self.db, "C1", 2, {"outcome": "accepted", "accepted_at": NOW})
        self.assertEqual(ctx.exception.code, "not_in_cohort")

    def test_a_frozen_cohort_cannot_be_refrozen(self):
        self._prospect(1, "In Co", "qualified_batch_07")
        self._identity(1, "https://uk.linkedin.com/in/in")
        freeze_execution_cohort(self.db, "C1")
        self._prospect(2, "Late Co", "qualified_batch_07")
        self._identity(2, "https://uk.linkedin.com/in/late")
        with self.assertRaises(ExecutionError) as ctx:
            freeze_execution_cohort(self.db, "C1")
        self.assertEqual(ctx.exception.code, "cohort_frozen")


class AccessIsNotDemandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)
        with connect(self.db) as con:
            for pid in range(1, 40):
                con.execute(
                    """INSERT INTO prospects(id, company, website, priority, target_roles,
                                             evidence, source_url, status)
                       VALUES (?, ?, 'https://x.test', 'B', 'MD', 'MULTI_DIRECTOR',
                               'https://x.test/a', 'qualified_batch_07')""",
                    (pid, f"Co {pid}"))
        for pid in range(1, 40):
            add_identity(self.db, {"prospect_id": pid, "identity_type": "linkedin",
                                   "value": f"https://uk.linkedin.com/in/p{pid}", "provider": "test",
                                   "verification_status": "observed_published",
                                   "source_url": f"https://uk.linkedin.com/in/p{pid}",
                                   "observed_at": NOW, "confidence": 0.8})
        freeze_execution_cohort(self.db, "C1")

    def _accept(self, n):
        for pid in range(1, 40):
            outcome = "accepted" if pid <= n else "pending"
            record_invitation(self.db, "C1", pid, {
                "outcome": outcome, "submitted_at": NOW,
                "accepted_at": NOW if outcome == "accepted" else ""})

    def _settle(self, accepted):
        for pid in range(1, 40):
            outcome = "accepted" if pid <= accepted else "withdrawn"
            record_invitation(self.db, "C1", pid, {
                "outcome": outcome, "submitted_at": NOW,
                "accepted_at": NOW if outcome == "accepted" else ""})

    def test_acceptance_never_touches_replies_pain_proposals_or_revenue(self):
        before = scoreboard(self.db)
        self._settle(39)
        after = scoreboard(self.db)
        for key in ("meaningful_responses", "discovery_calls", "diagnostics_proposed",
                    "commercial_proposals", "paying_customers", "collected_revenue_pence",
                    "outreach_sent"):
            self.assertEqual(after[key], before[key],
                             f"39 accepted connections must not move {key}")
        self.assertEqual(access_result(self.db, "C1")["accepted"], 39)

    def test_a_partial_cohort_is_not_evaluable(self):
        self._accept(30)   # 30 accepted, 9 still pending
        result = access_result(self.db, "C1")
        self.assertEqual(result["verdict"], "NOT_EVALUABLE")
        self.assertEqual(result["pending"], 9)

    def test_the_preregistered_bands_are_counts_not_opinions(self):
        for accepted, expected in ((0, "PIVOT"), (7, "PIVOT"), (8, "ADJUST"),
                                   (28, "ADJUST"), (29, "PROCEED"), (39, "PROCEED")):
            with self.subTest(accepted=accepted):
                db = str(Path(self.tmp.name) / f"g{accepted}.db")
                init_db(db)
                with connect(db) as con:
                    for pid in range(1, 40):
                        con.execute(
                            """INSERT INTO prospects(id, company, website, priority, target_roles,
                                 evidence, source_url, status) VALUES (?, ?, 'https://x.test','B','MD',
                                 'MULTI_DIRECTOR','https://x.test/a','qualified_batch_07')""",
                            (pid, f"Co {pid}"))
                for pid in range(1, 40):
                    add_identity(db, {"prospect_id": pid, "identity_type": "linkedin",
                                      "value": f"https://uk.linkedin.com/in/p{pid}", "provider": "test",
                                      "verification_status": "observed_published",
                                      "source_url": f"https://uk.linkedin.com/in/p{pid}",
                                      "observed_at": NOW, "confidence": 0.8})
                freeze_execution_cohort(db, "C1")
                for pid in range(1, 40):
                    out = "accepted" if pid <= accepted else "withdrawn"
                    record_invitation(db, "C1", pid, {"outcome": out, "submitted_at": NOW,
                                                      "accepted_at": NOW if out == "accepted" else ""})
                self.assertEqual(access_result(db, "C1")["verdict"], expected)

    def test_adjust_computes_expansion_from_the_observed_rate(self):
        self._settle(12)
        result = access_result(self.db, "C1")
        self.assertEqual(result["verdict"], "ADJUST")
        self.assertEqual(result["expansion"]["additional_accepts_required"], 17)
        # 17 / (12/39) = 55.25 -> 56
        self.assertEqual(result["expansion"]["additional_verified_identities_required"], 56)

    def test_the_denominator_is_invitations_submitted_not_cohort_size(self):
        for pid in range(1, 11):
            record_invitation(self.db, "C1", pid, {"outcome": "accepted", "submitted_at": NOW,
                                                   "accepted_at": NOW})
        for pid in range(11, 40):
            record_invitation(self.db, "C1", pid, {"outcome": "withdrawn", "submitted_at": NOW})
        self.assertAlmostEqual(access_result(self.db, "C1")["accept_rate"], 10 / 39)
        # An unsent invitation is not a refusal: with only 10 submitted the rate is 10/10.
        db2 = str(Path(self.tmp.name) / "partial.db")
        init_db(db2)
        with connect(db2) as con:
            for pid in (1, 2):
                con.execute("""INSERT INTO prospects(id, company, website, priority, target_roles,
                    evidence, source_url, status) VALUES (?, ?, 'https://x.test','B','MD','x',
                    'https://x.test/a','qualified_batch_07')""", (pid, f"Co {pid}"))
        for pid in (1, 2):
            add_identity(db2, {"prospect_id": pid, "identity_type": "linkedin",
                               "value": f"https://uk.linkedin.com/in/q{pid}", "provider": "test",
                               "verification_status": "observed_published",
                               "source_url": f"https://uk.linkedin.com/in/q{pid}",
                               "observed_at": NOW, "confidence": 0.8})
        freeze_execution_cohort(db2, "C2")
        record_invitation(db2, "C2", 1, {"outcome": "accepted", "submitted_at": NOW,
                                         "accepted_at": NOW})
        r = access_result(db2, "C2")
        self.assertEqual(r["accept_rate"], 1.0)
        self.assertEqual(r["not_submitted"], 1)
        self.assertEqual(r["verdict"], "NOT_EVALUABLE")

    def test_nothing_submitted_reports_no_rate_rather_than_zero(self):
        result = access_result(self.db, "C1")
        self.assertIsNone(result["accept_rate"], "0 of 0 is not a 0% accept rate")

    def test_the_invitation_treatment_is_frozen(self):
        with self.assertRaises(ExecutionError) as ctx:
            record_invitation(self.db, "C1", 1, {"outcome": "accepted", "accepted_at": NOW,
                                                 "treatment": "invitation_with_note"})
        self.assertEqual(ctx.exception.code, "treatment_changed")

    def test_an_acceptance_must_carry_its_timestamp(self):
        with self.assertRaises(ExecutionError):
            record_invitation(self.db, "C1", 1, {"outcome": "accepted"})
        with self.assertRaises(ExecutionError):
            record_invitation(self.db, "C1", 1, {"outcome": "pending", "accepted_at": NOW})


class WilsonTests(unittest.TestCase):
    def test_zero_of_none_spans_the_whole_interval(self):
        self.assertEqual(wilson(0, 0), (0.0, 1.0))

    def test_a_measured_zero_bounds_the_upper_tail(self):
        lo, hi = wilson(0, 39)
        self.assertEqual(lo, 0.0)
        self.assertLess(hi, 0.10)


if __name__ == "__main__":
    unittest.main()
