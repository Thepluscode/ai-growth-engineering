"""The marketer: research named buyers for a product market, verify them against the public web,
and write drafts into the approval queue. It never sends.

    market + offer --research--> candidates --verify--> prospects --write--> drafts (pending approval)

The model proposes; the web decides. Every candidate must survive a check the model cannot fake:
the person's name must appear on the page it cites, the evidence quote must appear verbatim on
its page, and an email or LinkedIn route is kept only if it too appears on a fetched page. A
candidate that cannot be confirmed is rejected with a named reason, never repaired by a guess.
A person approves every draft; sending stays with them.

Every run is logged in `marketer_runs` - tokens, searches, what was proposed, drafted and why the
rest was rejected - including runs that fail, so a quiet zero is always explained.
"""
from __future__ import annotations

import html
import ipaddress
import json
import os
import re
import socket
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlparse

from . import registries
from .outbound_workbench import WorkbenchError, create_draft
from .storage import connect, init_db

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_COUNT, MAX_COUNT = 15, 25
SEARCHES_PER_PROSPECT, MAX_SEARCHES = 3, 40     # hard cost ceiling per run
MIN_QUOTE_CHARS = 20
FETCH_TIMEOUT_S, FETCH_MAX_BYTES = 15, 2_000_000
_EMAIL = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.I)
_LINKEDIN = re.compile(r"^https://([a-z]{2,3}\.)?linkedin\.com/in/[A-Za-z0-9_%-]+/?$")


@dataclass(frozen=True)
class LLMResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    web_searches: int = 0


LLM = Callable[[str, int], LLMResult]     # (prompt, max web searches) -> result
Fetch = Callable[[str], str]              # url -> page text, "" when it cannot be read


class MarketerError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- context

def market_context(db_path: str, market_id: str) -> dict:
    market = next((m for m in registries.rows(db_path, "markets") if m["market_id"] == market_id), None)
    if market is None:
        raise MarketerError("unknown_market", f"unknown market {market_id!r}")
    link = next((l for l in registries.rows(db_path, "market_experiments")
                 if l["market_id"] == market_id and l["layer"] == "DEMAND"), None)
    if link is None:
        raise MarketerError("no_demand_experiment", f"{market_id} has no DEMAND experiment to credit drafts to")
    offer = next((o for o in registries.rows(db_path, "offers") if o["offer_id"] == market.get("offer_id")), None)
    if offer is None:
        raise MarketerError("no_offer", f"{market_id} names no registered offer (offer_id)")
    forbidden = [p.strip() for p in str(market.get("forbidden_claims") or "").split(";") if p.strip()]
    return {"market": market, "experiment_id": link["experiment_id"], "offer": offer, "forbidden": forbidden}


# --------------------------------------------------------------------------- prompts

def research_prompt(ctx: dict, count: int, exclude: list[str]) -> str:
    m, o = ctx["market"], ctx["offer"]
    return f"""You are researching B2B prospects for a real outbound campaign. Accuracy matters more than volume:
a wrong name or email damages the sender. Return FEWER results rather than any you are unsure of.

Market hypothesis: {m['hypothesis']}
Buyer role: {m.get('buyer') or o['buyer']}
Geography: {m.get('geography') or 'any'}
Offer: {o['outcome']} for the problem "{o['problem']}"

Find up to {count} distinct companies that fit, each with ONE named person in the buyer role.
Exclude these companies: {', '.join(exclude) if exclude else 'none'}.

Rules:
- person_source_url must be a public page (ideally the company's own team/leadership page) where the
  person's full name AND role appear. It will be fetched and checked.
- evidence_quote must be copied VERBATIM (20-200 characters) from evidence_url and show why this
  company fits the market. It will be fetched and checked character for character.
- email: only if published verbatim on a public page; give that page as email_source_url. Otherwise "".
  Never construct or guess an email pattern.
- linkedin_url: only if it is linked from person_source_url. Otherwise "".

Reply with ONLY a JSON array, no prose:
[{{"company": "", "website": "", "person_name": "", "role": "", "person_source_url": "",
   "evidence_quote": "", "evidence_url": "", "email": "", "email_source_url": "", "linkedin_url": ""}}]"""


