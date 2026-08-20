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


class ClaimPublicationGate:
    """Whether a specific registered claim may be published.

    `GrowthActionPolicy` only checks that *some* evidence id is attached. That is not the
    same as being supported: a creator's "$100k/month" cited to the video it came from has
    an evidence id and no support. This gate reads the claim's registered status and the
    confidence of the evidence behind it.

    MIN_PUBLIC_CLAIM_CONFIDENCE is a documented default, not a discovered constant. Raise
    it for regulated or financial claims; it is deliberately not zero, because "we wrote
    the source down" is the failure mode it exists to catch.
    """

    MIN_PUBLIC_CLAIM_CONFIDENCE = 0.5

    # Statuses that can never be published, whatever evidence is attached.
    BLOCKED_STATUSES = frozenset({
        "creator_claim_rejected_as_benchmark",
        "rejected",
        "retracted",
    })

    @classmethod
    def evaluate(
        cls,
        claim_status: str,
        evidence_confidence: float | None,
        evidence_observed: bool = True,
    ) -> PolicyDecision:
        if claim_status in cls.BLOCKED_STATUSES:
            return PolicyDecision(False, False, (f"claim_status_blocked:{claim_status}",))
        if evidence_confidence is None:
            return PolicyDecision(False, False, ("claim_has_no_evidence",))
        if not evidence_observed:
            return PolicyDecision(False, False, ("claim_rests_on_inference_not_observation",))
        if evidence_confidence < cls.MIN_PUBLIC_CLAIM_CONFIDENCE:
            return PolicyDecision(
                False,
                False,
                (f"evidence_confidence_below_floor:{evidence_confidence:.2f}"
                 f"<{cls.MIN_PUBLIC_CLAIM_CONFIDENCE}",),
            )
        # Supported claims still go to a human. Support is not authorisation.
        return PolicyDecision(True, True, ("claim_supported_requires_approval",))


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
