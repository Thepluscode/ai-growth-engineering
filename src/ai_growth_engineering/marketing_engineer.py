"""The Marketing Engineer: reads deterministic numbers, says what they mean, proposes one test.

Interpretation here is rule-based and every finding is labelled `deterministic_rules`. It
never produces a metric — every number it cites comes from `revenue_loop` — and it never
acts: a recommendation is data until a person approves it through the existing controls.
"""
from __future__ import annotations

from typing import Any

from .funnel_events import effective_events, synthetic_count
from .revenue_loop import (
    FUNNEL_PATHS, attribute, compute_metrics, funnel, group_by, money_graph_for_campaign, totals,
)
from .storage import connect, init_db

MIN_SAMPLE = 30
ASSUMED_TRUE_RATE = 0.10

# Which single variable moves which step. A leak proposes a test on that step's lever and
# nothing else, so a recommendation cannot quietly change two things at once.
STEP_LEVERS: dict[tuple[str, str], tuple[str, str]] = {
    ("impression", "click"): ("hook", "ctr"),
    ("click", "lead_created"): ("landing_page_headline", "lead_cvr"),
    ("lead_created", "lead_qualified"): ("audience", "qualified_lead_rate"),
    ("message_sent", "reply_meaningful"): ("cta", "meaningful_reply_rate"),
    ("invitation_sent", "invitation_accepted"): ("recipient_route", "accept_rate"),
    ("invitation_accepted", "reply_meaningful"): ("cta", "meaningful_reply_rate"),
    ("reply_meaningful", "meeting_booked"): ("cta", "reply_to_meeting_rate"),
    ("lead_qualified", "meeting_booked"): ("cta", "meeting_rate"),
    ("meeting_booked", "proposal_sent"): ("offer", "proposal_rate"),
    ("proposal_sent", "customer_won"): ("price", "close_rate"),
    ("customer_won", "payment_received"): ("price", "close_rate"),
}

RECOMMENDATION_FIELDS = (
    "status", "experiment_id", "hypothesis", "single_variable", "control", "variant", "icp",
    "offer", "channel", "primary_metric", "guardrails", "sample_and_stopping_rule",
    "why_highest_value", "evidence", "previous_experiments", "stop_condition",
)


def _finding(kind: str, experiment_id: str, observation: str, evidence: dict, interpretation: str,
             action: str, variable: str | None, metric: str | None, why_not: str) -> dict:
    return {"kind": kind, "experiment_id": experiment_id, "observation": observation,
            "evidence": evidence, "interpretation": interpretation, "proposed_action": action,
            "proposed_test_variable": variable, "primary_metric": metric,
            "why_not_other_metric": why_not, "source": "deterministic_rules"}


def _first_zero_step(events: list[dict], experiment_id: str, path: str, min_sample: int) -> list[dict]:
    """Only the first zero on a path is a finding: every zero after it is its consequence."""
    t = totals(events)
    steps = FUNNEL_PATHS[path]
    for upstream, downstream in zip(steps, steps[1:]):
        n = t.get(upstream, 0)
        if not n or t.get(downstream, 0):
            continue
        variable, metric = STEP_LEVERS[(upstream, downstream)]
        classes = {k: len(v) for k, v in group_by(
            [e for e in events if e["event_type"] == upstream], "metadata.recipient_class").items() if k}
        evidence: dict[str, Any] = {upstream: n, downstream: 0, "minimum_sample": min_sample,
                                    "p_zero_at_true_10pct": round((1 - ASSUMED_TRUE_RATE) ** n, 6)}
        if classes:
            evidence["by_recipient_class"] = classes
        if upstream == "message_sent" and classes and classes.get("named_buyer", 0) * 2 < n:
            # Most sends never reached a named buyer, so the message was not what was tested.
            variable = "recipient_route"
        observation = f"{experiment_id or 'unassigned'}: {n} {upstream}, 0 {downstream}"
        if classes:
            observation += " (" + ", ".join(f"{k} {v}" for k, v in sorted(classes.items())) + ")"
        if n < min_sample:
            return [_finding(
                "unmeasured_not_rejected", experiment_id, observation, evidence,
                f"{n} is below the {min_sample} minimum: zero from {n} happens "
                f"{evidence['p_zero_at_true_10pct']:.0%} of the time even at a true 10% rate. "
                "This is not a rejection.",
                "Do not conclude on this step; keep exposing the frozen design to its minimum sample.",
                None, metric, f"Judging {metric} now would read noise as a market answer.")]
        return [_finding(
            "leak", experiment_id, observation, evidence,
            f"Zero from {n}: at a true 10% rate that happens {evidence['p_zero_at_true_10pct']:.2%} "
            "of the time, so this step is not working as run."
            + (" Most sends reached a shared inbox, so access was tested, not the message."
               if variable == "recipient_route" else ""),
            f"Test one change at this step: vary {variable} only.", variable, metric,
            f"Everything after {downstream} is empty, so optimising any later metric improves nothing.")]
    return []