def draft_prompt(ctx: dict, candidate: dict) -> str:
    m, o = ctx["market"], ctx["offer"]
    forbidden = "; ".join(ctx["forbidden"]) or "none listed"
    return f"""Write a short, specific first-contact message from a UK founder to {candidate['person_name']},
{candidate['role']} at {candidate['company']}.

What we offer: {o['outcome']} (problem: {o['problem']}). Market hypothesis: {m['hypothesis']}
Verified fact about them (quoted from {candidate['evidence_url']}): "{candidate['evidence_quote']}"
Notes that bind this market: {m.get('notes') or 'none'}
Never state or imply: {forbidden}

Rules: British English. No flattery, no hype, no invented numbers. The observation is one factual
sentence grounded ONLY in the verified fact. The economic_hypothesis is one sentence framed as a
hypothesis about the business consequence, and must say something different from the observation.
The cta is one low-friction question (never ask to book a call or meeting). Subject: at most 8 words,
plain, no clickbait. metric: the outcome the offer would move, in 2-5 words.

Reply with ONLY a JSON object:
{{"subject": "", "observation": "", "economic_hypothesis": "", "cta": "", "metric": ""}}"""


# --------------------------------------------------------------------------- parsing & verification

def _json(text: str, opener: str, closer: str):
    start, end = text.find(opener), text.rfind(closer)
    if start < 0 or end <= start:
        raise MarketerError("unparseable_output", "the model returned no JSON")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise MarketerError("unparseable_output", f"the model returned invalid JSON: {exc}") from exc


def parse_candidates(text: str) -> list[dict]:
    data = _json(text, "[", "]")
    if not isinstance(data, list) or not all(isinstance(c, dict) for c in data):
        raise MarketerError("unparseable_output", "research must be a JSON array of objects")
    return data


def page_text(raw: str) -> str:
    """Visible text, unescaped, whitespace collapsed, case-folded — what a quote is checked against."""
    raw = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip().casefold()


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value))).strip().casefold()


def _http(url: str) -> bool:
    return isinstance(url, str) and url.startswith(("https://", "http://")) and bool(urlparse(url).netloc)


def verify(candidate: dict, fetch: Fetch, exclude: set[str], suppressed: set[str]) -> tuple[dict | None, str, list[str]]:
    """(verified candidate | None, rejection reason, notes). Pure given `fetch`."""
    c = {k: str(candidate.get(k) or "").strip() for k in (
        "company", "website", "person_name", "role", "person_source_url", "evidence_quote",
        "evidence_url", "email", "email_source_url", "linkedin_url")}
    for name in ("company", "person_name", "role", "person_source_url", "evidence_quote", "evidence_url"):
        if not c[name]:
            return None, f"missing_{name}", []
    if not (_http(c["person_source_url"]) and _http(c["evidence_url"])):
        return None, "invalid_source_url", []
    if c["company"].casefold() in exclude:
        return None, "duplicate_company", []
    if not MIN_QUOTE_CHARS <= len(c["evidence_quote"]) <= 400:
        return None, "quote_length", []

    raw_pages: dict[str, str] = {}

    def raw(url: str) -> str:
        """The page as served, case-folded: routes live in attributes (href, mailto:)."""
        if url not in raw_pages:
            raw_pages[url] = html.unescape(fetch(url) or "").casefold()
        return raw_pages[url]

    def text(url: str) -> str:
        """Visible text only: a name or quote hidden in a script or attribute does not count."""
        return page_text(raw(url))

    person_page = text(c["person_source_url"])
    if not person_page:
        return None, "source_unreachable", []
    if _norm(c["person_name"]) not in person_page:
        return None, "name_not_on_source", []
    evidence_page = text(c["evidence_url"])
    if not evidence_page:
        return None, "source_unreachable", []
    if _norm(c["evidence_quote"]) not in evidence_page:
        return None, "quote_not_on_source", []

    notes = []
    email = c["email"]
    if email:
        where = c["email_source_url"] if _http(c["email_source_url"]) else c["person_source_url"]
        if not (_EMAIL.fullmatch(email) and email.casefold() in raw(where)):
            notes.append("email_unverified_dropped")
            email = ""
    linkedin = c["linkedin_url"]
    if linkedin and not (_LINKEDIN.fullmatch(linkedin) and _norm(linkedin).rstrip("/") in raw(c["person_source_url"])):
        notes.append("linkedin_unverified_dropped")
        linkedin = ""
    if email and email.casefold() in suppressed:
        return None, "suppressed", notes
    if email or linkedin:
        return {**c, "email": email, "linkedin_url": linkedin, "channel": "email" if email else "linkedin",
                "recipient_identity": email or linkedin}, "", notes
    # The person and company are verified; only the profile link is not. The operator finds
    # them by name at send time and confirms it is the same person - never a guessed address.
    notes.append("route_manual_lookup")
    return {**c, "email": "", "linkedin_url": "", "channel": "linkedin",
            "recipient_identity": f"{c['person_name']} at {c['company']} (find on LinkedIn by name)"}, "", notes


