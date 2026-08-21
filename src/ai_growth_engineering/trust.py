"""Trust guardrails — a conversion win that costs trust is not a win.

Non-compensatory by construction:

    PRIMARY METRIC WINS  +  ALL REQUIRED GUARDRAILS PASS  =  KEEP

never "+35% conversion, -300% trust, overall score 82". A weighted score is exactly how a
campaign that damages the brand gets promoted: the damage is deferred to a quarter where
nobody connects it back to the experiment that caused it.

Two limits, not one. Baseline 0.05% -> observed 0.15% is +0.10 points absolute and +200%
relative; watching only one hides the other. For rare severe events (complaints,
chargebacks) the absolute ceiling is what matters, because a 200% rise on a tiny base can
still be commercially irrelevant while a small absolute rise is not.
"""
from __future__ import annotations

from dataclasses import dataclass

from .policies import PolicyDecision

DIRECTIONS = ("lower_is_better", "higher_is_better")

# A metric that cannot exist on a channel must be declared not-applicable with a reason,
# never quietly omitted. Omission is indistinguishable from forgetting.
CHANNEL_GUARDRAILS: dict[str, tuple[str, ...]] = {
    "email": ("unsubscribe_rate", "spam_complaint_rate", "negative_reply_rate"),
    "outbound": ("opt_out_rate", "negative_reply_rate", "complaint_rate"),
    "dm": ("opt_out_rate", "negative_reply_rate", "complaint_rate"),
    "paid_social": ("hide_rate", "report_rate", "block_rate", "negative_comment_rate"),
    "creative": ("hide_rate", "report_rate", "block_rate", "negative_comment_rate"),
    "landing_page": ("refund_rate", "cancellation_rate", "complaint_rate", "chargeback_rate"),
    "offer": ("refund_rate", "cancellation_rate", "complaint_rate", "chargeback_rate"),
}

# Sentiment is a diagnostic signal, not an enforcement signal. "sentiment = -0.63" reads
# as precision while potentially being nonsense. Before it can gate anything it needs a
# pinned classifier version, a written label definition, a validation set and human
# calibration — none of which exist yet.
DIAGNOSTIC_ONLY_METRICS = ("sentiment", "sentiment_score", "reply_sentiment")


@dataclass(frozen=True)
class TrustGuardrailSpec:
    """Declared BEFORE exposure begins. Frozen once observations exist."""

    metric: str
    direction: str = "lower_is_better"
    baseline: float | None = None
    max_absolute: float | None = None
    max_adverse_delta: float | None = None
    max_relative_increase: float | None = None
    minimum_sample: int = 0
    required: bool = True
    source: str = ""
    not_applicable_reason: str = ""

    def validate(self) -> None:
        if not self.metric.strip():
            raise ValueError("metric is required")
        if self.direction not in DIRECTIONS:
            raise ValueError(f"direction must be one of {DIRECTIONS}")
        if self.metric in DIAGNOSTIC_ONLY_METRICS and self.required:
            raise ValueError(
                f"{self.metric!r} is diagnostic only and cannot be a required guardrail "
                "until a pinned classifier, label definition and validation set exist"
            )
        if not self.required and not self.not_applicable_reason.strip():
            raise ValueError(
                "a guardrail that is not required must say why "
                "(e.g. 'no subscription relationship on this channel')"
            )
        if self.required:
            if self.max_absolute is None and self.max_adverse_delta is None \
                    and self.max_relative_increase is None:
                raise ValueError("a required guardrail needs at least one limit")
            if not self.source.strip():
                raise ValueError("a required guardrail needs a source for its baseline")
            if self.max_adverse_delta is not None and self.baseline is None:
                raise ValueError("max_adverse_delta needs a baseline to be relative to")
            if self.max_relative_increase is not None and self.baseline is None:
                raise ValueError("max_relative_increase needs a baseline")
        if self.minimum_sample < 0:
            raise ValueError("minimum_sample cannot be negative")

    # Fields that must not move once the experiment has observations. Changing a complaint
    # cap from 0.2% to 1.0% after seeing 0.8% is moving a Sharpe threshold after a backtest.
    FROZEN_FIELDS = ("metric", "direction", "baseline", "max_absolute",
                     "max_adverse_delta", "max_relative_increase",
                     "minimum_sample", "required")


