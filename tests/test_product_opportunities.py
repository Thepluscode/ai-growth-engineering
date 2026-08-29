from __future__ import annotations

import unittest

from ai_growth_engineering.product_opportunities import (
    OpportunityStatus,
    ProductBuildGate,
    ProductOpportunity,
    opportunity_priority,
    opportunity_from_registry,
    park_in_graveyard,
    rank_opportunities,
)


def eligible(**changes) -> ProductOpportunity:
    fields = {
        "opportunity_id": "OPP-001",
        "buyer": "Operations lead",
        "problem": "Repeated manual reconciliation",
        "evidence_ids": ("EV-001", "EV-002"),
        "demand_signal": "Three buyers paid for the manual workaround",
        "distribution_path": "Existing customer list",
        "purchase_action": "Paid diagnostic checkout",
        "validation_test": "Offer 10 diagnostics; require 2 purchases",
        "economics_hypothesis": "£2,000 price at 70% contribution margin",
        "pain_severity": 4,
        "frequency": 4,
        "urgency": 3,
        "buying_intent": 4,
        "economic_value": 5,
        "distribution_access": 4,
        "evidence_strength": 4,
        "build_effort": 2,
        "delivery_effort": 2,
        "support_burden": 1,
        "validation_difficulty": 1,
    }
    fields.update(changes)
    return ProductOpportunity(**fields)


class ProductBuildGateTests(unittest.TestCase):
    def test_complete_opportunity_is_validation_eligible(self):
        decision = ProductBuildGate.evaluate(eligible())
        self.assertTrue(decision.eligible)
        self.assertEqual(decision.next_status, OpportunityStatus.VALIDATE)
        self.assertEqual(decision.missing, ())

    def test_high_scores_and_margin_cannot_replace_evidence(self):
        candidate = eligible(
            evidence_ids=(), expected_margin_rate=1.0,
            pain_severity=5, buying_intent=5, economic_value=5,
        )
        decision = ProductBuildGate.evaluate(candidate)
        self.assertFalse(decision.eligible)
        self.assertEqual(decision.next_status, OpportunityStatus.RESEARCH)
        self.assertIn("evidence", decision.missing)
        self.assertIsNone(opportunity_priority(candidate))

    def test_every_hard_requirement_is_named(self):
        candidate = ProductOpportunity("OPP-EMPTY")
        self.assertEqual(
            ProductBuildGate.evaluate(candidate).missing,
            ("buyer", "problem", "evidence", "demand_signal", "distribution_path",
             "purchase_action", "validation_test", "economics_hypothesis"),
        )

    def test_duplicate_evidence_does_not_meet_threshold(self):
        decision = ProductBuildGate.evaluate(eligible(evidence_ids=("EV-1", "EV-1")))
        self.assertIn("evidence", decision.missing)

    def test_only_gate_passing_candidates_are_ranked(self):
        strong = eligible(opportunity_id="OPP-STRONG")
        costly = eligible(
            opportunity_id="OPP-COSTLY", build_effort=5, delivery_effort=5,
            support_burden=5, validation_difficulty=5,
        )
        unsupported = eligible(opportunity_id="OPP-IDEA", evidence_ids=())
        ranked = rank_opportunities((costly, unsupported, strong))
        self.assertEqual([item[0].opportunity_id for item in ranked], ["OPP-STRONG", "OPP-COSTLY"])

    def test_invalid_scores_money_and_margin_are_rejected(self):
        for changes in (
            {"pain_severity": 6}, {"build_effort": -1},
            {"expected_price_pence": -1}, {"expected_margin_rate": 1.1},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                eligible(**changes)

    def test_graveyard_preserves_idea_and_requires_reopen_condition(self):
        parked = park_in_graveyard(
            eligible(), reason="No purchase after the fixed sample",
            decided_at="2026-08-29", reopen_condition="Two buyers request the workflow",
        )
        self.assertEqual(parked.opportunity_id, "OPP-001")
        self.assertEqual(parked.status, OpportunityStatus.GRAVEYARD)
        self.assertEqual(parked.decision, "parked")
        self.assertIn(
            "graveyard_reopen_required", ProductBuildGate.evaluate(parked).missing
        )
        with self.assertRaises(ValueError):
            park_in_graveyard(eligible(), reason="failed", decided_at="2026-08-29", reopen_condition="")

    def test_raw_status_string_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "OpportunityStatus"):
            eligible(status="research")

    def test_registry_rehydration_rejects_inflated_evidence_count(self):
        record = {
            "product_opportunity_id": "OPP-1", "buyer": "Buyer", "problem": "Problem",
            "evidence_ids": "EV-1;EV-1", "evidence_count": 2, "status": "research",
        }
        with self.assertRaisesRegex(ValueError, "does not match"):
            opportunity_from_registry(record)


if __name__ == "__main__":
    unittest.main()
