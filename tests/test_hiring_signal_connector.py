from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_growth_engineering.hiring_signal_connector import (
    PublicHiringSignalConnector,
    add_hiring_source,
    discover_careers_urls,
    discover_hiring_sources,
    extract_hiring_signal_candidates,
    list_hiring_sources,
    pending_hiring_candidates,
    preview_hiring_signals,
    scan_saved_hiring_sources,
    set_candidate_status,
)
from ai_growth_engineering.signal_intelligence import (
    IntelligenceError,
    PublicHTMLDocument,
    add_intent_signal,
)
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


class TitleBoundaryTests(unittest.TestCase):
    """A careers page that wraps a whole job card in one anchor must not put a
    paragraph into the title, and must not qualify on a word buried in prose."""

    def candidates(self, html):
        return extract_hiring_signal_candidates(
            html, "https://acme.example/careers", "Acme", observed_at=NOW
        )

    def test_a_job_card_in_one_anchor_yields_a_bounded_title(self):
        body = "Atlas is a managed IT provider founded in 2010 and we do many things. " * 40
        html = f'<a href="/careers/csm">Customer Success Manager Department: Sales {body}</a>'
        found = self.candidates(html)
        self.assertEqual(len(found), 1)
        self.assertLessEqual(len(found[0].title), 90)
        self.assertTrue(found[0].title.startswith("Customer Success Manager"))
        self.assertNotIn("founded in 2010", found[0].observed_fact)

    def test_a_commercial_word_buried_in_prose_is_not_a_vacancy(self):
        prose = "We care deeply about our people and our culture. " * 8
        html = f'<a href="/careers/culture">{prose} Our sales team is great.</a>'
        self.assertEqual(self.candidates(html), [])

    def test_the_character_cap_bounds_a_card_with_no_field_labels(self):
        # No "Department:" or "Full Time" here, so only the hard cap can stop it.
        run_on = "Head of Sales and also many other words that keep going and going " * 20
        found = self.candidates(f'<a href="/careers/x">{run_on}</a>')
        self.assertEqual(len(found), 1)
        self.assertLessEqual(len(found[0].title), 90)
        self.assertLess(len(found[0].observed_fact), 200)

    def test_a_normal_short_title_is_untouched(self):
        found = self.candidates('<a href="/careers/vp-sales">VP of Sales, UK</a>')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].title, "VP of Sales, UK")

    def test_an_empty_anchor_is_not_a_vacancy(self):
        self.assertEqual(self.candidates('<a href="/careers/x"></a>'), [])


class CareersDiscoveryTests(unittest.TestCase):
    def test_a_careers_page_is_found_by_path_or_by_link_text(self):
        html = (
            '<a href="/about">About us</a>'
            '<a href="/careers/">Careers</a>'
            '<a href="/company/work-with-us">Work with us</a>'
            '<a href="/who-we-are">Join us</a>'
        )
        found = discover_careers_urls(html, "https://example.com/")
        self.assertIn("https://example.com/careers", found)
        self.assertIn("https://example.com/who-we-are", found)
        self.assertNotIn("https://example.com/about", found)

    def test_the_index_outranks_a_single_vacancy(self):
        html = (
            '<a href="/careers/senior-account-executive-london">A role</a>'
            '<a href="/careers/">Careers</a>'
        )
        self.assertEqual(discover_careers_urls(html, "https://example.com/")[0],
                         "https://example.com/careers")

    def test_offsite_boards_and_unsafe_targets_are_not_followed(self):
        html = (
            '<a href="https://boards.greenhouse.io/acme">Jobs</a>'
            '<a href="http://127.0.0.1/careers">Careers</a>'
            '<a href="mailto:jobs@example.com">Jobs</a>'
            '<a href="/careers">Careers</a>'
        )
        self.assertEqual(discover_careers_urls(html, "https://example.com/"),
                         ["https://example.com/careers"])

    def test_a_page_with_no_careers_link_yields_nothing(self):
        self.assertEqual(discover_careers_urls('<a href="/pricing">Pricing</a>', "https://x.com/"), [])


