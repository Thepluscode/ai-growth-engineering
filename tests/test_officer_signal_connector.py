from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ai_growth_engineering.hiring_signal_connector import (
    PublicHiringSignalConnector,
    add_hiring_source,
    pending_hiring_candidates,
    preview_hiring_signals,
    scan_saved_hiring_sources,
)
from ai_growth_engineering.officer_signal_connector import (
    CompaniesHouseOfficerConnector,
    connector_for,
    extract_officer_appointment_candidates,
    officers_url,
)
from ai_growth_engineering.signal_intelligence import (
    ALLOWED_SIGNAL_TYPES,
    IntelligenceError,
    PublicHTMLDocument,
    add_intent_signal,
)
from ai_growth_engineering.storage import connect, init_db


# Fixed and in the past: `add_intent_signal` refuses a future observation, so a clock
# read at test time makes this suite fail on some days and pass on others.
NOW = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
SOURCE = "https://find-and-update.company-information.service.gov.uk/company/07144253/officers"


def officer_block(
    index: int,
    name: str,
    role: str,
    appointed: str,
    *,
    resigned: str = "",
    status: str = "",
    profile: str = "yn-XkB9KTx_IxuEUf950d2APyK0",
) -> str:
    """Mirrors the register's own markup: id-keyed fields, name inside an anchor."""
    parts = [
        '<div class="appointment-%d"><h2 class="heading-medium">' % index,
        f'<span id="officer-name-{index}">'
        f'<a class="govuk-link" href="/officers/{profile}/appointments">{name}</a></span></h2>',
    ]
    if status:
        parts.append(f'<span id="officer-status-tag-{index}" class="status-tag">{status}</span>')
    parts.append(f'<dl><dt>Role</dt><dd id="officer-role-{index}" class="data">{role}</dd></dl>')
    parts.append(
        f'<dl><dt>Appointed on</dt>'
        f'<dd id="officer-appointed-on-{index}" class="data">{appointed}</dd></dl>'
    )
    if resigned:
        parts.append(
            f'<dl><dt>Resigned on</dt>'
            f'<dd id="officer-resigned-on-{index}" class="data">{resigned}</dd></dl>'
        )
    parts.append("</div>")
    return "".join(parts)


def page(*blocks: str) -> str:
    return '<div class="appointments-list">' + "".join(blocks) + "</div>"


def extract(html: str, *, max_age_days: int = 90):
    return extract_officer_appointment_candidates(
        html, SOURCE, "Acme", observed_at=NOW, max_age_days=max_age_days
    )


class OfficerExtractionTests(unittest.TestCase):
    def test_a_current_director_becomes_a_named_reviewable_candidate(self):
        found = extract(page(officer_block(1, "DAUGHTRY, Richard Phillip", "Director", "1 August 2026")))
        self.assertEqual(len(found), 1)
        candidate = found[0]
        self.assertEqual(candidate.person_name, "Richard Phillip Daughtry")
        self.assertEqual(candidate.person_name_register, "DAUGHTRY, Richard Phillip")
        self.assertEqual(candidate.person_role, "Director")
        self.assertEqual(candidate.date_posted, "2026-08-01")
        self.assertEqual(candidate.signal_type, "leadership_change")
        self.assertEqual(candidate.evidence_kind, "statutory_register")
        self.assertEqual(candidate.provider, "companies_house_officers")
        self.assertTrue(candidate.candidate_id.startswith("APPT-"))
        self.assertEqual(
            candidate.officer_profile_url,
            "https://find-and-update.company-information.service.gov.uk"
            "/officers/yn-XkB9KTx_IxuEUf950d2APyK0/appointments",
        )

    def test_the_candidate_never_claims_buying_intent(self):
        candidate = extract(page(officer_block(1, "SMITH, Jane", "Director", "1 August 2026")))[0]
        # An appointment is a strong FACT and a weak buying signal. Collapsing the two
        # is how a register lookup gets sold as demand.
        self.assertEqual(candidate.confidence, 0.95)
        self.assertEqual(candidate.strength, 2)
        for text in (candidate.commercial_interpretation, candidate.uncertainty):
            self.assertIn("does not establish", text)
        self.assertIn("budget", candidate.uncertainty)
        self.assertNotEqual(
            candidate.observed_fact.casefold(), candidate.commercial_interpretation.casefold()
        )

    def test_the_signal_type_is_one_the_store_already_accepts(self):
        self.assertIn("leadership_change", ALLOWED_SIGNAL_TYPES)

    def test_a_resigned_officer_is_not_a_person_to_approach(self):
        self.assertEqual(
            extract(page(officer_block(
                1, "GONE, Pat", "Director", "1 August 2026", resigned="20 August 2026"
            ))),
            [],
        )

    def test_a_status_tag_of_resigned_is_enough_on_its_own(self):
        self.assertEqual(
            extract(page(officer_block(
                1, "GONE, Pat", "Director", "1 August 2026", status="Resigned"
            ))),
            [],
        )

    def test_secretaries_and_corporate_officers_are_rejected(self):
        html = page(
            officer_block(1, "KEEPER, Sam", "Secretary", "1 August 2026"),
            officer_block(2, "NOMINEE SERVICES LIMITED", "Corporate Director", "1 August 2026"),
        )
        self.assertEqual(extract(html), [])

    def test_a_future_dated_appointment_has_not_happened(self):
        self.assertEqual(
            extract(page(officer_block(1, "LATER, Alex", "Director", "1 October 2026"))), []
        )

    def test_the_window_is_a_boundary_not_a_suggestion(self):
        # 2026-09-01 minus 90 days is 2026-06-03 exactly.
        inside = extract(page(officer_block(1, "EDGE, Chris", "Director", "3 June 2026")))
        outside = extract(page(officer_block(1, "EDGE, Chris", "Director", "2 June 2026")))
        self.assertEqual(len(inside), 1)
        self.assertEqual(outside, [])

    def test_a_missing_or_unreadable_field_yields_nothing_rather_than_a_guess(self):
        self.assertEqual(extract('<dd id="officer-role-1">Director</dd>'), [])
        self.assertEqual(
            extract(page(officer_block(1, "NODATE, Sam", "Director", "sometime in August"))), []
        )
        self.assertEqual(
            extract(page(officer_block(1, "NODATE, Sam", "Director", "31 Febtober 2026"))), []
        )
        self.assertEqual(
            extract(page(officer_block(1, "NODATE, Sam", "Director", "31 February 2026"))), []
        )
        self.assertEqual(extract(""), [])

    def test_a_mixed_case_surname_is_left_exactly_as_filed(self):
        found = extract(page(officer_block(1, "McDonald, Fiona", "Director", "1 August 2026")))
        self.assertEqual(found[0].person_name, "Fiona McDonald")

    def test_a_name_the_register_did_not_split_is_not_rearranged(self):
        found = extract(page(officer_block(1, "PLC NOMINEE ONE", "Director", "1 August 2026")))
        self.assertEqual(found[0].person_name, "PLC NOMINEE ONE")

    def test_the_same_officer_twice_on_one_page_is_one_candidate(self):
        html = page(
            officer_block(1, "TWICE, Sam", "Director", "1 August 2026"),
            officer_block(2, "TWICE, Sam", "Director", "1 August 2026"),
        )
        self.assertEqual(len(extract(html)), 1)

    def test_officers_url_refuses_anything_that_is_not_a_company_number(self):
        self.assertEqual(
            officers_url("07144253"),
            "https://find-and-update.company-information.service.gov.uk/company/07144253/officers",
        )
        self.assertEqual(officers_url("sc123456"), officers_url("SC123456"))
        for bad in ("", "123", "071442534", "07144-25"):
            with self.assertRaises(IntelligenceError):
                officers_url(bad)


