"""Preview public hiring evidence without converting it into buyer intent."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from typing import Any, Mapping
from urllib.parse import urljoin, urlparse

from .signal_intelligence import IntelligenceError, fetch_public_html
from .storage import connect, init_db


_SPACE = re.compile(r"\s+")
_COMMERCIAL_ROLE = re.compile(
    r"\b(?:sales|revenue|growth|marketing|commercial|business development|"
    r"demand generation|go[- ]to[- ]market|partnerships?|account executive|"
    r"customer success|sales development|revenue operations|revops)\b",
    re.I,
)
_SENIOR_ROLE = re.compile(r"\b(?:chief|vp|vice president|head|director)\b", re.I)
_REVOPS_ROLE = re.compile(r"\b(?:revenue operations|revops|sales operations)\b", re.I)
_JOB_LINK = re.compile(r"/(?:jobs?|careers?|vacanc(?:y|ies)|positions?|openings?)(?:/|$)", re.I)


@dataclass(frozen=True)
class HiringSignalCandidate:
    candidate_id: str
    provider: str
    signal_type: str
    source_url: str
    title: str
    organization_name: str
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
            "observed_fact": self.observed_fact,
            "commercial_interpretation": self.commercial_interpretation,
            "observed_at": self.observed_at,
            "confidence": self.confidence,
            "strength": self.strength,
            "freshness_half_life_days": self.freshness_half_life_days,
        }


class _CareersHTMLParser(HTMLParser):
    def __init__(self, source_url: str):
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self.json_ld: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._json_parts: list[str] | None = None
        self._link_url = ""
        self._link_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script" and str(values.get("type") or "").casefold() == "application/ld+json":
            self._json_parts = []
        if tag == "a" and values.get("href"):
            self._link_url = urljoin(self.source_url, str(values["href"]).strip())
            self._link_parts = []

    def handle_data(self, data: str) -> None:
        if self._json_parts is not None:
            self._json_parts.append(data)
        if self._link_parts is not None:
            self._link_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._json_parts is not None:
            self.json_ld.append("".join(self._json_parts))
            self._json_parts = None
        if tag == "a" and self._link_parts is not None:
            self.links.append((self._link_url, _clean(" ".join(self._link_parts))))
            self._link_url = ""
            self._link_parts = None


class PublicHiringSignalConnector:
    name = "public_hiring_page"

    def scan(
        self,
        source_url: str,
        company: str,
        *,
        observed_at: datetime | None = None,
        max_age_days: int = 45,
    ) -> list[HiringSignalCandidate]:
        document = fetch_public_html(
            source_url,
            user_agent="AI-Growth-Engineering/0.1 hiring-signal-inspection",
            failure_code="hiring_source_failed",
        )
        clock = _utc(observed_at or datetime.now(timezone.utc))
        return extract_hiring_signal_candidates(
            document.html,
            document.source_url,
            company,
            observed_at=clock,
            max_age_days=max_age_days,
        )


def preview_hiring_signals(
    db_path: str,
    values: Mapping[str, Any],
    *,
    connector: PublicHiringSignalConnector | None = None,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    try:
        prospect_id = int(values.get("prospect_id"))
        max_age_days = int(values.get("max_age_days", 45))
    except (TypeError, ValueError) as exc:
        raise IntelligenceError("invalid_field", "prospect_id and max_age_days must be integers") from exc
    if prospect_id < 1 or not 1 <= max_age_days <= 365:
        raise IntelligenceError("invalid_field", "prospect_id must be positive and max_age_days must be 1-365")
    source_url = str(values.get("source_url") or "").strip()
    if not source_url:
        raise IntelligenceError("invalid_field", "source_url is required")
    with connect(db_path) as con:
        prospect = con.execute(
            "SELECT company FROM prospects WHERE id = ?", (prospect_id,)
        ).fetchone()
    if prospect is None:
        raise IntelligenceError("prospect_not_found", "Prospect does not exist")

    candidates = (connector or PublicHiringSignalConnector()).scan(
        source_url,
        prospect["company"],
        observed_at=observed_at,
        max_age_days=max_age_days,
    )
    with connect(db_path) as con:
        existing = {
            (row["source_url"], row["observed_fact"]): row["signal_id"]
            for row in con.execute(
                "SELECT signal_id, source_url, observed_fact FROM intent_signals WHERE prospect_id = ?",
                (prospect_id,),
            ).fetchall()
        }
    rows = []
    for candidate in candidates:
        row = candidate.as_dict()
        row["signal_payload"] = candidate.signal_payload(prospect_id)
        row["already_recorded_as"] = existing.get(
            (candidate.source_url, candidate.observed_fact)
        )
        rows.append(row)
    return {
        "prospect_id": prospect_id,
        "company": prospect["company"],
        "source_url": source_url,
        "provider": PublicHiringSignalConnector.name,
        "persisted": False,
        "candidate_count": len(rows),
        "candidates": rows,
    }


def extract_hiring_signal_candidates(
    html: str,
    source_url: str,
    company: str,
    *,
    observed_at: datetime,
    max_age_days: int = 45,
) -> list[HiringSignalCandidate]:
    if not 1 <= max_age_days <= 365:
        raise IntelligenceError("invalid_field", "max_age_days must be 1-365")
    parser = _CareersHTMLParser(source_url)
    parser.feed(html)
    records: list[tuple[dict[str, Any], str]] = []
    for raw in parser.json_ld:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in _objects(value):
            if _is_job_posting(item):
                records.append((item, "structured_job_posting"))
    for url, title in parser.links:
        if _is_public_http_url(url) and _JOB_LINK.search(urlparse(url).path) and _COMMERCIAL_ROLE.search(title):
            records.append(({"title": title, "url": url}, "careers_link"))

    clock = _utc(observed_at)
    candidates: list[HiringSignalCandidate] = []
    seen: set[tuple[str, str]] = set()
    for record, evidence_kind in records:
        candidate = _candidate_from_record(
            record,
            evidence_kind,
            source_url,
            company,
            clock,
            max_age_days,
        )
        if candidate is None:
            continue
        evidence_key = (candidate.source_url.casefold(), candidate.title.casefold())
        if evidence_key in seen:
            continue
        seen.add(evidence_key)
        candidates.append(candidate)
    return sorted(candidates, key=lambda row: (-row.strength, row.title.casefold(), row.source_url))


def _candidate_from_record(
    record: Mapping[str, Any],
    evidence_kind: str,
    source_url: str,
    company: str,
    observed_at: datetime,
    max_age_days: int,
) -> HiringSignalCandidate | None:
    title = _clean(record.get("title") or record.get("name"))
    if not title or not _COMMERCIAL_ROLE.search(title):
        return None
    job_url = urljoin(source_url, str(record.get("url") or "").strip()) or source_url
    if not _is_public_http_url(job_url):
        return None
    posted = _date_value(record.get("datePosted"))
    valid_through = _date_value(record.get("validThrough"))
    today = observed_at.date()
    if posted and (posted > today or (today - posted).days > max_age_days):
        return None
    if valid_through and valid_through < today:
        return None

    organization = record.get("hiringOrganization")
    organization_name = _clean(
        organization.get("name") if isinstance(organization, Mapping) else organization
    ) or company
    location = _location(record.get("jobLocation"))
    employment_type = _clean(record.get("employmentType"))
    details = [f'{company} published the role "{title}"']
    if posted:
        details.append(f"dated {posted.isoformat()}")
    if location:
        details.append(f"for {location}")
    observed_fact = " ".join(details) + " on a public careers source."
    interpretation = _interpretation(title)
    confidence = 0.95 if evidence_kind == "structured_job_posting" else 0.65
    strength = 4 if _SENIOR_ROLE.search(title) else 3
    half_life = 21 if strength == 4 else 14
    fingerprint = "\x1f".join(
        (job_url.casefold(), title.casefold(), (posted.isoformat() if posted else ""))
    )
    candidate_id = "HIRE-" + hashlib.sha256(fingerprint.encode()).hexdigest()[:12].upper()
    return HiringSignalCandidate(
        candidate_id=candidate_id,
        provider=PublicHiringSignalConnector.name,
        signal_type="hiring",
        source_url=job_url,
        title=title,
        organization_name=organization_name,
        location=location,
        employment_type=employment_type,
        date_posted=posted.isoformat() if posted else "",
        valid_through=valid_through.isoformat() if valid_through else "",
        observed_fact=observed_fact,
        commercial_interpretation=interpretation,
        observed_at=observed_at.isoformat(),
        confidence=confidence,
        strength=strength,
        freshness_half_life_days=half_life,
        evidence_kind=evidence_kind,
        uncertainty="A vacancy is not evidence of budget, vendor demand, or purchase intent.",
    )


def _interpretation(title: str) -> str:
    if _REVOPS_ROLE.search(title):
        lead = "This vacancy may indicate investment in commercial systems or measurement."
    elif _SENIOR_ROLE.search(title):
        lead = "This senior commercial vacancy may indicate a change in go-to-market capacity."
    else:
        lead = "This commercial vacancy may indicate active investment in go-to-market capacity."
    return f"{lead} It does not establish budget, vendor demand, or buying intent."


def _objects(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from _objects(item)
    elif isinstance(value, dict):
        yield value
        graph = value.get("@graph")
        if isinstance(graph, (list, dict)):
            yield from _objects(graph)


def _is_job_posting(value: Mapping[str, Any]) -> bool:
    kind = value.get("@type")
    if isinstance(kind, list):
        return any(str(item).casefold() == "jobposting" for item in kind)
    return str(kind or "").casefold() == "jobposting"


def _date_value(value: Any) -> date | None:
    raw = str(value or "").strip().replace("Z", "+00:00")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date() if "T" in raw else date.fromisoformat(raw)
    except ValueError:
        return None


def _location(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(filter(None, (_location(item) for item in value)))
    if not isinstance(value, Mapping):
        return _clean(value)
    address = value.get("address")
    if isinstance(address, Mapping):
        parts = [address.get("addressLocality"), address.get("addressRegion"), address.get("addressCountry")]
        return ", ".join(_clean(part) for part in parts if _clean(part))
    return _clean(value.get("name"))


def _clean(value: Any) -> str:
    return _SPACE.sub(" ", str(value or "")).strip()


def _is_public_http_url(value: str) -> bool:
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port not in {None, 80, 443}
        or parsed.hostname.casefold() == "localhost"
    ):
        return False
    try:
        return ipaddress.ip_address(parsed.hostname).is_global
    except ValueError:
        return True


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
