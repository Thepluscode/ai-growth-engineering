from __future__ import annotations

import csv
import json
from dataclasses import asdict

from .models import Evidence, ExperimentDecision, ExperimentSpec
from .storage import connect


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
                 start_date, end_date, learning
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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


def scoreboard(db_path: str) -> dict[str, int]:
    with connect(db_path) as con:
        return {
            "qualified_prospects": con.execute(
                "SELECT COUNT(*) FROM prospects WHERE status NOT LIKE 'disqualified%'"
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
        if con.execute(
            "SELECT 1 FROM experiments WHERE experiment_id = ?", (experiment_id,)
        ).fetchone() is None:
            raise ValueError(f"experiment {experiment_id} is not preregistered")

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
        return written


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
    from .trust import TrustGuardrailSpec, TrustObservation, evaluate_all

    with connect(db_path) as con:
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