class ConnectorDispatchTests(unittest.TestCase):
    def test_a_register_url_gets_the_officer_connector_and_nothing_else_does(self):
        self.assertIsInstance(connector_for(SOURCE), CompaniesHouseOfficerConnector)
        self.assertIsInstance(
            connector_for("https://find-and-update.company-information.service.gov.uk/company/1"),
            CompaniesHouseOfficerConnector,
        )
        self.assertIsInstance(
            connector_for("https://example.com/careers"), PublicHiringSignalConnector
        )

    def test_a_lookalike_host_does_not_get_the_officer_connector(self):
        # Suffix matching on a bare string would accept this.
        self.assertIsInstance(
            connector_for("https://find-and-update.company-information.service.gov.uk.evil.test/x"),
            PublicHiringSignalConnector,
        )

    def test_the_live_connector_rejects_a_private_address_before_fetching(self):
        with self.assertRaises(IntelligenceError) as ctx:
            CompaniesHouseOfficerConnector().scan("http://127.0.0.1/company/1/officers", "Acme")
        self.assertEqual(ctx.exception.code, "unsafe_source")


class OfficerPipelineTests(unittest.TestCase):
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
        self.html = page(officer_block(1, "DAUGHTRY, Richard Phillip", "Director", "1 August 2026"))

    def _stub(self, html: str):
        connector = CompaniesHouseOfficerConnector()
        original = __import__(
            "ai_growth_engineering.officer_signal_connector", fromlist=["fetch_public_html"]
        )
        self._saved = original.fetch_public_html
        original.fetch_public_html = lambda url, **kw: PublicHTMLDocument(SOURCE, html)
        self.addCleanup(setattr, original, "fetch_public_html", self._saved)
        return connector

    def test_preview_reports_the_officer_provider_not_the_careers_one(self):
        self._stub(self.html)
        preview = preview_hiring_signals(
            self.db,
            {"prospect_id": 1, "source_url": SOURCE, "max_age_days": 90},
            observed_at=NOW,
        )
        self.assertEqual(preview["provider"], "companies_house_officers")
        self.assertEqual(preview["candidate_count"], 1)
        self.assertFalse(preview["persisted"])
        with connect(self.db) as con:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM intent_signals").fetchone()[0], 0
            )

    def test_a_reviewed_candidate_records_a_named_signal(self):
        self._stub(self.html)
        preview = preview_hiring_signals(
            self.db,
            {"prospect_id": 1, "source_url": SOURCE, "max_age_days": 90},
            observed_at=NOW,
        )
        signal = add_intent_signal(self.db, preview["candidates"][0]["signal_payload"])
        self.assertEqual(signal["person_name"], "Richard Phillip Daughtry")
        self.assertEqual(signal["person_role"], "Director")
        self.assertEqual(signal["signal_type"], "leadership_change")

    def test_a_saved_register_source_sweeps_without_a_new_command(self):
        self._stub(self.html)
        add_hiring_source(self.db, {"prospect_id": 1, "source_url": SOURCE, "label": "register"})
        result = scan_saved_hiring_sources(
            self.db, observed_at=NOW, max_age_days=90, persist_candidates=True
        )
        self.assertEqual(result["candidate_count"], 1)
        pending = pending_hiring_candidates(self.db)
        self.assertEqual(len(pending), 1)
        self.assertTrue(pending[0]["candidate_id"].startswith("APPT-"))
        self.assertEqual(pending[0]["status"], "pending")
        # A sweep proposes; it never records a signal.
        with connect(self.db) as con:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM intent_signals").fetchone()[0], 0
            )


if __name__ == "__main__":
    unittest.main()