def check_draft(text: str, forbidden: list[str]) -> dict:
    data = _json(text, "{", "}")
    if not isinstance(data, dict):
        raise MarketerError("unparseable_output", "a draft must be a JSON object")
    draft = {k: str(data.get(k) or "").strip() for k in ("subject", "observation", "economic_hypothesis", "cta", "metric")}
    body = " ".join(draft.values()).casefold()
    hit = next((p for p in forbidden if p.casefold() in body), None)
    if hit:
        raise MarketerError("forbidden_claim", f"draft contains a forbidden claim: {hit!r}")
    return draft


# --------------------------------------------------------------------------- the run

@dataclass
class _Tally:
    input_tokens: int = 0
    output_tokens: int = 0
    web_searches: int = 0
    rejections: Counter = field(default_factory=Counter)

    def add(self, result: LLMResult) -> str:
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens
        self.web_searches += result.web_searches
        return result.text


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(db_path: str, market_id: str, *, llm: LLM, fetch: Fetch, count: int = DEFAULT_COUNT,
        dry_run: bool = False, model: str = DEFAULT_MODEL, allow_paid: bool = False) -> dict:
    """Research with the model, then verify and draft. The expensive step is the research: the
    first live run spent 33 searches and 1.43M input tokens for two unusable candidates. It
    therefore never starts without an explicit opt-in."""
    if not allow_paid:
        raise MarketerError("paid_research_not_allowed",
                            "model web research spends API credit (first run: ~1.4M tokens for 0 drafts); "
                            "research in-session and use `import`, or pass --paid deliberately")
    count = max(1, min(MAX_COUNT, int(count)))
    searches = min(MAX_SEARCHES, count * SEARCHES_PER_PROSPECT)

    def research(ctx, exclude, tally):
        return parse_candidates(tally.add(llm(research_prompt(ctx, count, sorted(exclude)[:200]), searches)))[:count]

    return _pipeline(db_path, market_id, research, llm=llm, fetch=fetch, requested=count,
                     dry_run=dry_run, model=model)


