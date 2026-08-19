"""Cross-platform social conversion metrics.

The profile, conversation and owned-contact path is one funnel. Raw reach and
engagement remain inputs; qualified conversations, captured contacts, customers and
revenue are the decision measures.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SocialFunnelSnapshot:
    content_views: int = 0
    profile_visits: int = 0
    dm_starts: int = 0
    qualified_social_interactions: int = 0
    qualified_conversations: int = 0
    owned_contacts: int = 0
    leads: int = 0
    qualified_leads: int = 0
    opportunities: int = 0
    customers: int = 0
    revenue_pence: int = 0

    def validate(self) -> None:
        for name, value in vars(self).items():
            if value < 0:
                raise ValueError(f"{name} cannot be negative")


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def profile_visit_rate(snapshot: SocialFunnelSnapshot) -> float | None:
    snapshot.validate()
    return _rate(snapshot.profile_visits, snapshot.content_views)


def dm_start_rate(snapshot: SocialFunnelSnapshot) -> float | None:
    snapshot.validate()
    return _rate(snapshot.dm_starts, snapshot.profile_visits)


def qualified_conversations_per_thousand_views(
    snapshot: SocialFunnelSnapshot,
) -> float | None:
    snapshot.validate()
    rate = _rate(snapshot.qualified_conversations, snapshot.content_views)
    return None if rate is None else rate * 1_000


def audience_capture_rate(snapshot: SocialFunnelSnapshot) -> float | None:
    """Owned contacts divided by qualified social interactions."""
    snapshot.validate()
    return _rate(snapshot.owned_contacts, snapshot.qualified_social_interactions)


def revenue_per_thousand_views(snapshot: SocialFunnelSnapshot) -> float | None:
    snapshot.validate()
    rate = _rate(snapshot.revenue_pence, snapshot.content_views)
    return None if rate is None else rate * 1_000
