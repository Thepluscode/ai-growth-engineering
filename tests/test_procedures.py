"""Marketing procedures as experimental inputs. Synthetic stores; every expected value is hard-coded.
Admission belongs to the Intelligent Machine: these tests prove only that an export which is not a
current approval is refused, that a declared version cannot drift after exposure, and that nothing
weaker than a controlled, matured, powered comparison is called causal."""
from __future__ import annotations

import ast
import copy
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from ai_growth_engineering import procedures as pr
from ai_growth_engineering import registries
from ai_growth_engineering.cli import main
from ai_growth_engineering.funnel_events import effective_events, record_event
from ai_growth_engineering.marketing_engineer import render_status, status_report
from ai_growth_engineering.models import ExperimentSpec
from ai_growth_engineering.registry import add_experiment, seed_registries
from ai_growth_engineering.revenue_loop import compute_metrics
from ai_growth_engineering.storage import connect, init_db

ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-09-30"
FROZEN = "2026-07-01T00:00:00+00:00"
CANDIDATE_HASH = "a" * 64
EXPORT = {
    "contract_version": "1", "contract": "approved-skill-export.v1", "skill_id": "ext_outbound_writer",
    "skill_version": "2.0.0", "content_hash": CANDIDATE_HASH,
    "source": {"source_type": "github", "original_source_url": None, "original_repository": "example/skills",
               "source_commit": "5b2c0007766c6a1cf1d53fd8fc73e979e0821022", "license": "MIT"},
    "admission_status": "APPROVED", "effective_status": "FORKED",
    "permissions": {"filesystem": "none", "network": "none", "credentials": "none", "tools": [], "code_execution": False,
                    "external_actions": [], "data_classes": [], "human_approval": True},
    "approved_use_cases": ["message_generation"], "control_plane_mapping": ["evidence"],
    "evaluation_refs": ["evaluations/ext_outbound_writer-aaaaaaaa-vs-outreach.yaml"],
    "approved_by": "founder", "approved_at": "2026-09-10", "review_after": "2027-03-10",
}
BASELINE_REF = "theplus.outreach-research@1.0.0"
CANDIDATE_REF = "ext_outbound_writer@2.0.0"


def frozen_clock():
    return mock.patch("ai_growth_engineering.procedures._utc_now", return_value=FROZEN)


class ProcedureCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)
        self.n = 0
        registries.add(self.db, "offers", {"offer_id": "OFF-A", "buyer": "b", "problem": "p", "outcome": "o"})
        registries.add(self.db, "offers", {"offer_id": "OFF-B", "buyer": "b", "problem": "p", "outcome": "o"})
        for campaign, experiment, offer in (("CMP-P", "EXP-ACQ-0010", "OFF-A"), ("CMP-X", "EXP-ACQ-0010", "OFF-B"),
                                            ("CMP-Q", "EXP-ACQ-0011", "OFF-A"), ("CMP-Y", "EXP-ACQ-0011", "OFF-B")):
            registries.add(self.db, "campaigns", {"campaign_id": campaign, "channel": "email", "icp": "Founders",
                                                  "objective": "qualified_reply_rate", "status": "active",
                                                  "offer_id": offer, "experiment_id": experiment})
        self.experiment("EXP-ACQ-0010", variable="procedure")
        self.experiment("EXP-ACQ-0011")
        pr.register_internal(self.db, str(ROOT / "skills" / "outreach-research"), ["message_generation"])
        self.import_export(EXPORT)

    def experiment(self, experiment_id, variable="", primary_metric="qualified_reply_rate", minimum_sample=60):
        add_experiment(self.db, ExperimentSpec(
            experiment_id=experiment_id, hypothesis="the candidate procedure earns more qualified replies",
            primary_metric=primary_metric, success_threshold=0.2, review_threshold=0.05, minimum_sample=minimum_sample,
            variable=variable, control="baseline procedure" if variable else "", variant="candidate" if variable else ""))

    def import_export(self, doc, name="export.json"):
        path = Path(self.tmp.name) / name
        path.write_text(json.dumps(doc), encoding="utf-8")
        return pr.import_export(self.db, str(path), today="2026-09-15")

    def declare_controlled(self, experiment="EXP-ACQ-0010"):
        with frozen_clock():
            pr.bind(self.db, experiment, CANDIDATE_REF, "VARIABLE", arm="candidate")
            pr.bind(self.db, experiment, BASELINE_REF, "VARIABLE", arm="baseline")

    def ev(self, event_type, company, **kw):
        self.n += 1
        values = {"event_type": event_type, "company": company, "occurred_at": "2026-08-02", "source": "test",
                  "source_record_id": f"r{self.n}", "provenance": "operator_recorded"}
        values.update(kw)
        return record_event(self.db, values)

    def cohort(self, prefix, n, *, qualified=0, experiment="EXP-ACQ-0010", arm="", campaign="CMP-P", at="2026-08-02",
               provenance="operator_recorded", bounced=False, payments=0):
        for i in range(n):
            company = f"{prefix}{i}"
            common = {"experiment_id": experiment, "arm": arm, "campaign_id": campaign, "occurred_at": at,
                      "provenance": provenance}
            self.ev("message_sent", company, creative_id="CR-A", channel="email",
                    metadata={"recipient_class": "named_buyer"}, **common)
            if bounced:
                self.ev("message_bounced", company, **common)
            if i < qualified:
                self.ev("reply_meaningful", company, **common)
            if i < payments:
                self.ev("payment_received", company, value_pence=150_000, currency="GBP", **common)

    def evaluate(self, **kw):
        args = {"experiment_id": "EXP-ACQ-0010", "candidate_arm": "candidate", "baseline_arm": "baseline",
                "use_case": "message_generation", "as_of": AS_OF}
        args.update(kw)
        return pr.evaluate(self.db, **args)


