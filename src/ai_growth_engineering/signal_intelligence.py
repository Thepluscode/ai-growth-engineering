"""Evidence-backed signal intake, prospect eligibility, and deterministic prioritisation."""
from __future__ import annotations

import ipaddress
import math
import re
import socket
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
from html.parser import HTMLParser
from typing import Any, Mapping, Protocol
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .storage import connect, init_db


ALLOWED_SIGNAL_TYPES = frozenset(
    {
        "funding",
        "leadership_change",
        "hiring",
        "job_posting",
        "website_change",
        "technology_change",
        "compliance_event",
        "public_engagement",
        "social_intent",
        "product_launch",
        "partnership",
        "expansion",
        "custom_observed",
    }
)
ALLOWED_IDENTITY_TYPES = frozenset({"email", "linkedin", "contact_form"})
ALLOWED_VERIFICATION_STATUSES = frozenset(
    {"observed_published", "verified", "unverified", "bounced"}
)
MAX_ENRICHMENT_BYTES = 1024 * 1024
_EMAIL = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.I)


class IntelligenceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class IdentityCandidate:
    identity_type: str
    value: str
    provider: str
    verification_status: str
    source_url: str
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class EnrichmentProvider(Protocol):
    name: str

    def inspect(self, source_url: str) -> list[IdentityCandidate]: ...


