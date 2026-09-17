#!/usr/bin/env python3
"""PII guard — this repository is public, so natural-person data must not enter it.

The distinction this guard exists to draw, because the earlier leak was not a leak of
"contact data" in general:

    synthetic fixture        person@example.com, x@acme.test        allowed
    generic business inbox   info@, sales@, enquiries@ at a firm    allowed
    allowlisted example      a documented illustration              allowed
    natural-person contact   a named individual's address, an       REFUSED
                             individual profile URL, a person's
                             name in an identity column

A person's *name* in free prose cannot be detected structurally, so this guard does not
pretend to. It enforces the three classes that CAN be checked exactly — addresses,
profile URLs, and the identity columns of committed CSVs — and the operational rule is
that identity-bearing records live in `private/`, which is git-ignored.

    python3 scripts/pii_guard.py            # check the repo
    python3 scripts/pii_guard.py --selftest
"""
from __future__ import annotations

import csv
import re
import subprocess
import sys
import tempfile
from pathlib import Path

EMAIL = re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
PROFILE = re.compile(r"linkedin\.com/in/([A-Za-z0-9\-_%]+)")

# Domains that cannot belong to a real person.
SYNTHETIC_DOMAIN = re.compile(r"(^|\.)(test|example|invalid|localhost)$|^example\.(com|org|net)$", re.I)

# Local parts that address a function, not a person. A firm's `info@` is company data.
GENERIC_LOCAL = {
    "info", "sales", "hello", "enquiries", "enquiry", "contact", "support", "itsupport",
    "admin", "team", "marketing", "office", "mail", "privacy", "dpo", "careers", "jobs",
    "accounts", "help", "ask", "web", "new", "business", "general", "noreply", "no-reply",
    "bookings", "service", "hi", "post", "reception", "billing", "finance", "legal",
}

# Individual addresses and profile slugs that are deliberately published here. Each one
# needs a reason, and a reason that is about documentation rather than convenience.
ALLOWED_EMAILS: dict[str, str] = {
    # Department inboxes at prospect firms, published on their own contact pages. Two
    # independent sources classify each as functional rather than a person: the operator's
    # own `recipient_class` in the EXP-ACQ-0001 send log, and the 2026-09-17 identity
    # review. Listed per address on purpose — the local parts are firm-specific, so
    # admitting them to GENERIC_LOCAL would weaken the guard on every other domain.
    "cyber@waterstons.com": "cyber practice inbox, recipient_class=role_inbox",
    "cra@probrand.co.uk": "cyber-risk-assessment desk, recipient_class=role_inbox",
    "uksales@dsiltd.co.uk": "UK sales inbox, recipient_class=role_inbox",
}
ALLOWED_PROFILE_SLUGS: dict[str, str] = {
    "example-buyer": "illustration in the command-center placeholder",
}

# Committed CSVs whose identity columns must carry a pseudonym or a role, never a person.
IDENTITY_COLUMNS = {
    "experiments/EXP-ACQ-0001/sales/outreach.csv": ("recipient",),
    "experiments/EXP-ACQ-0001/sales/execution-manifest-50.csv": ("destination",),
}
PSEUDONYM = re.compile(r"^(P-\d{2,}|ROLE_INBOX|UNKNOWN|)$")
ROLE_WORDS = {
    "director", "managing", "head", "of", "it", "sales", "marketing", "operations",
    "chief", "executive", "officer", "manager", "owner", "founder", "general", "and",
    "commercial", "technical", "service", "account", "partner", "team", "business",
    "development", "cto", "ceo", "coo", "cio", "md", "gm", "desk", "info", "&",
    # A log may record an alternative rather than one title ("Director or Owner").
    # Adding the conjunction does not admit a person: a name's tokens are still not roles.
    "or",
}

SCANNED_SUFFIXES = {".py", ".md", ".json", ".csv", ".yml", ".yaml", ".txt", ".html"}
# A scan of fewer files than this has not run properly — an empty result must never pass.
MIN_FILES_SCANNED = 50


def tracked_files(root: Path) -> list[Path]:
    out = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True)
    return [root / line for line in out.stdout.split("\n") if line]


def is_role_phrase(value: str) -> bool:
    tokens = [t.strip("(),./&").lower() for t in value.split() if t.strip("(),./&")]
    return bool(tokens) and all(t in ROLE_WORDS for t in tokens)


