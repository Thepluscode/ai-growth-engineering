"""Preview public hiring evidence without converting it into buyer intent."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import time
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


SOURCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS hiring_signal_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL REFERENCES prospects(id),
    source_url TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_scanned_at TEXT NOT NULL DEFAULT '',
    last_candidate_count INTEGER NOT NULL DEFAULT -1,
    last_error TEXT NOT NULL DEFAULT '',
    UNIQUE(prospect_id, source_url)
);

CREATE TABLE IF NOT EXISTS hiring_signal_candidates (
    candidate_id TEXT PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES hiring_signal_sources(id),
    prospect_id INTEGER NOT NULL REFERENCES prospects(id),
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    observed_fact TEXT NOT NULL,
    commercial_interpretation TEXT NOT NULL,
    date_posted TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL,
    strength INTEGER NOT NULL,
    freshness_half_life_days INTEGER NOT NULL,
    evidence_kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    recorded_signal_id TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hiring_candidates_status
ON hiring_signal_candidates(status, last_seen_at DESC);
"""


def init_source_store(db_path: str) -> None:
    init_db(db_path)
    with connect(db_path) as con:
        con.executescript(SOURCE_SCHEMA)


def add_hiring_source(db_path: str, values: Mapping[str, Any]) -> dict[str, Any]:
    """Save a public careers page so later scans need no pasted URL."""
    init_source_store(db_path)
    try:
        prospect_id = int(values.get("prospect_id"))
    except (TypeError, ValueError) as exc:
        raise IntelligenceError("invalid_field", "prospect_id must be an integer") from exc
    source_url = str(values.get("source_url") or "").strip()
    label = str(values.get("label") or "").strip()[:120]
    if not _is_public_http_url(source_url):
        raise IntelligenceError("invalid_field", "source_url must be a public http(s) URL")
    with connect(db_path) as con:
        prospect = con.execute(
            "SELECT company FROM prospects WHERE id = ?", (prospect_id,)
        ).fetchone()
        if prospect is None:
            raise IntelligenceError("prospect_not_found", "Prospect does not exist")
        duplicate = con.execute(
            "SELECT id FROM hiring_signal_sources WHERE prospect_id = ? AND source_url = ?",
            (prospect_id, source_url),
        ).fetchone()
        if duplicate is not None:
            raise IntelligenceError(
                "duplicate_source", f"This source is already saved as source {duplicate['id']}"
            )
        cursor = con.execute(
            "INSERT INTO hiring_signal_sources(prospect_id, source_url, label) VALUES (?, ?, ?)",
            (prospect_id, source_url, label),
        )
    return {
        "source_id": cursor.lastrowid,
        "prospect_id": prospect_id,
        "company": prospect["company"],
        "source_url": source_url,
        "label": label,
    }


def list_hiring_sources(db_path: str) -> list[dict[str, Any]]:
    init_source_store(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            """SELECT s.*, p.company FROM hiring_signal_sources s
               JOIN prospects p ON p.id = s.prospect_id
               ORDER BY p.company, s.id"""
        ).fetchall()
    return [dict(row) for row in rows]


DEFAULT_MIN_INTERVAL_HOURS = 20


def _hours_since(stamp: str, now: datetime) -> float | None:
    """None when never scanned — an unknown age is not a small one."""
    if not stamp:
        return None
    try:
        seen = _utc(datetime.fromisoformat(stamp))
    except ValueError:
        return None
    return (now - seen).total_seconds() / 3600