def add_intent_signal(db_path: str, values: Mapping[str, Any]) -> dict[str, Any]:
    init_db(db_path)
    prospect_id = _positive_int(values.get("prospect_id"), "prospect_id")
    signal_type = _required(values, "signal_type", 3, 80).lower().replace("-", "_")
    if signal_type not in ALLOWED_SIGNAL_TYPES:
        raise IntelligenceError(
            "invalid_signal_type",
            f"signal_type must be one of {', '.join(sorted(ALLOWED_SIGNAL_TYPES))}",
        )
    source_url = _http_url(_required(values, "source_url", 8, 800), "source_url")
    observed_fact = _required(values, "observed_fact", 30, 1600)
    interpretation = _required(values, "commercial_interpretation", 30, 1600)
    if observed_fact.casefold() == interpretation.casefold():
        raise IntelligenceError(
            "fact_inference_blended", "Observed fact and commercial interpretation must differ"
        )
    observed_at = _observed_at(values.get("observed_at"))
    confidence = _bounded_float(values.get("confidence"), "confidence", 0, 1)
    strength = _bounded_int(values.get("strength"), "strength", 1, 5)
    half_life = _bounded_int(
        values.get("freshness_half_life_days"), "freshness_half_life_days", 1, 365
    )
    person_name = _optional(values, "person_name", 160)
    person_role = _optional(values, "person_role", 160)
    signal_id = f"SIG-{uuid.uuid4().hex[:12].upper()}"

    with connect(db_path) as con:
        prospect = con.execute("SELECT id FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
        if prospect is None:
            raise IntelligenceError("prospect_not_found", "Prospect does not exist")
        con.execute(
            """INSERT INTO intent_signals(
                 signal_id, prospect_id, person_name, person_role, signal_type,
                 source_url, observed_fact, commercial_interpretation, observed_at,
                 confidence, strength, freshness_half_life_days
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal_id,
                prospect_id,
                person_name,
                person_role,
                signal_type,
                source_url,
                observed_fact,
                interpretation,
                observed_at,
                confidence,
                strength,
                half_life,
            ),
        )
    return get_signal(db_path, signal_id)


def add_identity(db_path: str, values: Mapping[str, Any]) -> dict[str, Any]:
    init_db(db_path)
    prospect_id = _positive_int(values.get("prospect_id"), "prospect_id")
    identity_type = _required(values, "identity_type", 3, 40).lower().replace("-", "_")
    if identity_type not in ALLOWED_IDENTITY_TYPES:
        raise IntelligenceError("invalid_identity_type", "Unsupported identity type")
    value = _required(values, "value", 5, 800)
    if identity_type == "email" and not _EMAIL.fullmatch(value):
        raise IntelligenceError("invalid_identity", "Email identity is not valid")
    if identity_type in {"linkedin", "contact_form"}:
        value = _http_url(value, "value")
    status = _required(values, "verification_status", 3, 40).lower().replace("-", "_")
    if status not in ALLOWED_VERIFICATION_STATUSES:
        raise IntelligenceError("invalid_verification_status", "Unsupported verification status")
    provider = _required(values, "provider", 2, 120)
    source_url = _http_url(_required(values, "source_url", 8, 800), "source_url")
    observed_at = _observed_at(values.get("observed_at"))
    confidence = _bounded_float(values.get("confidence"), "confidence", 0, 1)

    with connect(db_path) as con:
        prospect = con.execute("SELECT id FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
        if prospect is None:
            raise IntelligenceError("prospect_not_found", "Prospect does not exist")
        con.execute(
            """INSERT INTO prospect_identities(
                 prospect_id, identity_type, value, provider, verification_status,
                 source_url, observed_at, confidence
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(prospect_id, identity_type, value) DO UPDATE SET
                 provider = excluded.provider,
                 verification_status = excluded.verification_status,
                 source_url = excluded.source_url,
                 observed_at = excluded.observed_at,
                 confidence = excluded.confidence""",
            (
                prospect_id,
                identity_type,
                value,
                provider,
                status,
                source_url,
                observed_at,
                confidence,
            ),
        )
        row = con.execute(
            """SELECT * FROM prospect_identities
               WHERE prospect_id = ? AND identity_type = ? AND value = ?""",
            (prospect_id, identity_type, value),
        ).fetchone()
    return dict(row)


def get_signal(db_path: str, signal_id: str) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM intent_signals WHERE signal_id = ?", (signal_id,)).fetchone()
    if row is None:
        raise IntelligenceError("signal_not_found", "Intent signal does not exist")
    return dict(row)


def intelligence_state(
    db_path: str, *, now: datetime | None = None, limit: int = 10
) -> dict[str, Any]:
    init_db(db_path)
    clock = _utc(now or datetime.now(timezone.utc))
    with connect(db_path) as con:
        prospects = con.execute(
            """SELECT id, company, website, priority, target_roles, evidence,
                      source_url, status FROM prospects ORDER BY company"""
        ).fetchall()
        signals = con.execute(
            """SELECT * FROM intent_signals
               ORDER BY observed_at DESC, created_at DESC"""
        ).fetchall()
        identities = con.execute(
            """SELECT * FROM prospect_identities
               ORDER BY CASE verification_status
                          WHEN 'verified' THEN 0
                          WHEN 'observed_published' THEN 1
                          WHEN 'unverified' THEN 2
                          ELSE 3
                        END,
                        confidence DESC, observed_at DESC"""
        ).fetchall()
        suppression = {
            row["identity"].casefold()
            for row in con.execute("SELECT identity FROM suppression").fetchall()
        }
        lineage = con.execute(
            """SELECT l.signal_id, d.id AS draft_id, d.status AS draft_status,
                      d.channel, d.recipient_identity, d.outreach_id,
                      o.meaningful_reply, o.proposal, o.paid,
                      o.collected_revenue_pence
               FROM draft_signal_lineage l
               JOIN outbound_drafts d ON d.id = l.draft_id
               LEFT JOIN outreach o ON o.id = d.outreach_id
               ORDER BY d.id DESC"""
        ).fetchall()

    by_prospect: dict[int, list[dict[str, Any]]] = {}
    for row in signals:
        by_prospect.setdefault(row["prospect_id"], []).append(dict(row))
    identities_by_prospect: dict[int, list[dict[str, Any]]] = {}
    for row in identities:
        identities_by_prospect.setdefault(row["prospect_id"], []).append(dict(row))

    ranked: list[dict[str, Any]] = []
    ineligible: list[dict[str, Any]] = []
    for row in prospects:
        prospect = dict(row)
        prospect_signals = by_prospect.get(prospect["id"], [])
        scored_signals = [
            (_signal_score(prospect, signal, clock), signal) for signal in prospect_signals
        ]
        scored_signals.sort(key=lambda item: item[0]["score"], reverse=True)
        eligible_signals = [
            (score, signal)
            for score, signal in scored_signals
            if not _signal_ineligibility_reasons(signal, score)
        ]
        best_score, best_signal = eligible_signals[0] if eligible_signals else (None, None)
        reasons = _prospect_ineligibility_reasons(prospect)
        if not prospect_signals:
            reasons.append("No observed intent event")
        elif not eligible_signals:
            reasons.extend(_signal_ineligibility_reasons(scored_signals[0][1], scored_signals[0][0]))
        if reasons:
            ineligible.append(
                {
                    "prospect_id": prospect["id"],
                    "company": prospect["company"],
                    "reasons": reasons,
                    "signal_count": len(prospect_signals),
                }
            )
            continue
        available_identities = [
            value
            for value in identities_by_prospect.get(prospect["id"], [])
            if value["verification_status"] != "bounced"
            and value["value"].casefold() not in suppression
        ]
        identity = available_identities[0] if available_identities else None
        unknowns = []
        if not identity:
            unknowns.append("No usable recipient identity has been observed or verified")
        ranked.append(
            {
                "prospect_id": prospect["id"],
                "company": prospect["company"],
                "priority_score": best_score["score"],
                "score_components": best_score,
                "icp": {
                    "pass": True,
                    "priority": prospect["priority"],
                    "target_roles": prospect["target_roles"],
                    "observed_evidence": prospect["evidence"],
                    "source_url": prospect["source_url"],
                },
                "signal": best_signal,
                "why_now": best_signal["commercial_interpretation"],
                "evidence": {
                    "observed_fact": best_signal["observed_fact"],
                    "source_url": best_signal["source_url"],
                    "observed_at": best_signal["observed_at"],
                    "confidence": best_signal["confidence"],
                },
                "unknowns": unknowns,
                "disqualifier": None,
                "suggested_angle": best_signal["commercial_interpretation"],
                "identity": identity,
                "recommended_channel": _channel(identity) if identity else "identity_research",
                "recommended_action": "prepare_approval_draft" if identity else "enrich_identity",
                "approval_required": True,
            }
        )
    ranked.sort(key=lambda value: (-value["priority_score"], value["company"]))
    lineage_by_signal: dict[str, list[dict[str, Any]]] = {}
    for row in lineage:
        lineage_by_signal.setdefault(row["signal_id"], []).append(dict(row))
    return {
        "generated_at": clock.isoformat(),
        "mode": "DETERMINISTIC / EVIDENCE BACKED / HUMAN GATED",
        "ranked_buyers": ranked[: max(1, min(limit, 100))],
        "eligible_count": len(ranked),
        "ineligible_count": len(ineligible),
        "ineligible": ineligible,
        "signals": [dict(row) for row in signals],
        "identities": [dict(row) for row in identities],
        "lineage": lineage_by_signal,
        "signal_types": sorted(ALLOWED_SIGNAL_TYPES),
        "identity_types": sorted(ALLOWED_IDENTITY_TYPES),
        "verification_statuses": sorted(ALLOWED_VERIFICATION_STATUSES),
    }


def _signal_score(
    prospect: Mapping[str, Any], signal: Mapping[str, Any], now: datetime
) -> dict[str, Any]:
    observed = _parse_datetime(signal["observed_at"])
    age_days = max(0.0, (now - observed).total_seconds() / 86400)
    half_life = int(signal["freshness_half_life_days"])
    freshness = math.pow(0.5, age_days / half_life)
    fit = {"A": 1.0, "B": 0.75}.get(str(prospect["priority"]).upper(), 0.5)
    strength = int(signal["strength"]) / 5
    confidence = float(signal["confidence"])
    return {
        "score": round(100 * fit * strength * confidence * freshness, 1),
        "fit": fit,
        "strength": round(strength, 3),
        "confidence": confidence,
        "freshness": round(freshness, 3),
        "age_days": round(age_days, 1),
    }


def _prospect_ineligibility_reasons(prospect: Mapping[str, Any]) -> list[str]:
    reasons = []
    if str(prospect["status"]).lower().startswith("disqualified"):
        reasons.append(f"Prospect status is {prospect['status']}")
    if not str(prospect["target_roles"]).strip():
        reasons.append("ICP target role is unknown")
    if not str(prospect["evidence"]).strip() or not str(prospect["source_url"]).strip():
        reasons.append("ICP evidence or its source is missing")
    return reasons


def _signal_ineligibility_reasons(
    signal: Mapping[str, Any], score: Mapping[str, Any]
) -> list[str]:
    reasons = []
    if float(signal["confidence"]) < 0.5:
        reasons.append("Signal confidence is below 0.50")
    if int(signal["strength"]) < 2:
        reasons.append("Signal strength is below 2/5")
    if score["age_days"] > int(signal["freshness_half_life_days"]) * 3:
        reasons.append("Signal is beyond three freshness half-lives")
    return reasons


def _channel(identity: Mapping[str, Any]) -> str:
    return {
        "email": "email",
        "linkedin": "linkedin",
        "contact_form": "contact_form",
    }[identity["identity_type"]]


class _IdentityHTMLParser(HTMLParser):
    def __init__(self, source_url: str):
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self.text: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(urljoin(self.source_url, href.strip()))

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def extract_public_identities(html: str, source_url: str) -> list[IdentityCandidate]:
    parser = _IdentityHTMLParser(source_url)
    parser.feed(html)
    emails = set(_EMAIL.findall(" ".join(parser.text)))
    linkedin = set()
    contact_forms = set()
    for link in parser.links:
        parsed = urlparse(link)
        if parsed.scheme == "mailto":
            address = parsed.path.split("?", 1)[0]
            if _EMAIL.fullmatch(address):
                emails.add(address)
        elif parsed.scheme in {"http", "https"} and parsed.hostname:
            host = parsed.hostname.casefold()
            if host.endswith("linkedin.com") and parsed.path.startswith("/in/"):
                linkedin.add(link)
            elif any(part in parsed.path.casefold() for part in ("contact", "enquiry", "inquiry")):
                contact_forms.add(link)
    candidates = [
        IdentityCandidate("email", value, "public_page", "observed_published", source_url, 0.75)
        for value in sorted(emails, key=str.casefold)
    ]
    candidates.extend(
        IdentityCandidate("linkedin", value, "public_page", "observed_published", source_url, 0.7)
        for value in sorted(linkedin)
    )
    candidates.extend(
        IdentityCandidate("contact_form", value, "public_page", "observed_published", source_url, 0.6)
        for value in sorted(contact_forms)
    )
    return candidates


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        _validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PublicPageEnrichmentProvider:
    name = "public_page"

    def inspect(self, source_url: str) -> list[IdentityCandidate]:
        safe_url = _validate_public_url(source_url)
        request = Request(
            safe_url,
            headers={"User-Agent": "AI-Growth-Engineering/0.1 identity-inspection"},
        )
        try:
            with build_opener(_SafeRedirectHandler()).open(request, timeout=8) as response:
                final_url = _validate_public_url(response.geturl())
                content_type = response.headers.get_content_type()
                if content_type not in {"text/html", "application/xhtml+xml"}:
                    raise IntelligenceError("unsupported_content", "Source must be an HTML page")
                body = response.read(MAX_ENRICHMENT_BYTES + 1)
        except IntelligenceError:
            raise
        except Exception as exc:
            raise IntelligenceError("enrichment_failed", f"Public page inspection failed: {exc}") from exc
        if len(body) > MAX_ENRICHMENT_BYTES:
            raise IntelligenceError("source_too_large", "Source exceeds the 1 MiB inspection limit")
        return extract_public_identities(body.decode("utf-8", errors="replace"), final_url)


def _validate_public_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise IntelligenceError("unsafe_source", "Source must be a public http(s) URL without credentials")
    if parsed.port not in {None, 80, 443}:
        raise IntelligenceError("unsafe_source", "Source port must be 80 or 443")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise IntelligenceError("source_unresolved", "Source hostname could not be resolved") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise IntelligenceError("unsafe_source", "Source hostname resolves outside the public internet")
    return value


def _parse_datetime(value: str) -> datetime:
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        if "T" not in raw and " " not in raw:
            parsed = datetime.combine(date.fromisoformat(raw), time.min, tzinfo=timezone.utc)
        else:
            parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise IntelligenceError("invalid_observed_at", "observed_at must be ISO-8601") from exc
    return _utc(parsed)


def _observed_at(value: Any) -> str:
    parsed = _parse_datetime(str(value or ""))
    if parsed > datetime.now(timezone.utc):
        raise IntelligenceError("future_observation", "observed_at cannot be in the future")
    return parsed.isoformat()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _http_url(value: str, name: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise IntelligenceError("invalid_source", f"{name} must be an http(s) URL")
    return value


def _required(values: Mapping[str, Any], name: str, minimum: int, maximum: int) -> str:
    value = str(values.get(name) or "").strip()
    if len(value) < minimum or len(value) > maximum:
        raise IntelligenceError("invalid_field", f"{name} must be {minimum}-{maximum} characters")
    return value


def _optional(values: Mapping[str, Any], name: str, maximum: int) -> str:
    value = str(values.get(name) or "").strip()
    if len(value) > maximum:
        raise IntelligenceError("invalid_field", f"{name} must be at most {maximum} characters")
    return value


def _positive_int(value: Any, name: str) -> int:
    return _bounded_int(value, name, 1, 2_147_483_647)


def _bounded_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise IntelligenceError("invalid_field", f"{name} must be an integer") from exc
    if number < minimum or number > maximum:
        raise IntelligenceError("invalid_field", f"{name} must be between {minimum} and {maximum}")
    return number


def _bounded_float(value: Any, name: str, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise IntelligenceError("invalid_field", f"{name} must be a number") from exc
    if not math.isfinite(number) or number < minimum or number > maximum:
        raise IntelligenceError("invalid_field", f"{name} must be between {minimum} and {maximum}")
    return number


# Backwards-compatible exports for the evidence-governed revenue lineage store.
from .revenue_signal_intelligence import (  # noqa: E402
    IntentSignal,
    PriorityInput,
    PriorityResult,
    ProspectEligibilityGate,
    ProspectEligibilityInput,
    freshness_weight,
    priority_score,
    recommendation_object,
    signal_record,
)