@dataclass(frozen=True)
class TrustObservation:
    """Stored as numerator and denominator, not as a rendered percentage.

    "1.7%" cannot be audited, recomputed, or pooled with another period.
    """

    metric: str
    numerator: int
    denominator: int
    observed_at: str = ""
    evidence_id: str = ""

    def validate(self) -> None:
        if self.numerator < 0 or self.denominator < 0:
            raise ValueError("numerator and denominator cannot be negative")
        if self.denominator and self.numerator > self.denominator:
            raise ValueError("numerator cannot exceed denominator")

    @property
    def value(self) -> float | None:
        """None when nothing was observed — distinct from a rate of zero."""
        if self.denominator == 0:
            return None
        return self.numerator / self.denominator


def evaluate_guardrail(spec: TrustGuardrailSpec, obs: TrustObservation | None) -> PolicyDecision:
    """PASS / BREACH / PENDING for one guardrail."""
    spec.validate()

    if not spec.required:
        return PolicyDecision(True, False, (f"not_applicable:{spec.not_applicable_reason}",))

    if obs is None:
        return PolicyDecision(False, True, (f"missing_observation:{spec.metric}",))

    obs.validate()
    if obs.denominator < spec.minimum_sample or obs.value is None:
        # Underpowered is not "passed". Treating it as a pass is how a breach hides.
        return PolicyDecision(
            False, True,
            (f"underpowered:{spec.metric}:{obs.denominator}<{spec.minimum_sample}",),
        )

    value = obs.value
    adverse = (lambda a, b: a > b) if spec.direction == "lower_is_better" else (lambda a, b: a < b)

    if spec.max_absolute is not None and adverse(value, spec.max_absolute):
        return PolicyDecision(
            False, False,
            (f"breach_absolute:{spec.metric}:{value:.4f} vs cap {spec.max_absolute:.4f}",),
        )

    if spec.max_adverse_delta is not None and spec.baseline is not None:
        delta = value - spec.baseline if spec.direction == "lower_is_better" else spec.baseline - value
        if delta > spec.max_adverse_delta:
            return PolicyDecision(
                False, False,
                (f"breach_delta:{spec.metric}:+{delta:.4f} vs allowed {spec.max_adverse_delta:.4f}",),
            )

    if spec.max_relative_increase is not None and spec.baseline:
        relative = (value - spec.baseline) / spec.baseline
        if spec.direction == "higher_is_better":
            relative = -relative
        if relative > spec.max_relative_increase:
            return PolicyDecision(
                False, False,
                (f"breach_relative:{spec.metric}:+{relative:.1%} vs allowed "
                 f"{spec.max_relative_increase:.1%}",),
            )

    return PolicyDecision(True, False, (f"pass:{spec.metric}:{value:.4f}",))


@dataclass(frozen=True)
class TrustVerdict:
    passed: bool
    pending: bool
    reasons: tuple[str, ...]


def evaluate_all(
    specs: list[TrustGuardrailSpec], observations: dict[str, TrustObservation]
) -> TrustVerdict:
    """A breach outranks pending; pending outranks pass.

    Pending and breach are kept distinct because they mean different things: pending says
    "do not conclude yet", breach says "a person must look at this".
    """
    breaches: list[str] = []
    pending: list[str] = []
    passes: list[str] = []

    for spec in specs:
        decision = evaluate_guardrail(spec, observations.get(spec.metric))
        if decision.allowed:
            passes.append(decision.reasons[0])
        elif decision.requires_approval:
            pending.append(decision.reasons[0])
        else:
            breaches.append(decision.reasons[0])

    if breaches:
        return TrustVerdict(False, False, tuple(breaches))
    if pending:
        return TrustVerdict(False, True, tuple(pending))
    return TrustVerdict(True, False, tuple(passes) or ("no_guardrails_declared",))
