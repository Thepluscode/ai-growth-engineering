from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering import registries
from ai_growth_engineering.models import ActionProposal, ActionRisk, Evidence, EvidenceKind
from ai_growth_engineering.policies import ClaimPublicationGate, GrowthActionPolicy
from ai_growth_engineering.registry import add_evidence, claim_publication_check
from ai_growth_engineering.storage import init_db


class ClaimPublicationGateTests(unittest.TestCase):
    def test_blocked_status_cannot_be_published_whatever_evidence_says(self):
        d = ClaimPublicationGate.evaluate("creator_claim_rejected_as_benchmark", 0.99)
        self.assertFalse(d.allowed)

    def test_weak_evidence_is_denied(self):
        d = ClaimPublicationGate.evaluate("accepted_directional", 0.25)
        self.assertFalse(d.allowed)
        self.assertIn("below_floor", d.reasons[0])

    def test_inference_cannot_support_a_public_claim(self):
        d = ClaimPublicationGate.evaluate("accepted_directional", 0.9, evidence_observed=False)
        self.assertFalse(d.allowed)

    def test_missing_evidence_is_denied(self):
        self.assertFalse(ClaimPublicationGate.evaluate("accepted_directional", None).allowed)

    def test_supported_claim_still_requires_a_human(self):
        d = ClaimPublicationGate.evaluate("accepted_directional", 0.75)
        self.assertTrue(d.allowed)
        self.assertTrue(d.requires_approval)


class ClaimGateAgainstTheRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "g.db")
        init_db(self.db)

        add_evidence(self.db, Evidence(
            evidence_id="EV-WEAK", kind=EvidenceKind.THIRD_PARTY,
            statement="A creator's marketing figure restated by a summariser",
            source="https://example.test/summary", confidence=0.25))
        add_evidence(self.db, Evidence(
            evidence_id="EV-STRONG", kind=EvidenceKind.THIRD_PARTY,
            statement="Platform-published product measurement",
            source="https://example.test/vendor-report", confidence=0.75))

        registries.add(self.db, "claims", {
            "claim_id": "CLM-CR-999", "statement": "$100k/month",
            "evidence_id": "EV-WEAK", "status": "creator_claim_rejected_as_benchmark"})
        registries.add(self.db, "claims", {
            "claim_id": "CLM-AC-999", "statement": "reach beyond followers is possible",
            "evidence_id": "EV-STRONG", "status": "accepted_directional"})
        registries.add(self.db, "claims", {
            "claim_id": "CLM-THIN-999", "statement": "cited but unsupported",
            "evidence_id": "EV-WEAK", "status": "accepted_directional"})

    def test_the_hole_this_gate_exists_to_close(self):
        """An evidence id is not support.

        GrowthActionPolicy allows any claim carrying an evidence id, so a creator figure
        cited to the video it came from passes. The claim gate must still deny it.
        """
        proposal = ActionProposal(
            action="publish '$100k/month' on the site",
            risk=ActionRisk.R2_LOW_RISK,
            evidence_ids=("EV-WEAK",),
            publishes_claim=True,
        )
        self.assertTrue(GrowthActionPolicy.evaluate(proposal).allowed)  # the hole
        self.assertFalse(claim_publication_check(self.db, "CLM-CR-999").allowed)  # closed

    def test_registered_and_supported_claim_passes_to_approval(self):
        d = claim_publication_check(self.db, "CLM-AC-999")
        self.assertTrue(d.allowed)
        self.assertTrue(d.requires_approval)

    def test_accepted_status_with_weak_evidence_is_still_denied(self):
        # Status alone must not launder thin evidence.
        self.assertFalse(claim_publication_check(self.db, "CLM-THIN-999").allowed)

    def test_unregistered_claim_is_denied_not_assumed_fine(self):
        self.assertFalse(claim_publication_check(self.db, "CLM-DOES-NOT-EXIST").allowed)

    def test_every_rejected_creator_claim_is_actually_blocked(self):
        # Assert a minimum count first: a query returning nothing would otherwise
        # "pass" this test by checking no claims at all.
        rows = [r for r in registries.rows(self.db, "claims")
                if r["status"] == "creator_claim_rejected_as_benchmark"]
        self.assertGreaterEqual(len(rows), 1)
        for row in rows:
            self.assertFalse(claim_publication_check(self.db, row["claim_id"]).allowed)


if __name__ == "__main__":
    unittest.main()
