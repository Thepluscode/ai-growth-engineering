from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_growth_engineering import registries
from ai_growth_engineering.product_opportunities import (
    ProductBuildGate,
    opportunity_from_registry,
    rank_opportunities,
)
from ai_growth_engineering.registry import seed_registries
from ai_growth_engineering.storage import init_db


class CurrentProductPortfolioTests(unittest.TestCase):
    def test_current_offers_are_preserved_but_none_are_build_eligible(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "growth.db")
            init_db(db)
            seed_registries(db, str(root / "seeds" / "registries.json"))
            opportunities = [
                opportunity_from_registry(row)
                for row in registries.rows(db, "product_opportunities")
            ]
        self.assertEqual(len(opportunities), 5)
        self.assertTrue(all(not ProductBuildGate.evaluate(item).eligible for item in opportunities))
        self.assertEqual(rank_opportunities(opportunities), [])


if __name__ == "__main__":
    unittest.main()
