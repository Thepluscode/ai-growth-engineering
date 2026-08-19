from __future__ import annotations

from dataclasses import dataclass

from .models import ActionProposal, ActionRisk, RuleOfOne


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    requires_approval: bool
    reasons: tuple[str, ...]


class RuleOfOneGate:
    @staticmethod
    def evaluate(rule: RuleOfOne) -> PolicyDecision:
        missing = rule.missing()
        if missing:
            return PolicyDecision(False, False, (f"missing:{','.join(missing)}",))
        return PolicyDecision(True, False, ("rule_of_one_complete",))


class DemandEvidenceGate:
    """Major assets require >=2 independent demand signals before build priority."""

    @staticmethod
    def evaluate(independent_signal_count: int) -> PolicyDecision:
        if independent_signal_count <= 0:
            return PolicyDecision(False, False, ("no_demand_signal",))
        if independent_signal_count == 1:
            return PolicyDecision(False, False, ("research_only",))
        return PolicyDecision(True, False, ("demand_gate_passed",))


class GrowthActionPolicy:
    """Default authority boundary for action-producing growth agents."""

    MAX_AUTONOMOUS_BUDGET_INCREASE_PCT = 10.0

    @classmethod
    def evaluate(cls, proposal: ActionProposal) -> PolicyDecision:
        reasons: list[str] = []
        if proposal.deletes_data:
            return PolicyDecision(False, False, ("destructive_action_denied",))
        if proposal.risk == ActionRisk.R4_HIGH_RISK:
            return PolicyDecision(False, False, ("high_risk_action_denied",))
        if proposal.publishes_claim and not proposal.evidence_ids:
            return PolicyDecision(False, False, ("unsupported_public_claim",))

        requires = proposal.risk == ActionRisk.R3_MATERIAL
        if proposal.changes_price:
            requires = True
            reasons.append("price_change_requires_approval")
        if proposal.bulk_outreach:
            requires = True
            reasons.append("bulk_outreach_requires_approval")
        if proposal.changes_budget_pct > cls.MAX_AUTONOMOUS_BUDGET_INCREASE_PCT:
            requires = True
            reasons.append("budget_change_exceeds_delegation")
        if proposal.publishes_claim:
            requires = True
            reasons.append("public_claim_requires_approval")

        if not reasons:
            reasons.append("within_default_authority")
        return PolicyDecision(True, requires, tuple(reasons))
