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
        self.assertGreaterEqual(sum(totals.values()), 80)
        self.assertGreaterEqual(len(self.data["domains"]), 8)

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
            "EMAIL": "email",
            "LIFECYCLE": "retention",
        }
        for namespace in EXPERIMENT_NAMESPACES:
            self.assertIn(namespace, aliases, f"{namespace} has no declared scope")
            self.assertIn(aliases[namespace], blob, f"{namespace} maps to nothing in the map")


if __name__ == "__main__":
    unittest.main()
