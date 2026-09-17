from __future__ import annotations

import csv
import json
from dataclasses import asdict

from .models import Evidence, ExperimentDecision, ExperimentSpec
from .storage import connect, init_db


def add_evidence(db_path: str, evidence: Evidence) -> None:
    evidence.validate()
    with connect(db_path) as con:
        con.execute(
            """INSERT INTO evidence(
                 evidence_id, kind, statement, source, confidence, observed,
                 inference, observed_at, commercial_implication, metadata_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                evidence.evidence_id,
                evidence.kind.value,
                evidence.statement,
                evidence.source,
                evidence.confidence,
                int(evidence.observed),
                evidence.inference,
                evidence.observed_at,
                evidence.commercial_implication,
                json.dumps(evidence.metadata, sort_keys=True),
            ),
        )


def add_experiment(db_path: str, spec: ExperimentSpec) -> None:
    spec.validate()
    with connect(db_path) as con:
        if spec.evidence_ids:
            placeholders = ",".join("?" for _ in spec.evidence_ids)
            count = con.execute(
                f"SELECT COUNT(*) FROM evidence WHERE evidence_id IN ({placeholders})",
                spec.evidence_ids,
            ).fetchone()[0]
            if count != len(set(spec.evidence_ids)):
                raise ValueError("all referenced evidence_ids must exist")
        con.execute(
            """INSERT INTO experiments(
                 experiment_id, hypothesis, primary_metric, success_threshold,
                 review_threshold, minimum_sample, market, buyer, problem, channel,
                 control, variant, secondary_metrics, economic_metric, budget_pence,
                 start_date, end_date, learning, variable
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                spec.experiment_id,
                spec.hypothesis,
                spec.primary_metric,
                spec.success_threshold,
                spec.review_threshold,
                spec.minimum_sample,
                spec.market,
                spec.buyer,
                spec.problem,
                spec.channel,
                spec.control,
                spec.variant,
                "; ".join(spec.secondary_metrics),
                spec.economic_metric,
                spec.budget_pence,
                spec.start_date,
                spec.end_date,
                spec.learning,
                spec.variable,
            ),
        )
        con.executemany(
            "INSERT INTO experiment_evidence(experiment_id, evidence_id) VALUES (?, ?)",
            ((spec.experiment_id, evidence_id) for evidence_id in spec.evidence_ids),
        )


def record_experiment_result(
    db_path: str,
    experiment_id: str,
    sample_size: int,
    observed_value: float,
    learning: str = "",
) -> str:
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)).fetchone()
        if row is None:
            raise ValueError("experiment not found")
        if sample_size < 0:
            raise ValueError("sample_size cannot be negative")
        if sample_size < row["minimum_sample"]:
            # A partial sample is evidence-in-progress, not a failed or invalid test.
            # EXP-ACQ-0001 explicitly forbids a final conclusion before 50 sends.
            decision = ExperimentDecision.PREREGISTERED.value
        elif observed_value >= row["success_threshold"]:
            # The primary metric won. That earns a KEEP only if trust held: a conversion
            # lift bought with unsubscribes, complaints or refunds is a cost deferred to a
            # quarter where nobody connects it back. Non-compensatory by construction —
            # no amount of primary-metric success offsets a breach.
            verdict = trust_verdict(db_path, experiment_id)
            if verdict.passed:
                decision = ExperimentDecision.KEEP.value
            elif verdict.pending:
                # Missing or underpowered guardrail data is not permission to conclude.
                decision = ExperimentDecision.PREREGISTERED.value
            else:
                # A breach hands the decision to a person; it never kills the business.
                decision = ExperimentDecision.REVIEW.value
            learning = "; ".join(filter(None, [learning, *verdict.reasons]))
        elif observed_value < row["review_threshold"]:
            decision = ExperimentDecision.REVIEW.value
        else:
            decision = ExperimentDecision.ITERATE.value
        con.execute(
            """UPDATE experiments
               SET sample_size=?, observed_value=?, decision=?, learning=?
               WHERE experiment_id=?""",
            (sample_size, observed_value, decision, learning, experiment_id),
        )
        return decision


EXECUTION_MODES = ("PREREGISTERED", "DESCRIPTIVE_FROZEN_COHORT")


