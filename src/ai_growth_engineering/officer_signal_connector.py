"""Preview statutory officer appointments without converting them into buyer intent.

The Companies House register is the one place a UK company's decision-makers are
published by law. `EXP-ACQ-0002/DISCOVERY-RESULT.md` measured **0 reachable
named-buyer mailboxes across 18 accounts** because first-party sites do not name
them; the register does, and it does so as a matter of statute rather than
marketing choice.

What this connector therefore produces is an **identity**, not an address, and not
a buying signal. A newly appointed director is a change in who runs the company.
It is not evidence of budget, vendor demand or purchase intent, and the register
does not publish a commercial remit — the `Role` field is the statutory office
("Director"), never the function. Every candidate says so in its own words, in the
same shape `hiring_signal_connector` uses, because a signal that overstates itself
is worse than no signal.

It reuses that module's source and candidate stores rather than adding its own: an
appointment is a hiring event, its columns fit unchanged, and the sweep, dedupe,
minimum-interval guard and human review path are already tested there.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

from .signal_intelligence import IntelligenceError, fetch_public_html


COMPANIES_HOUSE_HOST = "find-and-update.company-information.service.gov.uk"

_SPACE = re.compile(r"\s+")
_OFFICER_FIELD = re.compile(
    r"^officer-(name|role|appointed-on|resigned-on|status-tag)-(\d+)$", re.I
)
# A secretary keeps the register; a corporate officer is not a person at all.
# Neither is a named commercial decision-maker, and recording one as a candidate
# puts a reviewer in front of a row that can never become a conversation.
_NON_BUYER_ROLE = re.compile(r"\b(?:secretar(?:y|ies)|corporate)\b", re.I)
_OFFICER_PROFILE = re.compile(r"^/officers/[A-Za-z0-9_\-]+/appointments/?$")
# "31 January 2013" — the register's own rendering, and the only one it uses.
_REGISTER_DATE = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$")
_MONTHS = {
    m: i
    for i, m in enumerate(
        (
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        ),
        start=1,
    )
}

# An appointment is a rarer event than a job advert, so the same 45-day window that
# suits a careers page would report "nothing here" for a company that changed its
# board last quarter. The window is still bounded, and still a parameter.
#
# Known ceiling: `preview_hiring_signals` always passes an explicit `max_age_days`,
# so this default does not reach the sweep — `age sweep-sources` and its daily cron
# entry apply their own 45. Register sources want `--max-age-days 90`. Raising the
# shared CLI default would widen the careers window too, which is a different
# decision than this one.
DEFAULT_MAX_AGE_DAYS = 90


@dataclass(frozen=True)
class OfficerAppointmentCandidate:
    """Field names mirror `HiringSignalCandidate` so the existing candidate store,
    sweep and review path accept this connector's output unchanged."""

    candidate_id: str
    provider: str
    signal_type: str
    source_url: str
    title: str
    organization_name: str
    person_name: str
    person_name_register: str
    person_role: str
    officer_profile_url: str
    location: str
    employment_type: str
    date_posted: str
    valid_through: str
    observed_fact: str
    commercial_interpretation: str
    observed_at: str
    confidence: float
    strength: int
    freshness_half_life_days: int
    evidence_kind: str
    uncertainty: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def signal_payload(self, prospect_id: int) -> dict[str, Any]:
        return {
            "prospect_id": prospect_id,
            "signal_type": self.signal_type,
            "source_url": self.source_url,
            "person_name": self.person_name,
            "person_role": self.person_role,
            "observed_fact": self.observed_fact,
            "commercial_interpretation": self.commercial_interpretation,
            "observed_at": self.observed_at,
            "confidence": self.confidence,
            "strength": self.strength,
            "freshness_half_life_days": self.freshness_half_life_days,
        }


