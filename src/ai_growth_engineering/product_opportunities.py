"""Evidence-first product opportunity decisions.

The hard gate is deliberately non-compensatory: attractive economics or a high
idea score cannot replace a buyer, demand evidence, distribution, or a test.
"""
from __future__ import annotations

from dataclasses import dataclass, fields as dataclass_fields, replace
from datetime import date
from enum import Enum
from typing import Iterable


class OpportunityStatus(str, Enum):
    IDEA = "idea"
    RESEARCH = "research"
    VALIDATE = "validate"
    PROVEN = "proven"
    BUILD = "build"
    LAUNCHED = "launched"
    GRAVEYARD = "graveyard"


SCORE_FIELDS = (
    "pain_severity",
    "frequency",
    "urgency",
    "buying_intent",
    "economic_value",
    "distribution_access",
    "evidence_strength",
    "build_effort",
    "delivery_effort",
    "support_burden",
    "validation_difficulty",
)


@dataclass(frozen=True)
class ProductOpportunity:
    opportunity_id: str
    buyer: str = ""
    problem: str = ""
    evidence_ids: tuple[str, ...] = ()
    demand_signal: str = ""
    distribution_path: str = ""
    purchase_action: str = ""
    validation_test: str = ""
    economics_hypothesis: str = ""
    pain_severity: int = 0
    frequency: int = 0
    urgency: int = 0
    buying_intent: int = 0
    economic_value: int = 0
    distribution_access: int = 0
    evidence_strength: int = 0
    build_effort: int = 0
    delivery_effort: int = 0
    support_burden: int = 0
    validation_difficulty: int = 0
    product_format: str = ""
    expected_price_pence: int = 0
    expected_margin_rate: float = 0.0
    existing_spend_pence: int = 0
    existing_alternatives: str = ""
    recurring_value: int = 0
    expansion_potential: int = 0
    validation_cost_pence: int = 0
    validation_speed_days: int = 0
    status: OpportunityStatus = OpportunityStatus.IDEA
    decision: str = ""
    graveyard_reason: str = ""
    decided_at: str = ""
    reopen_condition: str = ""

    def __post_init__(self) -> None:
        if not self.opportunity_id.strip():
            raise ValueError("opportunity_id is required")
        if not isinstance(self.status, OpportunityStatus):
            raise ValueError("status must be an OpportunityStatus")
        for field in SCORE_FIELDS + ("recurring_value", "expansion_potential"):
            value = getattr(self, field)
            if not 0 <= value <= 5:
                raise ValueError(f"{field} must be between 0 and 5")
        for field in (
            "expected_price_pence", "existing_spend_pence", "validation_cost_pence",
            "validation_speed_days",
        ):
            if getattr(self, field) < 0:
                raise ValueError(f"{field} cannot be negative")
        if not 0 <= self.expected_margin_rate <= 1:
            raise ValueError("expected_margin_rate must be between 0 and 1")
        if self.status == OpportunityStatus.GRAVEYARD:
            missing = [
                name for name in ("graveyard_reason", "decided_at", "reopen_condition")
                if not getattr(self, name).strip()
            ]
            if missing:
                raise ValueError(f"graveyard opportunity missing: {', '.join(missing)}")
            _parse_date(self.decided_at)


@dataclass(frozen=True)
class OpportunityGateDecision:
    eligible: bool
    next_status: OpportunityStatus
    missing: tuple[str, ...]


class ProductBuildGate:
    """Return build-validation eligibility only when every premise input exists."""

    @staticmethod
    def evaluate(
        opportunity: ProductOpportunity, *, evidence_threshold: int = 2
    ) -> OpportunityGateDecision:
        if evidence_threshold < 1:
            raise ValueError("evidence_threshold must be at least 1")
        missing: list[str] = []
        if opportunity.status == OpportunityStatus.GRAVEYARD:
            missing.append("graveyard_reopen_required")
        if not opportunity.buyer.strip():
            missing.append("buyer")
        if not opportunity.problem.strip():
            missing.append("problem")
        if len(set(filter(str.strip, opportunity.evidence_ids))) < evidence_threshold:
            missing.append("evidence")
        for field in (
            "demand_signal", "distribution_path", "purchase_action",
            "validation_test", "economics_hypothesis",
        ):
            if not getattr(opportunity, field).strip():
                missing.append(field)
        return OpportunityGateDecision(
            eligible=not missing,
            next_status=OpportunityStatus.VALIDATE if not missing else OpportunityStatus.RESEARCH,
            missing=tuple(missing),
        )


def opportunity_priority(
    opportunity: ProductOpportunity, *, evidence_threshold: int = 2
) -> int | None:
    """Score a gate-passing candidate; research ideas are intentionally unranked."""
    if not ProductBuildGate.evaluate(
        opportunity, evidence_threshold=evidence_threshold
    ).eligible:
        return None
    value = sum(getattr(opportunity, field) for field in (
        "pain_severity", "frequency", "urgency", "buying_intent",
        "economic_value", "distribution_access", "evidence_strength",
    ))
    cost = sum(getattr(opportunity, field) for field in (
        "build_effort", "delivery_effort", "support_burden", "validation_difficulty",
    ))
    return value - cost


def rank_opportunities(
    opportunities: Iterable[ProductOpportunity], *, evidence_threshold: int = 2
) -> list[tuple[ProductOpportunity, int]]:
    """Rank only eligible opportunities, with stable ID ordering for equal scores."""
    ranked = []
    for opportunity in opportunities:
        score = opportunity_priority(opportunity, evidence_threshold=evidence_threshold)
        if score is not None:
            ranked.append((opportunity, score))
    return sorted(ranked, key=lambda item: (-item[1], item[0].opportunity_id))


def opportunity_from_registry(record: dict) -> ProductOpportunity:
    """Rehydrate a durable registry row and reject false evidence counts."""
    evidence_ids = tuple(filter(None, (
        item.strip() for item in str(record.get("evidence_ids", "")).split(";")
    )))
    unique_count = len(set(evidence_ids))
    declared_count = int(record.get("evidence_count", 0) or 0)
    if declared_count != unique_count:
        raise ValueError(
            f"evidence_count {declared_count} does not match {unique_count} unique evidence IDs"
        )
    allowed = {field.name for field in dataclass_fields(ProductOpportunity)}
    values = {
        key: value for key, value in record.items()
        if key in allowed and key not in {"opportunity_id", "evidence_ids"} and value is not None
    }
    values["opportunity_id"] = record.get("product_opportunity_id", "")
    values["evidence_ids"] = evidence_ids
    status = values.get("status")
    if status:
        values["status"] = OpportunityStatus(status)
    return ProductOpportunity(**values)


def park_in_graveyard(
    opportunity: ProductOpportunity, *, reason: str, decided_at: str, reopen_condition: str
) -> ProductOpportunity:
    """Preserve a failed idea with the evidence needed to know when to resume it."""
    for name, value in (
        ("reason", reason), ("decided_at", decided_at),
        ("reopen_condition", reopen_condition),
    ):
        if not value.strip():
            raise ValueError(f"{name} is required")
    _parse_date(decided_at)
    return replace(
        opportunity,
        status=OpportunityStatus.GRAVEYARD,
        decision="parked",
        graveyard_reason=reason,
        decided_at=decided_at,
        reopen_condition=reopen_condition,
    )


def _parse_date(value: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("decided_at must be YYYY-MM-DD") from exc