def _attention_vs_quality(events: list[dict], experiment_id: str) -> list[dict]:
    rows = []
    for creative, scoped in group_by(events, "creative_id").items():
        m = compute_metrics(scoped)["metrics"]
        if creative and m["ctr"]["value"] is not None and m["qualified_lead_rate"]["value"] is not None:
            rows.append((creative, m["ctr"], m["qualified_lead_rate"]))
    if len(rows) < 2:
        return []
    attention = max(rows, key=lambda r: r[1]["value"])
    quality = max(rows, key=lambda r: r[2]["value"])
    if attention[0] == quality[0] or quality[1]["value"] >= attention[1]["value"]:
        return []
    describe = lambda r: (f"{r[0]}: CTR {r[1]['value']:.1%} ({r[1]['numerator']}/{r[1]['denominator']}), "  # noqa: E731
                          f"qualified-lead rate {r[2]['value']:.0%} ({r[2]['numerator']}/{r[2]['denominator']})")
    return [_finding(
        "attention_vs_quality", experiment_id, f"{describe(attention)}; {describe(quality)}",
        {r[0]: {"ctr": r[1], "qualified_lead_rate": r[2]} for r in rows},
        f"{attention[0]} wins attention; {quality[0]} wins buyer quality. Optimising CTR would promote "
        "the creative that brings fewer qualified buyers.",
        f"Keep {quality[0]}'s positioning, offer, audience and CTA; vary only its hook.",
        "hook", "qualified_lead_rate",
        "CTR rewards whatever attracts clicks, including the wrong buyers; the qualified-lead rate is "
        "the nearest observed step to revenue.")]


def evaluate(events: list[dict], *, min_sample: int = MIN_SAMPLE,
             minimums: dict[str, int] | None = None) -> list[dict]:
    """Findings per experiment. Experiments are never pooled: blending two tests' sends into one
    rate is how a result answers a question nobody asked. An experiment's own preregistered
    minimum sample decides whether a zero is measured; `min_sample` covers unregistered events."""
    if not events:
        return [_finding("no_events", "", "No effective funnel events are recorded.", {"events": 0},
                         "There is nothing to interpret; any conclusion now would be invented.",
                         "Import a real acquisition channel before evaluating.", None, None,
                         "No metric is observed.")]
    findings = []
    for experiment_id, scoped in sorted(group_by(events, "experiment_id").items()):
        findings += _attention_vs_quality(scoped, experiment_id)
        t = totals(scoped)
        sample = (minimums or {}).get(experiment_id) or min_sample
        for path, steps in FUNNEL_PATHS.items():
            if t.get(steps[0], 0):
                findings += _first_zero_step(scoped, experiment_id, path, sample)
    return findings


