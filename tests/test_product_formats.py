from __future__ import annotations

import unittest

from ai_growth_engineering.product_formats import (
    ProductFormat,
    ProductFormatSignals,
    choose_product_format,
)


class ProductFormatDecisionTests(unittest.TestCase):
    def test_one_time_knowledge_is_a_static_asset(self):
        self.assertEqual(choose_product_format(ProductFormatSignals()), ProductFormat.STATIC_ASSET)

    def test_one_time_data_utility_is_an_interactive_tool(self):
        signals = ProductFormatSignals(new_data_changes_answer=True, automation_improves_value=True)
        self.assertEqual(choose_product_format(signals), ProductFormat.INTERACTIVE_TOOL)

    def test_recurring_ongoing_problem_starts_as_manual_service(self):
        signals = ProductFormatSignals(recurring_problem=True, ongoing_value=True)
        self.assertEqual(choose_product_format(signals), ProductFormat.MANUAL_SERVICE)

    def test_recurring_stateful_automation_is_software(self):
        signals = ProductFormatSignals(
            recurring_problem=True, new_data_changes_answer=True,
            saved_state_required=True, automation_improves_value=True,
        )
        self.assertEqual(choose_product_format(signals), ProductFormat.SOFTWARE)

    def test_ongoing_integrated_software_is_subscription(self):
        signals = ProductFormatSignals(
            recurring_problem=True, new_data_changes_answer=True,
            saved_state_required=True, automation_improves_value=True,
            integration_increases_value=True, ongoing_value=True,
        )
        self.assertEqual(choose_product_format(signals), ProductFormat.SUBSCRIPTION_SOFTWARE)

    def test_automation_alone_does_not_force_software(self):
        signals = ProductFormatSignals(automation_improves_value=True)
        self.assertEqual(choose_product_format(signals), ProductFormat.STATIC_ASSET)


if __name__ == "__main__":
    unittest.main()
