from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering.funnel_events import record_event
from ai_growth_engineering.models import ExperimentSpec
from ai_growth_engineering.registry import (
    add_experiment,
    declare_trust_not_applicable,
    preregister_trust_guardrails,
    record_experiment_result,
    record_trust_observation,
    trust_policy,
    trust_verdict,
)
from ai_growth_engineering.storage import init_db
from ai_growth_engineering.trust import (
    TrustGuardrailSpec, TrustObservation, evaluate_all, evaluate_guardrail,
)


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


NA_REASON = "one-to-one cold outreach: no subscription, billing or ad-placement relationship exists"


class EmptyTrustPolicyFailsClosed(unittest.TestCase):
    """Declaring nothing is not the same as having no trust risk.

    An experiment that never declared a policy used to pass the trust gate on the strength
    of having nothing to check. Silence is now PENDING; only a resolved policy — required
    guardrails, or NOT_APPLICABLE with a recorded reason — can contribute to KEEP.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)
        add_experiment(self.db, ExperimentSpec("EXP-CREATIVE-0101", "h", "m", 0.10, 0.05, 100))

    def test_an_undeclared_policy_is_pending_not_passed(self):
        verdict = trust_verdict(self.db, "EXP-CREATIVE-0101")
        self.assertFalse(verdict.passed)
        self.assertTrue(verdict.pending)
        self.assertIn("no_trust_policy_declared", verdict.reasons)

    def test_a_primary_win_with_no_declared_policy_does_not_keep(self):
        self.assertEqual(record_experiment_result(self.db, "EXP-CREATIVE-0101", 100, 0.14), "preregistered")

    def test_evaluate_all_with_no_specs_is_pending(self):
        verdict = evaluate_all([], {})
        self.assertFalse(verdict.passed)
        self.assertTrue(verdict.pending)

    def test_not_applicable_with_a_recorded_reason_resolves_the_policy(self):
        declare_trust_not_applicable(self.db, "EXP-CREATIVE-0101", NA_REASON)
        verdict = trust_verdict(self.db, "EXP-CREATIVE-0101")
        self.assertTrue(verdict.passed)
        self.assertEqual(record_experiment_result(self.db, "EXP-CREATIVE-0101", 100, 0.14), "keep")

    def test_not_applicable_without_a_reason_is_refused(self):
        with self.assertRaises(ValueError):
            declare_trust_not_applicable(self.db, "EXP-CREATIVE-0101", "   ")

    def test_a_policy_cannot_be_both_declared_and_not_applicable(self):
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0101", [unsub()])
        with self.assertRaises(ValueError):
            declare_trust_not_applicable(self.db, "EXP-CREATIVE-0101", NA_REASON)


class TrustContractFreezesBeforeTreatment(unittest.TestCase):
    """The contract freezes at first treatment, not at first trust observation.

    Declaring a guardrail after exposure has begun is choosing the gate with the outcome in
    view. The old freeze fired only once trust observations existed, which left the whole
    exposure window open for adding or loosening guardrails.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)
        add_experiment(self.db, ExperimentSpec("EXP-CREATIVE-0102", "h", "m", 0.10, 0.05, 100))

    def _expose(self, event_type="message_sent"):
        record_event(self.db, {
            "event_type": event_type, "occurred_at": "2026-09-01", "company": "Acme",
            "person_id": "P-01", "channel": "email", "experiment_id": "EXP-CREATIVE-0102",
            "source": "test", "source_record_id": f"EXP-CREATIVE-0102|{event_type}",
            "provenance": "operator_recorded"})

    def test_guardrails_may_be_declared_before_exposure(self):
        self.assertEqual(preregister_trust_guardrails(self.db, "EXP-CREATIVE-0102", [unsub()]), 1)

    def test_declaring_a_guardrail_after_exposure_is_refused(self):
        self._expose()
        with self.assertRaises(ValueError) as ctx:
            preregister_trust_guardrails(self.db, "EXP-CREATIVE-0102", [unsub()])
        self.assertIn("frozen", str(ctx.exception))

    def test_adding_a_second_guardrail_after_exposure_is_refused(self):
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0102", [unsub()])
        self._expose()
        with self.assertRaises(ValueError):
            preregister_trust_guardrails(self.db, "EXP-CREATIVE-0102", [
                TrustGuardrailSpec(metric="spam_complaint_rate", baseline=0.001,
                                   max_absolute=0.003, source="mailbox provider report")])

    def test_loosening_a_guardrail_after_exposure_is_refused(self):
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0102", [unsub(max_absolute=0.002)])
        self._expose()
        with self.assertRaises(ValueError):
            preregister_trust_guardrails(self.db, "EXP-CREATIVE-0102", [unsub(max_absolute=0.050)])

    def test_resubmitting_the_identical_contract_after_exposure_is_refused(self):
        """No writes at all after treatment — even a no-op re-declaration."""
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0102", [unsub()])
        self._expose()
        with self.assertRaises(ValueError):
            preregister_trust_guardrails(self.db, "EXP-CREATIVE-0102", [unsub()])

    def test_declaring_not_applicable_after_exposure_is_refused(self):
        self._expose()
        with self.assertRaises(ValueError):
            declare_trust_not_applicable(self.db, "EXP-CREATIVE-0102", NA_REASON)

    def test_a_recorded_result_also_freezes_the_contract(self):
        record_experiment_result(self.db, "EXP-CREATIVE-0102", 100, 0.14)
        with self.assertRaises(ValueError):
            preregister_trust_guardrails(self.db, "EXP-CREATIVE-0102", [unsub()])

    def test_an_undelivered_attempt_is_not_treatment(self):
        """A bounce reached nobody; the contract may still be declared."""
        self._expose("message_bounced")
        self.assertEqual(preregister_trust_guardrails(self.db, "EXP-CREATIVE-0102", [unsub()]), 1)

    def test_the_policy_state_and_freeze_point_are_recorded(self):
        self.assertEqual(trust_policy(self.db, "EXP-CREATIVE-0102")["state"], "UNDECLARED")
        preregister_trust_guardrails(self.db, "EXP-CREATIVE-0102", [unsub()])
        self.assertEqual(trust_policy(self.db, "EXP-CREATIVE-0102")["state"], "DECLARED")
        self.assertFalse(trust_policy(self.db, "EXP-CREATIVE-0102")["treatment_started_at"])
        self._expose()
        self.assertEqual(trust_policy(self.db, "EXP-CREATIVE-0102")["treatment_started_at"], "2026-09-01")


