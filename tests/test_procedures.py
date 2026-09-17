"""Marketing procedures as experimental inputs. Synthetic stores; every expected value is hard-coded.
Admission belongs to the Intelligent Machine: these tests prove only that an export which is not a
current approval is refused, that a declared version cannot drift after exposure, and that nothing
weaker than a controlled, matured, powered comparison is called causal."""
from __future__ import annotations

import ast
import copy
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from ai_growth_engineering import procedures as pr
from ai_growth_engineering import registries
from ai_growth_engineering.cli import main
from ai_growth_engineering.funnel_events import effective_events, record_event
from ai_growth_engineering.marketing_engineer import render_status, status_report
from ai_growth_engineering.models import ExperimentSpec
from ai_growth_engineering.registry import (
    add_experiment, declare_trust_not_applicable, preregister_trust_guardrails, record_trust_observation, seed_registries,
)
from ai_growth_engineering.trust import TrustGuardrailSpec, TrustObservation
from ai_growth_engineering.revenue_loop import compute_metrics
from ai_growth_engineering.storage import connect, init_db

ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-09-30"
FROZEN = "2026-07-01T00:00:00+00:00"
# Written by the Intelligent Machine's own export_document() and normalise_permissions() at IM commit
# 0cddae4, and schema-valid there, so every permission section has the nested shape the IM really emits.
# Only review_after moves: the fixture must describe a CURRENT approval whenever the suite runs.
FIXTURE = ROOT / "tests" / "fixtures" / "im_approved_skill_export.v1.json"
# Written by the Intelligent Machine's own revocation_notice() for that same published identity.
REVOCATION_FIXTURE = ROOT / "tests" / "fixtures" / "im_skill_revocation.v1.json"
IM_REPO = Path(os.environ.get("IM_REPO", str(ROOT.parent / "theplus-intelligent-machine")))
EXPORT = dict(json.loads(FIXTURE.read_text(encoding="utf-8")),
              review_after=(date.today() + timedelta(days=90)).isoformat())
CANDIDATE_HASH = EXPORT["content_hash"]
BASELINE_REF = "theplus.outreach-research@1.0.0"
CANDIDATE_REF = f"{EXPORT['skill_id']}@{EXPORT['skill_version']}"


def frozen_clock():
    return mock.patch("ai_growth_engineering.procedures._utc_now", return_value=FROZEN)


class ProcedureCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # This test's governed exports directory — the one origin import accepts.
        self.exports = Path(self.tmp.name) / "published" / "contracts" / "exports"
        env = mock.patch.dict(os.environ, {pr.EXPORTS_DIR_ENV: str(self.exports)})
        env.start()
        self.addCleanup(env.stop)
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

    def import_export(self, doc):
        """Write the export where the Intelligent Machine publishes it — this test's governed exports
        directory, one file per skill — and import that file itself."""
        self.exports.mkdir(parents=True, exist_ok=True)
        path = self.exports / f"{doc.get('skill_id')}.json"
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
            self.import_export(doc)
        return caught.exception.code

    def mutate(self, **changes):
        doc = copy.deepcopy(EXPORT)
        doc["skill_version"] = "9.9.9"
        doc.update(changes)
        return doc

    def test_an_unapproved_export_is_rejected(self):
        self.assertEqual(self.refused(self.mutate(admission_status="QUARANTINED")), "not_approved")
        self.assertNotIn("vendor_outbound_writer@9.9.9", pr.procedure_rows(self.db))

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
        doc["source"] = dict(EXPORT["source"], original_repository=None, original_source_url=None)
        self.assertEqual(self.refused(doc), "provenance_missing")

    def test_a_use_case_that_does_not_permit_marketing_is_rejected(self):
        self.assertEqual(self.refused(self.mutate(approved_use_cases=["code_review"])), "use_case_not_permitted")

    def test_an_expired_review_and_an_off_contract_field_are_rejected(self):
        self.assertEqual(self.refused(self.mutate(review_after="2026-09-01")), "review_expired")
        self.assertEqual(self.refused(self.mutate(effectiveness="proven")), "schema_invalid")

    def test_registration_preserves_provenance_and_claims_nothing_about_performance(self):
        row = pr.procedure_rows(self.db)[CANDIDATE_REF]
        self.assertEqual((row["procedure_id"], row["procedure_version"], row["content_hash"], row["source_type"]),
                         ("vendor_outbound_writer", "2.0.0", CANDIDATE_HASH, "git"))
        self.assertEqual(row["source_ref"], "vendor/skills@5b2c0007766c6a1cf1d53fd8fc73e979e0821022")
        self.assertEqual(json.loads(row["permissions_json"]), EXPORT["permissions"])
        self.assertEqual((row["license"], row["admission_status"], row["effective_status"], row["approved_by"]),
                         ("MIT", "APPROVED", "FORKED", "founder"))
        self.assertEqual(row["admission_ref"], "approved-skill-export.v1:vendor_outbound_writer@2.0.0:2026-09-10")
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
        self.import_export(dict(copy.deepcopy(EXPORT), skill_version="2.1.0", content_hash="c" * 64))
        for arm, code in (("candidate", "frozen_binding"), ("challenger", "exposure_started")):
            with self.assertRaises(pr.ProcedureError) as caught:
                pr.bind(self.db, "EXP-ACQ-0010", "vendor_outbound_writer@2.1.0", "VARIABLE", arm=arm)
            self.assertEqual(caught.exception.code, code)
        self.experiment("EXP-ACQ-0012", variable="procedure")
        self.assertTrue(pr.bind(self.db, "EXP-ACQ-0012", "vendor_outbound_writer@2.1.0", "VARIABLE", arm="candidate")["inserted"])
        declared = {(b["experiment_id"], b["arm"]): (b["procedure_ref"], b["content_hash"]) for b in pr.bindings(self.db)}
        self.assertEqual(declared[("EXP-ACQ-0010", "candidate")], (CANDIDATE_REF, CANDIDATE_HASH))
        self.assertEqual(declared[("EXP-ACQ-0012", "candidate")], ("vendor_outbound_writer@2.1.0", "c" * 64))

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
        declare_trust_not_applicable(self.db, "EXP-ACQ-0010", "fixture: trust not under test here")
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
        self.assertEqual((doc["skill_id"], doc["content_hash"], doc["decision"]), ("vendor_outbound_writer", CANDIDATE_HASH, "KEEP"))
        self.assertIn("RECOMMENDATION_ONLY", pr.render_report(r))

    def test_a_controlled_win_without_a_trust_policy_is_withheld_not_kept(self):
        """Evidence class stands; the decision waits for a resolved trust policy."""
        self.declare_controlled()
        self.cohort("c", 60, qualified=30, arm="candidate")
        self.cohort("b", 60, qualified=12, arm="baseline")
        r = self.evaluate()
        self.assertEqual((r["result_class"], r["decision"]), ("CONTROLLED_EFFECT", "NEED_MORE_DATA"))
        self.assertIn("no_trust_policy_declared", r["reason"])
        self.assertEqual(pr.validate_result(pr.result_document(r, generated_at="2026-09-30T00:00:00+00:00")), [])

    def test_a_controlled_win_that_breaches_trust_is_iterate_not_keep(self):
        self.declare_controlled()
        preregister_trust_guardrails(self.db, "EXP-ACQ-0010", [TrustGuardrailSpec(
            metric="complaint_rate", baseline=0.001, max_absolute=0.01, minimum_sample=10, source="fixture")])
        self.cohort("c", 60, qualified=30, arm="candidate")
        self.cohort("b", 60, qualified=12, arm="baseline")
        record_trust_observation(self.db, "EXP-ACQ-0010",
                                 TrustObservation("complaint_rate", 5, 60, observed_at="2026-08-20"))
        r = self.evaluate()
        self.assertEqual((r["result_class"], r["decision"]), ("CONTROLLED_EFFECT", "ITERATE"))
        self.assertIn("breach_absolute", r["reason"])

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
        errors = pr.validate_result(dict(pr.result_document(r), result_class="CONTROLLED_EFFECT", decision="KEEP",
                                         market_validation=True))
        for fragment in ("only a CONTROLLED_MARKET_EXPERIMENT", "market_validation needs", "KEEP needs"):
            self.assertTrue(any(fragment in e for e in errors), errors)

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
        doc = {"contract_version": "2", "contract": "skill-evaluation-result.v2", "skill_id": "x", "skill_version": "1",
               "content_hash": "d" * 64, "evaluation_type": "OFFLINE_EVAL", "evidence_class": "OFFLINE_EVAL",
               "result_class": "DESCRIPTIVE_DIFFERENCE", "use_case": "experiment_design",
               "baseline": {"procedure_ref": BASELINE_REF, "content_hash": "e" * 64}, "experiment_id": None,
               "metrics": {}, "sample": {}, "maturity": {}, "revenue": {"claim": "NONE_OBSERVED"}, "confounders": [],
               "competing_variables": [], "includes_synthetic": False, "unsupported_claims": [],
               "market_validation": False, "decision": "REJECT", "authority": "RECOMMENDATION_ONLY",
               "generated_at": "2026-09-15", "generated_by": "test"}
        self.assertEqual(pr.validate_result(doc), [])
        self.assertTrue(pr.validate_result(dict(doc, market_validation=True)))
        self.assertTrue(pr.validate_result(dict(doc, revenue={"claim": "ASSOCIATED_ONLY"})))
        self.assertTrue(pr.validate_result(dict(doc, revenue={"claim": "made up"})))
        self.assertTrue(pr.validate_result(dict(doc, contract="skill-evaluation-result.v1", contract_version="1")),
                        "a v1 label does not make v2 fields valid under the v1 schema")
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