class _OfficerHTMLParser(HTMLParser):
    """Collects the text of every element carrying an `officer-<field>-<n>` id.

    Depth counting matters: the officer's name is wrapped in an anchor, so the id
    element's own end tag is not the first `</...>` encountered.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fields: dict[str, dict[str, str]] = {}
        self.profile_urls: dict[str, str] = {}
        self._field = ""
        self._index = ""
        self._parts: list[str] | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if self._parts is not None:
            self._depth += 1
            href = str(values.get("href") or "").strip()
            if self._field == "name" and _OFFICER_PROFILE.match(urlparse(href).path or ""):
                self.profile_urls[self._index] = href
            return
        match = _OFFICER_FIELD.match(str(values.get("id") or ""))
        if match:
            self._field = match.group(1).lower().replace("-", "_")
            self._index = match.group(2)
            self._parts = []
            self._depth = 1

    def handle_data(self, data: str) -> None:
        if self._parts is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._parts is None:
            return
        self._depth -= 1
        if self._depth:
            return
        text = _clean("".join(self._parts))
        self.fields.setdefault(self._index, {})[self._field] = text
        self._field = ""
        self._index = ""
        self._parts = None


class CompaniesHouseOfficerConnector:
    name = "companies_house_officers"

    def scan(
        self,
        source_url: str,
        company: str,
        *,
        observed_at: datetime | None = None,
        max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    ) -> list[OfficerAppointmentCandidate]:
        document = fetch_public_html(
            source_url,
            user_agent="AI-Growth-Engineering/0.1 officer-signal-inspection",
            failure_code="officer_source_failed",
        )
        clock = _utc(observed_at or datetime.now(timezone.utc))
        return extract_officer_appointment_candidates(
            document.html,
            document.source_url,
            company,
            observed_at=clock,
            max_age_days=max_age_days,
        )


def extract_officer_appointment_candidates(
    html: str,
    source_url: str,
    company: str,
    *,
    observed_at: datetime,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> list[OfficerAppointmentCandidate]:
    parser = _OfficerHTMLParser()
    parser.feed(html)
    today = observed_at.date()
    candidates: list[OfficerAppointmentCandidate] = []
    seen: set[str] = set()
    for index in sorted(parser.fields, key=_sort_key):
        record = parser.fields[index]
        candidate = _candidate_from_officer(
            record,
            parser.profile_urls.get(index, ""),
            source_url,
            company,
            observed_at,
            today,
            max_age_days,
        )
        if candidate is None or candidate.candidate_id in seen:
            continue
        seen.add(candidate.candidate_id)
        candidates.append(candidate)
    return candidates


def _candidate_from_officer(
    record: dict[str, str],
    profile_path: str,
    source_url: str,
    company: str,
    observed_at: datetime,
    today: date,
    max_age_days: int,
) -> OfficerAppointmentCandidate | None:
    register_name = record.get("name", "")
    role = record.get("role", "")
    if not register_name or not role:
        return None
    # A departed officer is a matter of record, not a person to approach.
    if record.get("resigned_on") or "resigned" in record.get("status_tag", "").casefold():
        return None
    if _NON_BUYER_ROLE.search(role):
        return None
    appointed = _register_date(record.get("appointed_on", ""))
    if appointed is None:
        return None
    # A future-dated appointment has not happened, and one outside the window is
    # no longer a change. Both are rejections, never a widened window.
    if appointed > today or (today - appointed).days > max_age_days:
        return None

    person_name = _readable_name(register_name)
    profile_url = urljoin(source_url, profile_path) if profile_path else ""
    observed_fact = (
        f"The Companies House register records {person_name} as appointed "
        f"{role} of {company} on {appointed.isoformat()}."
    )
    fingerprint = "\x1f".join(
        (source_url.casefold(), register_name.casefold(), role.casefold(), appointed.isoformat())
    )
    return OfficerAppointmentCandidate(
        candidate_id="APPT-" + hashlib.sha256(fingerprint.encode()).hexdigest()[:12].upper(),
        provider=CompaniesHouseOfficerConnector.name,
        signal_type="leadership_change",
        source_url=source_url,
        title=f"{role}: {person_name}",
        organization_name=company,
        person_name=person_name,
        person_name_register=register_name,
        person_role=role,
        officer_profile_url=profile_url,
        location="",
        employment_type="",
        date_posted=appointed.isoformat(),
        valid_through="",
        observed_fact=observed_fact,
        commercial_interpretation=_interpretation(),
        observed_at=observed_at.isoformat(),
        # The fact is a statutory filing, so it is as certain as this pipeline gets.
        # Certainty about the fact is not strength as a buying signal: an appointment
        # says who runs the company, and nothing about whether it is buying.
        confidence=0.95,
        strength=2,
        freshness_half_life_days=60,
        evidence_kind="statutory_register",
        uncertainty=(
            "A statutory appointment names an officer of record. It does not establish "
            "a commercial remit, budget, vendor demand, or buying intent."
        ),
    )


def _interpretation() -> str:
    return (
        "A recent board appointment may indicate a change in commercial direction or "
        "priorities. The register publishes the statutory office, not the function, so "
        "this person's commercial remit is unknown. It does not establish budget, "
        "vendor demand, or buying intent."
    )


def connector_for(source_url: str):
    """Pick the connector a saved source needs.

    Sources are saved as plain URLs against a prospect, so the sweep and its daily
    cron entry pick this up with no new command and no new schedule.
    """
    from .hiring_signal_connector import PublicHiringSignalConnector

    host = (urlparse(source_url).hostname or "").casefold()
    if host == COMPANIES_HOUSE_HOST or host.endswith("." + COMPANIES_HOUSE_HOST):
        return CompaniesHouseOfficerConnector()
    return PublicHiringSignalConnector()


def officers_url(company_number: str) -> str:
    """The public officers page for a company number, as saved by `age source-add`."""
    number = str(company_number or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{8}", number):
        raise IntelligenceError(
            "invalid_field", "company_number must be the 8-character Companies House number"
        )
    return f"https://{COMPANIES_HOUSE_HOST}/company/{number}/officers"


def _readable_name(register_name: str) -> str:
    """"DAUGHTRY, Richard Phillip" -> "Richard Phillip Daughtry".

    The register shouts the surname and puts it first. A name that is already mixed
    case is left exactly as filed — de-shouting "McDonald" into "Mcdonald" would
    corrupt the one field this connector exists to produce.
    """
    surname, _, forenames = register_name.partition(",")
    surname, forenames = surname.strip(), forenames.strip()
    if not forenames:
        return register_name.strip()
    return f"{forenames} {_deshout(surname)}".strip()


def _deshout(value: str) -> str:
    return " ".join(part.title() if part.isupper() else part for part in value.split())


def _register_date(value: str) -> date | None:
    match = _REGISTER_DATE.match(value.strip())
    if not match:
        return None
    month = _MONTHS.get(match.group(2).casefold())
    if month is None:
        return None
    try:
        return date(int(match.group(3)), month, int(match.group(1)))
    except ValueError:
        return None


def _sort_key(index: str) -> tuple[int, str]:
    return (int(index), index) if index.isdigit() else (10**9, index)


def _clean(value: str) -> str:
    return _SPACE.sub(" ", str(value or "")).strip()


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