class ImportContractTests(ProcedureCase):
    def refused(self, doc):
        with self.assertRaises(pr.ProcedureError) as caught:
            self.import_export(doc, name="bad.json")
        return caught.exception.code

    def mutate(self, **changes):
        doc = copy.deepcopy(EXPORT)
        doc["skill_version"] = "9.9.9"
        doc.update(changes)
        return doc

    def test_an_unapproved_export_is_rejected(self):
        self.assertEqual(self.refused(self.mutate(admission_status="QUARANTINED")), "not_approved")
        self.assertNotIn("ext_outbound_writer@9.9.9", pr.procedure_rows(self.db))

    def test_an_unsupported_contract_version_is_rejected(self):
        self.assertEqual(self.refused(self.mutate(contract_version="2")), "unsupported_contract")
        self.assertEqual(self.refused(self.mutate(contract="approved-skill-export.v2")), "unsupported_contract")

    def test_a_missing_or_malformed_hash_is_rejected(self):
        self.assertEqual(self.refused(self.mutate(content_hash=None)), "hash_missing")
        self.assertEqual(self.refused(self.mutate(content_hash="deadbeef")), "hash_missing")

    def test_a_revoked_or_unadopted_skill_is_rejected(self):
        self.assertEqual(self.refused(self.mutate(effective_status="REVOKED")), "revoked")
        self.assertEqual(self.refused(self.mutate(revocation={"revoked": True})), "revoked")

    def test_missing_provenance_is_rejected(self):
        doc = self.mutate()
        doc["source"] = dict(doc["source"], source_commit="unknown")
        self.assertEqual(self.refused(doc), "provenance_missing")
        doc["source"] = dict(EXPORT["source"], original_repository=None)
        self.assertEqual(self.refused(doc), "provenance_missing")

    def test_a_use_case_that_does_not_permit_marketing_is_rejected(self):
        self.assertEqual(self.refused(self.mutate(approved_use_cases=["code_review"])), "use_case_not_permitted")

    def test_an_expired_review_and_an_off_contract_field_are_rejected(self):
        self.assertEqual(self.refused(self.mutate(review_after="2026-09-01")), "review_expired")
        self.assertEqual(self.refused(self.mutate(effectiveness="proven")), "schema_invalid")

    def test_registration_preserves_provenance_and_claims_nothing_about_performance(self):
        row = pr.procedure_rows(self.db)[CANDIDATE_REF]
        self.assertEqual((row["procedure_id"], row["procedure_version"], row["content_hash"], row["source_type"]),
                         ("ext_outbound_writer", "2.0.0", CANDIDATE_HASH, "github"))
        self.assertEqual(row["source_ref"], "example/skills@5b2c0007766c6a1cf1d53fd8fc73e979e0821022")
        self.assertEqual((row["license"], row["admission_status"], row["effective_status"], row["approved_by"]),
                         ("MIT", "APPROVED", "FORKED", "founder"))
        self.assertEqual(row["admission_ref"], "approved-skill-export.v1:ext_outbound_writer@2.0.0:2026-09-10")
        self.assertEqual(len(row["import_sha256"]), 64)
        self.assertFalse({"score", "lift", "win_rate", "revenue_pence", "proven"} & set(row))
        self.assertEqual(self.import_export(EXPORT), {"procedure_ref": CANDIDATE_REF, "inserted": False,
                                                      "evidence_status": "KNOWN"})

    def test_new_content_under_the_same_version_is_refused(self):
        self.assertEqual(self.refused(dict(copy.deepcopy(EXPORT), content_hash="b" * 64)),
                         "content_changed_without_version")
        self.assertEqual(pr.procedure_rows(self.db)[CANDIDATE_REF]["content_hash"], CANDIDATE_HASH)