def scan_text(path: Path, relative: str) -> list[str]:
    hits: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for local, domain in EMAIL.findall(text):
        address = f"{local}@{domain}"
        if SYNTHETIC_DOMAIN.search(domain) or local.lower() in GENERIC_LOCAL:
            continue
        if address in ALLOWED_EMAILS:
            continue
        hits.append(f"{relative}: personal-looking address at {domain}")
    for slug in PROFILE.findall(text):
        # `example-*` is the fixture convention, the profile-URL equivalent of example.com.
        if slug in ALLOWED_PROFILE_SLUGS or slug.startswith("example-"):
            continue
        hits.append(f"{relative}: individual profile URL")
    return hits


def scan_identity_columns(root: Path) -> list[str]:
    hits: list[str] = []
    for relative, columns in IDENTITY_COLUMNS.items():
        path = root / relative
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            for lineno, row in enumerate(csv.DictReader(handle), 2):
                for column in columns:
                    value = (row.get(column) or "").strip()
                    if PSEUDONYM.match(value) or is_role_phrase(value):
                        continue
                    # A web contact form is a company destination, not a person. An
                    # address is still refused here, URL or not.
                    if value.startswith(("http://", "https://")) and "@" not in value:
                        continue
                    hits.append(f"{relative}:{lineno}: column '{column}' carries an identity")
    return hits


def scan(root: Path) -> tuple[list[str], int]:
    hits: list[str] = []
    seen = 0
    for path in tracked_files(root):
        if path.suffix not in SCANNED_SUFFIXES or not path.exists():
            continue
        seen += 1
        hits.extend(scan_text(path, str(path.relative_to(root))))
    hits.extend(scan_identity_columns(root))
    return hits, seen


def selftest() -> int:
    checks = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        subprocess.run(["git", "init", "-q", str(root)], check=True)

        def write(name: str, body: str) -> None:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")

        # Negative controls: none of these may ever fail the guard.
        write("clean.md", "Write to info@realcompany.co.uk or sales@other.com.\n"
                          "Fixtures use person@example.com and buyer@acme.test.\n")
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        hits, seen = scan(root)
        assert hits == [], f"generic and synthetic addresses must pass, got {hits}"
        checks += 1
        assert seen >= 1, "the selftest scanned nothing"
        checks += 1

        # Positive control: a named individual's address must fail.
        write("leak.md", "Contact firstname.lastname@realcompany.co.uk about the offer.\n")
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        hits, _ = scan(root)
        assert any("personal-looking address" in h for h in hits), "a personal address must be caught"
        checks += 1

        # Positive control: an individual profile URL must fail.
        write("leak.md", "See https://www.linkedin.com/in/some-person1/ for the buyer.\n")
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        hits, _ = scan(root)
        assert any("profile URL" in h for h in hits), "a profile URL must be caught"
        checks += 1

        # Positive control: a person's name in an identity column must fail.
        write("experiments/EXP-ACQ-0001/sales/outreach.csv",
              "date_first_contact,company,recipient,role\n2026-01-01,Acme,Jane Roe,Managing Director\n")
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        hits, _ = scan(root)
        assert any("carries an identity" in h for h in hits), "a name in an identity column must be caught"
        checks += 1

        # Negative control for the same column: a pseudonym and a role phrase both pass.
        write("experiments/EXP-ACQ-0001/sales/outreach.csv",
              "date_first_contact,company,recipient,role\n"
              "2026-01-01,Acme,P-01,Managing Director\n"
              "2026-01-02,Beta,Managing Director,Managing Director\n")
        write("leak.md", "nothing to see\n")
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        hits, _ = scan(root)
        assert hits == [], f"pseudonyms and role phrases must pass, got {hits}"
        checks += 1

    print(f"pii_guard selftest: {checks} assertions passed")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    root = Path(__file__).resolve().parents[1]
    hits, seen = scan(root)
    if seen < MIN_FILES_SCANNED:
        print(f"pii_guard: scanned only {seen} files (expected at least {MIN_FILES_SCANNED}) — "
              "treat this as a failed run, not a pass", file=sys.stderr)
        return 2
    if hits:
        print(f"pii_guard: {len(hits)} natural-person identifier(s) found in {seen} tracked files:",
              file=sys.stderr)
        for hit in hits:
            print(f"  {hit}", file=sys.stderr)
        print("\nIdentity-bearing records belong in private/ (git-ignored). If an identifier is a "
              "generic business inbox or a documented example, add it to the allowlist in "
              "scripts/pii_guard.py with a reason.", file=sys.stderr)
        return 1
    print(f"pii_guard: {seen} tracked files scanned, no natural-person identifiers")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
