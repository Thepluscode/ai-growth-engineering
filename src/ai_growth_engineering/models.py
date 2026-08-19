from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any


class EvidenceKind(StrEnum):
    OBSERVATION = "observation"
    CUSTOMER_QUOTE = "customer_quote"
    CRM = "crm"
    ANALYTICS = "analytics"
    EXPERIMENT = "experiment"
    THIRD_PARTY = "third_party"
    INFERENCE = "inference"


class ExperimentDecision(StrEnum):
    PREREGISTERED = "preregistered"
    KEEP = "keep"
    ITERATE = "iterate"
    KILL = "kill"
    INVALID = "invalid"


class ActionRisk(StrEnum):
    R0_OBSERVE = "R0"
    R1_RECOMMEND = "R1"
    R2_LOW_RISK = "R2"
    R3_MATERIAL = "R3"
    R4_HIGH_RISK = "R4"


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    kind: EvidenceKind
    statement: str
    source: str
    confidence: float
    observed: bool = True
    inference: str = ""
    observed_at: str = ""
    commercial_implication: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id is required")
        if not self.statement.strip():
            raise ValueError("statement is required")
        if not self.source.strip():
            raise ValueError("source is required")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if self.kind == EvidenceKind.INFERENCE and self.observed:
            raise ValueError("inference cannot be marked observed")


# Experiment namespaces, one per Digital Marketing domain that can carry an experiment.
# Documented in docs/ROADMAP.md; enforced here so the taxonomy cannot drift in prose alone.
EXPERIMENT_NAMESPACES = frozenset(
    {
        "ACQ",
        "CONTENT",
        "CREATIVE",
        "CRO",
        "EMAIL",
        "LIFECYCLE",
        "OFFER",
        "PAID",
        "PARTNER",
        "SEO",
    }
)


@dataclass(frozen=True)
class ExperimentSpec:
    experiment_id: str
    hypothesis: str
    primary_metric: str
    success_threshold: float
    kill_threshold: float
    minimum_sample: int
    evidence_ids: tuple[str, ...] = ()

    # The universal contract. Every channel files an experiment the same way, so an SEO
    # test and a paid-media test are comparable objects rather than two dialects.
    # Optional so EXP-ACQ-0001 and anything already preregistered stays valid.
    market: str = ""
    buyer: str = ""
    problem: str = ""
    channel: str = ""
    control: str = ""
    variant: str = ""
    secondary_metrics: tuple[str, ...] = ()
    economic_metric: str = ""
    budget_pence: int = 0
    start_date: str = ""
    end_date: str = ""
    learning: str = ""

    def validate(self) -> None:
        parts = self.experiment_id.split("-")
        if (
            len(parts) != 3
            or parts[0] != "EXP"
            or len(parts[2]) != 4
            or not parts[2].isdigit()
        ):
            raise ValueError("experiment_id must look like EXP-<NAMESPACE>-<NNNN>")
        if parts[1] not in EXPERIMENT_NAMESPACES:
            raise ValueError(
                f"unknown experiment namespace {parts[1]!r}; "
                f"add it to EXPERIMENT_NAMESPACES and docs/ROADMAP.md first"
            )
        if not self.hypothesis.strip():
            raise ValueError("hypothesis is required")
        if not self.primary_metric.strip():
            raise ValueError("primary_metric is required")
        if self.minimum_sample <= 0:
            raise ValueError("minimum_sample must be > 0")
        if self.kill_threshold > self.success_threshold:
            raise ValueError("kill_threshold cannot exceed success_threshold")
        if self.budget_pence < 0:
            raise ValueError("budget_pence cannot be negative")
        try:
            start = date.fromisoformat(self.start_date) if self.start_date else None
            end = date.fromisoformat(self.end_date) if self.end_date else None
        except ValueError as exc:
            raise ValueError("experiment dates must use YYYY-MM-DD") from exc
        if start and end and end < start:
            raise ValueError("end_date cannot precede start_date")


@dataclass(frozen=True)
class RuleOfOne:
    buyer: str
    problem: str
    outcome: str
    offer: str
    cta: str
    channel: str
    metric: str

    def missing(self) -> list[str]:
        fields = {
            "buyer": self.buyer,
            "problem": self.problem,
            "outcome": self.outcome,
            "offer": self.offer,
            "cta": self.cta,
            "channel": self.channel,
            "metric": self.metric,
        }
        return [name for name, value in fields.items() if not value.strip()]


@dataclass(frozen=True)
class ActionProposal:
    action: str
    risk: ActionRisk
    evidence_ids: tuple[str, ...] = ()
    changes_price: bool = False
    changes_budget_pct: float = 0.0
    publishes_claim: bool = False
    bulk_outreach: bool = False
    deletes_data: bool = False