def _experiment_state(db_path: str) -> tuple[list[dict], dict[str, int], dict[str, list[dict]]]:
    with connect(db_path) as con:
        experiments = [dict(r) for r in con.execute("SELECT * FROM experiments ORDER BY created_at, experiment_id")]
        supply = dict(con.execute("SELECT cohort_id, COUNT(*) FROM execution_cohort GROUP BY cohort_id").fetchall())
        guardrails: dict[str, list[dict]] = {}
        for row in con.execute("SELECT * FROM experiment_trust_guardrails"):
            guardrails.setdefault(row["experiment_id"], []).append(dict(row))
    return experiments, supply, guardrails


def _history(experiments: list[dict]) -> list[dict]:
    return [{"experiment_id": e["experiment_id"], "decision": e["decision"], "sample_size": e["sample_size"],
             "observed_value": e["observed_value"], "primary_metric": e["primary_metric"],
             "learning": (e["learning"] or "")[:240]}
            for e in experiments if e["decision"] != "preregistered"]


def _run_preregistered(e: dict, supply: int, exposed: int, guardrails: list[dict],
                       findings: list[dict], history: list[dict]) -> dict:
    return {
        "status": "PREREGISTERED_UNRUN",
        "experiment_id": e["experiment_id"],
        "hypothesis": e["hypothesis"],
        "single_variable": e.get("variable") or "not declared in the contract (it predates the variable field)",
        "control": e["control"] or "not declared in the contract",
        "variant": e["variant"] or "not declared in the contract",
        "icp": e["buyer"] or e["market"] or "not declared in the experiment contract",
        "offer": "not declared in the experiment contract",
        "channel": e["channel"] or "not declared in the contract",
        "primary_metric": e["primary_metric"],
        "guardrails": [g["metric"] for g in guardrails] or ["none declared"],
        "sample_and_stopping_rule": (
            f"minimum sample {e['minimum_sample']}; evaluated whole, never on a partial read; "
            f"KEEP needs {e['primary_metric']} >= {e['success_threshold']} with guardrails passing"),
        "why_highest_value": (
            f"It is preregistered with {supply} frozen participants and {exposed} recorded exposures. "
            "Running it reduces the open commercial uncertainty at no design cost; designing a new "
            "test while a frozen one is unrun adds a protocol without adding evidence."),
        "evidence": [f["observation"] for f in findings if f["kind"] != "no_events"],
        "previous_experiments": history,
        "stop_condition": (
            f"At the full sample, {e['primary_metric']} below {e['review_threshold']} returns REVIEW: stop "
            "pursuing this hypothesis as run, and a person decides what follows."),
    }


def _proposal_from_leak(leak: dict, history: list[dict], min_sample: int) -> dict:
    variable, metric = leak["proposed_test_variable"], leak["primary_metric"]
    return {
        "status": "PROPOSED_NEEDS_CONTRACT",
        "experiment_id": None,
        "hypothesis": f"Changing only {variable} raises {metric} at the step where {leak['observation']}.",
        "single_variable": variable,
        "control": f"the {variable} used in {leak['experiment_id']}",
        "variant": "not written: the operator writes the variant; the engine does not invent copy, "
                   "targeting or prices",
        "icp": f"carried over from {leak['experiment_id']}",
        "offer": f"carried over from {leak['experiment_id']}",
        "channel": f"carried over from {leak['experiment_id']}",
        "primary_metric": metric,
        "guardrails": ["declare before exposure (experiment_trust_guardrails)"],
        "sample_and_stopping_rule": f"at least {min_sample} exposures per arm, evaluated whole",
        "why_highest_value": leak["interpretation"],
        "evidence": [leak["observation"]],
        "previous_experiments": history,
        "stop_condition": (f"If {metric} is still zero after {min_sample} exposures per arm, {variable} is "
                           "not the constraint: stop and re-examine the step before it."),
    }


