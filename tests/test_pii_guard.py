"""The PII guard is the control that keeps natural-person data out of a public repo.

A guard nobody has watched fail is decoration, so every class it draws is tested from
both sides: the thing that must be refused, and the thing that must keep passing.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pii_guard  # noqa: E402


class GuardFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def write(self, name: str, body: str) -> None:
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)

    def hits(self) -> list[str]:
        found, _ = pii_guard.scan(self.root)
        return found


class RefusesNaturalPersonData(GuardFixture):
    def test_a_named_individuals_address_is_refused(self):
        self.write("notes.md", "Reach firstname.lastname@realfirm.co.uk before Friday.\n")
        self.assertTrue(any("personal-looking address" in h for h in self.hits()))

    def test_a_single_token_personal_local_part_is_refused(self):
        self.write("notes.md", "Reach jamesmorrison@realfirm.co.uk before Friday.\n")
        self.assertTrue(any("personal-looking address" in h for h in self.hits()))

    def test_an_individual_profile_url_is_refused(self):
        self.write("notes.md", "Profile: https://www.linkedin.com/in/a-real-person2/\n")
        self.assertTrue(any("profile URL" in h for h in self.hits()))

    def test_a_person_in_an_identity_column_is_refused(self):
        self.write("experiments/EXP-ACQ-0001/sales/outreach.csv",
                   "date_first_contact,company,recipient,role\n"
                   "2026-01-01,Acme,Jane Roe,Managing Director\n")
        self.assertTrue(any("carries an identity" in h for h in self.hits()))

    def test_a_personal_address_in_a_destination_column_is_refused(self):
        self.write("experiments/EXP-ACQ-0001/sales/execution-manifest-50.csv",
                   "send_number,company,destination\n1,Acme,jane.roe@realfirm.co.uk\n")
        self.assertTrue(self.hits())


class KeepsCompanyAndSyntheticData(GuardFixture):
    def test_generic_business_inboxes_pass(self):
        self.write("notes.md", "info@realfirm.co.uk, sales@other.com, enquiries@third.co.uk\n")
        self.assertEqual(self.hits(), [])

    def test_synthetic_fixture_addresses_pass(self):
        self.write("notes.md", "person@example.com buyer@acme.test agent@beta.test\n")
        self.assertEqual(self.hits(), [])

    def test_a_company_name_containing_a_surname_passes(self):
        self.write("notes.md", "| FSP-0003 | Williams Heating Services | VERIFIED |\n")
        self.assertEqual(self.hits(), [])

    def test_a_pseudonym_in_an_identity_column_passes(self):
        self.write("experiments/EXP-ACQ-0001/sales/outreach.csv",
                   "date_first_contact,company,recipient,role\n2026-01-01,Acme,P-01,Managing Director\n")
        self.assertEqual(self.hits(), [])

    def test_a_role_phrase_in_an_identity_column_passes(self):
        self.write("experiments/EXP-ACQ-0001/sales/outreach.csv",
                   "date_first_contact,company,recipient,role\n"
                   "2026-01-01,Acme,Managing Director,Managing Director\n")
        self.assertEqual(self.hits(), [])

    def test_a_role_alternative_in_an_identity_column_passes(self):
        """A send log may record "Director or Owner" rather than one title."""
        self.write("experiments/EXP-ACQ-0001/sales/outreach.csv",
                   "date_first_contact,company,recipient,role\n"
                   "2026-01-01,Acme,Director or Owner,Managing Director\n")
        self.assertEqual(self.hits(), [])

    def test_a_web_contact_form_destination_passes(self):
        self.write("experiments/EXP-ACQ-0001/sales/execution-manifest-50.csv",
                   "send_number,company,destination\n1,Acme,https://acme.co.uk/contact\n")
        self.assertEqual(self.hits(), [])

    def test_a_url_shaped_value_containing_an_address_is_still_refused(self):
        """The URL exemption must not become a way to smuggle an address through."""
        self.write("experiments/EXP-ACQ-0001/sales/execution-manifest-50.csv",
                   "send_number,company,destination\n1,Acme,https://acme.co.uk/?to=jane.roe@acme.co.uk\n")
        self.assertTrue(self.hits())

    def test_an_allowlisted_profile_slug_passes(self):
        self.write("notes.md", "https://www.linkedin.com/in/example-buyer/\n")
        self.assertEqual(self.hits(), [])


class TheAllowlistIsNotABypass(GuardFixture):
    def test_an_allowlisted_address_passes(self):
        address = next(iter(pii_guard.ALLOWED_EMAILS))
        self.write("notes.md", f"Verified contact: {address}\n")
        self.assertEqual(self.hits(), [])

    def test_allowlisting_one_address_does_not_allow_its_domain(self):
        """A person at an allowlisted firm must still be refused."""
        domain = next(iter(pii_guard.ALLOWED_EMAILS)).split("@")[1]
        self.write("notes.md", f"Spoke to jane.roe@{domain} on Tuesday.\n")
        self.assertTrue(any("personal-looking address" in h for h in self.hits()))

    def test_every_allowlist_entry_states_a_reason(self):
        for address, reason in pii_guard.ALLOWED_EMAILS.items():
            self.assertTrue(reason.strip(), f"{address} is allowlisted without a reason")


class CannotPassVacuously(GuardFixture):
    def test_a_scan_that_walked_nothing_is_a_failed_run(self):
        """An empty result set is only meaningful if the scan actually read files."""
        rc = pii_guard.main([])
        self.assertIn(rc, (0, 1))  # the real repo either passes or reports hits
        _, seen = pii_guard.scan(ROOT)
        self.assertGreaterEqual(seen, pii_guard.MIN_FILES_SCANNED)

    def test_the_selftest_runs_its_own_positive_and_negative_controls(self):
        self.assertEqual(pii_guard.selftest(), 0)


class TheRepositoryItselfIsClean(unittest.TestCase):
    def test_no_natural_person_identifier_is_committed(self):
        hits, seen = pii_guard.scan(ROOT)
        self.assertGreaterEqual(seen, pii_guard.MIN_FILES_SCANNED)
        self.assertEqual(hits, [], f"{len(hits)} natural-person identifier(s) committed")


if __name__ == "__main__":
    unittest.main()