class UpstreamApprovalTests(ProcedureCase):
    """An import is a snapshot. A NEW declaration re-reads the export the procedure came from and fails
    closed; declarations already made stay exactly as they were."""

    def upstream(self, **changes):
        path = Path(self.tmp.name) / "published" / "contracts" / "exports" / f"{EXPORT['skill_id']}.json"
        path.write_text(json.dumps(dict(copy.deepcopy(EXPORT), **changes)), encoding="utf-8")
        return path

    def snapshot(self):
        with connect(self.db) as con:
            return tuple([dict(r) for r in con.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                         for table in ("experiments", "procedures", "experiment_procedures"))

    def refused(self, code, **bind):
        args = {"experiment_id": "EXP-ACQ-0011", "procedure_ref": CANDIDATE_REF, "role": "COMMON_INPUT"}
        args.update(bind)
        before = self.snapshot()
        with self.assertRaises(pr.ProcedureError) as caught:
            pr.bind(self.db, args.pop("experiment_id"), args.pop("procedure_ref"), args.pop("role"), **args)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        self.assertEqual(self.snapshot(), before)

    def test_the_real_intelligent_machine_export_imports_registers_and_binds(self):
        row = pr.procedure_rows(self.db)[CANDIDATE_REF]
        permissions = json.loads(row["permissions_json"])
        self.assertEqual(permissions["network"], {"enabled": False, "allowed_domains": []})
        self.assertEqual(permissions["human_approval"], {"required_for": ["email_send", "publish"]})
        self.assertEqual(permissions["filesystem"], {"read": ["workspace/briefs"], "write": []})
        self.assertEqual(set(permissions), {"filesystem", "network", "credentials", "tools", "code_execution",
                                            "external_actions", "data_classes", "human_approval"})
        self.assertTrue(pr.bind(self.db, "EXP-ACQ-0011", CANDIDATE_REF, "COMMON_INPUT")["inserted"])

    def test_an_expired_review_refuses_a_new_binding(self):
        with mock.patch("ai_growth_engineering.procedures._utc_now", return_value="2099-01-01T00:00:00+00:00"):
            self.refused("review_expired")
            # A re-reviewed upstream export does not silently refresh what was imported.
            self.upstream(review_after="2100-01-01")
            self.refused("review_expired")

    def test_a_removed_upstream_export_refuses_a_new_binding(self):
        self.upstream().unlink()
        self.refused("upstream_export_missing")

    def test_an_upstream_export_no_longer_approved_or_revoked_refuses_a_new_binding(self):
        self.upstream(admission_status="QUARANTINED")
        self.refused("upstream_approval_not_current")
        self.upstream(effective_status="REVOKED")
        self.refused("upstream_approval_not_current")

    def test_changed_upstream_content_refuses_a_new_binding(self):
        self.upstream(content_hash="d" * 64)
        self.refused("upstream_content_changed")

    def test_a_changed_upstream_version_refuses_a_new_binding(self):
        self.upstream(skill_version="2.0.1")
        self.refused("upstream_identity_changed")

    def test_a_withdrawn_use_case_refuses_a_new_binding(self):
        self.upstream(approved_use_cases=["marketing_experimentation"])
        self.refused("upstream_use_case_withdrawn")

    def test_a_historical_binding_survives_revocation_and_a_new_binding_does_not(self):
        with frozen_clock():
            pr.bind(self.db, "EXP-ACQ-0010", CANDIDATE_REF, "VARIABLE", arm="candidate")
            pr.bind(self.db, "EXP-ACQ-0010", BASELINE_REF, "VARIABLE", arm="baseline")
        self.cohort("c", 2, arm="candidate")
        history = pr.bindings(self.db)
        self.upstream(effective_status="REVOKED")
        self.refused("upstream_approval_not_current")
        self.assertEqual(pr.bindings(self.db), history)
        self.assertEqual([b["procedure_ref"] for b in pr.lineage(
            {"experiment_id": "EXP-ACQ-0010", "arm": "candidate", "occurred_at": "2026-08-02"}, pr.bindings(self.db))],
            [CANDIDATE_REF])
        self.assertEqual(pr.procedure_rows(self.db)[CANDIDATE_REF]["content_hash"], CANDIDATE_HASH)

    def test_a_theplus_baseline_has_no_upstream_to_lapse(self):
        with mock.patch("ai_growth_engineering.procedures._utc_now", return_value="2099-01-01T00:00:00+00:00"):
            self.assertTrue(pr.bind(self.db, "EXP-ACQ-0011", BASELINE_REF, "COMMON_INPUT")["inserted"])


    def test_the_intelligent_machine_revocation_notice_refuses_a_new_binding_and_keeps_history(self):
        with frozen_clock():
            pr.bind(self.db, "EXP-ACQ-0010", CANDIDATE_REF, "VARIABLE", arm="candidate")
        history = pr.bindings(self.db)
        notice = json.loads(REVOCATION_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual((notice["skill_id"], notice["skill_version"], notice["content_hash"]),
                         (EXPORT["skill_id"], EXPORT["skill_version"], CANDIDATE_HASH))
        path = self.upstream()
        path.write_text(json.dumps(notice), encoding="utf-8")
        self.refused("upstream_revoked")
        self.assertEqual(pr.bindings(self.db), history)
        path.write_text(json.dumps(dict(notice, skill_version="1.9.0")), encoding="utf-8")
        self.refused("upstream_approval_not_current")
        path.write_text(json.dumps(dict(notice, status="PAUSED")), encoding="utf-8")
        self.refused("upstream_approval_not_current")

    def test_an_export_outside_a_published_exports_path_is_refused(self):
        elsewhere = Path(self.tmp.name) / "downloads" / "export.json"
        elsewhere.parent.mkdir()
        elsewhere.write_text(json.dumps(dict(EXPORT, skill_version="3.0.0")), encoding="utf-8")
        with self.assertRaises(pr.ProcedureError) as caught:
            pr.import_export(self.db, str(elsewhere), today="2026-09-15")
        self.assertEqual(caught.exception.code, "not_the_published_export")
        self.assertNotIn(f"{EXPORT['skill_id']}@3.0.0", pr.procedure_rows(self.db))

    def test_a_copy_under_the_published_shape_is_refused_so_it_cannot_outlive_revocation(self):
        """P2 MANAGED_EXPORT_ORIGIN_ENFORCEMENT, closed on purpose: this test previously asserted that such a copy
        imported and stayed bindable after revocation. Only the governed export imports now; a copy kept at
        …/contracts/exports/<skill_id>.json anywhere else, or a symlink at the governed name, is refused."""
        doc = dict(EXPORT, skill_version="7.0.0", content_hash="7" * 64)
        copy_path = Path(self.tmp.name) / "operator-backup" / "contracts" / "exports" / f"{EXPORT['skill_id']}.json"
        copy_path.parent.mkdir(parents=True)
        copy_path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(pr.ProcedureError) as caught:
            pr.import_export(self.db, str(copy_path), today="2026-09-15")
        self.assertEqual(caught.exception.code, "not_the_published_export")
        link = self.exports / f"{EXPORT['skill_id']}.json"
        link.unlink()
        link.symlink_to(copy_path)
        with self.assertRaises(pr.ProcedureError) as caught:
            pr.import_export(self.db, str(link), today="2026-09-15")
        self.assertEqual(caught.exception.code, "not_the_published_export")
        self.assertNotIn(f"{EXPORT['skill_id']}@7.0.0", pr.procedure_rows(self.db))

    def test_a_procedure_no_longer_at_the_governed_origin_cannot_be_declared_again(self):
        with frozen_clock():
            pr.bind(self.db, "EXP-ACQ-0010", CANDIDATE_REF, "VARIABLE", arm="candidate")
        history = pr.bindings(self.db)
        with mock.patch.dict(os.environ, {pr.EXPORTS_DIR_ENV: str(Path(self.tmp.name) / "moved" / "contracts" / "exports")}):
            self.refused("untrusted_export_origin")
        self.assertEqual(pr.bindings(self.db), history)


def _im_committed(path: str) -> bytes | None:
    """The Intelligent Machine's COMMITTED bytes at HEAD: git objects only, no runtime coupling."""
    out = subprocess.run(["git", "-C", str(IM_REPO), "show", f"HEAD:{path}"], capture_output=True)
    return out.stdout if out.returncode == 0 else None


class ContractPinTests(unittest.TestCase):
    CONTRACTS = ROOT / "src" / "ai_growth_engineering" / "contracts"

    def test_every_shared_contract_is_its_pinned_bytes(self):
        self.assertEqual(set(pr.SCHEMA_PINS), {p.name.removesuffix(".schema.json")
                                               for p in self.CONTRACTS.glob("*.schema.json")})
        self.assertEqual(len(pr.SCHEMA_PINS), 4)
        for contract, pin in pr.SCHEMA_PINS.items():
            self.assertEqual(hashlib.sha256((self.CONTRACTS / f"{contract}.schema.json").read_bytes()).hexdigest(),
                             pin, contract)

    def test_a_changed_contract_validates_nothing(self):
        with mock.patch.dict(pr.SCHEMA_PINS, {pr.RESULT_CONTRACT: "0" * 64}):
            self.assertIn("not its pinned", pr.validate_result({"contract": pr.RESULT_CONTRACT})[0])
        with mock.patch.dict(pr.SCHEMA_PINS, {pr.EXPORT_CONTRACT: "0" * 64}):
            with self.assertRaises(pr.ProcedureError) as caught:
                pr.export_refusal(EXPORT)
            self.assertEqual(caught.exception.code, "schema_drift")

    @unittest.skipIf(_im_committed("agentic-os/external-skills/contracts/approved-skill-export.v1.schema.json") is None,
                     "theplus-intelligent-machine git checkout not present beside this repository (set IM_REPO)")
    def test_the_intelligent_machine_publishes_the_same_pinned_contracts(self):
        for contract, pin in pr.SCHEMA_PINS.items():
            theirs = _im_committed(f"agentic-os/external-skills/contracts/{contract}.schema.json")
            self.assertIsNotNone(theirs, f"the Intelligent Machine has not published {contract}")
            self.assertEqual(hashlib.sha256(theirs).hexdigest(), pin, contract)


class ResultContractVersionTests(unittest.TestCase):
    """A result is validated against the contract it declares, never against the newest one."""
    # The committed example exactly as published under v1 at e749c9b: a genuine historical result.
    HISTORICAL_V1 = json.loads((ROOT / "tests" / "fixtures" / "historical_result.v1.json").read_text(encoding="utf-8"))

    def test_a_genuine_historical_v1_result_is_valid_against_v1(self):
        self.assertEqual(self.HISTORICAL_V1["contract"], "skill-evaluation-result.v1")
        self.assertNotIn("competing_variables", self.HISTORICAL_V1)
        self.assertEqual(pr.validate_result(self.HISTORICAL_V1), [])

    def test_v1_cannot_carry_a_causal_class_market_validation_or_keep(self):
        for changes, fragment in (({"result_class": "CONTROLLED_EFFECT"}, "cannot be shown"),
                                  ({"result_class": "REGRESSION"}, "cannot be shown"),
                                  ({"market_validation": True}, "does not record whether synthetic"),
                                  ({"result_class": "DESCRIPTIVE_DIFFERENCE", "decision": "KEEP"}, "KEEP needs")):
            errors = pr.validate_result(dict(copy.deepcopy(self.HISTORICAL_V1), **changes))
            self.assertTrue(any(fragment in e for e in errors), (changes, errors))

    def test_an_unsupported_or_missing_contract_is_refused(self):
        for contract in ("skill-evaluation-result.v3", None, 7):
            doc = dict(copy.deepcopy(self.HISTORICAL_V1), contract=contract)
            self.assertIn("is not supported", pr.validate_result(doc)[0])
        self.assertIn("is not supported", pr.validate_result([])[0])

    def test_each_version_is_checked_by_its_own_pin(self):
        with mock.patch.dict(pr.SCHEMA_PINS, {pr.RESULT_CONTRACT_V1: "0" * 64}):
            self.assertIn("not its pinned", pr.validate_result(self.HISTORICAL_V1)[0])


class ResultGateTests(ProcedureCase):
    """A result file may not carry a causal claim its own evidence does not support."""

    def setUp(self):
        super().setUp()
        self.experiment("EXP-ACQ-0016", variable="procedure", primary_metric="paid_rate")
        with frozen_clock():
            pr.bind(self.db, "EXP-ACQ-0016", CANDIDATE_REF, "VARIABLE", arm="candidate")
            pr.bind(self.db, "EXP-ACQ-0016", BASELINE_REF, "VARIABLE", arm="baseline")
        self.cohort("c", 60, experiment="EXP-ACQ-0016", arm="candidate", payments=30)
        self.cohort("b", 60, experiment="EXP-ACQ-0016", arm="baseline", payments=12)
        self.result = self.evaluate(experiment_id="EXP-ACQ-0016")
        self.doc = pr.result_document(self.result, generated_at="2026-09-30T00:00:00+00:00")

    def rejected(self, fragment, **changes):
        errors = pr.validate_result(dict(copy.deepcopy(self.doc), **changes))
        self.assertTrue(any(fragment in e for e in errors), errors)

    def test_a_genuinely_controlled_paid_outcome_is_accepted_as_causal_revenue(self):
        self.assertEqual((self.result["result_class"], self.result["revenue"]["claim"], self.doc["market_validation"]),
                         ("CONTROLLED_EFFECT", "CAUSAL_SUPPORTED", True))
        self.assertEqual(pr.validate_result(self.doc), [])

    def test_observational_or_offline_evidence_cannot_claim_causal_revenue(self):
        self.rejected("revenue CAUSAL_SUPPORTED needs a CONTROLLED_EFFECT", evidence_class="OBSERVATIONAL_MARKET_RESULT",
                      result_class="DESCRIPTIVE_DIFFERENCE", decision="ITERATE", market_validation=False)
        self.rejected("revenue CAUSAL_SUPPORTED needs a CONTROLLED_EFFECT", evaluation_type="OFFLINE_EVAL",
                      evidence_class="OFFLINE_EVAL", result_class="DESCRIPTIVE_DIFFERENCE", decision="REJECT",
                      market_validation=False)

    def test_no_weaker_class_can_claim_causal_revenue(self):
        for weaker in ("DESCRIPTIVE_DIFFERENCE", "CONFOUNDED", "IMMATURE", "INSUFFICIENT_SAMPLE", "NO_DIFFERENCE",
                       "REGRESSION", "NOT_EVALUABLE"):
            self.rejected(f"not {weaker}", result_class=weaker, decision="NEED_MORE_DATA", market_validation=False)

    def test_causal_revenue_needs_a_paid_primary_metric(self):
        metrics = dict(self.doc["metrics"], primary_metric="qualified_reply_rate")
        self.rejected("needs a paid outcome", metrics=metrics)

    def test_a_controlled_effect_needs_an_experiment_and_a_sample(self):
        self.rejected("needs the experiment id", experiment_id=None)
        self.rejected("matured baseline exposures in the sample", sample={})

    def test_a_controlled_effect_needs_matured_uncompeted_exact_evidence(self):
        immature = {side: {"state": "IMMATURE", "matures_between": []} for side in ("baseline", "candidate")}
        self.rejected("needs matured candidate outcomes", maturity=immature)
        self.rejected("unresolved competing variables", competing_variables=["offer differs between the sides"])
        self.rejected("distinct candidate and baseline", baseline=dict(self.doc["baseline"], content_hash=None))
        self.rejected("beyond z", metrics=dict(self.doc["metrics"], z=1.2))

    def test_synthetic_data_never_validates_the_market(self):
        self.rejected("synthetic fixtures never validate the market", includes_synthetic=True)
        self.rejected("synthetic fixtures are not market exposure", includes_synthetic=True)


if __name__ == "__main__":
    unittest.main()
