"""The decision layer every channel shares.

A cheap lead and a profitable customer are different objects. These functions are the
only place that distinction is computed, so paid media, SEO, content, outbound and
partners are judged on one basis rather than on channel-flattering metrics.

Money is handled in integer pence. Floats lose pennies and the losses compound across a
funnel; contribution profit is exactly where that must not happen.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UnitEconomics:
    """One cohort, one channel, one period. All money in pence."""

    revenue_pence: int
    cogs_pence: int = 0
    media_spend_pence: int = 0
    delivery_cost_pence: int = 0
    sales_cost_pence: int = 0
    customers: int = 0
    gross_margin_rate: float = 0.0
    monthly_revenue_pence: int = 0
    churn_rate_monthly: float = 0.0

    def validate(self) -> None:
        for name in (
            "revenue_pence", "cogs_pence", "media_spend_pence",
            "delivery_cost_pence", "sales_cost_pence", "monthly_revenue_pence",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.customers < 0:
            raise ValueError("customers cannot be negative")
        if not 0.0 <= self.gross_margin_rate <= 1.0:
            raise ValueError("gross_margin_rate must be between 0 and 1")
        if not 0.0 <= self.churn_rate_monthly <= 1.0:
            raise ValueError("churn_rate_monthly must be between 0 and 1")


def gross_profit(e: UnitEconomics) -> int:
    return e.revenue_pence - e.cogs_pence


def acquisition_cost(e: UnitEconomics) -> int:
    """Everything spent to win the customer — media plus the sales effort behind it.
    Excluding sales cost is the usual way a channel is made to look cheaper than it is."""
    return e.media_spend_pence + e.sales_cost_pence


def contribution_profit(e: UnitEconomics) -> int:
    """What is left after the costs that scale with each customer won.
    This, not ROAS, decides whether a channel may scale."""
    return gross_profit(e) - e.delivery_cost_pence - acquisition_cost(e)


def cac(e: UnitEconomics) -> int | None:
    """Cost to acquire one customer. None when no customer was acquired — a spend with
    zero customers has no CAC, and reporting 0 there would read as free."""
    if e.customers <= 0:
        return None
    return round(acquisition_cost(e) / e.customers)


def ltv(e: UnitEconomics) -> int | None:
    """Gross-margin lifetime value from monthly revenue and churn.
    None when churn is unknown (0), because 1/0 lifetime is infinite, not excellent."""
    if e.churn_rate_monthly <= 0 or e.monthly_revenue_pence <= 0:
        return None
    return round(e.monthly_revenue_pence * e.gross_margin_rate / e.churn_rate_monthly)


def payback_months(e: UnitEconomics) -> float | None:
    """Months of gross margin needed to repay acquisition cost."""
    monthly_margin = e.monthly_revenue_pence * e.gross_margin_rate
    unit_cac = cac(e)
    if unit_cac is None or monthly_margin <= 0:
        return None
    return round(unit_cac / monthly_margin, 2)


def allowable_cac(e: UnitEconomics, target_ltv_multiple: float = 3.0) -> int | None:
    """The most that may be paid per customer and still hit the target LTV:CAC ratio.
    This is the number a scale gate compares against — not last month's CAC."""
    value = ltv(e)
    if value is None or target_ltv_multiple <= 0:
        return None
    return round(value / target_ltv_multiple)


def scale_verdict(e: UnitEconomics, target_ltv_multiple: float = 3.0) -> str:
    """SCALE / HOLD / KILL — one sentence a channel owner cannot argue with.

    INSUFFICIENT_DATA is a distinct answer from KILL. Treating unknown economics as
    failure kills channels that were never measured, which is how a real edge gets
    thrown away.
    """
    e.validate()
    unit_cac = cac(e)
    ceiling = allowable_cac(e, target_ltv_multiple)
    if unit_cac is None or ceiling is None:
        return "INSUFFICIENT_DATA"
    if contribution_profit(e) <= 0:
        return "KILL"
    if unit_cac <= ceiling:
        return "SCALE"
    return "HOLD"
