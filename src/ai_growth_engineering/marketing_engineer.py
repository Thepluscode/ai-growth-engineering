"""The Marketing Engineer: reads deterministic numbers, says what they mean, proposes one test.

Interpretation here is rule-based and every finding is labelled `deterministic_rules`. It
never produces a metric — every number it cites comes from `revenue_loop` — and it never
acts: a recommendation is data until a person approves it through the existing controls.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from . import registries
from .buyer_truth import buyer_evidence, buyer_truth, problem_revenue, stalled_objections, truth_summary
from .funnel_events import effective_events, synthetic_count
from .revenue_loop import (
    LADDERS, STAGE_LABELS, attribute, compute_metrics, diagnose_funnel, entity, group_by,
    money_graph_for_campaign, money_graph_for_entity, totals,
)
from .storage import connect, init_db

MIN_SAMPLE = 30
ASSUMED_TRUE_RATE = 0.10
DESCRIPTIVE = "DESCRIPTIVE_FROZEN_COHORT"
EXPOSURE_TYPES = frozenset({"invitation_sent", "message_sent"})

# Which single variable moves which step. A leak proposes a test on that step's lever and
# nothing else, so a recommendation cannot quietly change two things at once.
STEP_LEVERS: dict[tuple[str, str], tuple[str, str]] = {
    ("impression", "click"): ("hook", "ctr"),
    ("click", "lead_created"): ("landing_page_headline", "lead_cvr"),
    ("lead_created", "lead_qualified"): ("audience", "qualified_lead_rate"),
    ("lead_qualified", "meeting_booked"): ("cta", "meeting_rate"),
    ("message_sent", "reply_received"): ("cta", "reply_rate"),
    ("invitation_sent", "invitation_accepted"): ("recipient_route", "accept_rate"),
    ("invitation_accepted", "reply_received"): ("cta", "reply_rate"),
    ("reply_received", "reply_meaningful"): ("offer", "qualified_reply_rate"),
    ("reply_meaningful", "meeting_booked"): ("cta", "reply_to_meeting_rate"),
    ("meeting_booked", "proposal_sent"): ("offer", "proposal_rate"),
    ("proposal_sent", "customer_won"): ("price", "close_rate"),
    ("customer_won", "payment_received"): ("price", "close_rate"),
}

RECOMMENDATION_FIELDS = (
    "status", "experiment_id", "hypothesis", "single_variable", "control", "variant", "icp",
    "offer", "channel", "primary_metric", "guardrails", "sample_and_stopping_rule",
    "why_highest_value", "evidence", "previous_experiments", "stop_condition", "based_on_experiment_id",
)


def _finding(kind: str, experiment_id: str, observation: str, evidence: dict, interpretation: str,
             action: str, variable: str | None, metric: str | None, why_not: str) -> dict:
    return {"kind": kind, "experiment_id": experiment_id, "observation": observation,
            "evidence": evidence, "interpretation": interpretation, "proposed_action": action,
            "proposed_test_variable": variable, "primary_metric": metric,
            "why_not_other_metric": why_not, "source": "deterministic_rules"}


def _constraint_findings(events: list[dict], experiment_id: str, path: str, min_sample: int,
                         as_of: str) -> list[dict]:
    diag = diagnose_funnel(events, path, as_of=as_of, min_sample=min_sample)
    name = experiment_id or "unassigned"
    constraint = diag["constraint"]
    if constraint and constraint["is_leak"]:
        tr = next(s["transition"] for s in diag["stages"] if s["stage"] == constraint["to"])
        variable, metric = STEP_LEVERS[(tr["from"], tr["to"])]
        n, k = tr["denominator"], tr["numerator"]
        classes = {c: len(v) for c, v in group_by(
            [e for e in events if e["event_type"] == tr["from"]], "metadata.recipient_class").items() if c}
        if tr["from"] == "message_sent" and classes and classes.get("named_buyer", 0) * 2 < n:
            # Most sends never reached a named buyer, so the message was not what was tested.
            variable = "recipient_route"
        evidence: dict[str, Any] = {tr["from"]: n, tr["to"]: k, "rate": tr["rate"], "ci95": tr["ci95"],
                                    "minimum_sample": min_sample,
                                    "p_zero_at_true_10pct": round((1 - ASSUMED_TRUE_RATE) ** n, 6) if k == 0 else None}
        if classes:
            evidence["by_recipient_class"] = classes
        observation = f"{name}: {k}/{n} {tr['from']} -> {tr['to']}"
        if classes:
            observation += " (" + ", ".join(f"{c} {v}" for c, v in sorted(classes.items())) + ")"
        if k == 0:
            interpretation = (f"Zero from {n}: at a true 10% rate that happens "
                              f"{evidence['p_zero_at_true_10pct']:.2%} of the time, so this step is not working as run.")
        else:
            interpretation = (f"{STAGE_LABELS[tr['to']]} converts {tr['rate']:.1%} of {n} "
                              f"(95% CI {tr['ci95'][0]:.1%}-{tr['ci95'][1]:.1%}), the lowest measured transition on this path.")
        if variable == "recipient_route" and tr["from"] == "message_sent":
            interpretation += " Most sends reached a shared inbox, so access was tested, not the message."
        return [_finding(
            "leak", experiment_id, observation, evidence, interpretation,
            f"Test one change at this step: vary {variable} only.", variable, metric,
            f"Every stage after {tr['to']} depends on this one; optimising a later metric improves "
            "nothing while this step is the constraint.")]
    pending = next((s["transition"] for s in diag["stages"] if s["transition"]
                    and s["transition"]["status"] in ("IN_FLIGHT", "INSUFFICIENT_DATA")), None)
    if pending is None:
        return []
    metric = STEP_LEVERS.get((pending["from"], pending["to"]), (None, None))[1]
    n, k = pending["denominator"], pending["numerator"]
    evidence = {"stage": f"{pending['from']} -> {pending['to']}", "numerator": k, "denominator": n,
                "in_flight": pending["in_flight"], "minimum_sample": min_sample}
    if pending["status"] == "IN_FLIGHT":
        observation = (f"{name}: {pending['in_flight']} {pending['from']} inside the "
                       f"{diag['response_window_days']}-day response window")
        interpretation = (f"No {pending['to']} rate is derivable yet: every exposure is still inside the "
                          "response window. A pending exposure is not a refusal.")
    else:
        p_zero = round((1 - ASSUMED_TRUE_RATE) ** n, 6)
        evidence["p_zero_at_true_10pct"] = p_zero if k == 0 else None
        observation = f"{name}: {k}/{n} {pending['from']} -> {pending['to']}"
        if pending["in_flight"]:
            observation += f", {pending['in_flight']} more in flight"
        interpretation = (f"{n} is below the {min_sample} minimum"
                          + (f": zero from {n} happens {p_zero:.0%} of the time even at a true 10% rate" if k == 0 else "")
                          + ". This is not a rejection.")
    return [_finding(
        "unmeasured_not_rejected", experiment_id, observation, evidence, interpretation,
        "Do not conclude on this step; keep exposing the frozen design until it matures and reaches its minimum sample.",
        None, metric, f"Judging {metric} now would read noise or unanswered messages as a market answer.")]


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
             minimums: dict[str, int] | None = None, as_of: str | None = None) -> list[dict]:
    """Findings per experiment. Experiments are never pooled: blending two tests' sends into one
    rate is how a result answers a question nobody asked. An experiment's own minimum sample
    decides whether a zero is measured; `min_sample` covers unregistered events."""
    as_of = as_of or date.today().isoformat()
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
        for path, ladder in LADDERS.items():
            if t.get(ladder[0], 0):
                findings += _constraint_findings(scoped, experiment_id, path, sample, as_of)
    return findings


def _experiment_state(db_path: str) -> tuple[list[dict], dict[str, int], dict[str, list[dict]]]:
    with connect(db_path) as con:
        experiments = [dict(r) for r in con.execute("SELECT * FROM experiments ORDER BY created_at, experiment_id")]
        supply = dict(con.execute("SELECT cohort_id, COUNT(*) FROM execution_cohort GROUP BY cohort_id").fetchall())
        guardrails: dict[str, list[dict]] = {}
        for row in con.execute("SELECT * FROM experiment_trust_guardrails"):
            guardrails.setdefault(row["experiment_id"], []).append(dict(row))
    return experiments, supply, guardrails


def _minimums(experiments: list[dict]) -> dict[str, int]:
    """A descriptive execution is judged on the generic minimum, never its unreachable preregistered one."""
    return {e["experiment_id"]: MIN_SAMPLE if e.get("execution_mode") == DESCRIPTIVE else e["minimum_sample"]
            for e in experiments}


def _history(experiments: list[dict]) -> list[dict]:
    return [{"experiment_id": e["experiment_id"], "decision": e["decision"], "sample_size": e["sample_size"],
             "observed_value": e["observed_value"], "primary_metric": e["primary_metric"],
             "learning": (e["learning"] or "")[:240]}
            for e in experiments if e["decision"] != "preregistered"]


def _run_preregistered(e: dict, supply: int, exposed: int, guardrails: list[dict],
                       findings: list[dict], history: list[dict]) -> dict:
    descriptive = e.get("execution_mode") == DESCRIPTIVE
    return {
        "status": "PREREGISTERED_UNRUN",
        "experiment_id": e["experiment_id"],
        "based_on_experiment_id": e["experiment_id"],
        "hypothesis": e["hypothesis"],
        "single_variable": (f"{e['variable']} ({e['variable_metadata_source']})"
                            if e.get("variable") and e.get("variable_metadata_source") else
                            e.get("variable") or "not declared in the contract (it predates the variable field)"),
        "control": e["control"] or "not declared in the contract",
        "variant": e["variant"] or "not declared in the contract",
        "icp": e["buyer"] or e["market"] or "not declared in the experiment contract",
        "offer": "not declared in the experiment contract",
        "channel": e["channel"] or "not declared in the contract",
        "primary_metric": e["primary_metric"],
        "guardrails": [g["metric"] for g in guardrails] or ["none declared"],
        "sample_and_stopping_rule": (
            f"descriptive execution of the frozen cohort ({supply}): the preregistered minimum of "
            f"{e['minimum_sample']} is not reachable and is not claimed; every rate uses real exposure "
            "and the verdict is DESCRIPTIVE_POSITIVE / NEGATIVE / INCONCLUSIVE"
            if descriptive else
            f"minimum sample {e['minimum_sample']}; evaluated whole, never on a partial read; "
            f"KEEP needs {e['primary_metric']} >= {e['success_threshold']} with guardrails passing"),
        "why_highest_value": (
            f"It is preregistered with {supply} frozen participants and {exposed} delivered exposures. "
            "Running it reduces the open commercial uncertainty at no design cost; designing a new "
            "test while a frozen one is unrun adds a protocol without adding evidence."),
        "evidence": [f["observation"] for f in findings if f["kind"] != "no_events"],
        "previous_experiments": history,
        "stop_condition": (
            "no preregistered threshold applies to a descriptive execution: once every exposure has "
            "matured, a person judges the descriptive result and decides what follows"
            if descriptive else
            f"At the full sample, {e['primary_metric']} below {e['review_threshold']} returns REVIEW: stop "
            "pursuing this hypothesis as run, and a person decides what follows."),
    }


def _proposal_from_leak(leak: dict, history: list[dict], min_sample: int) -> dict:
    variable, metric = leak["proposed_test_variable"], leak["primary_metric"]
    return {
        "status": "PROPOSED_NEEDS_CONTRACT",
        "experiment_id": None,
        "based_on_experiment_id": leak["experiment_id"],
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
        "sample_and_stopping_rule": f"at least {min_sample} matured exposures per arm, evaluated whole",
        "why_highest_value": leak["interpretation"],
        "evidence": [leak["observation"]],
        "previous_experiments": history,
        "stop_condition": (f"If {metric} does not move after {min_sample} matured exposures per arm, {variable} "
                           "is not the constraint: stop and re-examine the step before it."),
    }


def _proposal_from_objection(objection: dict, evidence: list[dict], history: list[dict]) -> dict:
    theme = objection["theme"]
    items = [i for i in evidence if i["category"] == "OBJECTION" and i["evidence_id"] in objection["evidence_ids"]]
    experiments = sorted({i["experiment_id"] for i in items if i["experiment_id"]})
    return {
        "status": "PROPOSED_NEEDS_CONTRACT",
        "experiment_id": None,
        "based_on_experiment_id": experiments[0] if len(experiments) == 1 else None,
        "hypothesis": f"Changing only the offer so it answers the '{theme}' objection raises the close rate "
                      "of buyers who reach a proposal.",
        "single_variable": "offer",
        "control": "the offer exactly as proposed to the buyers who raised the objection",
        "variant": f"not written: the operator writes one offer change that answers '{theme}'; the engine "
                   "does not invent terms, prices or guarantees",
        "icp": "carried over from the stalled proposals",
        "offer": "carried over, except the one part that answers the objection",
        "channel": "carried over from the stalled proposals",
        "primary_metric": "close_rate",
        "guardrails": ["declare before exposure (experiment_trust_guardrails)"],
        "sample_and_stopping_rule": "declare the number of proposals per arm before the first is sent; proposals "
                                    "are low-volume, so the sample is counted in proposals, never sends",
        "why_highest_value": f"{objection['organisations']} organisations reached a proposal, did not buy and raised "
                             f"'{theme}'. That is the last observed step before money, so it outranks any earlier "
                             "funnel leak.",
        "evidence": [f"{i['evidence_id']}: \"{i['observation']}\"" for i in items],
        "previous_experiments": history,
        "stop_condition": f"If the close rate does not move after the declared proposals, '{theme}' was not what "
                          "stopped the purchase: stop and read the rejection reasons again.",
    }


def recommend_next_experiment(db_path: str, *, min_sample: int = MIN_SAMPLE, as_of: str | None = None) -> dict:
    """Exactly one preferred experiment, plus alternatives with the reason each was not preferred."""
    init_db(db_path)
    events = effective_events(db_path)
    experiments, supply, guardrails = _experiment_state(db_path)
    findings = evaluate(events, min_sample=min_sample, minimums=_minimums(experiments), as_of=as_of)
    history = _history(experiments)
    unrun = [e for e in experiments if e["decision"] == "preregistered" and not e["sample_size"]]
    runnable = [e for e in unrun if supply.get(e["experiment_id"], 0)]
    preferred = None
    alternatives: list[dict] = []
    if runnable:
        e = runnable[0]
        exposed = len({entity(ev) for ev in events
                       if ev["experiment_id"] == e["experiment_id"] and ev["event_type"] in EXPOSURE_TYPES})
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
    # Proposal-stage objections before funnel leaks: they sit nearer the money.
    evidence = buyer_evidence(db_path)
    candidates = ([_proposal_from_objection(o, evidence, history) for o in stalled_objections(evidence, events)]
                  + [_proposal_from_leak(leak, history, min_sample) for leak in findings if leak["kind"] == "leak"])
    for proposal in candidates:
        if preferred is None:
            preferred = proposal
        else:
            alternatives.append(dict(proposal, not_preferred_because=(
                "a frozen experiment already exists; propose new tests after it has run"
                if preferred["status"] == "PREREGISTERED_UNRUN" else
                "one test at a time: an earlier-ranked proposal is nearer the money or raised by more buyers")))
    if preferred is None:
        preferred = {name: None for name in RECOMMENDATION_FIELDS}
        preferred.update(status="NO_BASIS", evidence=[f["observation"] for f in findings],
                         previous_experiments=history,
                         why_highest_value="No preregistered experiment has supply and no measured leak "
                                           "exists. The next action is a first real observation, not a test design.")
    return {"preferred": preferred, "alternatives": alternatives, "findings": findings,
            "experiments": experiments, "supply": supply}


def descriptive_verdict(diag: dict) -> str:
    """Only INCONCLUSIVE is automatic. A measured descriptive result is judged by a person,
    because no preregistered threshold applies to it."""
    response = next((s["transition"] for s in diag["stages"] if s["transition"]
                     and s["transition"]["from"] in EXPOSURE_TYPES), None)
    if response is None or response["status"] != "MEASURED":
        return "DESCRIPTIVE_INCONCLUSIVE — the response step has not matured to a measurable sample"
    return ("MEASURED — a person assigns DESCRIPTIVE_POSITIVE or DESCRIPTIVE_NEGATIVE from the rates above; "
            "no preregistered threshold is claimed")


def render_diagnosis(experiment_id: str, diag: dict, execution_mode: str = "") -> list[str]:
    window = f" · response window {diag['response_window_days']}d" if diag["response_window_days"] else ""
    lines = [f"{experiment_id or 'unassigned'} [{diag['path']}]  as of {diag['as_of']}{window}"
             f" · min sample {diag['min_sample']}" + (f" · {execution_mode}" if execution_mode else "")]
    for s in diag["stages"]:
        tr = s["transition"]
        if tr is None:
            detail = "observed"
        elif tr["status"] == "IN_FLIGHT":
            detail = f"IN_FLIGHT — {tr['in_flight']} exposures inside the response window"
        elif tr["status"] == "NOT_REACHED":
            detail = "NOT_REACHED"
        else:
            detail = f"{tr['rate']:6.1%}  ({tr['numerator']}/{tr['denominator']})  {tr['status']}"
            if tr["in_flight"]:
                detail += f" · {tr['in_flight']} more in flight"
        lines.append(f"  {s['label']:<16}{s['count']:>5}   {detail}")
    if diag["attempts_not_exposure"]:
        lines.append(f"  attempts that never reached a buyer: {diag['attempts_not_exposure']} (not exposure)")
    if diag["unlinked_events"]:
        lines.append(f"  downstream events with no exposure on this path: {diag['unlinked_events']} (not counted)")
    c = diag["constraint"]
    if c is None:
        lines.append("  Largest measurable constraint: none yet — no transition has a matured denominator")
    else:
        lines.append(f"  Largest measurable constraint: {STAGE_LABELS[c['from']].lower()} -> "
                     f"{STAGE_LABELS[c['to']].lower()} ({c['rate']:.1%})")
        lines.append(f"  Confidence: {c['confidence']} — {c['reason']}"
                     + ("" if c["is_leak"] else "; below the minimum sample, so not called a leak"))
    if execution_mode == DESCRIPTIVE:
        lines.append(f"  Verdict: {descriptive_verdict(diag)}")
    return lines


COMMERCIAL_STAGES = ("impression", "click", "invitation_sent", "message_sent", "lead_created",
                     "lead_qualified", "reply_received", "reply_meaningful", "meeting_booked",
                     "proposal_sent", "customer_won", "payment_received")
# Which KEEP CONSTANT line a test variable releases.
VARIABLE_RELEASES = {"audience": "ICP", "offer": "offer", "price": "price", "channel": "channel", "body": "message body"}


def _row(db_path: str, registry: str, key: str | None) -> dict | None:
    if not key:
        return None
    pk = registries.REGISTRIES[registry][0]
    # ponytail: full registry scan per lookup; index by key once registries hold hundreds of rows.
    return next((r for r in registries.rows(db_path, registry) if r[pk] == key), None)


def linked_events(db_path: str) -> list[dict]:
    """Effective events, where an event naming no campaign inherits one only when its experiment
    has exactly one registered campaign. Two candidates is ambiguity, and it stays unlinked."""
    owners: dict[str, list[str]] = defaultdict(list)
    for c in registries.rows(db_path, "campaigns"):
        if c["experiment_id"]:
            owners[c["experiment_id"]].append(c["campaign_id"])
    linked = []
    for e in effective_events(db_path):
        candidates = owners.get(e["experiment_id"], [])
        if not e["campaign_id"] and len(candidates) == 1:
            e = dict(e, campaign_id=candidates[0],
                     metadata={**(e["metadata"] or {}), "campaign_linked_by": "experiment_id"})
        linked.append(e)
    return linked


def campaign_graph(db_path: str, campaign_id: str) -> dict:
    """A campaign's commercial record joined to what it produced. Every count lists the event ids
    behind it; money comes from the attribution the revenue loop already computes."""
    campaign = _row(db_path, "campaigns", campaign_id)
    if campaign is None:
        raise ValueError(f"campaign {campaign_id} is not registered")
    events = linked_events(db_path)
    scoped = [e for e in events if e["campaign_id"] == campaign_id]
    money = money_graph_for_campaign(events, campaign_id)
    t = totals(scoped)
    trace = {s: [e["event_id"] for e in scoped if e["event_type"] == s] for s in COMMERCIAL_STAGES}
    spend = money["spend_pence"]
    return {
        "campaign": campaign, "offer": _row(db_path, "offers", campaign["offer_id"]),
        "audience": _row(db_path, "audiences", campaign["audience_id"]),
        "creatives": [c for c in registries.rows(db_path, "creatives") if c["campaign_id"] == campaign_id],
        "counts": {s: t.get(s, 0) for s in COMMERCIAL_STAGES},
        "trace": {s: ids for s, ids in trace.items() if ids},
        "events_linked_by_experiment": sum(1 for e in scoped if (e["metadata"] or {}).get("campaign_linked_by")),
        "spend_pence": spend, "pipeline_pence": money["pipeline_pence"], "customers": money["customers"],
        "attributed_revenue_pence": money["attributed_revenue_pence"], "cac_pence": money["cac_pence"],
        "roas": money["roas"], "pipeline_roas": None if not spend else money["pipeline_pence"] / spend,
    }


def customer_graph(db_path: str, name: str) -> dict:
    """From one buyer back to the ICP, offer, campaign, creative, experiment and channel that reached them,
    and to what they actually said: problems, objections, criteria, each with its evidence id."""
    events = linked_events(db_path)
    graph = money_graph_for_entity(events, name)
    campaigns = {c: _row(db_path, "campaigns", c) for c in graph["campaigns"]}
    known = [c for c in campaigns.values() if c]
    offers = (_row(db_path, "offers", c["offer_id"]) for c in known)
    creative_ids = sorted({e["creative_id"] for e in graph["chain"] if e["creative_id"]})
    return {
        **graph,
        "icp": sorted({c["icp"] for c in known}),
        "offers": list({o["offer_id"]: o for o in offers if o}.values()),
        "channels": sorted({e["channel"] for e in graph["chain"] if e["channel"]}),
        "creatives": [_row(db_path, "creatives", i) or {"creative_id": i, "registered": False} for i in creative_ids],
        "unregistered_campaigns": sorted(c for c, row in campaigns.items() if row is None),
        "buyer_truth": buyer_truth(buyer_evidence(db_path), events, graph["entity"]),
    }


CUSTOMER_SECTIONS = {"PROBLEM_STATED": "OBSERVED PROBLEM", "OBJECTION": "OBJECTION",
                     "BUYING_CRITERION": "BUYING CRITERION", "REASON_FOR_PURCHASE": "REASON FOR PURCHASE"}


def _quote(item: dict) -> str:
    return (f"\"{item['observation']}\"  Evidence: {item['evidence_id']}"
            + ("" if item["observed_as"] == "verbatim" else " (source-backed, not verbatim)"))


def render_customer(graph: dict) -> str:
    truth = graph["buyer_truth"]
    lines = ["CUSTOMER TRUTH  [OBSERVED statements · DERIVED categories · INTERPRETED themes]"]

    def section(title: str, body: list[str] | None) -> None:
        lines.extend(["", title] + [f"  {line}" for line in (body or ["NOT OBSERVED"])])

    payments = [c for c in graph["chain"] if c["event_type"] == "payment_received"]
    section("PAYMENT", [f"{_money(graph['revenue_pence'])} from {len(payments)} payment(s)"] if payments else None)
    section("CUSTOMER", [graph["entity"]])
    section("OFFER", [f"{o['offer_id']} — {o['outcome']}" for o in graph["offers"]] or ["not recorded"])
    section("ATTRIBUTION", [
        f"channel: {', '.join(graph['channels']) or 'not recorded'}",
        f"campaign: {', '.join(graph['campaigns']) or 'not recorded'}",
        f"creative: {', '.join(c['creative_id'] for c in graph['creatives']) or 'not recorded'}",
        f"experiment: {', '.join(e for e, _ in graph['experiments']) or 'not recorded'}",
        f"ICP: {'; '.join(graph['icp']) or 'not recorded'}",
    ] + [f"linear attribution: {_money(r['attributed_amount_pence'])} of {_money(r['amount_pence'])}"
         for r in graph["attribution"]["linear"]])
    for category, title in CUSTOMER_SECTIONS.items():
        section(title, [_quote(i) for i in truth["observed"].get(category, [])])
    for category, items in sorted(truth["observed"].items()):
        if category not in CUSTOMER_SECTIONS:
            section(category.replace("_", " "), [_quote(i) for i in items])
    wtp = truth["willingness_to_pay"]
    section("WILLINGNESS TO PAY", [f"strongest observed: {wtp['strongest']}"]
            + [f"{r['rung']}: {', '.join(r['ids'])}" for r in wtp["rungs"] if r["observed"]] if wtp["strongest"] else None)
    section("INTERPRETATION", [
        f"{p['theme']}: {' / '.join(p['interpretations'])} · confidence {p['scope']['confidence']} — "
        f"{p['scope']['reason']} · evidence {', '.join(p['evidence_ids'])}"
        for p in truth["interpreted_problems"]] or ["none recorded"])
    return "\n".join(lines)


def render_problems(views: list[dict]) -> str:
    lines = ["PROBLEM → REVENUE  [INTERPRETED themes · OBSERVED stages and money]"]
    if not views:
        return "\n".join(lines + ["  no observation has been interpreted to a problem theme yet"])
    for v in views:
        lines += ["", f"Problem: {v['theme']}",
                  f"  Independent organisations stating it: {v['scope']['organisations']} ({v['buyers_stating']} buyers)"
                  f" · scope {v['scope']['level']}, confidence {v['scope']['confidence']}",
                  f"  Qualified conversations: {v['qualified_conversations']}", f"  Meetings: {v['meetings']}",
                  f"  Proposals: {v['proposals']}", f"  Customers: {v['customers']}",
                  f"  Observed revenue: {_money(v['observed_revenue_pence'])}",
                  f"  Evidence: {', '.join(v['evidence_ids'])}"]
    return "\n".join(lines)


def _constraint_summary(diag: dict | None, preferred: dict) -> tuple[str, list[str]]:
    if diag is None:
        return "no funnel events for this experiment", list(preferred["evidence"] or [])
    c = diag["constraint"]
    if c:
        tr = next(s["transition"] for s in diag["stages"] if s["stage"] == c["to"])
        return (f"{STAGE_LABELS[c['from']]} → {STAGE_LABELS[c['to']]}",
                [f"{tr['denominator']} {STAGE_LABELS[c['from']].lower()}",
                 f"{tr['numerator']} {STAGE_LABELS[c['to']].lower()}",
                 f"{c['rate']:.1%} conversion",
                 f"confidence {c['confidence']} — {c['reason']}"])
    first = diag["stages"][1]["transition"]
    evidence = [f"{diag['stages'][0]['count']} {STAGE_LABELS[first['from']].lower()}"]
    if first["in_flight"]:
        evidence.append(f"{first['in_flight']} still inside the {diag['response_window_days']}-day response window")
    return f"none measurable yet — {STAGE_LABELS[first['from']]} → {STAGE_LABELS[first['to']]} {first['status']}", evidence


def _keep_constant(campaign: dict | None, offer: dict | None, creative: dict | None, variable: str | None) -> dict:
    values = {
        "ICP": campaign and campaign["icp"],
        "offer": offer and f"{offer['offer_id']} — {offer['outcome']}",
        "message body": creative and creative["body"],
        "channel": campaign and campaign["channel"],
        # A price of 0 is how an unpriced offer is stored, so it is never shown as free.
        "price": offer and offer["price_pence"] and _money(offer["price_pence"]),
    }
    return {k: v or "not recorded" for k, v in values.items() if k != VARIABLE_RELEASES.get(variable or "")}


def next_experiment_card(db_path: str, *, as_of: str | None = None) -> dict:
    """The ONE preferred experiment in decision form: the constraint it attacks, the evidence, the
    single variable, and what stays fixed — resolved from registered records, never invented."""
    report = status_report(db_path, as_of=as_of)
    p = report["recommendation"]["preferred"]
    base = p["based_on_experiment_id"]
    diag = next(iter(report["diagnoses"].get(base, {}).values()), None) if base else None
    campaign = next((c for c in registries.rows(db_path, "campaigns") if base and c["experiment_id"] == base), None)
    offer = _row(db_path, "offers", campaign["offer_id"]) if campaign else None
    creative = next((c for c in registries.rows(db_path, "creatives")
                     if campaign and c["campaign_id"] == campaign["campaign_id"] and c["body"]), None)
    constraint, evidence = _constraint_summary(diag, p)
    return {
        "status": p["status"], "experiment_id": p["experiment_id"], "based_on_experiment_id": base,
        "campaign_id": campaign and campaign["campaign_id"],
        "current_constraint": constraint, "evidence": evidence,
        "highest_value_uncertainty": p["hypothesis"] or p["why_highest_value"],
        "variable": p["single_variable"], "control": p["control"], "variant": p["variant"],
        "primary_metric": p["primary_metric"],
        "keep_constant": _keep_constant(campaign, offer, creative, p["single_variable"]),
        "kill_condition": p["stop_condition"],
    }


def render_card(card: dict) -> str:
    head = f"{card['status']}: {card['experiment_id'] or '(new contract needed)'}"
    if card["based_on_experiment_id"] and card["based_on_experiment_id"] != card["experiment_id"]:
        head += f" · from {card['based_on_experiment_id']}"
    lines = ["NEXT EXPERIMENT  [RECOMMENDATION — requires human approval]", head]
    sections = (
        ("CURRENT CONSTRAINT", [card["current_constraint"]]), ("EVIDENCE", card["evidence"]),
        ("HIGHEST-VALUE UNCERTAINTY", [card["highest_value_uncertainty"]]),
        ("NEXT TEST", [f"Variable: {card['variable']}", f"Control: {card['control']}", f"Variant: {card['variant']}"]),
        ("PRIMARY METRIC", [card["primary_metric"]]),
        ("KEEP CONSTANT", [f"{k}: {v}" for k, v in card["keep_constant"].items()]),
        ("KILL CONDITION", [card["kill_condition"]]),
    )
    for title, body in sections:
        lines += ["", title] + [f"  {line}" for line in body if line]
    return "\n".join(lines)


def status_report(db_path: str, *, as_of: str | None = None) -> dict:
    as_of = as_of or date.today().isoformat()
    events = linked_events(db_path)
    metrics = compute_metrics(events)
    recommendation = recommend_next_experiment(db_path, as_of=as_of)
    minimums = _minimums(recommendation["experiments"])
    diagnoses: dict[str, dict[str, dict]] = {}
    for experiment_id, scoped in group_by(events, "experiment_id").items():
        t = totals(scoped)
        for path, ladder in LADDERS.items():
            if t.get(ladder[0], 0):
                diagnoses.setdefault(experiment_id, {})[path] = diagnose_funnel(
                    scoped, path, as_of=as_of, min_sample=minimums.get(experiment_id) or MIN_SAMPLE)
    campaigns = {k: money_graph_for_campaign(events, k) for k in group_by(events, "campaign_id") if k}
    payments = [e for e in events if e["event_type"] == "payment_received"]
    return {
        "as_of": as_of, "events": len(events), "synthetic_excluded": synthetic_count(db_path),
        "buyer_truth": truth_summary(buyer_evidence(db_path), events),
        "totals": metrics["totals"], "metrics": metrics["metrics"], "diagnoses": diagnoses,
        "by_channel": {k or "unknown": totals(v) for k, v in group_by(events, "channel").items()},
        "campaigns": campaigns,
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
    modes = {e["experiment_id"]: e.get("execution_mode") or "" for e in rec["experiments"]}
    lines = [
        "THEPLUS MARKETING ENGINEER",
        f"  [OBSERVED] {report['events']} effective events"
        + (f"; {synthetic} synthetic fixtures excluded" if synthetic else ""),
        f"  [OBSERVED] Revenue {_money(t['revenue_pence'])} from {t.get('payment_received', 0)} payments"
        f" · Pipeline {_money(t['pipeline_pence'])} · Spend {spend}",
        f"  [DERIVED]  ROAS {roas_text}",
        "",
        "1. What is happening?  [OBSERVED counts · DERIVED rates]",
    ]
    for channel, ct in sorted(report["by_channel"].items()):
        counts = ", ".join(f"{k} {v}" for k, v in sorted(ct.items())
                           if isinstance(v, int) and not isinstance(v, bool) and not k.endswith("_pence"))
        lines.append(f"   {channel}: {counts}")
    for experiment_id, paths in sorted(report["diagnoses"].items()):
        for diag in paths.values():
            lines += ["   " + line for line in render_diagnosis(experiment_id, diag, modes.get(experiment_id, ""))]

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
    lines += [f"   {e['experiment_id']}: {e.get('execution_mode') or 'preregistered'}, "
              f"{rec['supply'][e['experiment_id']]} frozen participants" for e in live] or ["   none with frozen supply"]
    lines.append("7. What have we learned?  [OBSERVED experiment decisions]")
    lines += [f"   {h['experiment_id']}: {h['decision'].upper()} at n={h['sample_size']}, "
              f"{h['primary_metric']}={h['observed_value']}" for h in rec["preferred"]["previous_experiments"] or []] \
        or ["   no experiment has concluded"]
    truth = report.get("buyer_truth")
    if truth:
        lines.append("BUYER TRUTH  [OBSERVED statements · INTERPRETED themes]")
        lines.append(f"   observations linked: {truth['observations']} ({truth['uninterpreted']} uninterpreted)")
        if best := truth.get("best_evidenced_problem"):
            lines.append(f"   best evidenced problem: {best['theme']} — {best['scope']['organisations']} independent "
                         f"organisations, confidence {best['scope']['confidence']}")
        if strong := truth.get("strongest_commercial_problem"):
            lines.append(f"   strongest commercial problem: {strong['theme']} — {strong['proposals']} proposals, "
                         f"{strong['customers']} customers, {_money(strong['observed_revenue_pence'])} revenue")
        for key, label in (("common_objection", "common objection"), ("buying_criterion", "buying criterion")):
            if found := truth.get(key):
                lines.append(f"   {label}: {found['theme']} — {found['organisations']} organisations")
        lines.append(f"   current uncertainty: {truth['current_uncertainty']}")
    p = rec["preferred"]
    lines.append("8. What should we test next?  [RECOMMENDATION — requires human approval]")
    lines.append(f"   {p['status']}: {p['experiment_id'] or '(new contract needed)'}")
    for field in ("hypothesis", "single_variable", "primary_metric", "sample_and_stopping_rule",
                  "why_highest_value", "stop_condition"):
        if p.get(field):
            lines.append(f"   {field}: {p[field]}")
    for alt in rec["alternatives"]:
        lines.append(f"   alternative {alt['status']} {alt.get('experiment_id') or ''}: {alt['not_preferred_because']}")
    return "\n".join(lines)
