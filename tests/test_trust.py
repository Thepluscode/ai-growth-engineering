from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering.models import ExperimentSpec
from ai_growth_engineering.registry import (
    add_experiment,
    preregister_trust_guardrails,
    record_experiment_result,
    record_trust_observation,
    trust_verdict,
)
from ai_growth_engineering.storage import init_db
from ai_growth_engineering.trust import TrustGuardrailSpec, TrustObservation, evaluate_guardrail


def unsub(**kw) -> TrustGuardrailSpec:
    args = dict(metric="unsubscribe_rate", direction="lower_is_better", baseline=0.012,
                max_absolute=0.020, max_adverse_delta=0.005, minimum_sample=500,
                required=True, source="12-month email baseline")
    args.update(kw)
    return TrustGuardrailSpec(**args)


class GuardrailSpecTests(unittest.TestCase):
    def test_a_required_guardrail_needs_at_least_one_limit(self):
        with self.assertRaises(ValueError):
            TrustGuardrailSpec(metric="complaint_rate", source="x").validate()

    def test_a_required_guardrail_needs_a_baseline_source(self):
        with self.assertRaises(ValueError):
            TrustGuardrailSpec(metric="complaint_rate", max_absolute=0.002).validate()

    def test_a_not_applicable_guardrail_must_say_why(self):
        with self.assertRaises(ValueError):
            TrustGuardrailSpec(metric="unsubscribe_rate", required=False).validate()

    def test_a_not_applicable_guardrail_with_a_reason_is_allowed(self):
        spec = TrustGuardrailSpec(metric="unsubscribe_rate", required=False,
                                  not_applicable_reason="no subscription relationship")
        spec.validate()
        self.assertTrue(evaluate_guardrail(spec, None).allowed)

    def test_sentiment_cannot_be_a_required_gate(self):
        """Diagnostic signal, not enforcement signal, until it can be validated."""
        with self.assertRaises(ValueError):
            TrustGuardrailSpec(metric="sentiment", max_absolute=0.5,
                               source="llm").validate()

    def test_sentiment_is_allowed_as_a_diagnostic(self):
        TrustGuardrailSpec(metric="sentiment", required=False,
                           not_applicable_reason="diagnostic only, not validated").validate()


class GuardrailEvaluationTests(unittest.TestCase):
    def test_within_limits_passes(self):
        obs = TrustObservation("unsubscribe_rate", numerator=8, denominator=1000)  # 0.8%
        self.assertTrue(evaluate_guardrail(unsub(), obs).allowed)

    def test_absolute_ceiling_breach(self):
        obs = TrustObservation("unsubscribe_rate", numerator=25, denominator=1000)  # 2.5%
        d = evaluate_guardrail(unsub(), obs)
        self.assertFalse(d.allowed)
        self.assertIn("breach_absolute", d.reasons[0])

    def test_adverse_delta_breach_even_under_the_absolute_cap(self):
        # 1.8% is under the 2.0% cap but +0.6 points on a 1.2% baseline.
        obs = TrustObservation("unsubscribe_rate", numerator=18, denominator=1000)
        d = evaluate_guardrail(unsub(), obs)
        self.assertFalse(d.allowed)
        self.assertIn("breach_delta", d.reasons[0])

    def test_relative_limit_catches_what_absolute_misses(self):
        # Rare severe event: 0.05% -> 0.15% is +200% but a tiny absolute move.
        spec = TrustGuardrailSpec(metric="chargeback_rate", baseline=0.0005,
                                  max_relative_increase=1.0, minimum_sample=1000,
                                  source="processor statements")
        obs = TrustObservation("chargeback_rate", numerator=15, denominator=10000)
        d = evaluate_guardrail(spec, obs)
        self.assertFalse(d.allowed)
        self.assertIn("breach_relative", d.reasons[0])

    def test_underpowered_is_pending_not_pass(self):
        obs = TrustObservation("unsubscribe_rate", numerator=0, denominator=50)
        d = evaluate_guardrail(unsub(), obs)
        self.assertFalse(d.allowed)
        self.assertTrue(d.requires_approval)
        self.assertIn("underpowered", d.reasons[0])

    def test_missing_observation_is_pending_not_pass(self):
        d = evaluate_guardrail(unsub(), None)
        self.assertFalse(d.allowed)
        self.assertTrue(d.requires_approval)

    def test_zero_denominator_is_not_a_rate_of_zero(self):
        self.assertIsNone(TrustObservation("x", 0, 0).value)

    def test_higher_is_better_direction(self):
        spec = TrustGuardrailSpec(metric="csat", direction="higher_is_better",
                                  baseline=0.90, max_adverse_delta=0.05,
                                  minimum_sample=10, source="survey")
        good = TrustObservation("csat", numerator=88, denominator=100)
        bad = TrustObservation("csat", numerator=80, denominator=100)
        self.assertTrue(evaluate_guardrail(spec, good).allowed)
        self.assertFalse(evaluate_guardrail(spec, bad).allowed)


