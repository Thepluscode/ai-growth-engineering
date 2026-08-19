from __future__ import annotations

from dataclasses import dataclass


def _validate_0_5(values: dict[str, int]) -> None:
    for key, value in values.items():
        if value < 0 or value > 5:
            raise ValueError(f"{key} must be between 0 and 5")


@dataclass(frozen=True)
class OutreachQuality:
    icp_fit: int
    decision_maker_fit: int
    research_evidence: int
    pain_relevance: int
    message_specificity: int
    cta_friction: int

    @property
    def total(self) -> int:
        values = self.__dict__
        _validate_0_5(values)
        return sum(values.values())

    @property
    def decision(self) -> str:
        score = self.total
        if score < 18:
            return "DO_NOT_SEND"
        if score < 24:
            return "REVIEW"
        return "SEND"


@dataclass(frozen=True)
class OfferStrength:
    pain_severity: int
    buyer_specificity: int
    outcome_clarity: int
    mechanism: int
    proof: int
    risk_reduction: int
    cta_friction: int
    economic_value: int

    @property
    def total(self) -> int:
        values = self.__dict__
        _validate_0_5(values)
        return sum(values.values())


@dataclass(frozen=True)
class CongruenceScore:
    audience_match: int
    problem_match: int
    message_match: int
    visual_match: int
    offer_match: int
    cta_match: int

    @property
    def total(self) -> int:
        values = self.__dict__
        _validate_0_5(values)
        return sum(values.values())

    @property
    def decision(self) -> str:
        score = self.total
        if score < 18:
            return "DO_NOT_SPEND"
        if score < 24:
            return "REVIEW"
        return "ELIGIBLE_FOR_TEST"