class DeclarationTests(ProcedureCase):
    def test_a_procedure_is_the_variable_only_when_the_frozen_contract_says_so(self):
        with self.assertRaises(pr.ProcedureError) as caught:
            pr.bind(self.db, "EXP-ACQ-0011", CANDIDATE_REF, "VARIABLE", arm="candidate")
        self.assertEqual(caught.exception.code, "variable_not_declared")
        self.assertTrue(pr.bind(self.db, "EXP-ACQ-0011", CANDIDATE_REF, "COMMON_INPUT")["inserted"])
        with self.assertRaises(pr.ProcedureError) as caught:
            pr.bind(self.db, "EXP-ACQ-0011", CANDIDATE_REF, "COMMON_INPUT", arm="x")
        self.assertEqual(caught.exception.code, "arm_rule")

    def test_a_declared_version_cannot_change_after_exposure_and_a_new_version_is_a_new_condition(self):
        self.declare_controlled()
        self.assertFalse(pr.bind(self.db, "EXP-ACQ-0010", CANDIDATE_REF, "VARIABLE", arm="candidate")["inserted"])
        self.cohort("c", 2, arm="candidate")
        self.import_export(dict(copy.deepcopy(EXPORT), skill_version="2.1.0", content_hash="c" * 64), name="v21.json")
        for arm, code in (("candidate", "frozen_binding"), ("challenger", "exposure_started")):
            with self.assertRaises(pr.ProcedureError) as caught:
                pr.bind(self.db, "EXP-ACQ-0010", "ext_outbound_writer@2.1.0", "VARIABLE", arm=arm)
            self.assertEqual(caught.exception.code, code)
        self.experiment("EXP-ACQ-0012", variable="procedure")
        self.assertTrue(pr.bind(self.db, "EXP-ACQ-0012", "ext_outbound_writer@2.1.0", "VARIABLE", arm="candidate")["inserted"])
        declared = {(b["experiment_id"], b["arm"]): (b["procedure_ref"], b["content_hash"]) for b in pr.bindings(self.db)}
        self.assertEqual(declared[("EXP-ACQ-0010", "candidate")], (CANDIDATE_REF, CANDIDATE_HASH))
        self.assertEqual(declared[("EXP-ACQ-0012", "candidate")], ("ext_outbound_writer@2.1.0", "c" * 64))

    def test_a_declaration_is_frozen_in_storage_and_never_touches_the_contract(self):
        with connect(self.db) as con:
            before = dict(con.execute("SELECT * FROM experiments WHERE experiment_id = 'EXP-ACQ-0010'").fetchone())
        self.declare_controlled()
        for statement in ("UPDATE experiment_procedures SET content_hash = 'x'", "DELETE FROM experiment_procedures"):
            with self.assertRaises(sqlite3.DatabaseError):
                with connect(self.db) as con:
                    con.execute(statement)
        with connect(self.db) as con:
            self.assertEqual(dict(con.execute("SELECT * FROM experiments WHERE experiment_id = 'EXP-ACQ-0010'").fetchone()),
                             before)

    def test_a_retired_procedure_cannot_be_declared(self):
        pr.retire(self.db, CANDIDATE_REF, "superseded by a reviewed fork")
        with self.assertRaises(pr.ProcedureError) as caught:
            pr.bind(self.db, "EXP-ACQ-0010", CANDIDATE_REF, "VARIABLE", arm="candidate")
        self.assertEqual(caught.exception.code, "retired")


