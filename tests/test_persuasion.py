from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering import registries
from ai_growth_engineering.persuasion import (
    PersuasionAsset,
    PersuasionIntegrityGate,
    ScarcityClaim,
    cta_friction_check,
)
from ai_growth_engineering.storage import init_db

HONEST = (
    "Your existing pipeline may already contain revenue you are paying for and failing to "
    "convert. We trace click to qualified opportunity before recommending spend. "
    "Get the one-page teardown."
)


class IntegrityGateTests(unittest.TestCase):
    def test_an_honest_evidence_led_asset_passes(self):
        d = PersuasionIntegrityGate.evaluate(PersuasionAsset("A-1", HONEST, evidence_ids=("EV-1",)))
        self.assertTrue(d.allowed)

    def test_superlative_without_evidence_is_refused(self):
        asset = PersuasionAsset("A-2", "We are the industry-leading growth partner.")
        d = PersuasionIntegrityGate.evaluate(asset)
        self.assertFalse(d.allowed)
        self.assertIn("unsupported_superlative", d.reasons[0])

    def test_the_same_superlative_with_a_source_is_allowed(self):
        # The rule is "cite it", not "never say it".
        asset = PersuasionAsset("A-3", "Rated #1 in the 2026 survey.", evidence_ids=("EV-SURVEY",))
        self.assertTrue(PersuasionIntegrityGate.evaluate(asset).allowed)

    def test_urgency_without_a_declared_capacity_is_refused(self):
        asset = PersuasionAsset("A-4", "Last chance — only 2 spaces left!")
        d = PersuasionIntegrityGate.evaluate(asset)
        self.assertFalse(d.allowed)

    def test_real_scarcity_is_allowed(self):
        asset = PersuasionAsset(
            "A-5", "Pilot cohort limited to five businesses. Spaces filling fast.",
            scarcity=ScarcityClaim("S-1", "5 pilot slots", capacity=5, committed=2,
                                   verification="delivery calendar 2026-09"),
        )
        self.assertTrue(PersuasionIntegrityGate.evaluate(asset).allowed)

    def test_a_limit_smaller_than_the_truth_is_refused(self):
        """'Only 2 left' with 48 remaining is a fabricated limit, not marketing."""
        asset = PersuasionAsset(
            "A-6", "Only 2 spaces left!",
            scarcity=ScarcityClaim("S-2", "50 slots", capacity=50, committed=2,
                                   verification="delivery calendar"),
        )
        d = PersuasionIntegrityGate.evaluate(asset)
        self.assertFalse(d.allowed)
        self.assertIn("understates_remaining", d.reasons[0])

    def test_exploiting_a_vulnerability_is_refused_even_with_evidence(self):
        # No amount of proof licenses pressure aimed at self-worth rather than value.
        asset = PersuasionAsset(
            "A-7", "Your competitors are already winning. Serious founders don't wait.",
            evidence_ids=("EV-1", "EV-2"),
        )
        d = PersuasionIntegrityGate.evaluate(asset)
        self.assertFalse(d.allowed)
        self.assertIn("exploits_vulnerability", d.reasons[0])

    def test_a_cta_that_hides_the_next_step_is_refused(self):
        asset = PersuasionAsset("A-8", HONEST, evidence_ids=("EV-1",),
                                cta_describes_next_step=False)
        self.assertFalse(PersuasionIntegrityGate.evaluate(asset).allowed)

    def test_scarcity_claim_requires_a_verification_source(self):
        with self.assertRaises(ValueError):
            ScarcityClaim("S-3", "3 slots", capacity=3, verification="").validate()

    def test_committed_cannot_exceed_capacity(self):
        with self.assertRaises(ValueError):
            ScarcityClaim("S-4", "3 slots", capacity=3, committed=4,
                          verification="calendar").validate()

    def test_the_gate_is_not_a_score(self):
        """One real violation fails the asset however good the rest is.

        A weighted score would let a strong hook outvote a false claim, which is the
        trade this gate exists to refuse.
        """
        asset = PersuasionAsset(
            "A-9",
            HONEST + " We are the world-class market leader and only 1 space left!",
        )
        d = PersuasionIntegrityGate.evaluate(asset)
        self.assertFalse(d.allowed)
        self.assertGreaterEqual(len(d.reasons), 2)


class CtaAwarenessTests(unittest.TestCase):
    def test_high_commitment_cta_to_an_unaware_buyer_is_refused(self):
        self.assertFalse(cta_friction_check("Start the 30-Day Sprint", "unaware").allowed)

    def test_the_same_cta_is_fine_for_a_ready_buyer(self):
        self.assertTrue(cta_friction_check("Start the 30-Day Sprint", "ready").allowed)

    def test_low_friction_cta_suits_an_unaware_buyer(self):
        self.assertTrue(cta_friction_check("See the analysis", "unaware").allowed)

    def test_empty_cta_is_refused(self):
        self.assertFalse(cta_friction_check("   ", "ready").allowed)

    def test_unknown_awareness_stage_raises(self):
        with self.assertRaises(ValueError):
            cta_friction_check("See the analysis", "curious")


class PersuasionRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)

    def test_the_four_persuasion_registries_exist(self):
        for name in ("angles", "belief_shifts", "drivers", "scarcity_claims"):
            self.assertIn(name, registries.REGISTRIES)
            registries.rows(self.db, name)  # table must exist

    def test_an_angle_records_the_belief_it_shifts_and_its_evidence(self):
        registries.add(self.db, "angles", {
            "angle_id": "ANG-001", "audience": "Founder/MD, mid-market services firm",
            "problem": "leads are not converting",
            "current_belief": "we need more traffic",
            "contrarian_belief": "cheap leads can be the most expensive leads",
            "emotional_driver": "loss of control", "logical_driver": "wasted acquisition spend",
            "evidence_id": "EV-1", "integrity_status": "pass",
        })
        row = registries.rows(self.db, "angles")[0]
        self.assertEqual(row["contrarian_belief"], "cheap leads can be the most expensive leads")

    def test_a_driver_without_customer_evidence_is_still_recorded_as_unsourced(self):
        # The schema does not force evidence, so the absence must be visible rather than
        # invented later. An empty evidence_id is the signal to go and ask a customer.
        registries.add(self.db, "drivers", {
            "driver_id": "DRV-001", "audience": "Founder/MD", "kind": "emotional",
            "driver": "frustration",
        })
        self.assertEqual(registries.rows(self.db, "drivers")[0]["evidence_id"], "")

    def test_scarcity_capacity_is_stored_as_an_integer(self):
        registries.add(self.db, "scarcity_claims", {
            "scarcity_claim_id": "SC-001", "statement": "5 pilot slots",
            "verification": "delivery calendar", "capacity": 5, "committed": 2,
        })
        row = registries.rows(self.db, "scarcity_claims")[0]
        self.assertEqual(row["capacity"], 5)
        self.assertIsInstance(row["capacity"], int)


if __name__ == "__main__":
    unittest.main()
