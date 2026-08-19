from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TeardownPacket:
    company: str
    observation: str
    hypothesis: str
    metric: str

    def markdown(self) -> str:
        return f"""# Growth Leak Teardown — {self.company}

## 1. Observable signal

{self.observation}

## 2. Commercial hypothesis

{self.hypothesis}

## 3. What is fact vs inference

- **Observed:** {self.observation}
- **Inference:** {self.hypothesis}
- **Unknown:** downstream economics until the company supplies funnel / CRM evidence.

## 4. Smallest valid experiment

Create one bounded intervention that changes only the suspected bottleneck. Do not redesign the entire acquisition system.

## 5. Primary metric

`{self.metric}`

## 6. Decision rule

Preregister baseline, minimum sample, success threshold and kill threshold before launch.

## 7. CTA

Offer the teardown as a low-friction conversation starter. Do not claim a revenue result that has not been measured.
"""
