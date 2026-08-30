from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ai_growth_engineering.signal_intelligence import (
    IntelligenceError,
    PublicPageEnrichmentProvider,
    add_identity,
    add_intent_signal,
    extract_public_identities,
    intelligence_state,
)
from ai_growth_engineering.storage import connect, init_db


NOW = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)


class SignalIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)
        with connect(self.db) as con:
            con.execute(
                """INSERT INTO prospects(
                     id, company, website, priority, target_roles, evidence, source_url, status
                   ) VALUES (1, 'Acme Platform', 'https://example.com', 'A', 'Founder, Revenue lead',
                             'Public B2B offer and named buyer role', 'https://example.com/about',
                             'qualified')"""
            )

    def add_signal(self, **overrides):
        values = {
            "prospect_id": 1,
            "signal_type": "hiring",
            "source_url": "https://example.com/careers",
            "observed_fact": "The company published a revenue operations vacancy on its careers page.",
            "commercial_interpretation": "The new role may indicate active investment in pipeline operations and measurement.",
            "observed_at": "2026-08-29T12:00:00+00:00",
            "confidence": 0.9,
            "strength": 4,
            "freshness_half_life_days": 10,
        }
        return add_intent_signal(self.db, {**values, **overrides})

    def test_no_signal_is_ineligible_instead_of_receiving_a_score(self):
        state = intelligence_state(self.db, now=NOW)
        self.assertEqual(state["ranked_buyers"], [])
        self.assertIn("No observed intent event", state["ineligible"][0]["reasons"])

    def test_ranked_buyer_separates_evidence_inference_and_unknown_identity(self):
        signal = self.add_signal()
        buyer = intelligence_state(self.db, now=NOW)["ranked_buyers"][0]
        self.assertEqual(buyer["signal"]["signal_id"], signal["signal_id"])
        self.assertEqual(buyer["evidence"]["observed_fact"], signal["observed_fact"])
        self.assertEqual(buyer["why_now"], signal["commercial_interpretation"])
        self.assertEqual(buyer["recommended_action"], "enrich_identity")
        self.assertTrue(buyer["approval_required"])
        self.assertGreater(buyer["priority_score"], 0)

    def test_hard_disqualification_cannot_be_compensated_by_a_strong_signal(self):
        self.add_signal(confidence=1, strength=5)
        with connect(self.db) as con:
            con.execute("UPDATE prospects SET status = 'disqualified_fit' WHERE id = 1")
        state = intelligence_state(self.db, now=NOW)
        self.assertEqual(state["ranked_buyers"], [])
        self.assertIn("Prospect status is disqualified_fit", state["ineligible"][0]["reasons"])

    def test_stale_signal_fails_eligibility_before_ranking(self):
        self.add_signal(observed_at="2026-06-01", freshness_half_life_days=10)
        state = intelligence_state(self.db, now=NOW)
        self.assertEqual(state["ranked_buyers"], [])
        self.assertIn("Signal is beyond three freshness half-lives", state["ineligible"][0]["reasons"])

    def test_ineligible_signal_cannot_hide_a_lower_scoring_eligible_signal(self):
        eligible = self.add_signal(strength=2, confidence=0.5)
        self.add_signal(
            signal_type="funding",
            observed_fact="The company announced a new funding round on its public company news page.",
            commercial_interpretation="The funding event may indicate budget availability for a new commercial initiative.",
            confidence=0.49,
            strength=5,
        )
        buyer = intelligence_state(self.db, now=NOW)["ranked_buyers"][0]
        self.assertEqual(buyer["signal"]["signal_id"], eligible["signal_id"])

    def test_observed_identity_changes_action_without_claiming_deliverability(self):
        self.add_signal()
        identity = add_identity(
            self.db,
            {
                "prospect_id": 1,
                "identity_type": "email",
                "value": "buyer@example.com",
                "provider": "public_page",
                "verification_status": "observed_published",
                "source_url": "https://example.com/team",
                "observed_at": "2026-08-29",
                "confidence": 0.75,
            },
        )
        buyer = intelligence_state(self.db, now=NOW)["ranked_buyers"][0]
        self.assertEqual(buyer["identity"]["id"], identity["id"])
        self.assertEqual(buyer["identity"]["verification_status"], "observed_published")
        self.assertEqual(buyer["recommended_action"], "prepare_approval_draft")
        self.assertEqual(buyer["recommended_channel"], "email")

    def test_verified_identity_is_preferred_to_higher_confidence_unverified_identity(self):
        self.add_signal()
        for value, status, confidence in (
            ("unverified@example.com", "unverified", 0.99),
            ("verified@example.com", "verified", 0.7),
        ):
            add_identity(
                self.db,
                {
                    "prospect_id": 1,
                    "identity_type": "email",
                    "value": value,
                    "provider": "operator_research",
                    "verification_status": status,
                    "source_url": "https://example.com/team",
                    "observed_at": "2026-08-29",
                    "confidence": confidence,
                },
            )
        buyer = intelligence_state(self.db, now=NOW)["ranked_buyers"][0]
        self.assertEqual(buyer["identity"]["value"], "verified@example.com")

    def test_public_page_parser_returns_observed_candidates_only(self):
        candidates = extract_public_identities(
            """<a href="mailto:buyer@example.com">buyer@example.com</a>
                <a href="https://www.linkedin.com/in/example-buyer">Profile</a>
                <a href="/contact">Contact</a>""",
            "https://example.com/team",
        )
        self.assertEqual(
            [value.identity_type for value in candidates],
            ["email", "linkedin", "contact_form"],
        )
        self.assertTrue(
            all(value.verification_status == "observed_published" for value in candidates)
        )

    def test_public_page_provider_rejects_loopback_sources(self):
        with self.assertRaisesRegex(IntelligenceError, "public internet"):
            PublicPageEnrichmentProvider().inspect("http://127.0.0.1/")

    def test_signal_source_rejects_embedded_credentials(self):
        with self.assertRaisesRegex(IntelligenceError, r"http\(s\) URL"):
            self.add_signal(source_url="https://user:secret@example.com/careers")


if __name__ == "__main__":
    unittest.main()
