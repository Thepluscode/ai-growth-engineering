"""Persuasion Engineering — make genuine value hard to dismiss, never manufacture pressure.

The objective is not to force action. It is to find which truthful framing makes real value
easiest to understand. Coercive tactics lift short-term conversion and charge for it later in
refunds, churn, complaints and CAC, by which point the cause is no longer attributable.

So the integrity gate here is code rather than a checklist. A checklist is passed by whoever
is in a hurry; this refuses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .policies import PolicyDecision


# Claims of popularity, rank or scale that assert a fact about the world. Each needs a
# source; none may be asserted because it sounds good.
UNSUPPORTED_SUPERLATIVES = (
    r"\b#1\b", r"\bnumber one\b", r"\bindustry[- ]leading\b", r"\bworld[- ]class\b",
    r"\bbest[- ]in[- ]class\b", r"\bmarket leader\b", r"\bthe only\b",
    r"\btrusted by thousands\b", r"\bmillions of\b", r"\beveryone\b",
)

# Urgency language that implies a limit. Permitted only against a declared capacity.
SCARCITY_PATTERNS = (
    r"\bonly \d+ (spaces?|slots?|seats?|places?) left\b",
    r"\blast chance\b", r"\bact now\b", r"\bhurry\b", r"\bending soon\b",
    r"\bwhile stocks last\b", r"\bdon'?t miss out\b", r"\blimited time\b",
    r"\bspaces? (are )?filling fast\b",
)

# Pressure aimed at a person's self-worth rather than at the value of the product.
# This is the line between persuasion and coercion.
VULNERABILITY_PATTERNS = (
    r"\byou'?re (falling|being left) behind\b",
    r"\byour competitors are (already )?(winning|beating you)\b",
    r"\bserious (founders|businesses|leaders) (do|don'?t)\b",
    r"\bif you (really )?cared about\b",
    r"\bexcuses?\b.{0,30}\bnot ready\b",
    r"\bstop (making excuses|being)\b",
    r"\bafraid\b.{0,20}\bfail\b",
)


@dataclass(frozen=True)
class ScarcityClaim:
    """A limit may be stated only when the limit exists.

    capacity is the real number of slots; committed is how many are already taken.
    A claim of fewer remaining than actually remain is a false limit, not marketing.
    """

    claim_id: str
    statement: str
    capacity: int
    committed: int = 0
    expiry: str = ""
    verification: str = ""

    @property
    def remaining(self) -> int:
        return max(0, self.capacity - self.committed)

    def validate(self) -> None:
        if self.capacity < 0 or self.committed < 0:
            raise ValueError("capacity and committed cannot be negative")
        if self.committed > self.capacity:
            raise ValueError("committed cannot exceed capacity")
        if not self.verification.strip():
            raise ValueError("a scarcity claim needs a verification source")


@dataclass(frozen=True)
class PersuasionAsset:
    """Anything shown to a buyer: an ad, an email, a landing page, a CTA, a deck."""

    asset_id: str
    body: str
    evidence_ids: tuple[str, ...] = ()
    scarcity: ScarcityClaim | None = None
    cta_describes_next_step: bool = True
    metadata: dict = field(default_factory=dict)


def _matches(patterns: tuple[str, ...], text: str) -> list[str]:
    found = []
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            found.append(match.group(0))
    return found


class PersuasionIntegrityGate:
    """PASS -> eligible for experiment. FAIL -> revise.

    Deliberately not a score. A weighted score lets a strong hook outvote a false claim,
    which is exactly the trade this gate exists to refuse.
    """

    @staticmethod
    def evaluate(asset: PersuasionAsset) -> PolicyDecision:
        reasons: list[str] = []

        superlatives = _matches(UNSUPPORTED_SUPERLATIVES, asset.body)
        if superlatives and not asset.evidence_ids:
            reasons.append(f"unsupported_superlative:{superlatives[0]!r}")

        urgency = _matches(SCARCITY_PATTERNS, asset.body)
        if urgency:
            if asset.scarcity is None:
                reasons.append(f"scarcity_without_declared_capacity:{urgency[0]!r}")
            else:
                asset.scarcity.validate()
                # "only 2 left" against 50 remaining is a fabricated limit.
                stated = re.search(r"only (\d+)", asset.body, re.IGNORECASE)
                if stated and int(stated.group(1)) < asset.scarcity.remaining:
                    reasons.append(
                        f"scarcity_understates_remaining:claims {stated.group(1)}, "
                        f"actually {asset.scarcity.remaining}"
                    )

        exploitation = _matches(VULNERABILITY_PATTERNS, asset.body)
        if exploitation:
            # Pressure unrelated to product value. No amount of evidence licenses it.
            reasons.append(f"exploits_vulnerability_not_value:{exploitation[0]!r}")

        if not asset.cta_describes_next_step:
            reasons.append("cta_does_not_describe_what_happens_next")

        if reasons:
            return PolicyDecision(False, False, tuple(reasons))
        return PolicyDecision(True, False, ("persuasion_integrity_pass",))


AWARENESS_STAGES = ("unaware", "problem_aware", "solution_aware", "product_aware", "ready")


def cta_friction_check(cta: str, awareness: str) -> PolicyDecision:
    """A CTA must match what the buyer is ready to do.

    Asking an unaware buyer to start a paid engagement is not persuasion, it is a
    mismatch that reads as pressure and converts worse than the honest step.
    """
    if awareness not in AWARENESS_STAGES:
        raise ValueError(f"unknown awareness stage {awareness!r}; expected {AWARENESS_STAGES}")
    high_commitment = re.search(r"\b(buy|start the|book a call|purchase|sign up now)\b", cta, re.I)
    if high_commitment and awareness in ("unaware", "problem_aware"):
        return PolicyDecision(
            False, False,
            (f"cta_commitment_exceeds_awareness:{awareness}",),
        )
    if not cta.strip():
        return PolicyDecision(False, False, ("cta_empty",))
    return PolicyDecision(True, False, ("cta_matches_awareness",))