def scan_saved_hiring_sources(
    db_path: str,
    *,
    connector: PublicHiringSignalConnector | None = None,
    observed_at: datetime | None = None,
    max_age_days: int = 45,
    min_interval_hours: float = 0.0,
    persist_candidates: bool = False,
    pause_seconds: float = 0.0,
) -> dict[str, Any]:
    """Scan every saved source. Persists the per-source outcome, and the candidates
    themselves when `persist_candidates` is set.

    One source failing must not lose the candidates found by the others, so each
    failure is recorded against its own row and the sweep continues.

    `min_interval_hours` is what makes an unattended run safe for somebody else's
    server: a source fetched recently is skipped rather than fetched again, so a
    crash-looping schedule cannot turn into a crawl. `pause_seconds` spaces the
    requests that do go out.
    """
    sources = list_hiring_sources(db_path)
    connector = connector or PublicHiringSignalConnector()
    now = _utc(observed_at or datetime.now(timezone.utc))
    scanned_at = now.isoformat(timespec="seconds")
    results: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    skipped = 0
    for index, source in enumerate(sources):
        age_hours = _hours_since(source["last_scanned_at"], now)
        if min_interval_hours > 0 and age_hours is not None and age_hours < min_interval_hours:
            skipped += 1
            results.append({
                "source_id": source["id"],
                "prospect_id": source["prospect_id"],
                "company": source["company"],
                "source_url": source["source_url"],
                "label": source["label"],
                "candidate_count": None,
                "error": "",
                "skipped": f"scanned {age_hours:.1f}h ago, inside the {min_interval_hours:g}h interval",
            })
            continue
        if pause_seconds > 0 and index:
            time.sleep(pause_seconds)
        error = ""
        found: list[dict[str, Any]] = []
        try:
            preview = preview_hiring_signals(
                db_path,
                {
                    "prospect_id": source["prospect_id"],
                    "source_url": source["source_url"],
                    "max_age_days": max_age_days,
                },
                connector=connector,
                observed_at=observed_at,
            )
            found = preview["candidates"]
        except IntelligenceError as exc:
            error = f"{exc.code}: {exc}"
        except Exception as exc:  # a single unreachable source must not end the sweep
            error = f"scan_failed: {exc}"
        for row in found:
            row["source_id"] = source["id"]
            row["prospect_id"] = source["prospect_id"]
            row["company"] = source["company"]
        candidates.extend(found)
        with connect(db_path) as con:
            con.execute(
                """UPDATE hiring_signal_sources
                   SET last_scanned_at = ?, last_candidate_count = ?, last_error = ?
                   WHERE id = ?""",
                (scanned_at, -1 if error else len(found), error, source["id"]),
            )
        results.append({
            "source_id": source["id"],
            "prospect_id": source["prospect_id"],
            "company": source["company"],
            "source_url": source["source_url"],
            "label": source["label"],
            "candidate_count": None if error else len(found),
            "error": error,
            "skipped": "",
        })
    new_candidates = [row for row in candidates if not row.get("already_recorded_as")]
    stored = _store_candidates(db_path, candidates, scanned_at) if persist_candidates else 0
    return {
        "scanned_at": scanned_at,
        "persisted": bool(persist_candidates),
        "source_count": len(sources),
        "scanned_source_count": len(sources) - skipped,
        "skipped_source_count": skipped,
        "failed_source_count": sum(1 for row in results if row["error"]),
        "candidate_count": len(candidates),
        "new_candidate_count": len(new_candidates),
        "stored_candidate_count": stored,
        "sources": results,
        "candidates": candidates,
    }


def _store_candidates(db_path: str, candidates: list[dict[str, Any]], scanned_at: str) -> int:
    """Upsert candidates as pending proposals. Returns how many were new.

    A candidate the operator already recorded or dismissed must never come back as
    pending on the next sweep, so a conflict only refreshes when it was last seen —
    the status a person set is never overwritten by a machine.
    """
    if not candidates:
        return 0
    with connect(db_path) as con:
        for row in candidates:
            status = "recorded" if row.get("already_recorded_as") else "pending"
            con.execute(
                """INSERT INTO hiring_signal_candidates(
                       candidate_id, source_id, prospect_id, company, title, source_url,
                       observed_fact, commercial_interpretation, date_posted, confidence,
                       strength, freshness_half_life_days, evidence_kind, status,
                       recorded_signal_id, first_seen_at, last_seen_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(candidate_id) DO UPDATE SET last_seen_at = excluded.last_seen_at""",
                (
                    row["candidate_id"], row["source_id"], row["prospect_id"], row["company"],
                    row["title"], row["source_url"], row["observed_fact"],
                    row["commercial_interpretation"], row["date_posted"], row["confidence"],
                    row["strength"], row["freshness_half_life_days"], row["evidence_kind"],
                    status, row.get("already_recorded_as") or "", scanned_at, scanned_at,
                ),
            )
        stored = con.execute(
            "SELECT COUNT(*) FROM hiring_signal_candidates WHERE first_seen_at = ?",
            (scanned_at,),
        ).fetchone()[0]
    return stored


def pending_hiring_candidates(db_path: str, *, limit: int = 50) -> list[dict[str, Any]]:
    """Candidates a sweep found and nobody has reviewed yet."""
    init_source_store(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            """SELECT * FROM hiring_signal_candidates
               WHERE status = 'pending'
               ORDER BY strength DESC, confidence DESC, last_seen_at DESC
               LIMIT ?""",
            (max(1, min(limit, 200)),),
        ).fetchall()
    return [dict(row) for row in rows]


def set_candidate_status(db_path: str, candidate_id: str, status: str, signal_id: str = "") -> dict[str, Any]:
    if status not in {"pending", "recorded", "dismissed"}:
        raise IntelligenceError("invalid_field", "status must be pending, recorded or dismissed")
    init_source_store(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT candidate_id FROM hiring_signal_candidates WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise IntelligenceError("candidate_not_found", "Candidate does not exist")
        con.execute(
            "UPDATE hiring_signal_candidates SET status = ?, recorded_signal_id = ? WHERE candidate_id = ?",
            (status, signal_id, candidate_id),
        )
    return {"candidate_id": candidate_id, "status": status, "recorded_signal_id": signal_id}
