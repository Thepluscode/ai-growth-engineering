import unittest

from ai_growth_engineering.models import ActionProposal, ActionRisk, RuleOfOne
from ai_growth_engineering.policies import DemandEvidenceGate, GrowthActionPolicy, RuleOfOneGate


class PolicyTests(unittest.TestCase):
    def test_rule_of_one_blocks_missing_fields(self):
        decision = RuleOfOneGate.evaluate(RuleOfOne("buyer", "problem", "", "offer", "cta", "channel", "metric"))
        self.assertFalse(decision.allowed)

    def test_demand_gate_requires_two_signals(self):
        self.assertFalse(DemandEvidenceGate.evaluate(1).allowed)
        self.assertTrue(DemandEvidenceGate.evaluate(2).allowed)

    def test_unsupported_claim_denied(self):
        decision = GrowthActionPolicy.evaluate(
            ActionProposal("publish claim", ActionRisk.R3_MATERIAL, publishes_claim=True)
        )
        self.assertFalse(decision.allowed)

    def test_material_budget_increase_requires_approval(self):
        decision = GrowthActionPolicy.evaluate(
            ActionProposal("increase spend", ActionRisk.R2_LOW_RISK, changes_budget_pct=15)
        )
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.requires_approval)

    def test_destructive_action_denied(self):
        decision = GrowthActionPolicy.evaluate(
            ActionProposal("delete campaigns", ActionRisk.R4_HIGH_RISK, deletes_data=True)
        )
        self.assertFalse(decision.allowed)


if __name__ == "__main__":
    unittest.main()
