from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_growth_engineering.hiring_signal_connector import (
    PublicHiringSignalConnector,
    add_hiring_source,
    extract_hiring_signal_candidates,
    list_hiring_sources,
    pending_hiring_candidates,
    preview_hiring_signals,
    scan_saved_hiring_sources,
    set_candidate_status,
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


class SavedHiringSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)
        with connect(self.db) as con:
            con.execute(
                """INSERT INTO prospects(id, company, website, priority, target_roles,
                                         evidence, source_url, status)
                   VALUES (1, 'Acme', 'https://acme.example', 'A', 'Revenue leader',
                           'Public B2B offer', 'https://acme.example/about', 'qualified')"""
            )
            con.execute(
                """INSERT INTO prospects(id, company, website, priority, target_roles,
                                         evidence, source_url, status)
                   VALUES (2, 'Beta', 'https://beta.example', 'A', 'Revenue leader',
                           'Public B2B offer', 'https://beta.example/about', 'qualified')"""
            )

    def _candidate(self, title="VP Sales", url="/jobs/vp-sales"):
        return extract_hiring_signal_candidates(
            structured_page(
                {"@type": "JobPosting", "title": title, "url": url, "datePosted": "2026-08-29"}
            ),
            SOURCE,
            "Acme",
            observed_at=NOW,
        )[0]

    def test_a_source_must_be_a_public_url_on_a_known_prospect_and_saved_once(self):
        saved = add_hiring_source(
            self.db,
            {"prospect_id": 1, "source_url": "https://acme.example/careers", "label": "Careers"},
        )
        self.assertEqual(saved["company"], "Acme")
        self.assertEqual(len(list_hiring_sources(self.db)), 1)
        with self.assertRaisesRegex(IntelligenceError, "already saved"):
            add_hiring_source(
                self.db, {"prospect_id": 1, "source_url": "https://acme.example/careers"}
            )
        with self.assertRaisesRegex(IntelligenceError, "public http"):
            add_hiring_source(self.db, {"prospect_id": 1, "source_url": "http://127.0.0.1/careers"})
        with self.assertRaisesRegex(IntelligenceError, "does not exist"):
            add_hiring_source(self.db, {"prospect_id": 99, "source_url": "https://x.example/jobs"})
        self.assertEqual(len(list_hiring_sources(self.db)), 1)

    def test_one_unreachable_source_does_not_lose_the_candidates_from_the_others(self):
        add_hiring_source(self.db, {"prospect_id": 1, "source_url": "https://acme.example/careers"})
        add_hiring_source(self.db, {"prospect_id": 2, "source_url": "https://beta.example/careers"})
        candidate = self._candidate()

        class HalfBrokenConnector:
            def scan(self, source_url, company, *, observed_at=None, max_age_days=45):
                if "beta" in source_url:
                    raise IntelligenceError("source_fetch_failed", "Public page inspection failed")
                return [candidate]

        result = scan_saved_hiring_sources(
            self.db, connector=HalfBrokenConnector(), observed_at=NOW
        )
        self.assertFalse(result["persisted"])
        self.assertEqual(result["source_count"], 2)
        self.assertEqual(result["failed_source_count"], 1)
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidates"][0]["company"], "Acme")

        by_company = {row["company"]: row for row in result["sources"]}
        self.assertEqual(by_company["Acme"]["candidate_count"], 1)
        self.assertEqual(by_company["Acme"]["error"], "")
        self.assertIsNone(by_company["Beta"]["candidate_count"])
        self.assertIn("source_fetch_failed", by_company["Beta"]["error"])

        stored = {row["company"]: row for row in list_hiring_sources(self.db)}
        self.assertEqual(stored["Acme"]["last_candidate_count"], 1)
        self.assertEqual(stored["Beta"]["last_candidate_count"], -1)
        self.assertIn("source_fetch_failed", stored["Beta"]["last_error"])
        self.assertTrue(stored["Beta"]["last_scanned_at"])

        with connect(self.db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM intent_signals").fetchone()[0], 0)

    def test_an_already_recorded_candidate_is_not_counted_as_new(self):
        add_hiring_source(self.db, {"prospect_id": 1, "source_url": "https://acme.example/careers"})
        candidate = self._candidate()

        class StubConnector:
            def scan(self, source_url, company, *, observed_at=None, max_age_days=45):
                return [candidate]

        first = scan_saved_hiring_sources(self.db, connector=StubConnector(), observed_at=NOW)
        self.assertEqual(first["new_candidate_count"], 1)
        add_intent_signal(self.db, first["candidates"][0]["signal_payload"])
        second = scan_saved_hiring_sources(self.db, connector=StubConnector(), observed_at=NOW)
        self.assertEqual(second["candidate_count"], 1)
        self.assertEqual(second["new_candidate_count"], 0)


class ScheduledSweepTests(unittest.TestCase):
    """What has to hold before this runs unattended on somebody else's server."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)
        with connect(self.db) as con:
            con.execute(
                """INSERT INTO prospects(id, company, website, priority, target_roles,
                                         evidence, source_url, status)
                   VALUES (1, 'Acme', 'https://acme.example', 'A', 'Revenue leader',
                           'Public B2B offer', 'https://acme.example/about', 'qualified')"""
            )
        add_hiring_source(self.db, {"prospect_id": 1, "source_url": "https://acme.example/careers"})
        self.calls = []

    def connector(self, *titles):
        candidates = [
            extract_hiring_signal_candidates(
                structured_page({"@type": "JobPosting", "title": title,
                                 "url": f"/jobs/{title.lower().replace(' ', '-')}",
                                 "datePosted": "2026-08-29"}),
                SOURCE, "Acme", observed_at=NOW,
            )[0]
            for title in titles
        ]
        calls = self.calls

        class Stub:
            def scan(self, source_url, company, *, observed_at=None, max_age_days=45):
                calls.append(source_url)
                return list(candidates)

        return Stub()

    def test_a_swept_candidate_is_stored_as_a_proposal_and_never_as_a_signal(self):
        result = scan_saved_hiring_sources(
            self.db, connector=self.connector("VP Sales"), observed_at=NOW,
            persist_candidates=True,
        )
        self.assertTrue(result["persisted"])
        self.assertEqual(result["stored_candidate_count"], 1)
        pending = pending_hiring_candidates(self.db)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["status"], "pending")
        self.assertEqual(pending[0]["company"], "Acme")
        with connect(self.db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM intent_signals").fetchone()[0], 0)

    def test_a_source_fetched_recently_is_skipped_rather_than_fetched_again(self):
        later = NOW + timedelta(hours=2)
        first = scan_saved_hiring_sources(
            self.db, connector=self.connector("VP Sales"), observed_at=NOW,
            persist_candidates=True, min_interval_hours=20,
        )
        self.assertEqual(first["scanned_source_count"], 1)
        self.assertEqual(first["skipped_source_count"], 0)
        self.assertEqual(len(self.calls), 1)

        second = scan_saved_hiring_sources(
            self.db, connector=self.connector("VP Sales"), observed_at=later,
            persist_candidates=True, min_interval_hours=20,
        )
        self.assertEqual(second["scanned_source_count"], 0)
        self.assertEqual(second["skipped_source_count"], 1)
        self.assertIn("inside the 20h interval", second["sources"][0]["skipped"])
        self.assertEqual(len(self.calls), 1, "the skipped source must not be fetched")

    def test_the_interval_lets_the_source_through_once_it_has_elapsed(self):
        scan_saved_hiring_sources(
            self.db, connector=self.connector("VP Sales"), observed_at=NOW,
            persist_candidates=True, min_interval_hours=20,
        )
        scan_saved_hiring_sources(
            self.db, connector=self.connector("VP Sales"), observed_at=NOW + timedelta(hours=21),
            persist_candidates=True, min_interval_hours=20,
        )
        self.assertEqual(len(self.calls), 2)

    def test_a_never_scanned_source_is_not_treated_as_recently_scanned(self):
        result = scan_saved_hiring_sources(
            self.db, connector=self.connector("VP Sales"), observed_at=NOW,
            persist_candidates=True, min_interval_hours=999,
        )
        self.assertEqual(result["scanned_source_count"], 1)
        self.assertEqual(len(self.calls), 1)

    def test_a_reviewed_candidate_never_returns_as_pending_on_the_next_sweep(self):
        scan_saved_hiring_sources(
            self.db, connector=self.connector("VP Sales"), observed_at=NOW,
            persist_candidates=True,
        )
        candidate_id = pending_hiring_candidates(self.db)[0]["candidate_id"]
        set_candidate_status(self.db, candidate_id, "dismissed")
        self.assertEqual(pending_hiring_candidates(self.db), [])

        again = scan_saved_hiring_sources(
            self.db, connector=self.connector("VP Sales"), observed_at=NOW + timedelta(days=1),
            persist_candidates=True,
        )
        self.assertEqual(again["candidate_count"], 1)
        self.assertEqual(again["stored_candidate_count"], 0)
        self.assertEqual(pending_hiring_candidates(self.db), [],
                         "a dismissed candidate must not be resurrected by a machine")

    def test_a_second_sweep_stores_only_what_is_genuinely_new(self):
        scan_saved_hiring_sources(
            self.db, connector=self.connector("VP Sales"), observed_at=NOW,
            persist_candidates=True,
        )
        second = scan_saved_hiring_sources(
            self.db, connector=self.connector("VP Sales", "Head of Revenue Operations"),
            observed_at=NOW + timedelta(days=1), persist_candidates=True,
        )
        self.assertEqual(second["candidate_count"], 2)
        self.assertEqual(second["stored_candidate_count"], 1)
        self.assertEqual(len(pending_hiring_candidates(self.db)), 2)

    def test_persistence_is_off_unless_asked_for(self):
        result = scan_saved_hiring_sources(
            self.db, connector=self.connector("VP Sales"), observed_at=NOW
        )
        self.assertFalse(result["persisted"])
        self.assertEqual(pending_hiring_candidates(self.db), [])

    def test_an_unknown_candidate_cannot_be_reviewed(self):
        with self.assertRaisesRegex(IntelligenceError, "does not exist"):
            set_candidate_status(self.db, "HIRE-NOPE", "dismissed")
        with self.assertRaisesRegex(IntelligenceError, "must be pending"):
            set_candidate_status(self.db, "HIRE-NOPE", "banished")


if __name__ == "__main__":
    unittest.main()
