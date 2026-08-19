from __future__ import annotations

import unittest

from ai_growth_engineering.social import (
    SocialFunnelSnapshot,
    audience_capture_rate,
    dm_start_rate,
    profile_visit_rate,
    qualified_conversations_per_thousand_views,
    revenue_per_thousand_views,
)


class SocialFunnelTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = SocialFunnelSnapshot(
            content_views=10_000,
            profile_visits=1_000,
            dm_starts=200,
            qualified_social_interactions=100,
            qualified_conversations=50,
            owned_contacts=40,
            leads=45,
            qualified_leads=30,
            opportunities=10,
            customers=2,
            revenue_pence=500_000,
        )

    def test_profile_and_conversation_rates_use_the_full_funnel(self):
        self.assertEqual(profile_visit_rate(self.snapshot), 0.1)
        self.assertEqual(dm_start_rate(self.snapshot), 0.2)
        self.assertEqual(qualified_conversations_per_thousand_views(self.snapshot), 5.0)

    def test_audience_capture_measures_owned_relationships(self):
        self.assertEqual(audience_capture_rate(self.snapshot), 0.4)

    def test_revenue_is_attributed_to_reach_without_becoming_a_vanity_metric(self):
        self.assertEqual(revenue_per_thousand_views(self.snapshot), 50_000.0)

    def test_unobserved_denominator_is_unknown_not_zero(self):
        empty = SocialFunnelSnapshot()
        self.assertIsNone(profile_visit_rate(empty))
        self.assertIsNone(audience_capture_rate(empty))

    def test_negative_counts_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "dm_starts"):
            dm_start_rate(SocialFunnelSnapshot(dm_starts=-1))


if __name__ == "__main__":
    unittest.main()