def set_execution_mode(db_path: str, experiment_id: str, mode: str, reason: str) -> None:
    """Record how a frozen experiment is being run. The hypothesis, thresholds and sample stay
    exactly as preregistered; a descriptive execution only stops them being claimed."""
    if mode not in EXECUTION_MODES:
        raise ValueError(f"execution mode must be one of {EXECUTION_MODES}")
    if not reason.strip():
        raise ValueError("an execution mode needs the reason it was chosen")
    init_db(db_path)
    with connect(db_path) as con:
        updated = con.execute(
            "UPDATE experiments SET execution_mode = ?, execution_mode_reason = ? WHERE experiment_id = ?",
            (mode, reason.strip(), experiment_id))
        if updated.rowcount == 0:
            raise ValueError(f"experiment {experiment_id} not found")


VARIABLE_METADATA_SOURCES = ("declared_at_registration", "retrospective_from_preregistration")


def backfill_variable(db_path: str, experiment_id: str, variable: str, source: str, note: str) -> dict:
    """Make an already-declared design explicit. Writes only the variable and where it came from:
    never over a variable already declared, never the hypothesis, thresholds, cohort or outcomes."""
    from .models import TEST_VARIABLES

    if variable not in TEST_VARIABLES:
        raise ValueError(f"variable must be one of {sorted(TEST_VARIABLES)}")
    if source not in VARIABLE_METADATA_SOURCES:
        raise ValueError(f"source must be one of {VARIABLE_METADATA_SOURCES}")
    if not note.strip():
        raise ValueError("a backfilled variable needs a note saying what it was derived from")
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute("SELECT variable FROM experiments WHERE experiment_id = ?", (experiment_id,)).fetchone()
        if row is None:
            raise ValueError(f"experiment {experiment_id} not found")
        if row["variable"]:
            raise ValueError(f"{experiment_id} already declares {row['variable']!r}; a declared variable is never overwritten")
        con.execute(
            """UPDATE experiments SET variable = ?, variable_metadata_source = ?, variable_metadata_note = ?
               WHERE experiment_id = ? AND variable = ''""",
            (variable, source, note.strip(), experiment_id))
    return {"experiment_id": experiment_id, "variable": variable, "variable_metadata_source": source}


def _seed_experiment(db_path: str, record: dict) -> bool:
    """Restore a frozen experiment and the metadata recorded about it. Fills only what is missing:
    an existing contract is never rewritten, and metadata never overwrites a value already set."""
    from dataclasses import fields as dataclass_fields

    names = {f.name for f in dataclass_fields(ExperimentSpec)}
    experiment_id = record["experiment_id"]
    read = "SELECT * FROM experiments WHERE experiment_id = ?"
    with connect(db_path) as con:
        exists = con.execute(read, (experiment_id,)).fetchone() is not None
    if not exists:
        add_experiment(db_path, ExperimentSpec(**{k: tuple(v) if isinstance(v, list) else v
                                                   for k, v in record.items() if k in names}))
    changed = not exists
    with connect(db_path) as con:
        row = con.execute(read, (experiment_id,)).fetchone()
        if record.get("execution_mode") and not row["execution_mode"]:
            if record["execution_mode"] not in EXECUTION_MODES:
                raise ValueError(f"{experiment_id}: unknown execution mode {record['execution_mode']!r}")
            con.execute("UPDATE experiments SET execution_mode = ?, execution_mode_reason = ? WHERE experiment_id = ?",
                        (record["execution_mode"], record.get("execution_mode_reason", ""), experiment_id))
            changed = True
        if record.get("variable_metadata_source") and not row["variable_metadata_source"]:
            if record["variable_metadata_source"] not in VARIABLE_METADATA_SOURCES:
                raise ValueError(f"{experiment_id}: unknown variable metadata source")
            if row["variable"] != record.get("variable"):
                raise ValueError(f"{experiment_id}: stored variable {row['variable']!r} does not match the seed's "
                                 f"{record.get('variable')!r}; a declared variable is never overwritten")
            con.execute("UPDATE experiments SET variable_metadata_source = ?, variable_metadata_note = ? "
                        "WHERE experiment_id = ?",
                        (record["variable_metadata_source"], record.get("variable_metadata_note", ""), experiment_id))
            changed = True
    return changed