class LineageTests(ProcedureCase):
    def test_events_carry_a_procedure_only_through_their_own_declared_experiment(self):
        self.declare_controlled()
        with frozen_clock():
            pr.bind(self.db, "EXP-ACQ-0011", BASELINE_REF, "COMMON_INPUT")
        declared = pr.bindings(self.db)
        event = {"experiment_id": "EXP-ACQ-0010", "arm": "candidate", "occurred_at": "2026-08-02"}
        self.assertEqual([b["procedure_ref"] for b in pr.lineage(event, declared)], [CANDIDATE_REF])
        self.assertEqual(pr.lineage(dict(event, experiment_id="EXP-ACQ-0099"), declared), [])
        self.assertEqual(pr.lineage(dict(event, occurred_at="2026-06-30"), declared), [])
        self.assertEqual([b["procedure_ref"] for b in pr.lineage(dict(event, experiment_id="EXP-ACQ-0011", arm="any"),
                                                                 declared)], [BASELINE_REF])

    def test_outcomes_in_an_undeclared_experiment_are_never_credited_to_a_procedure_active_at_the_time(self):
        with frozen_clock():
            pr.bind(self.db, "EXP-ACQ-0011", CANDIDATE_REF, "COMMON_INPUT")
        self.cohort("u", 60, qualified=40, experiment="EXP-ACQ-0010", campaign="CMP-P")
        r = self.evaluate(candidate_arm="", baseline_arm="", experiment_id="EXP-ACQ-0010",
                          baseline_experiment_id="EXP-ACQ-0011")
        self.assertEqual(r["result_class"], "NOT_EVALUABLE")
        self.assertIn("never inferred from timing", r["reason"])

    def test_exposures_dated_before_the_declaration_break_the_comparison(self):
        with mock.patch("ai_growth_engineering.procedures._utc_now", return_value="2026-08-05T00:00:00+00:00"):
            pr.bind(self.db, "EXP-ACQ-0010", CANDIDATE_REF, "VARIABLE", arm="candidate")
            pr.bind(self.db, "EXP-ACQ-0010", BASELINE_REF, "VARIABLE", arm="baseline")
        self.cohort("c", 60, qualified=30, arm="candidate")
        self.cohort("b", 60, qualified=12, arm="baseline")
        r = self.evaluate()
        self.assertEqual(r["result_class"], "CONFOUNDED")
        self.assertIn("predate the procedure's declaration", r["reason"])

    def test_an_event_recording_a_different_procedure_is_a_competing_variable(self):
        self.declare_controlled()
        self.cohort("c", 60, qualified=30, arm="candidate")
        self.cohort("b", 60, qualified=12, arm="baseline")
        self.ev("reply_received", "c0", experiment_id="EXP-ACQ-0010", arm="candidate",
                metadata={"procedure_ref": "other_writer@1.0.0"})
        self.assertEqual(self.evaluate()["result_class"], "CONFOUNDED")


