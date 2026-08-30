from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from ai_growth_engineering.growthops import command_center_state
from ai_growth_engineering.models import Evidence, EvidenceKind
from ai_growth_engineering.registry import add_evidence
from ai_growth_engineering.signal_intelligence import (
    IntentSignal,
    PriorityInput,
    ProspectEligibilityGate,
    ProspectEligibilityInput,
    freshness_weight,
    priority_score,
)
from ai_growth_engineering.signal_store import (
    add_identity,
    add_lineage,
    add_signal,
    init_signal_store,
    ranked_prospects,
)
from ai_growth_engineering.storage import connect, init_db


class RevenueSignalIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)
        add_evidence(
            self.db,
            Evidence(
                evidence_id="EV-SIG-001",
                kind=EvidenceKind.OBSERVATION,
                statement="Buyer changed role this week",
                source="https://example.com/source",
                confidence=0.95,
                observed=True,
                observed_at="2026-08-29",
            ),
        )

    def candidate(self, **overrides):
        data = dict(
            prospect_id="P-001",
            company="Example Co",
            buyer="VP Sales",
            identity_status="verified",
            suppression_clear=True,
            icp_fit=True,
            hard_disqualifier=False,
            evidence_ids=("EV-SIG-001",),
            reachable_channel="linkedin",
        )
        data.update(overrides)
        return ProspectEligibilityInput(**data)

    def test_eligibility_is_non_compensatory(self):
        decision = ProspectEligibilityGate.evaluate(
            self.candidate(hard_disqualifier=True, identity_status="verified")
        )
        self.assertFalse(decision.eligible)
        self.assertIn("hard_disqualifier", decision.reasons)

    def test_missing_identity_cannot_be_ranked(self):
        decision = ProspectEligibilityGate.evaluate(self.candidate(identity_status="unverified"))
        self.assertFalse(decision.eligible)
        self.assertIn("identity_not_verified", decision.reasons)

    def test_freshness_decays_without_erasing_old_evidence(self):
        recent = freshness_weight("2026-08-29", today=date(2026, 8, 30))
        old = freshness_weight("2026-05-01", today=date(2026, 8, 30))
        self.assertGreater(recent, old)
        self.assertGreater(old, 0)

    def test_priority_is_explainable_and_bounded(self):
        result = priority_score(
            PriorityInput(
                icp_fit_score=5,
                signal_strength=5,
                signal_confidence=0.9,
                observed_at="2026-08-29",
                evidence_count=3,
                route_quality=4,
            ),
            today=date(2026, 8, 30),
        )
        self.assertGreater(result.score, 80)
        self.assertLessEqual(result.score, 100)
        self.assertTrue(any(item.startswith("signal_strength=") for item in result.explanation))

    def test_signal_requires_registered_evidence(self):
        signal = IntentSignal(
            signal_id="SIG-404", prospect_id="P-404", company="No Evidence Ltd",
            signal_type="funding", source="https://example.com/funding",
            observed_at="2026-08-29", evidence_id="EV-MISSING", confidence=0.8, strength=4,
        )
        with self.assertRaises(ValueError):
            add_signal(self.db, signal)

    def test_store_preserves_signal_identity_and_revenue_lineage(self):
        signal = IntentSignal(
            signal_id="SIG-001", prospect_id="P-001", company="Example Co",
            signal_type="job_change", source="https://example.com/source",
            observed_at="2026-08-29", evidence_id="EV-SIG-001", confidence=0.95,
            strength=5, commercial_interpretation="New VP Sales may be rebuilding pipeline motion",
        )
        add_signal(self.db, signal, raw={"observed": "role changed"})
        add_identity(
            self.db, identity_id="ID-001", prospect_id="P-001", company="Example Co",
            person_name="Alex Buyer", buyer_role="VP Sales", status="verified",
            reachable_channel="linkedin", provider="manual", source="https://example.com/profile",
            linkedin_url="https://linkedin.example/alex", confidence=0.9,
            verified_at="2026-08-29",
        )
        add_lineage(
            self.db, lineage_id="LIN-001", prospect_id="P-001", signal_id="SIG-001",
            evidence_id="EV-SIG-001", identity_id="ID-001", offer_id="OFF-001",
            angle_id="ANGLE-001", experiment_id="EXP-ACQ-0002", channel_id="CH-LINKEDIN",
            recommended_action="review outreach draft", outcome_id="CUS-001",
            revenue_pence=200_000, contribution_profit_pence=120_000,
        )
        with connect(self.db) as con:
            row = con.execute(
                "SELECT * FROM prospect_signal_lineage WHERE lineage_id='LIN-001'"
            ).fetchone()
        self.assertEqual(row["signal_id"], "SIG-001")
        self.assertEqual(row["revenue_pence"], 200_000)
        self.assertEqual(row["contribution_profit_pence"], 120_000)

    def test_ranked_prospects_excludes_suppressed_and_surfaces_authority(self):
        signal = IntentSignal(
            signal_id="SIG-001", prospect_id="P-001", company="Example Co",
            signal_type="job_change", source="https://example.com/source",
            observed_at="2026-08-29", evidence_id="EV-SIG-001", confidence=0.95,
            strength=5, commercial_interpretation="New VP Sales may be reviewing GTM systems",
        )
        add_signal(self.db, signal)
        add_identity(
            self.db, identity_id="ID-001", prospect_id="P-001", company="Example Co",
            person_name="Alex Buyer", buyer_role="VP Sales", status="verified",
            reachable_channel="linkedin", confidence=0.9,
        )
        ranked = ranked_prospects(self.db)
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["authority"], "R3_APPROVAL_REQUIRED")
        self.assertFalse(ranked[0]["executable"])

        with connect(self.db) as con:
            con.execute(
                "INSERT INTO suppression(identity, reason) VALUES (?, ?)", ("P-001", "opt_out")
            )
        self.assertEqual(ranked_prospects(self.db), [])

    def test_growthops_does_not_publish_a_structurally_empty_buyer_list(self):
        """`intent_prospects` read the table this schema was renamed OUT of, so it was
        always [] against a real store — and the old test asserted that emptiness as
        correct. An always-empty buyer list reads as "no buyers", not as "wrong table"."""
        from ai_growth_engineering.growthops import command_center_state
        state = command_center_state(self.db)
        self.assertNotIn("intent_prospects", state)
        self.assertEqual(state["authority"]["mode"], "HUMAN_GATED")

    def test_legacy_revenue_signal_schema_moves_without_blocking_operational_signals(self):
        legacy_db = str(Path(self.tmp.name) / "legacy.db")
        with connect(legacy_db) as con:
            con.execute(
                """CREATE TABLE intent_signals (
                     signal_id TEXT PRIMARY KEY, prospect_id TEXT NOT NULL, company TEXT NOT NULL,
                     signal_type TEXT NOT NULL, source TEXT NOT NULL, observed_at TEXT NOT NULL,
                     evidence_id TEXT NOT NULL, confidence REAL NOT NULL, strength INTEGER NOT NULL,
                     commercial_interpretation TEXT NOT NULL DEFAULT '',
                     raw_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                   )"""
            )
        init_db(legacy_db)
        with connect(legacy_db) as con:
            operational = {row[1] for row in con.execute("PRAGMA table_info(intent_signals)")}
            revenue = {row[1] for row in con.execute("PRAGMA table_info(revenue_intent_signals)")}
        self.assertIn("source_url", operational)
        self.assertIn("evidence_id", revenue)


if __name__ == "__main__":
    unittest.main()