class DiscoveryOutcomeTests(unittest.TestCase):
    """Four different facts must not collapse into one."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "growth.db")
        init_db(self.db)
        rows = [
            (1, "Hiring Ltd", "https://hiring.example/", "qualified"),
            (2, "Quiet Ltd", "https://quiet.example/", "qualified"),
            (3, "Opaque Ltd", "https://opaque.example/", "qualified"),
            (4, "Down Ltd", "https://down.example/", "qualified"),
            (5, "Dropped Ltd", "https://dropped.example/", "disqualified_market_fit"),
        ]
        with connect(self.db) as con:
            for pid, company, site, status in rows:
                con.execute(
                    """INSERT INTO prospects(id, company, website, priority, target_roles,
                                             evidence, source_url, status)
                       VALUES (?, ?, ?, 'A', 'Revenue leader', 'Public B2B offer', ?, ?)""",
                    (pid, company, site, site + "about", status),
                )

    def fetcher(self, url):
        pages = {
            "https://hiring.example/": '<a href="/careers">Careers</a>',
            "https://quiet.example/": '<a href="/careers">Careers</a>',
            "https://opaque.example/": '<a href="/pricing">Pricing</a>',
        }
        if url not in pages:
            raise IntelligenceError("source_fetch_failed", "Public page inspection failed")
        return PublicHTMLDocument(url, pages[url])

    def connector(self):
        candidate = extract_hiring_signal_candidates(
            structured_page({"@type": "JobPosting", "title": "VP Sales",
                             "url": "/jobs/vp-sales", "datePosted": "2026-08-29"}),
            SOURCE, "Hiring Ltd", observed_at=NOW,
        )[0]

        class Stub:
            def scan(self, source_url, company, *, observed_at=None, max_age_days=45):
                return [candidate] if "hiring.example" in source_url else []

        return Stub()

    def test_each_prospect_lands_in_exactly_one_distinct_outcome(self):
        result = discover_hiring_sources(
            self.db, connector=self.connector(), fetcher=self.fetcher, observed_at=NOW,
        )
        self.assertEqual(result["prospect_count"], 4, "disqualified prospects are not swept")
        self.assertEqual(result["outcomes"], {
            "commercial_role_published": 1,
            "no_commercial_role": 1,
            "no_careers_link": 1,
            "site_unreachable": 1,
        })
        by_company = {row["company"]: row for row in result["results"]}
        self.assertEqual(by_company["Hiring Ltd"]["titles"], ["VP Sales"])
        self.assertEqual(by_company["Quiet Ltd"]["careers_url"], "https://quiet.example/careers")
        self.assertEqual(by_company["Opaque Ltd"]["careers_url"], "")
        self.assertIn("source_fetch_failed", by_company["Down Ltd"]["detail"])
        self.assertNotIn("Dropped Ltd", by_company)

    def test_discovery_saves_nothing_unless_asked(self):
        discover_hiring_sources(
            self.db, connector=self.connector(), fetcher=self.fetcher, observed_at=NOW,
        )
        self.assertEqual(list_hiring_sources(self.db), [])

    def test_only_the_prospects_publishing_a_commercial_role_are_kept(self):
        result = discover_hiring_sources(
            self.db, connector=self.connector(), fetcher=self.fetcher, observed_at=NOW, save=True,
        )
        saved = list_hiring_sources(self.db)
        self.assertEqual([r["company"] for r in saved], ["Hiring Ltd"])
        self.assertEqual(saved[0]["source_url"], "https://hiring.example/careers")
        by_company = {row["company"]: row for row in result["results"]}
        self.assertEqual(by_company["Hiring Ltd"]["detail"], "saved")

        # re-running must not duplicate the source
        discover_hiring_sources(
            self.db, connector=self.connector(), fetcher=self.fetcher, observed_at=NOW, save=True,
        )
        self.assertEqual(len(list_hiring_sources(self.db)), 1)


if __name__ == "__main__":
    unittest.main()