class EvaluationTests(ProcedureCase):
    def test_a_controlled_matured_powered_experiment_earns_a_controlled_effect(self):
        self.declare_controlled()
        self.cohort("c", 60, qualified=30, arm="candidate", payments=1)
        self.cohort("b", 60, qualified=12, arm="baseline")
        r = self.evaluate()
        self.assertEqual((r["result_class"], r["evidence_class"], r["decision"], r["market_validation"]),
                         ("CONTROLLED_EFFECT", "CONTROLLED_MARKET_EXPERIMENT", "KEEP", True))
        self.assertEqual((r["metric"]["candidate"]["numerator"], r["metric"]["candidate"]["denominator"],
                          r["metric"]["baseline"]["numerator"]), (30, 60, 12))
        self.assertAlmostEqual(r["metric"]["delta"], 0.30)
        self.assertEqual(r["metric"]["z"], 3.45)
        self.assertEqual((r["revenue"]["claim"], r["revenue"]["candidate"]["customers"]), ("ASSOCIATED_ONLY", 1))
        self.assertIn(f"{CANDIDATE_REF} caused the revenue observed alongside it.", r["unsupported_claims"])
        self.assertEqual(r["money_graph"], {"baseline": ["CMP-P"], "candidate": ["CMP-P"]})
        doc = pr.result_document(r, generated_at="2026-09-30T00:00:00+00:00")
        self.assertEqual(pr.validate_result(doc), [])
        self.assertEqual((doc["skill_id"], doc["content_hash"], doc["decision"]), ("ext_outbound_writer", CANDIDATE_HASH, "KEEP"))
        self.assertIn("RECOMMENDATION_ONLY", pr.render_report(r))

    def test_a_controlled_loss_is_a_regression(self):
        self.declare_controlled()
        self.cohort("c", 60, qualified=12, arm="candidate")
        self.cohort("b", 60, qualified=30, arm="baseline")
        r = self.evaluate()
        self.assertEqual((r["result_class"], r["decision"], r["market_validation"]), ("REGRESSION", "REJECT", False))

    def test_an_observational_comparison_never_produces_a_controlled_effect(self):
        with frozen_clock():
            pr.bind(self.db, "EXP-ACQ-0010", CANDIDATE_REF, "VARIABLE", arm="candidate")
            pr.bind(self.db, "EXP-ACQ-0011", BASELINE_REF, "COMMON_INPUT")
        self.cohort("c", 60, qualified=30, arm="candidate")
        self.cohort("b", 60, qualified=12, experiment="EXP-ACQ-0011", campaign="CMP-Q")
        r = self.evaluate(baseline_arm="", baseline_experiment_id="EXP-ACQ-0011")
        self.assertEqual((r["result_class"], r["evidence_class"], r["decision"], r["market_validation"]),
                         ("DESCRIPTIVE_DIFFERENCE", "OBSERVATIONAL_MARKET_RESULT", "ITERATE", False))
        self.assertIn(f"{CANDIDATE_REF} caused any difference from the baseline.", r["unsupported_claims"])
        forged = dict(pr.result_document(r), result_class="CONTROLLED_EFFECT", decision="KEEP", market_validation=True)
        self.assertEqual(len(pr.validate_result(forged)), 3)

    def test_two_procedure_experiments_compared_with_each_other_are_still_observational(self):
        self.experiment("EXP-ACQ-0015", variable="procedure")
        with frozen_clock():
            pr.bind(self.db, "EXP-ACQ-0010", CANDIDATE_REF, "VARIABLE", arm="candidate")
            pr.bind(self.db, "EXP-ACQ-0015", BASELINE_REF, "VARIABLE", arm="baseline")
        self.cohort("c", 60, qualified=30, arm="candidate")
        self.cohort("b", 60, qualified=12, experiment="EXP-ACQ-0015", arm="baseline")
        r = self.evaluate(baseline_experiment_id="EXP-ACQ-0015")
        self.assertEqual((r["evidence_class"], r["result_class"]), ("OBSERVATIONAL_MARKET_RESULT", "DESCRIPTIVE_DIFFERENCE"))

    def test_a_confounded_experiment_is_labelled_confounded(self):
        self.declare_controlled()
        self.cohort("c", 60, qualified=30, arm="candidate", campaign="CMP-P")
        self.cohort("b", 60, qualified=12, arm="baseline", campaign="CMP-X")
        r = self.evaluate()
        self.assertEqual((r["result_class"], r["decision"]), ("CONFOUNDED", "ITERATE"))
        self.assertIn("offer differs between the sides", r["reason"])

    def test_arms_that_did_not_run_at_the_same_time_are_confounded(self):
        self.declare_controlled()
        self.cohort("c", 60, qualified=30, arm="candidate", at="2026-08-20")
        self.cohort("b", 60, qualified=12, arm="baseline", at="2026-08-02")
        r = self.evaluate()
        self.assertEqual(r["result_class"], "CONFOUNDED")
        self.assertIn("not concurrent", r["reason"])

    def test_immature_outcomes_generate_no_verdict(self):
        self.declare_controlled()
        self.cohort("c", 60, qualified=30, arm="candidate")
        self.cohort("b", 60, qualified=12, arm="baseline")
        r = self.evaluate(as_of="2026-08-10")
        self.assertEqual((r["result_class"], r["decision"], r["metric"]), ("IMMATURE", "NEED_MORE_DATA", {}))
        self.assertIn("2026-08-16", r["reason"])

    def test_synthetic_fixtures_cannot_validate_anything(self):
        self.declare_controlled()
        self.cohort("c", 60, qualified=30, arm="candidate", provenance="synthetic_fixture", payments=5)
        self.cohort("b", 60, qualified=12, arm="baseline", provenance="synthetic_fixture")
        r = self.evaluate()
        self.assertEqual((r["result_class"], r["market_validation"]), ("NOT_EVALUABLE", False))
        self.assertIn("60 synthetic fixture exposure(s) never count", r["reason"])

    def test_zero_denominators_and_zero_outcomes_stay_honest(self):
        self.declare_controlled()
        self.cohort("c", 40, arm="candidate", bounced=True)
        self.cohort("b", 40, arm="baseline", bounced=True)
        r = self.evaluate()
        self.assertEqual(r["result_class"], "NOT_EVALUABLE")
        self.assertIn("no delivered exposure", r["reason"])
        self.experiment("EXP-ACQ-0013", variable="procedure")
        with frozen_clock():
            pr.bind(self.db, "EXP-ACQ-0013", CANDIDATE_REF, "VARIABLE", arm="candidate")
            pr.bind(self.db, "EXP-ACQ-0013", BASELINE_REF, "VARIABLE", arm="baseline")
        self.cohort("zc", 60, experiment="EXP-ACQ-0013", arm="candidate")
        self.cohort("zb", 60, experiment="EXP-ACQ-0013", arm="baseline")
        r = self.evaluate(experiment_id="EXP-ACQ-0013")
        self.assertEqual((r["result_class"], r["metric"]["candidate"]["value"], r["metric"]["z"]),
                         ("INSUFFICIENT_SAMPLE", 0.0, 0.0))
        self.assertIn("two zeros", r["reason"])

    def test_an_underpowered_test_is_not_a_no_difference(self):
        self.declare_controlled()
        self.cohort("c", 30, qualified=5, arm="candidate")
        self.cohort("b", 30, qualified=3, arm="baseline")
        r = self.evaluate()
        self.assertEqual(r["result_class"], "INSUFFICIENT_SAMPLE")
        self.assertIn("underpowered", r["reason"])
        self.assertAlmostEqual(r["metric"]["minimum_detectable_difference"], 0.2455, places=3)

    def test_a_powered_test_with_no_gap_retains_the_baseline(self):
        self.declare_controlled()
        self.cohort("c", 260, qualified=55, arm="candidate")
        self.cohort("b", 260, qualified=52, arm="baseline")
        r = self.evaluate()
        self.assertEqual((r["result_class"], r["decision"]), ("NO_DIFFERENCE", "REJECT"))
        self.assertLessEqual(r["metric"]["minimum_detectable_difference"], 0.10)

    def test_activity_metrics_and_offline_jobs_are_not_market_evidence(self):
        self.experiment("EXP-ACQ-0014", variable="procedure", primary_metric="messages_generated")
        with frozen_clock():
            pr.bind(self.db, "EXP-ACQ-0014", CANDIDATE_REF, "VARIABLE", arm="candidate")
            pr.bind(self.db, "EXP-ACQ-0014", BASELINE_REF, "VARIABLE", arm="baseline")
        r = self.evaluate(experiment_id="EXP-ACQ-0014")
        self.assertEqual(r["result_class"], "NOT_EVALUABLE")
        self.assertIn("more activity is not better growth", r["reason"])
        self.assertIn("not approved for experiment_analysis",
                      self.evaluate(experiment_id="EXP-ACQ-0014", use_case="experiment_analysis")["reason"])

    def test_an_offline_result_can_never_claim_market_validation(self):
        doc = {"contract_version": "1", "contract": "skill-evaluation-result.v1", "skill_id": "x", "skill_version": "1",
               "content_hash": "d" * 64, "evaluation_type": "OFFLINE_EVAL", "evidence_class": "OFFLINE_EVAL",
               "result_class": "DESCRIPTIVE_DIFFERENCE", "use_case": "experiment_design",
               "baseline": {"procedure_ref": BASELINE_REF, "content_hash": "e" * 64}, "experiment_id": None,
               "metrics": {}, "sample": {}, "maturity": {}, "confounders": [], "unsupported_claims": [],
               "market_validation": False, "decision": "REJECT", "authority": "RECOMMENDATION_ONLY",
               "generated_at": "2026-09-15", "generated_by": "test"}
        self.assertEqual(pr.validate_result(doc), [])
        self.assertTrue(pr.validate_result(dict(doc, market_validation=True)))
        self.assertTrue(pr.validate_result(dict(doc, result_class="CONTROLLED_EFFECT")))
        self.assertTrue(pr.validate_result(dict(doc, authority="EXECUTE")))