def seed_prospects(db_path: str, csv_path: str) -> int:
    count = 0
    with open(csv_path, newline="", encoding="utf-8") as handle, connect(db_path) as con:
        reader = csv.DictReader(handle)
        for row in reader:
            con.execute(
                """INSERT INTO prospects(
                     company, website, priority, target_roles, evidence, source_url, status
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(company) DO UPDATE SET
                     website=excluded.website,
                     priority=excluded.priority,
                     target_roles=excluded.target_roles,
                     evidence=excluded.evidence,
                     source_url=excluded.source_url,
                     status=excluded.status""",
                (
                    row["company"], row.get("website", ""), row.get("priority", "B"),
                    row.get("target_roles", ""), row.get("evidence", ""),
                    row.get("source_url", ""), row.get("status", "research"),
                ),
            )
            count += 1
    return count


def import_outreach(db_path: str, csv_path: str) -> tuple[int, int]:
    """Load a sent-outreach log into the store. Returns (imported, skipped).

    Sends get recorded in the experiment's CSV as they happen; the scoreboard reads the
    store. Without this the scoreboard reports zero outreach while ten messages are out,
    which reads as a commercial blocker that does not exist.

    Idempotent on (company, sent_at) so re-running cannot inflate the count.
    """
    imported = skipped = 0
    with open(csv_path, newline="", encoding="utf-8") as handle, connect(db_path) as con:
        for row in csv.DictReader(handle):
            company = (row.get("company") or "").strip()
            sent_at = (row.get("date_first_contact") or "").strip()
            if not company or not sent_at:
                skipped += 1
                continue
            exists = con.execute(
                "SELECT 1 FROM outreach WHERE company = ? AND sent_at = ?", (company, sent_at)
            ).fetchone()
            if exists:
                skipped += 1
                continue
            reply = (row.get("meaningful_reply") or "").strip().lower()
            con.execute(
                """INSERT INTO outreach(company, sent_at, meaningful_reply, notes, stage, recipient_class, channel)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    company,
                    sent_at,
                    1 if reply in {"1", "true", "yes"} else 0,
                    (row.get("notes") or "").strip(),
                    (row.get("stage") or "sent_awaiting_reply").strip(),
                    parse_recipient_class(row.get("recipient_class"), company),
                    (row.get("channel") or "unknown").strip().lower() or "unknown",
                ),
            )
            imported += 1
    return imported, skipped


RECIPIENT_CLASSES = ("named_buyer", "role_inbox", "unclassified")


def parse_recipient_class(value: str | None, company: str = "") -> str:
    """Who the message actually reached, taken from the row rather than guessed.

    EXP-ACQ-0001 recorded 50 "qualified sends" and concluded REVIEW at 0 replies.
    48 of them had gone to info@, contact@, enquiries@ and the like; two reached a
    named buyer. The blended rate answered a question nobody asked, and at n=2 the
    route that mattered was never tested at all.

    An unrecognised value raises rather than falling back to a default. A silent
    fallback is how a typo becomes an entire class of sends nobody can find again.
    """
    text = (value or "").strip().lower().replace("-", "_") or "unclassified"
    if text not in RECIPIENT_CLASSES:
        raise ValueError(
            f"unknown recipient_class {value!r}"
            + (f" for {company}" if company else "")
            + f"; expected one of {', '.join(RECIPIENT_CLASSES)}"
        )
    return text


def reply_rate_by_route(db_path: str) -> dict[str, dict[str, int]]:
    """Delivered sends and replies per route, where a route is channel + recipient class.

    Keyed "channel/recipient_class" because those are the two ways a reply rate has
    already been wrong here. EXP-ACQ-0001 blended a named buyer with 48 shared inboxes
    and read the result as a market answer; EXP-ACQ-0002's discovery then proposed
    LinkedIn as the replacement route, which would have blended two channels the same
    way. Neither split can be recovered after the fact from a stored rate.

    Bounces are excluded on the same grounds as in `scoreboard`: a message that did not
    arrive is not a send. `unclassified` and `unknown` appear as their own routes rather
    than being folded into a real one, because "we do not know" is a finding.
    """
    routes: dict[str, dict[str, int]] = {}
    with connect(db_path) as con:
        rows = con.execute(
            """SELECT COALESCE(NULLIF(channel, ''), 'unknown') AS channel,
                      COALESCE(NULLIF(recipient_class, ''), 'unclassified') AS recipient_class,
                      COUNT(*) AS sent,
                      COALESCE(SUM(meaningful_reply), 0) AS replies
               FROM outreach
               WHERE sent_at IS NOT NULL AND stage != 'bounced'
               GROUP BY channel, recipient_class"""
        ).fetchall()
    for row in rows:
        routes[f"{row['channel']}/{row['recipient_class']}"] = {
            "sent": row["sent"],
            "replies": row["replies"],
        }
    return routes


# The revenue gate's counters that the canonical event log can compute. Where the log exists it
# is the figure; the legacy `outreach` counter is kept and shown beside it as an annotation.
CANONICAL_COUNTERS = ("outreach_sent", "meaningful_responses", "discovery_calls", "commercial_proposals",
                      "paying_customers", "collected_revenue_pence")
REGISTRY_COUNTERS = ("qualified_prospects", "unreviewed_prospects")


def _canonical_counters(db_path: str) -> dict[str, int] | None:
    from .funnel_events import effective_events
    from .revenue_loop import entity, totals, undelivered_units

    events = effective_events(db_path)
    if not events:
        return None
    undelivered = undelivered_units(events)

    def reached(event_type: str) -> set[tuple[str, str]]:
        return {(entity(e), e["experiment_id"]) for e in events if e["event_type"] == event_type}

    return {
        "outreach_sent": len(reached("message_sent") - undelivered),
        "meaningful_responses": len(reached("reply_meaningful")),
        "discovery_calls": len(reached("meeting_held")),
        "commercial_proposals": len(reached("proposal_sent")),
        "paying_customers": len({entity(e) for e in events if e["event_type"] == "payment_received"}),
        "collected_revenue_pence": totals(e for e in events if e["event_type"] in ("payment_received", "refund"))["revenue_pence"],
    }


def scoreboard_basis(db_path: str) -> list[dict]:
    """Every gate counter with where its number came from: COMPUTED from canonical events, REGISTRY,
    or MANUAL_ANNOTATION — and, where a hand-set counter exists beside a computed one, whether they agree."""
    legacy = _legacy_counters(db_path)
    computed = _canonical_counters(db_path)
    rows = []
    for metric, manual in legacy.items():
        if metric in REGISTRY_COUNTERS:
            rows.append({"metric": metric, "value": manual, "basis": "REGISTRY", "manual": None, "diverges": False})
        elif metric in CANONICAL_COUNTERS and computed is not None:
            value = computed[metric]
            rows.append({"metric": metric, "value": value, "basis": "COMPUTED", "manual": manual,
                         "diverges": manual != value})
        else:
            rows.append({"metric": metric, "value": manual, "basis": "MANUAL_ANNOTATION", "manual": manual,
                         "diverges": False})
    return rows


def scoreboard(db_path: str) -> dict[str, int]:
    return {row["metric"]: row["value"] for row in scoreboard_basis(db_path)}


def _legacy_counters(db_path: str) -> dict[str, int]:
    with connect(db_path) as con:
        return {
            # A prospect counts as qualified only when it SAYS it is qualified.
            #
            # This read `NOT LIKE 'disqualified%'`, which made qualification the default
            # and every other state qualified by omission. On 2026-09-08 that counted 10
            # rows nobody had qualified — 5 `research`, 5 `ready_for_deep_research` — and
            # reported 51 where the qualified figure was 41. The danger is not those 10:
            # it is that any later import using `candidate`, `pending`, `unreviewed`,
            # `borderline` or `unknown` would inflate a VERIFIED number without a person
            # deciding anything, which is the false validation this scoreboard exists to
            # prevent.
            "qualified_prospects": con.execute(
                "SELECT COUNT(*) FROM prospects WHERE status LIKE 'qualified%'"
            ).fetchone()[0],
            # Reported beside it so the pipeline stays visible. Without this the
            # correction reads as accounts having vanished, rather than as accounts that
            # were never qualified in the first place.
            "unreviewed_prospects": con.execute(
                """SELECT COUNT(*) FROM prospects
                   WHERE status NOT LIKE 'qualified%' AND status NOT LIKE 'disqualified%'"""
            ).fetchone()[0],
            "outreach_sent": con.execute(
                "SELECT COUNT(*) FROM outreach WHERE sent_at IS NOT NULL AND stage != 'bounced'"
            ).fetchone()[0],
            "meaningful_responses": con.execute("SELECT COALESCE(SUM(meaningful_reply),0) FROM outreach").fetchone()[0],
            "discovery_calls": con.execute("SELECT COALESCE(SUM(discovery),0) FROM outreach").fetchone()[0],
            "diagnostics_proposed": con.execute("SELECT COALESCE(SUM(diagnostic_proposed),0) FROM outreach").fetchone()[0],
            "commercial_proposals": con.execute("SELECT COALESCE(SUM(proposal),0) FROM outreach").fetchone()[0],
            "paying_customers": con.execute("SELECT COALESCE(SUM(paid),0) FROM outreach").fetchone()[0],
            "collected_revenue_pence": con.execute("SELECT COALESCE(SUM(collected_revenue_pence),0) FROM outreach").fetchone()[0],
        }


SOURCING_STEPS = (
    ("website_evidence_rate", "Register candidate to website-evidenced", "website_evidenced", "raw_candidates"),
    ("qualification_rate", "Website-evidenced to QUALIFIED", "qualified", "website_evidenced"),
    ("identity_rate", "QUALIFIED to LinkedIn identity", "identity_resolved", "qualified"),
)


def record_sourcing_run(db_path: str, values) -> dict:
    """Persist one sourcing run's stage counts.

    Stored per run rather than globally because the sourcing rates are only meaningful
    within the cohort they were measured on. Dividing a batch's qualified count by the
    portfolio's website-evidenced count would invent a denominator, which is the defect
    `funnel_rates` already exists to prevent one step further down the funnel.
    """
    init_db(db_path)
    counts = {k: int(values[k]) for k in
              ("raw_candidates", "website_evidenced", "qualified", "borderline",
               "rejected", "identity_resolved")}
    if counts["website_evidenced"] > counts["raw_candidates"]:
        raise ValueError("website_evidenced cannot exceed raw_candidates")
    reviewed = counts["qualified"] + counts["borderline"] + counts["rejected"]
    if reviewed and reviewed != counts["website_evidenced"]:
        raise ValueError(
            f"qualified+borderline+rejected ({reviewed}) must account for every "
            f"website_evidenced candidate ({counts['website_evidenced']})")
    if counts["identity_resolved"] > counts["qualified"]:
        raise ValueError("identity_resolved cannot exceed qualified")
    with connect(db_path) as con:
        con.execute(
            """INSERT INTO sourcing_runs(run_id, ran_at, source, raw_candidates,
                 website_evidenced, qualified, borderline, rejected, identity_resolved, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(run_id) DO UPDATE SET
                 ran_at=excluded.ran_at, source=excluded.source,
                 raw_candidates=excluded.raw_candidates,
                 website_evidenced=excluded.website_evidenced,
                 qualified=excluded.qualified, borderline=excluded.borderline,
                 rejected=excluded.rejected, identity_resolved=excluded.identity_resolved,
                 notes=excluded.notes""",
            (str(values["run_id"]), str(values["ran_at"]), str(values.get("source", "")),
             counts["raw_candidates"], counts["website_evidenced"], counts["qualified"],
             counts["borderline"], counts["rejected"], counts["identity_resolved"],
             str(values.get("notes", ""))),
        )
    return sourcing_funnel(db_path, run_id=str(values["run_id"]))


def sourcing_funnel(db_path: str, run_id: str | None = None) -> dict:
    """Register-to-identity conversion for one run, denominators kept honest.

    A zero denominator yields `rate: None`, never 0.0 — the same rule the commercial
    funnel uses, for the same reason: nothing asked is not the same as nothing returned.
    """
    init_db(db_path)
    with connect(db_path) as con:
        if run_id is None:
            row = con.execute(
                "SELECT * FROM sourcing_runs ORDER BY ran_at DESC, run_id DESC LIMIT 1"
            ).fetchone()
        else:
            row = con.execute("SELECT * FROM sourcing_runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        return {"run_id": None, "steps": [], "compound_rate": None}
    counts = dict(row)
    steps = []
    for key, label, num_key, den_key in SOURCING_STEPS:
        num, den = counts[num_key], counts[den_key]
        steps.append({"key": key, "label": label, "numerator": num, "denominator": den,
                      "numerator_label": num_key, "denominator_label": den_key,
                      "rate": None if den == 0 else num / den, "observed": den > 0})
    compound = (None if counts["raw_candidates"] == 0
                else counts["identity_resolved"] / counts["raw_candidates"])
    return {"run_id": counts["run_id"], "source": counts["source"], "counts": counts,
            "steps": steps, "compound_rate": compound}


def claim_publication_check(db_path: str, claim_id: str):
    """Look up a registered claim and its evidence, then apply ClaimPublicationGate.

    Kept here rather than in policies.py so the policy layer stays pure and testable
    without a database.
    """
    from .policies import ClaimPublicationGate, PolicyDecision

    with connect(db_path) as con:
        claim = con.execute(
            "SELECT status, evidence_id FROM claims WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        if claim is None:
            return PolicyDecision(False, False, ("claim_not_registered",))
        evidence = con.execute(
            "SELECT confidence, observed FROM evidence WHERE evidence_id = ?",
            (claim["evidence_id"],),
        ).fetchone()

    return ClaimPublicationGate.evaluate(
        claim_status=claim["status"],
        evidence_confidence=None if evidence is None else evidence["confidence"],
        evidence_observed=True if evidence is None else bool(evidence["observed"]),
    )


def seed_registries(db_path: str, seeds_path: str) -> dict[str, int]:
    """Load registry rows from their source file into the store.

    The store under .age/ is gitignored and rebuildable. Rows inserted ad hoc exist
    only there and are destroyed by the next rebuild — which has already happened
    once. Anything worth keeping belongs in the seed file and arrives through here.

    Idempotent: re-running inserts nothing and reports zero.
    """
    import json

    from . import registries as _registries
    from .models import Evidence, EvidenceKind

    with open(seeds_path, encoding="utf-8") as handle:
        data = json.load(handle)

    loaded: dict[str, int] = {}

    for record in data.get("evidence", []):
        with connect(db_path) as con:
            exists = con.execute(
                "SELECT 1 FROM evidence WHERE evidence_id = ?", (record["evidence_id"],)
            ).fetchone()
        if exists:
            continue
        add_evidence(db_path, Evidence(
            evidence_id=record["evidence_id"],
            kind=EvidenceKind(record["kind"]),
            statement=record["statement"],
            source=record["source"],
            confidence=float(record["confidence"]),
            observed=bool(record.get("observed", True)),
        ))
        loaded["evidence"] = loaded.get("evidence", 0) + 1

    # Experiments live only in the rebuildable store unless they are seeded, and a frozen
    # contract lost on rebuild takes its retrospective metadata with it.
    for record in data.get("experiments", []):
        if _seed_experiment(db_path, record):
            loaded["experiments"] = loaded.get("experiments", 0) + 1

    for name in _registries.REGISTRIES:
        rows = data.get(name)
        if not rows:
            continue
        pk = _registries.REGISTRIES[name][0]
        for record in rows:
            with connect(db_path) as con:
                exists = con.execute(
                    f"SELECT 1 FROM {name} WHERE {pk} = ?", (record[pk],)
                ).fetchone()
            if exists:
                continue
            _registries.add(db_path, name, record)
            loaded[name] = loaded.get(name, 0) + 1

    # Signal sources belong here for the same reason every other row does: a source
    # added ad hoc lives only in .age/ and is destroyed by the next rebuild, which
    # would leave the scheduled sweep quietly reading nothing.
    sources = data.get("hiring_sources", [])
    if sources:
        from .hiring_signal_connector import IntelligenceError as _Error, add_hiring_source
        with connect(db_path) as con:
            prospect_count = con.execute("SELECT COUNT(*) FROM prospects").fetchone()[0]
        # No prospects yet means this store has not been given any — `make demo` seeds
        # prospects first. That is a deferral, and it is reported rather than hidden.
        if not prospect_count:
            loaded["hiring_sources_awaiting_prospects"] = len(sources)
            sources = []
    for record in sources:
        with connect(db_path) as con:
            prospect = con.execute(
                "SELECT id FROM prospects WHERE company = ?", (record["company"],)
            ).fetchone()
        if prospect is None:
            # Prospects exist and this company is not among them: a defect in the seed
            # file, not a row to drop quietly — skipping it silently leaves a scheduled
            # sweep reading nothing, with no error to explain why.
            raise ValueError(
                f"hiring source names a company that is not a prospect: {record['company']!r}"
            )
        try:
            add_hiring_source(db_path, {
                "prospect_id": prospect["id"],
                "source_url": record["source_url"],
                "label": record.get("label", ""),
            })
        except _Error as exc:
            if exc.code != "duplicate_source":
                raise
            continue
        loaded["hiring_sources"] = loaded.get("hiring_sources", 0) + 1

    return loaded


def preregister_trust_guardrails(
    db_path: str, experiment_id: str, specs: list
) -> int:
    """Declare guardrails BEFORE exposure begins.

    Refuses to change a frozen field once the experiment has observations. Raising the
    complaint cap from 0.2% to 1.0% after seeing 0.8% is moving a Sharpe threshold after
    a backtest; the correct move is a new experiment, not an edited one.
    """
    from .trust import TrustGuardrailSpec

    with connect(db_path) as con:
        policy = _trust_policy(con, experiment_id)
        _refuse_if_treated(policy)
        if policy["state"] == "NOT_APPLICABLE":
            raise ValueError(f"{experiment_id} declared trust NOT_APPLICABLE; a policy is one or the other")

        has_observations = con.execute(
            "SELECT COUNT(*) FROM experiment_trust_results WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()[0] > 0

        written = 0
        for spec in specs:
            spec.validate()
            existing = con.execute(
                "SELECT * FROM experiment_trust_guardrails WHERE experiment_id=? AND metric=?",
                (experiment_id, spec.metric),
            ).fetchone()

            if existing and has_observations:
                for field in TrustGuardrailSpec.FROZEN_FIELDS:
                    old, new = existing[field], getattr(spec, field)
                    if field == "required":
                        new = int(new)
                    if old != new:
                        raise ValueError(
                            f"guardrail contract is frozen: {experiment_id}.{spec.metric}."
                            f"{field} cannot change from {old!r} to {new!r} after observations "
                            "exist. Create a new experiment instead."
                        )

            con.execute(
                """INSERT OR REPLACE INTO experiment_trust_guardrails(
                     experiment_id, metric, direction, baseline, max_absolute,
                     max_adverse_delta, max_relative_increase, minimum_sample,
                     required, source, not_applicable_reason
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (experiment_id, spec.metric, spec.direction, spec.baseline,
                 spec.max_absolute, spec.max_adverse_delta, spec.max_relative_increase,
                 spec.minimum_sample, int(spec.required), spec.source,
                 spec.not_applicable_reason),
            )
            written += 1
        if written:
            con.execute(
                "UPDATE experiments SET trust_policy_state='DECLARED', trust_policy_declared_at=? "
                "WHERE experiment_id=?", (_now(), experiment_id))
        return written


# Attempts that reached nobody. Everything else attributed to the experiment is treatment.
_NOT_TREATMENT = ("correction", "message_bounced", "invitation_undeliverable")


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _trust_policy(con, experiment_id: str) -> dict:
    row = con.execute(
        """SELECT trust_policy_state, trust_policy_reason, trust_policy_declared_at,
                  sample_size, observed_value FROM experiments WHERE experiment_id = ?""",
        (experiment_id,)).fetchone()
    if row is None:
        raise ValueError(f"experiment {experiment_id} is not preregistered")
    placeholders = ",".join("?" * len(_NOT_TREATMENT))
    first_exposure = con.execute(
        f"""SELECT MIN(occurred_at) FROM funnel_events e
            WHERE e.experiment_id = ? AND e.event_type NOT IN ({placeholders})
              AND e.provenance != 'synthetic_fixture'
              AND NOT EXISTS (SELECT 1 FROM funnel_events c WHERE c.corrects_event_id = e.event_id)""",
        (experiment_id, *_NOT_TREATMENT)).fetchone()[0]
    has_result = bool(row["sample_size"]) or row["observed_value"] is not None
    guardrails = con.execute(
        "SELECT COUNT(*) FROM experiment_trust_guardrails WHERE experiment_id = ?",
        (experiment_id,)).fetchone()[0]
    return {
        "experiment_id": experiment_id,
        "state": row["trust_policy_state"],
        "reason": row["trust_policy_reason"],
        "declared_at": row["trust_policy_declared_at"],
        "guardrails": guardrails,
        # Whichever came first: an exposure has a date; a result only proves it happened.
        "treatment_started_at": first_exposure or ("result_recorded" if has_result else ""),
    }


def _refuse_if_treated(policy: dict) -> None:
    if policy["treatment_started_at"]:
        raise ValueError(
            f"trust contract is frozen: {policy['experiment_id']} entered treatment "
            f"({policy['treatment_started_at']}). Declaring or changing a guardrail now is choosing "
            "the gate with the outcome in view; register a new experiment version instead.")


def trust_policy(db_path: str, experiment_id: str) -> dict:
    with connect(db_path) as con:
        return _trust_policy(con, experiment_id)


def declare_trust_not_applicable(db_path: str, experiment_id: str, reason: str) -> None:
    """Resolve the trust policy as NOT_APPLICABLE. The reason is the policy; silence is not."""
    if not reason.strip():
        raise ValueError("NOT_APPLICABLE needs a recorded reason; an unexplained exemption is a missing gate")
    with connect(db_path) as con:
        policy = _trust_policy(con, experiment_id)
        _refuse_if_treated(policy)
        if policy["guardrails"]:
            raise ValueError(f"{experiment_id} already declares guardrails; a policy is one or the other")
        con.execute(
            "UPDATE experiments SET trust_policy_state='NOT_APPLICABLE', trust_policy_reason=?, "
            "trust_policy_declared_at=? WHERE experiment_id=?", (reason.strip(), _now(), experiment_id))


def record_trust_observation(db_path: str, experiment_id: str, obs) -> None:
    """Store numerator and denominator, never a rendered percentage."""
    obs.validate()
    with connect(db_path) as con:
        declared = con.execute(
            "SELECT 1 FROM experiment_trust_guardrails WHERE experiment_id=? AND metric=?",
            (experiment_id, obs.metric),
        ).fetchone()
        if declared is None:
            raise ValueError(
                f"{obs.metric!r} was not preregistered for {experiment_id}; "
                "a guardrail declared after the fact is not a guardrail"
            )
        con.execute(
            """INSERT INTO experiment_trust_results(
                 experiment_id, metric, numerator, denominator, observed_value,
                 observed_at, evidence_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (experiment_id, obs.metric, obs.numerator, obs.denominator,
             obs.value, obs.observed_at, obs.evidence_id),
        )


def trust_verdict(db_path: str, experiment_id: str):
    """Evaluate every declared guardrail against its latest observation."""
    from .trust import TrustGuardrailSpec, TrustObservation, TrustVerdict, evaluate_all

    with connect(db_path) as con:
        policy = _trust_policy(con, experiment_id)
        if policy["state"] == "NOT_APPLICABLE":
            return TrustVerdict(True, False, (f"trust_not_applicable:{policy['reason']}",))
        specs = [
            TrustGuardrailSpec(
                metric=r["metric"], direction=r["direction"], baseline=r["baseline"],
                max_absolute=r["max_absolute"], max_adverse_delta=r["max_adverse_delta"],
                max_relative_increase=r["max_relative_increase"],
                minimum_sample=r["minimum_sample"], required=bool(r["required"]),
                source=r["source"], not_applicable_reason=r["not_applicable_reason"],
            )
            for r in con.execute(
                "SELECT * FROM experiment_trust_guardrails WHERE experiment_id=? ORDER BY metric",
                (experiment_id,),
            )
        ]
        observations = {}
        for r in con.execute(
            """SELECT metric, numerator, denominator, observed_at, evidence_id
               FROM experiment_trust_results WHERE experiment_id=?
               ORDER BY id""",
            (experiment_id,),
        ):
            observations[r["metric"]] = TrustObservation(
                metric=r["metric"], numerator=r["numerator"], denominator=r["denominator"],
                observed_at=r["observed_at"], evidence_id=r["evidence_id"],
            )
    return evaluate_all(specs, observations)