def import_candidates(db_path: str, market_id: str, candidates: list[dict], *, llm: LLM | None, fetch: Fetch,
                      dry_run: bool = False, model: str = DEFAULT_MODEL) -> dict:
    """Candidates researched elsewhere (a person, an assistant, another session) go through exactly
    the same verification and drafting as the model's own. The source never lowers the bar.

    A candidate may carry its own `draft` ({subject, observation, economic_hypothesis, cta, metric});
    it is checked exactly as a model-written one and costs nothing. Without `llm`, a candidate
    with no draft is rejected rather than silently spending credit."""
    if not isinstance(candidates, list) or not all(isinstance(c, dict) for c in candidates):
        raise MarketerError("invalid_import", "import must be a JSON array of candidate objects")
    candidates = candidates[:MAX_COUNT]
    return _pipeline(db_path, market_id, lambda ctx, exclude, tally: candidates, llm=llm, fetch=fetch,
                     requested=len(candidates), dry_run=dry_run, model=f"import+{model}")


def _pipeline(db_path, market_id, research, *, llm, fetch, requested, dry_run, model) -> dict:
    init_db(db_path)
    ctx = market_context(db_path, market_id)
    with connect(db_path) as con:
        exclude = {r["company"].casefold() for r in con.execute("SELECT company FROM prospects")}
        suppressed = {r["identity"].casefold() for r in con.execute("SELECT identity FROM suppression")}
        run_id = con.execute(
            """INSERT INTO marketer_runs(market_id, experiment_id, model, requested, dry_run, started_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (market_id, ctx["experiment_id"], model, requested, int(dry_run), _now())).lastrowid

    tally, drafts, previews, proposed, error, seen = _Tally(), [], [], 0, "", []
    try:
        candidates = research(ctx, exclude, tally)
        proposed = len(candidates)
        for candidate in candidates:
            verified, reason, notes = verify(candidate, fetch, exclude, suppressed)
            tally.rejections.update(notes)
            outcome, draft_id = reason, None
            if verified is not None:
                try:
                    supplied = candidate.get("draft")
                    if isinstance(supplied, dict):
                        draft = check_draft(json.dumps(supplied), ctx["forbidden"])
                    elif llm is None:
                        raise MarketerError("draft_missing", "no draft supplied and no model allowed")
                    else:
                        draft = check_draft(tally.add(llm(draft_prompt(ctx, verified), 0)), ctx["forbidden"])
                    exclude.add(verified["company"].casefold())
                    if dry_run:
                        previews.append({"company": verified["company"], "person": verified["person_name"],
                                         "channel": verified["channel"], **draft})
                        outcome = "previewed"
                    else:
                        draft_id = _store(db_path, ctx, verified, draft)
                        drafts.append(draft_id)
                        outcome = "drafted"
                except (MarketerError, WorkbenchError) as exc:
                    outcome = exc.code
            if outcome not in ("drafted", "previewed"):
                tally.rejections[outcome] += 1
            seen.append((run_id, str(candidate.get("company") or ""), str(candidate.get("person_name") or ""),
                         outcome, str(candidate.get("person_source_url") or ""),
                         str(candidate.get("evidence_url") or ""), draft_id))
    except MarketerError as exc:
        error = f"{exc.code}: {exc}"
    except Exception as exc:                        # recorded, then surfaced by the caller
        error = f"{type(exc).__name__}: {exc}"
    finally:
        with connect(db_path) as con:
            con.executemany(
                """INSERT INTO marketer_candidates(run_id, company, person_name, outcome, person_source_url,
                     evidence_url, draft_id) VALUES (?, ?, ?, ?, ?, ?, ?)""", seen)
            con.execute(
                """UPDATE marketer_runs SET proposed=?, drafted=?, rejections_json=?, input_tokens=?,
                     output_tokens=?, web_searches=?, error=?, finished_at=? WHERE id=?""",
                (proposed, len(drafts), json.dumps(dict(tally.rejections), sort_keys=True), tally.input_tokens,
                 tally.output_tokens, tally.web_searches, error, _now(), run_id))
    return {"run_id": run_id, "market_id": market_id, "experiment_id": ctx["experiment_id"], "requested": requested,
            "proposed": proposed, "drafted": len(drafts), "draft_ids": drafts, "previews": previews,
            "rejections": dict(tally.rejections), "input_tokens": tally.input_tokens,
            "output_tokens": tally.output_tokens, "web_searches": tally.web_searches,
            "dry_run": dry_run, "error": error}


def candidates_of(db_path: str, run_id: int) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        return [dict(r) for r in con.execute("SELECT * FROM marketer_candidates WHERE run_id = ? ORDER BY id", (run_id,))]


def _store(db_path: str, ctx: dict, c: dict, draft: dict) -> int:
    with connect(db_path) as con:
        prospect_id = con.execute(
            """INSERT INTO prospects(company, website, priority, target_roles, evidence, source_url, status)
               VALUES (?, ?, 'B', ?, ?, ?, 'researched_verified')""",
            (c["company"], c["website"], f"{c['person_name']} ({c['role']})", c["evidence_quote"],
             c["evidence_url"])).lastrowid
    first = c["person_name"].split()[0]
    return create_draft(db_path, {
        "prospect_id": prospect_id, "recipient_identity": c["recipient_identity"],
        "recipient_class": "named_buyer", "channel": c["channel"],
        "observation": f"Hi {first},\n\n{draft['observation']}", "economic_hypothesis": draft["economic_hypothesis"],
        "cta": draft["cta"], "metric": draft["metric"] or "qualified conversations",
        "source_url": c["evidence_url"], "experiment_id": ctx["experiment_id"], "subject": draft["subject"],
    })["id"]


def runs(db_path: str, limit: int = 20) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        return [dict(r) for r in con.execute("SELECT * FROM marketer_runs ORDER BY id DESC LIMIT ?", (limit,))]


def gmail_payloads(db_path: str) -> list[dict]:
    """Approved email drafts, shaped for a Gmail draft. The mailbox is written by the Gmail
    connector, never from here; the person still presses Send."""
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute("""SELECT id, recipient_identity, subject, message FROM outbound_drafts
                              WHERE status = 'approved' AND channel = 'email' ORDER BY id""").fetchall()
    return [{"draft_id": r["id"], "to": r["recipient_identity"], "subject": r["subject"] or "Quick question",
             "body": r["message"]} for r in rows]


# --------------------------------------------------------------------------- real adapters

def fetch_page(url: str) -> str:
    """Public http(s) page text, or "" — never a private or loopback address (the URL came from a model)."""
    if not _http(url):
        return ""
    try:
        host = urlparse(url).hostname or ""
        for info in socket.getaddrinfo(host, None):
            address = ipaddress.ip_address(info[4][0])
            if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
                return ""
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (ThePlus marketer verifier)"})
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_S) as response:
            return response.read(FETCH_MAX_BYTES).decode(response.headers.get_content_charset() or "utf-8", "replace")
    except Exception:
        return ""                                    # unreachable is a rejection reason, counted by the run


def claude_llm(model: str = "", timeout: float = 180.0) -> LLM:
    """The model behind the marketer. Needs ANTHROPIC_API_KEY; nothing else imports the SDK."""
    import anthropic

    client = anthropic.Anthropic(timeout=timeout, max_retries=2)
    model = model or os.environ.get("AGE_MARKETER_MODEL", DEFAULT_MODEL)

    def call(prompt: str, max_searches: int) -> LLMResult:
        tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}] if max_searches else []
        messages = [{"role": "user", "content": prompt}]
        text, tin, tout, searches = [], 0, 0, 0
        for _ in range(4):                          # server tools may pause a long turn
            msg = client.messages.create(model=model, max_tokens=8000, messages=messages,
                                         **({"tools": tools} if tools else {}))
            tin += msg.usage.input_tokens
            tout += msg.usage.output_tokens
            server = getattr(msg.usage, "server_tool_use", None)
            searches += int(getattr(server, "web_search_requests", 0) or 0)
            text.extend(b.text for b in msg.content if b.type == "text")
            if msg.stop_reason != "pause_turn":
                break
            messages = [*messages, {"role": "assistant", "content": msg.content}]
        return LLMResult("".join(text), tin, tout, searches)

    return call