class NonCompensatoryDecisionTests(unittest.TestCase):
    """The eight cases the decision path must get right."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)
        add_experiment(self.db, ExperimentSpec(
            "EXP-CREATIVE-0001", "proof hooks beat feature hooks", "qualified_conversion_rate",
            success_threshold=0.10, review_threshold=0.05, minimum_sample=1000))

    def _observe(self, metric, numerator, denominator):
        record_trust_observation(
            self.db, "EXP-CREATIVE-0001",
            TrustObservation(metric, numerator, denominator, observed_at="2026-09-01"))

    def test_winner_with_clean_trust_is_KEEP(self):
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0001", [unsub()])
        self._observe("unsubscribe_rate", 8, 1000)
        self.assertEqual(
            record_experiment_result(self.db, "EXP-CREATIVE-0001", 1000, 0.14), "keep")

    def test_winner_breaching_unsubscribe_is_REVIEW_not_KEEP(self):
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0001", [unsub()])
        self._observe("unsubscribe_rate", 30, 1000)
        self.assertEqual(
            record_experiment_result(self.db, "EXP-CREATIVE-0001", 1000, 0.35), "review")

    def test_winner_breaching_complaints_is_REVIEW_not_KEEP(self):
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0001", [
            TrustGuardrailSpec(metric="spam_complaint_rate", baseline=0.0005,
                               max_absolute=0.002, minimum_sample=500,
                               source="ESP reporting")])
        self._observe("spam_complaint_rate", 9, 1000)
        self.assertEqual(
            record_experiment_result(self.db, "EXP-CREATIVE-0001", 1000, 0.40), "review")

    def test_winner_with_a_required_guardrail_never_observed_does_not_KEEP(self):
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0001", [unsub()])
        self.assertNotEqual(
            record_experiment_result(self.db, "EXP-CREATIVE-0001", 1000, 0.30), "keep")

    def test_winner_with_underpowered_trust_data_does_not_KEEP(self):
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0001", [unsub()])
        self._observe("unsubscribe_rate", 0, 50)
        self.assertNotEqual(
            record_experiment_result(self.db, "EXP-CREATIVE-0001", 1000, 0.30), "keep")

    def test_a_primary_loser_with_pristine_trust_does_not_become_KEEP(self):
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0001", [unsub()])
        self._observe("unsubscribe_rate", 0, 5000)
        self.assertEqual(
            record_experiment_result(self.db, "EXP-CREATIVE-0001", 1000, 0.01), "review")

    def test_a_trust_breach_never_produces_a_kill_verdict(self):
        # The system reports numbers; it does not pronounce on the business.
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0001", [unsub()])
        self._observe("unsubscribe_rate", 90, 1000)
        decision = record_experiment_result(self.db, "EXP-CREATIVE-0001", 1000, 0.50)
        self.assertNotIn("kill", decision)
        self.assertEqual(decision, "review")

    def test_the_breach_reason_is_written_into_the_learning_field(self):
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0001", [unsub()])
        self._observe("unsubscribe_rate", 30, 1000)
        record_experiment_result(self.db, "EXP-CREATIVE-0001", 1000, 0.35, learning="proof hook won")
        from ai_growth_engineering.storage import connect
        with connect(self.db) as con:
            learning = con.execute(
                "SELECT learning FROM experiments WHERE experiment_id='EXP-CREATIVE-0001'"
            ).fetchone()["learning"]
        self.assertIn("proof hook won", learning)
        self.assertIn("breach", learning)


class FrozenContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)
        add_experiment(self.db, ExperimentSpec(
            "EXP-CREATIVE-0002", "h", "m", 0.10, 0.05, 100))

    def test_thresholds_may_be_revised_before_any_observation(self):
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0002", [unsub(max_absolute=0.020)])
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0002", [unsub(max_absolute=0.015)])

    def test_changing_a_threshold_after_observations_is_refused(self):
        """Raising a cap after seeing the number is moving a Sharpe threshold post-backtest."""
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0002", [unsub(max_absolute=0.002)])
        record_trust_observation(self.db, "EXP-CREATIVE-0002",
                                 TrustObservation("unsubscribe_rate", 8, 1000))
        with self.assertRaises(ValueError) as ctx:
            preregister_trust_guardrails(self.db, "EXP-CREATIVE-0002", [unsub(max_absolute=0.010)])
        self.assertIn("frozen", str(ctx.exception))

    def test_downgrading_required_after_observations_is_refused(self):
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0002", [unsub()])
        record_trust_observation(self.db, "EXP-CREATIVE-0002",
                                 TrustObservation("unsubscribe_rate", 40, 1000))
        with self.assertRaises(ValueError):
            preregister_trust_guardrails(self.db, "EXP-CREATIVE-0002", [
                unsub(required=False, not_applicable_reason="changed my mind")])

    def test_an_observation_for_an_undeclared_metric_is_refused(self):
        with self.assertRaises(ValueError):
            record_trust_observation(self.db, "EXP-CREATIVE-0002",
                                     TrustObservation("refund_rate", 1, 100))

    def test_guardrails_cannot_attach_to_an_unknown_experiment(self):
        with self.assertRaises(ValueError):
            preregister_trust_guardrails(self.db, "EXP-CREATIVE-9999", [unsub()])

    def test_verdict_reports_pending_when_nothing_observed(self):
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0002", [unsub()])
        v = trust_verdict(self.db, "EXP-CREATIVE-0002")
        self.assertFalse(v.passed)
        self.assertTrue(v.pending)


if __name__ == "__main__":
    unittest.main()
