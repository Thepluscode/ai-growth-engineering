from __future__ import annotations

import unittest

from ai_growth_engineering import capabilities
from ai_growth_engineering.models import EXPERIMENT_NAMESPACES


class CapabilityMapTests(unittest.TestCase):
    def setUp(self):
        self.data = capabilities.load()

    def test_map_is_wellformed(self):
        capabilities.validate(self.data)

    def test_map_covers_the_whole_project(self):
        # A map that shrank to a handful of entries is a failed load, not a clean pass.
        totals = capabilities.counts(self.data)
        self.assertGreaterEqual(sum(totals.values()), 140)
        self.assertEqual(len(self.data["domains"]), 8)

    def test_source_scope_is_first_class(self):
        required = {
            "1_market_intelligence": {
                "market_research_workflow",
                "customer_intelligence_workflow",
                "competitive_reverse_engineering",
                "demand_discovery",
                "product_research",
                "voice_of_customer",
                "problem_query_maps",
                "social_voice_of_customer",
                "content_to_offer_learning_loop",
            },
            "2_strategy": {
                "segmentation",
                "brand_strategy",
                "positioning_model",
                "offer_architecture",
                "offer_registry",
                "pricing_model",
                "messaging_strategy",
                "value_ladder_registry",
            },
            "3_creative": {
                "copy_creation",
                "image_creative",
                "video_creative",
                "ugc_creation",
                "creative_registry",
                "claims_registry",
                "creative_families",
                "creative_genome",
                "creative_mutation_trees",
                "creative_fatigue_detection",
            },
            "4_distribution": {
                "seo_problem_led_search",
                "ai_search_visibility",
                "content_as_market_sensing",
                "social_distribution",
                "email_marketing",
                "channel_registry",
                "paid_media_google",
                "paid_media_meta",
                "paid_media_linkedin",
                "paid_media_tiktok",
                "paid_media_other_channels",
                "influencer_and_creator",
                "referral_marketing",
                "affiliate_offer_routing",
                "performance_partnerships",
                "partner_registry",
                "public_to_private_conversation",
            },
            "5_conversion": {
                "ecommerce_offer_stacks",
                "storefront_experiments",
                "landing_page_experiments",
                "rapid_experiment_surfaces",
                "lead_generation",
                "lead_capture",
                "qualification_model",
                "booking_flow",
                "social_profile_surface_registry",
                "conversation_funnel_registry",
            },
            "6_lifecycle_revenue": {
                "crm_integration",
                "nurture_sequences",
                "retention_model",
                "expansion_model",
                "marketing_automation",
                "audience_ownership_registry",
                "customer_monetisation_metrics",
            },
            "7_measurement_economics": {
                "attribution_model",
                "revenue_attribution_registry",
                "analytics_and_reporting",
                "allowable_cac",
                "ltv_model",
                "contribution_profit_calculation",
                "pipeline_measurement",
                "social_funnel_attribution",
                "audience_capture_rate",
            },
            "8_ai_growth_engineering": {
                "experiment_preregistration",
                "experiment_registry",
                "growth_ops_agent",
                "growth_event_bus",
                "growth_control_plane",
                "generated_internal_tools",
                "audit_trail",
            },
        }
        for domain, expected in required.items():
            actual = set(self.data["domains"][domain]["capabilities"])
            self.assertTrue(expected <= actual, f"{domain} missing {sorted(expected - actual)}")

    def test_every_status_is_represented(self):
        # If HYPOTHESIS ever hits zero the map has stopped being honest about what is unbuilt.
        totals = capabilities.counts(self.data)
        for status in capabilities.STATUSES:
            self.assertGreater(totals.get(status, 0), 0, f"no capability marked {status}")

    def test_validate_rejects_bad_status(self):
        broken = {"domains": dict(self.data["domains"])}
        key = next(iter(broken["domains"]))
        domain = dict(broken["domains"][key])
        domain["capabilities"] = {"thing": "DONE"}
        broken["domains"][key] = domain
        with self.assertRaises(ValueError):
            capabilities.validate(broken)

    def test_validate_rejects_empty_domain(self):
        broken = {"domains": {k: {"capabilities": {}} for k in self.data["domains"]}}
        with self.assertRaises(ValueError):
            capabilities.validate(broken)

    def test_experiment_namespaces_have_a_home_domain(self):
        # Every namespace an experiment can be filed under must correspond to real scope.
        blob = repr(self.data).lower()
        aliases = {
            "ACQ": "outbound",
            "CREATIVE": "creative",
            "PAID": "paid_media",
            "SEO": "seo",
            "CONTENT": "content",
            "PARTNER": "partner",
            "CRO": "landing_page",
            "CONVERSATION": "conversation_funnel",
            "EMAIL": "email",
            "LIFECYCLE": "retention",
            "OFFER": "offer",
            "SOCIAL": "social_distribution",
            "PROFILE": "social_profile",
            "AISEARCH": "ai_search",
        }
        for namespace in EXPERIMENT_NAMESPACES:
            self.assertIn(namespace, aliases, f"{namespace} has no declared scope")
            self.assertIn(aliases[namespace], blob, f"{namespace} maps to nothing in the map")


if __name__ == "__main__":
    unittest.main()


class TreeMatchesTheMapTests(unittest.TestCase):
    """The generated taxonomy must not drift from the capability map."""

    def test_tree_is_current(self):
        import subprocess, sys, pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "scripts/build_tree.py", "--check"],
            cwd=root, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