class TrustCommandLine(unittest.TestCase):
    """The writers are reachable from a shipped command, and refusals surface as REFUSED."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)
        add_experiment(self.db, ExperimentSpec("EXP-CREATIVE-0103", "h", "m", 0.10, 0.05, 100))

    def run_cli(self, *argv):
        import contextlib
        import io
        import json

        from ai_growth_engineering.cli import build_parser

        args = build_parser().parse_args(["trust", *argv, "--db", self.db,
                                          "--experiment-id", "EXP-CREATIVE-0103"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            args.func(args)
        return json.loads(out.getvalue())

    def test_show_reports_an_undeclared_policy_as_pending(self):
        result = self.run_cli("show")
        self.assertEqual(result["policy"]["state"], "UNDECLARED")
        self.assertTrue(result["verdict"]["pending"])

    def test_declare_then_observe_resolves_through_the_command(self):
        self.run_cli("declare", "--metric", "unsubscribe_rate", "--baseline", "0.012",
                     "--max-absolute", "0.02", "--minimum-sample", "100", "--source", "email baseline")
        result = self.run_cli("observe", "--metric", "unsubscribe_rate", "--numerator", "1",
                              "--denominator", "200", "--observed-at", "2026-09-01")
        self.assertEqual(result["policy"]["state"], "DECLARED")
        self.assertTrue(result["verdict"]["passed"])

    def test_not_applicable_is_recorded_with_its_reason(self):
        result = self.run_cli("not-applicable", "--reason", NA_REASON)
        self.assertEqual(result["policy"]["state"], "NOT_APPLICABLE")
        self.assertEqual(result["policy"]["reason"], NA_REASON)

    def test_an_observation_without_its_own_date_is_refused(self):
        self.run_cli("declare", "--metric", "unsubscribe_rate", "--baseline", "0.012",
                     "--max-absolute", "0.02", "--source", "email baseline")
        with self.assertRaises(SystemExit) as ctx:
            self.run_cli("observe", "--metric", "unsubscribe_rate", "--numerator", "1", "--denominator", "200")
        self.assertIn("REFUSED", str(ctx.exception))

    def test_a_refusal_is_printed_not_swallowed(self):
        with self.assertRaises(SystemExit) as ctx:
            self.run_cli("not-applicable", "--reason", "")
        self.assertIn("REFUSED", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