class BoundaryTests(ProcedureCase):
    TABLES = ("funnel_events", "outbound_messages", "reply_candidates", "reply_decisions", "commercial_evidence",
              "evidence", "experiments")

    def counts(self):
        with connect(self.db) as con:
            return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in self.TABLES}

    def test_the_existing_revenue_loop_reads_the_same_before_and_after(self):
        self.cohort("u", 40, qualified=4, experiment="EXP-ACQ-0011", campaign="CMP-Q", payments=1)
        before = (render_status(status_report(self.db, as_of=AS_OF)), compute_metrics(effective_events(self.db)))
        self.declare_controlled()
        self.evaluate()
        self.evaluate(candidate_arm="", baseline_arm="", baseline_experiment_id="EXP-ACQ-0011")
        after = (render_status(status_report(self.db, as_of=AS_OF)), compute_metrics(effective_events(self.db)))
        self.assertEqual(before, after)

    def test_evaluating_and_exporting_never_acts(self):
        self.declare_controlled()
        self.cohort("c", 60, qualified=30, arm="candidate")
        self.cohort("b", 60, qualified=12, arm="baseline")
        before = self.counts()
        out = Path(self.tmp.name) / "result.json"
        with redirect_stdout(io.StringIO()):
            main(["marketing-engineer", "procedure", "--db", self.db, "--experiment-id", "EXP-ACQ-0010",
                  "--candidate-arm", "candidate", "--baseline-arm", "baseline", "--use-case", "message_generation",
                  "--as-of", AS_OF, "--export", str(out)])
        self.assertEqual(self.counts(), before)
        self.assertEqual(json.loads(out.read_text())["authority"], "RECOMMENDATION_ONLY")
        tree = ast.parse((ROOT / "src" / "ai_growth_engineering" / "procedures.py").read_text())
        imported = {(node.module or "", alias.name) for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                    for alias in node.names}
        self.assertTrue(imported)
        self.assertFalse({name for _, name in imported} & {"record_event", "correct_event", "approve", "link_outbound",
                                                           "import_outbound_sends", "record_commercial_evidence"})
        self.assertFalse({module for module, _ in imported} & {"reply_capture", "adapters", "outbound_workbench"})

    def test_real_experiment_contracts_are_not_rewritten_and_seeded_baselines_match_their_files(self):
        seed_registries(self.db, str(ROOT / "seeds" / "registries.json"))
        with connect(self.db) as con:
            before = [dict(row) for row in con.execute("SELECT * FROM experiments ORDER BY experiment_id")]
        seeded = {ref: row for ref, row in pr.procedure_rows(self.db).items() if row["source_type"] == "theplus_internal"}
        self.assertEqual(len({row["source_ref"] for row in seeded.values()}), 7)
        for source_ref in {row["source_ref"] for row in seeded.values()}:
            uses = next(row["approved_use_cases"] for row in seeded.values() if row["source_ref"] == source_ref)
            current = pr.internal_record(str(ROOT / Path(source_ref).parent), uses)
            # Older versions stay registered as history; the file's current version must be seeded with its exact hash.
            self.assertIn(current["procedure_ref"], seeded, f"{source_ref} {current['procedure_version']} is not seeded")
            self.assertEqual(seeded[current["procedure_ref"]]["content_hash"], current["content_hash"],
                             f"{source_ref} changed without a version bump")
        with self.assertRaises(pr.ProcedureError) as caught:
            pr.bind(self.db, "EXP-ACQ-0003", BASELINE_REF, "VARIABLE", arm="x")
        self.assertEqual(caught.exception.code, "variable_not_declared")
        with connect(self.db) as con:
            self.assertEqual([dict(row) for row in con.execute("SELECT * FROM experiments ORDER BY experiment_id")], before)


if __name__ == "__main__":
    unittest.main()
