from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ai_growth_engineering.hiring_signal_connector import (
    PublicHiringSignalConnector,
    extract_hiring_signal_candidates,
    preview_hiring_signals,
)
from ai_growth_engineering.signal_intelligence import IntelligenceError, add_intent_signal
from ai_growth_engineering.storage import connect, init_db


NOW = datetime(2026, 8, 29, 8, 15, tzinfo=timezone.utc)
SOURCE = "https://example.com/careers"


def structured_page(*records: dict) -> str:
    return (
        '<script type="application/ld+json">'
        + json.dumps({"@context": "https://schema.org", "@graph": list(records)})
        + "</script>"
    )


class HiringSignalConnectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)
        with connect(self.db) as con:
            con.execute(
                """INSERT INTO prospects(
                     id, company, website, priority, target_roles, evidence, source_url, status
                   ) VALUES (1, 'Acme', 'https://example.com', 'A', 'Revenue leader',
                             'Public B2B offer', 'https://example.com/about', 'qualified')"""
            )

    def test_structured_job_posting_becomes_reviewable_evidence_not_purchase_intent(self):
        html = structured_page(
            {
                "@type": "JobPosting",
                "title": "Head of Revenue Operations",
                "url": "/jobs/head-of-revenue-operations",
                "datePosted": "2026-08-24",
                "validThrough": "2026-09-30",
                "employmentType": "FULL_TIME",
                "hiringOrganization": {"name": "Acme Platform"},
                "jobLocation": {
                    "address": {
                        "addressLocality": "London",
                        "addressCountry": "GB",
                    }
                },
            }
        )
        candidates = extract_hiring_signal_candidates(
            html, SOURCE, "Acme", observed_at=NOW
        )
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.evidence_kind, "structured_job_posting")
        self.assertEqual(candidate.source_url, "https://example.com/jobs/head-of-revenue-operations")
        self.assertEqual(candidate.date_posted, "2026-08-24")
        self.assertEqual(candidate.location, "London, GB")
        self.assertIn("published the role", candidate.observed_fact)
        self.assertIn("may indicate", candidate.commercial_interpretation)
        self.assertIn("does not establish", candidate.commercial_interpretation)
        self.assertIn("not evidence", candidate.uncertainty)
        self.assertEqual(candidate.strength, 4)

    def test_noncommercial_stale_expired_and_future_jobs_are_not_candidates(self):
        html = structured_page(
            {"@type": "JobPosting", "title": "Software Engineer", "url": "/jobs/engineering", "datePosted": "2026-08-25"},
            {"@type": "JobPosting", "title": "Sales Director", "url": "/jobs/old", "datePosted": "2026-05-01"},
            {"@type": "JobPosting", "title": "Growth Lead", "url": "/jobs/expired", "datePosted": "2026-08-01", "validThrough": "2026-08-28"},
            {"@type": "JobPosting", "title": "VP Marketing", "url": "/jobs/future", "datePosted": "2026-09-01"},
        )
        self.assertEqual(
            extract_hiring_signal_candidates(html, SOURCE, "Acme", observed_at=NOW),
            [],
        )

    def test_careers_link_is_lower_confidence_and_deduplicated_against_structured_record(self):
        structured = structured_page(
            {"@type": "JobPosting", "title": "Revenue Operations Manager", "url": "/jobs/revops", "datePosted": "2026-08-24"}
        )
        html = structured + '<a href="/jobs/revops">Revenue Operations Manager</a>'
        candidates = extract_hiring_signal_candidates(html, SOURCE, "Acme", observed_at=NOW)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].confidence, 0.95)

        fallback = extract_hiring_signal_candidates(
            '<a href="/careers/account-executive">Account Executive</a>',
            SOURCE,
            "Acme",
            observed_at=NOW,
        )[0]
        self.assertEqual(fallback.evidence_kind, "careers_link")
        self.assertEqual(fallback.confidence, 0.65)

    def test_preview_does_not_persist_and_marks_an_exact_existing_signal(self):
        candidate = extract_hiring_signal_candidates(
            structured_page(
                {"@type": "JobPosting", "title": "VP Sales", "url": "/jobs/vp-sales", "datePosted": "2026-08-29"}
            ),
            SOURCE,
            "Acme",
            observed_at=NOW,
        )[0]

        class StubConnector:
            def scan(self, source_url, company, *, observed_at=None, max_age_days=45):
                return [candidate]

        first = preview_hiring_signals(
            self.db,
            {"prospect_id": 1, "source_url": SOURCE},
            connector=StubConnector(),
            observed_at=NOW,
        )
        self.assertFalse(first["persisted"])
        self.assertIsNone(first["candidates"][0]["already_recorded_as"])
        with connect(self.db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM intent_signals").fetchone()[0], 0)

        signal = add_intent_signal(self.db, first["candidates"][0]["signal_payload"])
        second = preview_hiring_signals(
            self.db,
            {"prospect_id": 1, "source_url": SOURCE},
            connector=StubConnector(),
            observed_at=NOW,
        )
        self.assertEqual(second["candidates"][0]["already_recorded_as"], signal["signal_id"])
        with self.assertRaisesRegex(IntelligenceError, "already recorded"):
            add_intent_signal(self.db, first["candidates"][0]["signal_payload"])

    def test_live_connector_rejects_loopback_before_fetching(self):
        with self.assertRaisesRegex(IntelligenceError, "public internet"):
            PublicHiringSignalConnector().scan(
                "http://127.0.0.1/careers", "Acme", observed_at=NOW
            )


if __name__ == "__main__":
    unittest.main()
