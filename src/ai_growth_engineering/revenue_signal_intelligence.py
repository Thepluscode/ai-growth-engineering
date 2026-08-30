"""Evidence-governed revenue-signal contracts used by the revenue lineage store."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import exp


@dataclass(frozen=True)
class IntentSignal:
    signal_id: str
    prospect_id: str
    company: str
    signal_type: str
    source: str
    observed_at: str
    evidence_id: str
    confidence: float
    strength: int
    commercial_interpretation: str = ""

    def validate(self) -> None:
        for field_name in (
            "signal_id",
            "prospect_id",
            "company",
            "signal_type",
            "source",
            "observed_at",
            "evidence_id",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not 1 <= self.strength <= 5:
            raise ValueError("strength must be between 1 and 5")
        try:
            date.fromisoformat(self.observed_at)
        except ValueError as exc:
            raise ValueError("observed_at must use YYYY-MM-DD") from exc


@dataclass(frozen=True)
class ProspectEligibilityInput:
    prospect_id: str
    company: str
    buyer: str
    identity_status: str
    suppression_clear: bool
    icp_fit: bool
    hard_disqualifier: bool
    evidence_ids: tuple[str, ...]
    reachable_channel: str


@dataclass(frozen=True)
class EligibilityDecision:
    eligible: bool
    reasons: tuple[str, ...]


class ProspectEligibilityGate:
    """Hard constraints that must pass before a prospect may be prioritised."""

    VERIFIED_IDENTITIES = frozenset({"verified", "observed_named_buyer"})

    @classmethod
    def evaluate(cls, candidate: ProspectEligibilityInput) -> EligibilityDecision:
        reasons: list[str] = []
        if not candidate.prospect_id.strip():
            reasons.append("missing_prospect_id")
        if not candidate.company.strip():
            reasons.append("missing_company")
        if not candidate.buyer.strip():
            reasons.append("missing_buyer")
        if candidate.identity_status not in cls.VERIFIED_IDENTITIES:
            reasons.append("identity_not_verified")
        if not candidate.suppression_clear:
            reasons.append("suppression_or_opt_out")
        if not candidate.icp_fit:
            reasons.append("icp_not_eligible")
        if candidate.hard_disqualifier:
            reasons.append("hard_disqualifier")
        if not candidate.evidence_ids:
            reasons.append("missing_evidence")
        if not candidate.reachable_channel.strip():
            reasons.append("no_reachable_channel")
        return EligibilityDecision(not reasons, tuple(reasons) if reasons else ("eligible",))


@dataclass(frozen=True)
class PriorityInput:
    icp_fit_score: int
    signal_strength: int
    signal_confidence: float
    observed_at: str
    evidence_count: int
    route_quality: int


@dataclass(frozen=True)
class PriorityResult:
    score: float
    freshness: float
    explanation: tuple[str, ...]


def freshness_weight(
    observed_at: str, *, today: date | None = None, half_life_days: int = 21
) -> float:
    """Exponential signal decay. Old intent remains evidence but loses priority."""
    if half_life_days <= 0:
        raise ValueError("half_life_days must be > 0")
    observed = date.fromisoformat(observed_at)
    today = today or date.today()
    age_days = max(0, (today - observed).days)
    return exp(-0.6931471805599453 * age_days / half_life_days)


def priority_score(value: PriorityInput, *, today: date | None = None) -> PriorityResult:
    """Rank only candidates that already passed ProspectEligibilityGate."""
    for name in ("icp_fit_score", "signal_strength", "route_quality"):
        number = getattr(value, name)
        if not 1 <= number <= 5:
            raise ValueError(f"{name} must be between 1 and 5")
    if not 0 <= value.signal_confidence <= 1:
        raise ValueError("signal_confidence must be between 0 and 1")
    if value.evidence_count <= 0:
        raise ValueError("evidence_count must be > 0")

    freshness = freshness_weight(value.observed_at, today=today)
    evidence_depth = min(value.evidence_count, 5) / 5
    weighted = (
        0.30 * (value.icp_fit_score / 5)
        + 0.30 * (value.signal_strength / 5)
        + 0.15 * value.signal_confidence
        + 0.10 * freshness
        + 0.10 * evidence_depth
        + 0.05 * (value.route_quality / 5)
    )
    score = round(weighted * 100, 2)
    return PriorityResult(
        score=score,
        freshness=round(freshness, 4),
        explanation=(
            f"icp_fit={value.icp_fit_score}/5",
            f"signal_strength={value.signal_strength}/5",
            f"signal_confidence={value.signal_confidence:.2f}",
            f"freshness={freshness:.2f}",
            f"evidence_count={value.evidence_count}",
            f"route_quality={value.route_quality}/5",
        ),
    )


def signal_record(signal: IntentSignal) -> dict:
    signal.validate()
    return {
        "signal_id": signal.signal_id,
        "prospect_id": signal.prospect_id,
        "company": signal.company,
        "signal_type": signal.signal_type,
        "source": signal.source,
        "observed_at": signal.observed_at,
        "evidence_id": signal.evidence_id,
        "confidence": signal.confidence,
        "strength": signal.strength,
        "commercial_interpretation": signal.commercial_interpretation,
    }


def recommendation_object(
    *,
    candidate: ProspectEligibilityInput,
    priority: PriorityResult,
    evidence_ids: tuple[str, ...],
    why_now: str,
    unknowns: tuple[str, ...] = (),
    suggested_angle: str = "",
    recommended_channel: str = "",
) -> dict:
    decision = ProspectEligibilityGate.evaluate(candidate)
    if not decision.eligible:
        raise ValueError(f"prospect is not eligible: {', '.join(decision.reasons)}")
    return {
        "prospect_id": candidate.prospect_id,
        "company": candidate.company,
        "buyer": candidate.buyer,
        "why_now": why_now,
        "why_fit": "eligible_under_prospect_gate",
        "evidence_ids": list(evidence_ids),
        "unknowns": list(unknowns),
        "priority_score": priority.score,
        "priority_explanation": list(priority.explanation),
        "suggested_angle": suggested_angle,
        "recommended_channel": recommended_channel or candidate.reachable_channel,
        "authority": "R3_APPROVAL_REQUIRED",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "executable": False,
    }