def recommend_next_experiment(db_path: str, *, min_sample: int = MIN_SAMPLE) -> dict:
    """Exactly one preferred experiment, plus alternatives with the reason each was not preferred."""
    init_db(db_path)
    events = effective_events(db_path)
    experiments, supply, guardrails = _experiment_state(db_path)
    findings = evaluate(events, min_sample=min_sample,
                        minimums={e["experiment_id"]: e["minimum_sample"] for e in experiments})
    history = _history(experiments)
    unrun = [e for e in experiments if e["decision"] == "preregistered" and not e["sample_size"]]
    runnable = [e for e in unrun if supply.get(e["experiment_id"], 0)]
    preferred = None
    alternatives: list[dict] = []
    if runnable:
        e = runnable[0]
        exposed = sum(1 for ev in events if ev["experiment_id"] == e["experiment_id"])
        preferred = _run_preregistered(e, supply[e["experiment_id"]], exposed,
                                       guardrails.get(e["experiment_id"], []), findings, history)
    for e in unrun:
        if preferred and e["experiment_id"] == preferred["experiment_id"]:
            continue
        runnable_now = bool(supply.get(e["experiment_id"], 0))
        alternatives.append({
            "status": "PREREGISTERED_UNRUN" if runnable_now else "PREREGISTERED_BLOCKED",
            "experiment_id": e["experiment_id"], "hypothesis": e["hypothesis"],
            "not_preferred_because": ("another runnable preregistered experiment is earlier" if runnable_now
                                      else "no frozen execution supply: it cannot run as written"),
        })
    for leak in (f for f in findings if f["kind"] == "leak"):
        proposal = _proposal_from_leak(leak, history, min_sample)
        if preferred is None:
            preferred = proposal
        else:
            alternatives.append(dict(proposal, not_preferred_because=(
                "a frozen experiment already exists; propose new tests after it has run")))
    if preferred is None:
        preferred = {name: None for name in RECOMMENDATION_FIELDS}
        preferred.update(status="NO_BASIS", evidence=[f["observation"] for f in findings],
                         previous_experiments=history,
                         why_highest_value="No preregistered experiment has supply and no measured leak "
                                           "exists. The next action is a first real observation, not a test design.")
    return {"preferred": preferred, "alternatives": alternatives, "findings": findings,
            "experiments": experiments, "supply": supply}


def status_report(db_path: str) -> dict:
    events = effective_events(db_path)
    metrics = compute_metrics(events)
    recommendation = recommend_next_experiment(db_path)
    by_channel = {k or "unknown": totals(v) for k, v in group_by(events, "channel").items()}
    campaigns = {k: money_graph_for_campaign(events, k) for k in group_by(events, "campaign_id") if k}
    payments = [e for e in events if e["event_type"] == "payment_received"]
    return {
        "events": len(events), "synthetic_excluded": synthetic_count(db_path),
        "totals": metrics["totals"], "metrics": metrics["metrics"],
        "funnels": {exp or "unassigned": {path: funnel(scoped, path) for path, steps in FUNNEL_PATHS.items()
                                          if totals(scoped).get(steps[0], 0)}
                    for exp, scoped in group_by(events, "experiment_id").items()},
        "by_channel": by_channel, "campaigns": campaigns,
        "attribution_linear": attribute(events, "linear") if payments else [],
        "recommendation": recommendation,
    }


def _money(pence: int | None) -> str:
    return "not derivable" if pence is None else f"£{pence / 100:,.2f}"


