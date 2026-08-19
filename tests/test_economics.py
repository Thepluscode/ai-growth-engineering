from __future__ import annotations

import unittest

from ai_growth_engineering.economics import (
    UnitEconomics,
    allowable_cac,
    cac,
    contribution_profit,
    ltv,
    payback_months,
    scale_verdict,
)


def base(**kw) -> UnitEconomics:
    args = dict(
        revenue_pence=1_000_00,
        cogs_pence=200_00,
        media_spend_pence=100_00,
        delivery_cost_pence=150_00,
        sales_cost_pence=50_00,
        customers=2,
        gross_margin_rate=0.8,
        monthly_revenue_pence=100_00,
        churn_rate_monthly=0.05,
    )
    args.update(kw)
    return UnitEconomics(**args)


class EconomicsTests(unittest.TestCase):
    def test_contribution_profit_subtracts_every_scaling_cost(self):
        # 1000 - 200 cogs - 150 delivery - (100 media + 50 sales) = 500
        self.assertEqual(contribution_profit(base()), 500_00)

    def test_cac_includes_sales_cost_not_only_media(self):
        # Excluding sales cost is how a channel is made to look cheaper than it is.
        self.assertEqual(cac(base()), 75_00)

    def test_cac_is_none_with_no_customers(self):
        # Spend with zero customers has no CAC; 0 would read as free.
        self.assertIsNone(cac(base(customers=0)))

    def test_ltv_is_none_when_churn_unknown(self):
        # 1/0 lifetime is infinite, not excellent.
        self.assertIsNone(ltv(base(churn_rate_monthly=0.0)))

    def test_ltv_and_allowable_cac(self):
        self.assertEqual(ltv(base()), 160_000)          # 10000 * 0.8 / 0.05
        self.assertEqual(allowable_cac(base()), 53_333)  # /3

    def test_payback_months(self):
        self.assertEqual(payback_months(base()), 0.94)   # 7500 / (10000*0.8)

    def test_scale_verdict_scale(self):
        self.assertEqual(scale_verdict(base()), "SCALE")

    def test_scale_verdict_kill_on_negative_contribution(self):
        self.assertEqual(scale_verdict(base(media_spend_pence=900_00)), "KILL")

    def test_scale_verdict_hold_when_cac_above_ceiling(self):
        # Profitable but paying more per customer than the LTV target allows.
        e = base(customers=1, media_spend_pence=400_00, churn_rate_monthly=0.5)
        self.assertEqual(scale_verdict(e), "HOLD")

    def test_unmeasured_is_not_the_same_as_failed(self):
        # Treating unknown economics as KILL throws away channels never measured.
        self.assertEqual(scale_verdict(base(churn_rate_monthly=0.0)), "INSUFFICIENT_DATA")
        self.assertEqual(scale_verdict(base(customers=0)), "INSUFFICIENT_DATA")

    def test_validate_rejects_impossible_inputs(self):
        for kw in ({"revenue_pence": -1}, {"gross_margin_rate": 1.5}, {"churn_rate_monthly": -0.1}):
            with self.assertRaises(ValueError):
                base(**kw).validate()


if __name__ == "__main__":
    unittest.main()