def render_status(report: dict) -> str:
    t, rec = report["totals"], report["recommendation"]
    spend = _money(t["spend_pence"]) if t["spend_recorded"] else "not recorded"
    roas = report["metrics"]["roas"]
    synthetic = report["synthetic_excluded"]
    roas_text = f"not derivable ({roas['reason']})" if roas["value"] is None else f"{roas['value']:.1f}x"
    lines = [
        "THEPLUS MARKETING ENGINEER",
        f"  [OBSERVED] {report['events']} effective events"
        + (f"; {synthetic} synthetic fixtures excluded" if synthetic else ""),
        f"  [OBSERVED] Revenue {_money(t['revenue_pence'])} from {t.get('payment_received', 0)} payments"
        f" · Pipeline {_money(t['pipeline_pence'])} · Spend {spend}",
        f"  [DERIVED]  ROAS {roas_text}",
        "",
        "1. What is happening?  [OBSERVED]",
    ]
    for channel, ct in sorted(report["by_channel"].items()):
        counts = ", ".join(f"{k} {v}" for k, v in sorted(ct.items())
                           if isinstance(v, int) and not isinstance(v, bool) and not k.endswith("_pence"))
        lines.append(f"   {channel}: {counts}")
    for experiment, funnels in sorted(report["funnels"].items()):
        for path, steps in funnels.items():
            chain = " -> ".join(f"{s['event_type']} {s['count']}" for s in steps)
            lines.append(f"   {experiment} [{path}] {chain}")

    findings = rec["findings"]
    leaks = [f for f in findings if f["kind"] in ("leak", "unmeasured_not_rejected", "attention_vs_quality")]
    lines.append("2. Where is the funnel leaking?  [INTERPRETATION: deterministic rules]")
    lines += [f"   {f['observation']} -> {f['interpretation']}" for f in leaks] or ["   no leak measurable yet"]
    lines.append("3. What is costing us money?  [OBSERVED]")
    lines.append(f"   spend {spend}" + ("" if t["spend_recorded"] else
                                      " — cost per outcome, CAC and ROAS are not derivable, not zero"))
    lines.append("4. What is producing qualified pipeline?  [OBSERVED]")
    qualified = {c: ct for c, ct in report["by_channel"].items()
                 if ct.get("reply_meaningful", 0) or ct.get("lead_qualified", 0) or ct.get("meeting_booked", 0)}
    lines += [f"   {c}: {ct.get('reply_meaningful', 0)} meaningful replies, {ct.get('lead_qualified', 0)} "
              f"qualified leads, {ct.get('meeting_booked', 0)} meetings" for c, ct in sorted(qualified.items())] \
        or ["   nothing yet: no channel has produced a meaningful reply, qualified lead or meeting"]
    lines.append("5. What is producing revenue?  [DERIVED: linear attribution]")
    lines += [f"   {r['entity']}: {_money(r['amount_pence'])} across {len(r['touchpoints'])} touches"
              for r in report["attribution_linear"]] or ["   no payment recorded"]
    lines.append("6. Which experiment is currently running?  [OBSERVED]")
    live = [e for e in rec["experiments"] if e["decision"] == "preregistered" and rec["supply"].get(e["experiment_id"])]
    lines += [f"   {e['experiment_id']}: preregistered, {rec['supply'][e['experiment_id']]} frozen participants, "
              f"sample {e['sample_size']}/{e['minimum_sample']}" for e in live] or ["   none with frozen supply"]
    lines.append("7. What have we learned?  [OBSERVED experiment decisions]")
    lines += [f"   {h['experiment_id']}: {h['decision'].upper()} at n={h['sample_size']}, "
              f"{h['primary_metric']}={h['observed_value']}" for h in rec["preferred"]["previous_experiments"] or []] \
        or ["   no experiment has concluded"]
    p = rec["preferred"]
    lines.append("8. What should we test next?  [RECOMMENDATION — requires human approval]")
    lines.append(f"   {p['status']}: {p['experiment_id'] or '(new contract needed)'}")
    for field in ("hypothesis", "single_variable", "primary_metric", "why_highest_value", "stop_condition"):
        if p.get(field):
            lines.append(f"   {field}: {p[field]}")
    for alt in rec["alternatives"]:
        lines.append(f"   alternative {alt['status']} {alt.get('experiment_id') or ''}: {alt['not_preferred_because']}")
    return "\n".join(lines)
