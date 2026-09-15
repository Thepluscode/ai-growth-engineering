from __future__ import annotations

import argparse
import csv
from pathlib import Path

from . import capabilities
from .growthops import TARGETS
from .hiring_signal_connector import (
    DEFAULT_MIN_INTERVAL_HOURS,
    add_hiring_source,
    discover_hiring_sources,
    list_hiring_sources,
    pending_hiring_candidates,
    scan_saved_hiring_sources,
)
from .execution import access_result, cohort, record_invitation
from .funnel_events import (
    PROVENANCES, EventError, correct_event, effective_events, import_invitations,
    import_outreach_csv, record_event,
)
from .marketing_engineer import (
    campaign_graph, customer_graph, linked_events, next_experiment_card, recommend_next_experiment, render_card,
    render_customer, render_diagnosis, render_problems, render_status, status_report,
)
from .models import ExperimentSpec
from .registry import (
    add_experiment,
    import_outreach,
    reply_rate_by_route,
    seed_registries,
    record_experiment_result,
    scoreboard,
    seed_prospects,
    sourcing_funnel,
)
from .storage import connect, init_db
from .teardown import TeardownPacket


def _money(pence: int) -> str:
    return f"£{pence / 100:,.2f}"


def cmd_init(args: argparse.Namespace) -> None:
    init_db(args.db)
    print(f"initialised {args.db}")


def cmd_seed(args: argparse.Namespace) -> None:
    init_db(args.db)
    count = seed_prospects(args.db, args.csv_path)
    print(f"processed {count} prospect rows")


def cmd_scoreboard(args: argparse.Namespace) -> None:
    init_db(args.db)
    values = scoreboard(args.db)
    for key, target in TARGETS.items():
        actual = values[key]
        if key == "collected_revenue_pence":
            print(f"{key:28} {_money(actual):>12} / {_money(target)}")
        else:
            print(f"{key:28} {actual:>12} / {target}")
    # No target, and printed anyway: these are prospects nobody has qualified or
    # disqualified. They used to be counted as qualified, so leaving them off the
    # scoreboard would hide the queue rather than the inflation.
    print(f"{'unreviewed_prospects':28} {values['unreviewed_prospects']:>12}   (no target; not qualified)")


def cmd_sourcing_funnel(args: argparse.Namespace) -> None:
    """Register-to-identity conversion for one sourcing run, denominators intact."""
    result = sourcing_funnel(args.db, run_id=args.run_id)
    if result["run_id"] is None:
        print("no sourcing run recorded")
        return
    print(f"run {result['run_id']}  source {result['source']}")
    for step in result["steps"]:
        rate = "NOT ASKED" if step["rate"] is None else f"{step['rate']:.1%}"
        print(f"  {step['label']:<42} {step['numerator']:>5}/{step['denominator']:<5} {rate:>9}")
    compound = result["compound_rate"]
    print(f"  {'compound: register -> LinkedIn identity':<42} "
          f"{'':>5} {'':<5} {'NOT ASKED' if compound is None else f'{compound:.3%}':>9}")


def cmd_invitation_record(args: argparse.Namespace) -> None:
    """Record one observed invitation outcome. Access only — it reaches no other metric."""
    result = record_invitation(args.db, args.cohort_id, args.prospect_id, {
        "outcome": args.outcome, "submitted_at": args.submitted_at,
        "accepted_at": args.accepted_at, "note": args.note})
    print(f"{result['prospect_id']}: {result['outcome']}")


def cmd_access_result(args: argparse.Namespace) -> None:
    r = access_result(args.db, args.cohort_id)
    rate = "NOT ASKED" if r["accept_rate"] is None else f"{r['accept_rate']:.1%}"
    ci = "" if r["accept_rate_ci"] is None else (
        f"   Wilson 95% CI {r['accept_rate_ci'][0]:.1%}-{r['accept_rate_ci'][1]:.1%}")
    print(f"cohort {r['cohort_id']}  size {r['cohort_size']}")
    print(f"  submitted {r['invitations_submitted']}  accepted {r['accepted']}  "
          f"pending {r['pending']}  blocked {r['blocked']}  not submitted {r['not_submitted']}")
    print(f"  accept rate {rate}{ci}   (denominator: invitations submitted)")
    for label, key in (("identity sourcing", "by_identity_sourcing"),
                       ("ownership structure", "by_ownership_structure")):
        print(f"  by {label}:")
        for name, row in sorted(r[key].items()):
            sub = "n/a" if row["rate"] is None else f"{row['rate']:.1%}"
            print(f"    {name:<18} {row['accepted']:>3}/{row['submitted']:<3} {sub:>7}"
                  f"   (in cohort {row['in_cohort']})")
    print(f"  VERDICT: {r['verdict']} — {r['reason']}")
    if "expansion" in r:
        e = r["expansion"]
        print(f"  expansion required: {e['additional_accepts_required']} more accepts at "
              f"{e['observed_accept_rate']:.1%} = "
              f"{e['additional_verified_identities_required']} more verified identities")
    print("\n  acceptance tests ACCESS only: it is not demand, not a reply, not pain, not revenue")


def cmd_cohort(args: argparse.Namespace) -> None:
    c = cohort(args.db, args.cohort_id)
    print(f"cohort {c['cohort_id']}: {c['size']} accounts")
    for m in c["members"]:
        print(f"  {m['prospect_id']:>3}  {m['company'][:34]:<36} {m['identity_sourcing']:<14}"
              f" {m['ownership_structure']:<16} {m['outcome']}")


def cmd_recipient_split(args: argparse.Namespace) -> None:
    """The rates EXP-ACQ-0001 needed and did not have, never blended."""
    init_db(args.db)
    routes = reply_rate_by_route(args.db)
    print(f"{'route':>28}  {'sent':>5}  {'replies':>7}  rate")
    for name, row in sorted(routes.items()):
        rate = f"{row['replies'] / row['sent']:.1%}" if row["sent"] else "n/a"
        print(f"{name:>28}  {row['sent']:>5}  {row['replies']:>7}  {rate}")
    unknown = [n for n in routes if "unknown" in n or "unclassified" in n]
    if unknown:
        # Loud, because an unattributed send is the defect this command exists to catch.
        print(f"\nno conclusion available for: {', '.join(sorted(unknown))}")


def cmd_gate_check(args: argparse.Namespace) -> None:
    values = scoreboard(args.db)
    failures = []
    for key, target in TARGETS.items():
        if values[key] < target:
            failures.append((key, values[key], target))
    if failures:
        print("REVENUE GATE: NOT MET")
        for key, actual, target in failures:
            print(f"- {key}: {actual}/{target}")
        raise SystemExit(2)
    print("REVENUE GATE: MET")


def cmd_teardown(args: argparse.Namespace) -> None:
    init_db(args.db)
    packet = TeardownPacket(args.company, args.observation, args.hypothesis, args.metric)
    with connect(args.db) as con:
        con.execute(
            "INSERT INTO teardowns(company, observation, hypothesis, metric) VALUES (?, ?, ?, ?)",
            (args.company, args.observation, args.hypothesis, args.metric),
        )
    out = Path(args.output or f"teardown-{args.company.lower().replace(' ', '-')}.md")
    out.write_text(packet.markdown(), encoding="utf-8")
    print(out)


def cmd_experiment_add(args: argparse.Namespace) -> None:
    init_db(args.db)
    add_experiment(
        args.db,
        ExperimentSpec(
            experiment_id=args.experiment_id,
            hypothesis=args.hypothesis,
            primary_metric=args.primary_metric,
            success_threshold=args.success_threshold,
            review_threshold=args.review_threshold,
            minimum_sample=args.minimum_sample,
            evidence_ids=tuple(args.evidence_id),
            market=args.market,
            buyer=args.buyer,
            problem=args.problem,
            channel=args.channel,
            control=args.control,
            variant=args.variant,
            secondary_metrics=tuple(args.secondary_metric),
            economic_metric=args.economic_metric,
            budget_pence=args.budget_pence,
            start_date=args.start_date,
            end_date=args.end_date,
            variable=args.variable,
        ),
    )
    print(f"preregistered {args.experiment_id}")


def cmd_experiment_result(args: argparse.Namespace) -> None:
    decision = record_experiment_result(
        args.db,
        args.experiment_id,
        args.sample_size,
        args.observed_value,
        args.learning,
    )
    print(decision)


def cmd_outreach_record(args: argparse.Namespace) -> None:
    init_db(args.db)
    with connect(args.db) as con:
        suppressed = con.execute("SELECT 1 FROM suppression WHERE identity = ?", (args.identity,)).fetchone()
        if suppressed:
            raise SystemExit("DENIED: identity is suppressed")
        con.execute(
            """INSERT INTO outreach(
                 company, sent_at, meaningful_reply, discovery, diagnostic_proposed,
                 proposal, paid, collected_revenue_pence, notes
               ) VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?)""",
            (
                args.company, int(args.meaningful_reply), int(args.discovery),
                int(args.diagnostic_proposed), int(args.proposal), int(args.paid),
                round(args.collected_revenue * 100), args.notes,
            ),
        )
    print(f"recorded outreach for {args.company}")


def cmd_suppress(args: argparse.Namespace) -> None:
    init_db(args.db)
    with connect(args.db) as con:
        con.execute("INSERT OR REPLACE INTO suppression(identity, reason) VALUES (?, ?)", (args.identity, args.reason))
    print(f"suppressed {args.identity}")


def cmd_source_add(args: argparse.Namespace) -> None:
    saved = add_hiring_source(
        args.db,
        {"prospect_id": args.prospect_id, "source_url": args.source_url, "label": args.label},
    )
    print(f"saved source {saved['source_id']} for {saved['company']}: {saved['source_url']}")


def cmd_discover_sources(args: argparse.Namespace) -> None:
    """Find each prospect's careers page and report which publish a commercial role."""
    result = discover_hiring_sources(
        args.db,
        pause_seconds=args.pause_seconds,
        include_disqualified=args.include_disqualified,
        save=args.save,
        limit=args.limit,
    )
    order = ["commercial_role_published", "no_commercial_role", "no_careers_link",
             "careers_page_unreachable", "site_unreachable"]
    for row in result["results"]:
        if row["outcome"] == "commercial_role_published":
            titles = "; ".join(row["titles"])
            print(f"  HIRING  {row['company']}: {row['careers_url']} -> {titles} [{row['detail']}]")
    print(f"\n{result['prospect_count']} prospects checked at {result['checked_at']}")
    for name in order:
        count = result["outcomes"].get(name, 0)
        if count:
            print(f"  {name:26} {count}")
    if not args.save:
        print("\nnothing saved; re-run with --save to keep the sources that published a role")


def cmd_sweep_sources(args: argparse.Namespace) -> None:
    """Unattended entry point. Exit non-zero only when nothing could be scanned."""
    sources = list_hiring_sources(args.db)
    if not sources:
        print("no saved sources; nothing to sweep")
        return
    result = scan_saved_hiring_sources(
        args.db,
        min_interval_hours=args.min_interval_hours,
        persist_candidates=True,
        pause_seconds=args.pause_seconds,
        max_age_days=args.max_age_days,
    )
    print(
        f"{result['scanned_at']} "
        f"scanned {result['scanned_source_count']}/{result['source_count']} sources "
        f"(skipped {result['skipped_source_count']}, failed {result['failed_source_count']}) "
        f"-> {result['candidate_count']} candidates, {result['stored_candidate_count']} new"
    )
    for row in result["sources"]:
        if row["error"]:
            print(f"  FAILED  {row['company']}: {row['error']}")
        elif row["skipped"]:
            print(f"  skipped {row['company']}: {row['skipped']}")
        else:
            print(f"  ok      {row['company']}: {row['candidate_count']} candidates")
    pending = pending_hiring_candidates(args.db)
    print(f"{len(pending)} candidates awaiting human review; nothing was recorded as a signal")


def cmd_import_outreach(args: argparse.Namespace) -> None:
    imported, skipped = import_outreach(args.db, args.csv_path)
    print(f"imported {imported} sends, skipped {skipped} (already present or incomplete)")


def cmd_seed_registries(args: argparse.Namespace) -> None:
    init_db(args.db)
    loaded = seed_registries(args.db, args.seeds_path)
    waiting = loaded.pop("hiring_sources_awaiting_prospects", 0)
    if not loaded:
        print("registries already current, nothing loaded")
    else:
        for name, count in sorted(loaded.items()):
            print(f"loaded {count} into {name}")
    if waiting:
        print(f"{waiting} hiring sources not loaded: this store has no prospects yet")


def cmd_capability_map(args: argparse.Namespace) -> None:
    data = capabilities.load(args.map_path)
    capabilities.validate(data)
    print(capabilities.render(data))


def cmd_command_center(args: argparse.Namespace) -> None:
    import errno
    import urllib.request

    from .command_center import serve_command_center

    try:
        serve_command_center(
            args.db, host=args.host, port=args.port, open_browser=args.open_browser
        )
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        # The traceback for this is forty lines of socketserver internals ending in
        # "Address already in use", which does not tell you the most likely cause:
        # the interface you are trying to start is already open.
        url = f"http://{args.host}:{args.port}"
        try:
            with urllib.request.urlopen(f"{url}/healthz", timeout=2) as response:
                ours = b'"mode":"human_gated"' in response.read()
        except Exception:
            ours = False
        if ours:
            raise SystemExit(f"already running - open {url}")
        raise SystemExit(
            f"{args.host}:{args.port} is taken by something else. "
            f"Start this on another port: --port {args.port + 1}"
        )


def cmd_events_import_outreach(args: argparse.Namespace) -> None:
    result = import_outreach_csv(args.db, args.csv_path, experiment_id=args.experiment_id,
                                 campaign_id=args.campaign_id, arm=args.arm)
    print(f"{result['inserted']} events appended, {result['already_present']} already present, "
          f"{result['incomplete_rows']} rows incomplete")


def cmd_events_import_invitations(args: argparse.Namespace) -> None:
    result = import_invitations(args.db, args.cohort_id, experiment_id=args.experiment_id)
    print(f"{result['members']} cohort members: {result['inserted']} events appended, "
          f"{result['corrected']} events corrected")


def cmd_event_record(args: argparse.Namespace) -> None:
    """Record one observed commercial fact — a meeting, proposal, win or payment."""
    values = {name: getattr(args, name) for name in (
        "event_type", "occurred_at", "source", "source_record_id", "provenance", "company",
        "company_id", "person_id", "campaign_id", "creative_id", "audience_id", "channel",
        "experiment_id", "arm", "value_pence", "currency", "quantity")}
    values["metadata"] = {"note": args.note} if args.note else {}
    try:
        result = record_event(args.db, values)
    except EventError as exc:
        raise SystemExit(f"REFUSED ({exc.code}): {exc}")
    print(f"{result['event_id']} {result['event_type']} "
          f"{'appended' if result['inserted'] else 'already present, nothing appended'}")


def cmd_event_correct(args: argparse.Namespace) -> None:
    try:
        result = correct_event(args.db, args.event_id, args.reason)
    except EventError as exc:
        raise SystemExit(f"REFUSED ({exc.code}): {exc}")
    print(f"{result['event_id']} voids {result['corrects_event_id']}")


def cmd_marketing_engineer(args: argparse.Namespace) -> None:
    import json

    if args.action == "status":
        report = status_report(args.db, as_of=args.as_of or None)
        print(json.dumps(report, indent=2, default=str) if args.json else render_status(report))
    elif args.action == "diagnose":
        report = status_report(args.db, as_of=args.as_of or None)
        diagnoses = {k: v for k, v in report["diagnoses"].items()
                     if not args.experiment_id or k == args.experiment_id}
        if not diagnoses:
            raise SystemExit(f"no funnel events for {args.experiment_id or 'any experiment'}")
        if args.json:
            print(json.dumps(diagnoses, indent=2, default=str))
            return
        modes = {e["experiment_id"]: e.get("execution_mode") or "" for e in report["recommendation"]["experiments"]}
        for experiment_id, paths in sorted(diagnoses.items()):
            for diag in paths.values():
                print("\n".join(render_diagnosis(experiment_id, diag, modes.get(experiment_id, ""))))
    elif args.action == "change":
        from datetime import date

        from .change_diagnosis import ChangeError, default_windows, diagnose_change, render_change

        as_of = args.as_of or date.today().isoformat()
        if bool(args.baseline) != bool(args.comparison):
            raise SystemExit("change needs both --baseline and --comparison (START:END), or neither for the declared "
                             "status windows")
        if args.baseline:
            baseline, comparison = ({"start": text.partition(":")[0], "end": text.partition(":")[2]}
                                    for text in (args.baseline, args.comparison))
        else:
            baseline, comparison = default_windows(as_of)
        for window, arm in ((baseline, args.baseline_arm), (comparison, args.comparison_arm)):
            window.update(experiment_id=args.experiment_id, campaign_id=args.campaign_id, arm=arm)
            if args.segment:
                dimension, _, value = args.segment.partition("=")
                window["segment"] = (dimension, value)
        try:
            diagnosis = diagnose_change(args.db, baseline, comparison, as_of=as_of)
        except ChangeError as exc:
            raise SystemExit(f"REFUSED: {exc}")
        print(json.dumps(diagnosis, indent=2, default=str) if args.json else render_change(diagnosis))
    elif args.action in ("segments", "target", "offer", "route"):
        from . import segments

        as_of = args.as_of or None
        if args.action == "segments":
            evidence = segments.buyer_evidence(args.db)
            result = segments.compare_segments(segments.segment_performance(
                linked_events(args.db), evidence, args.dimension, as_of=as_of or segments.date.today().isoformat(),
                registry=segments.load_registry(args.db), experiment_id=args.experiment_id or None))
            print(json.dumps(result, indent=2, default=str) if args.json else segments.render_segments(result))
            return
        recommend = {"target": segments.recommend_target_segment, "offer": segments.recommend_offer,
                     "route": segments.recommend_acquisition_route}[args.action]
        result = recommend(args.db, as_of=as_of)
        print(json.dumps(result, indent=2, default=str) if args.json else segments.render_decision(args.action, result))
    elif args.action == "customer":
        if not args.company:
            raise SystemExit("customer needs --company")
        graph = customer_graph(args.db, args.company)
        print(json.dumps(graph, indent=2, default=str) if args.json else render_customer(graph))
    elif args.action == "problems":
        from .buyer_truth import buyer_evidence, problem_revenue

        views = problem_revenue(buyer_evidence(args.db), linked_events(args.db))
        print(json.dumps(views, indent=2, default=str) if args.json else render_problems(views))
    elif args.action == "next-experiment":
        card = next_experiment_card(args.db, as_of=args.as_of or None)
        if args.json:
            rec = recommend_next_experiment(args.db, as_of=args.as_of or None)
            print(json.dumps({"card": card, **{k: rec[k] for k in ("preferred", "alternatives", "findings")}},
                             indent=2, default=str))
        else:
            print(render_card(card))
    else:
        if bool(args.company) == bool(args.campaign_id):
            raise SystemExit("money-graph needs exactly one of --company or --campaign-id")
        try:
            graph = (customer_graph(args.db, args.company) if args.company
                     else campaign_graph(args.db, args.campaign_id))
        except ValueError as exc:
            raise SystemExit(f"REFUSED: {exc}")
        print(json.dumps(graph, indent=2, default=str))


def cmd_evidence_record(args: argparse.Namespace) -> None:
    import json

    from .buyer_truth import BuyerTruthError, record_commercial_evidence

    try:
        result = record_commercial_evidence(
            args.db, statement=args.statement, categories=args.category, source=args.source,
            source_record_id=args.source_record_id, occurred_at=args.occurred_at, provenance=args.provenance,
            company=args.company, person_id=args.person_id, source_event_id=args.source_event_id,
            experiment_id=args.experiment_id, campaign_id=args.campaign_id, offer_id=args.offer_id,
            verbatim=not args.paraphrase)
    except BuyerTruthError as exc:
        raise SystemExit(f"REFUSED ({exc.code}): {exc}")
    print(json.dumps(result, indent=2))


def cmd_evidence_interpret(args: argparse.Namespace) -> None:
    from .buyer_truth import BuyerTruthError, interpret

    try:
        result = interpret(args.db, args.link_id, theme=args.theme, interpretation=args.interpretation,
                           confidence=args.confidence, interpreted_by=args.by)
    except BuyerTruthError as exc:
        raise SystemExit(f"REFUSED ({exc.code}): {exc}")
    print(f"{result['interpretation_id']} reads {result['link_id']} as {result['theme']}")


def cmd_experiment_backfill_variable(args: argparse.Namespace) -> None:
    from .registry import backfill_variable

    try:
        result = backfill_variable(args.db, args.experiment_id, args.variable, args.source, args.note)
    except ValueError as exc:
        raise SystemExit(f"REFUSED: {exc}")
    print(f"{result['experiment_id']}: variable = {result['variable']} ({result['variable_metadata_source']})")


def cmd_events_import_stripe(args: argparse.Namespace) -> None:
    import json

    from .adapters import StripeAdapter, ingest

    with open(args.json_path, encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        records = data["data"] if data.get("object") == "list" else [data]
    else:
        records = data
    print(json.dumps(ingest(args.db, StripeAdapter(), records), indent=2))


def cmd_adapter_specs(args: argparse.Namespace) -> None:
    from .adapters import render_specs

    print(render_specs(args.platform))


def cmd_experiment_execution_mode(args: argparse.Namespace) -> None:
    from .registry import set_execution_mode

    try:
        set_execution_mode(args.db, args.experiment_id, args.mode, args.reason)
    except ValueError as exc:
        raise SystemExit(f"REFUSED: {exc}")
    print(f"{args.experiment_id}: {args.mode}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="age",
        description="AI Growth Engineering layer for the Digital Marketing Project",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def dbarg(p: argparse.ArgumentParser) -> None:
        p.add_argument("--db", default=".age/growth.db")

    p = sub.add_parser("init"); dbarg(p); p.set_defaults(func=cmd_init)
    p = sub.add_parser("seed-prospects"); dbarg(p); p.add_argument("csv_path"); p.set_defaults(func=cmd_seed)
    p = sub.add_parser("scoreboard"); dbarg(p); p.set_defaults(func=cmd_scoreboard)
    p = sub.add_parser("gate-check"); dbarg(p); p.set_defaults(func=cmd_gate_check)
    p = sub.add_parser("recipient-split"); dbarg(p); p.set_defaults(func=cmd_recipient_split)
    p = sub.add_parser("import-outreach"); dbarg(p); p.add_argument("csv_path")
    p.set_defaults(func=cmd_import_outreach)
    p = sub.add_parser("seed-registries"); dbarg(p)
    p.add_argument("seeds_path", nargs="?", default="seeds/registries.json")
    p.set_defaults(func=cmd_seed_registries)
    p = sub.add_parser("capability-map")
    p.add_argument("--map-path", default=None)
    p.set_defaults(func=cmd_capability_map)

    p = sub.add_parser("command-center"); dbarg(p)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--open-browser", action="store_true")
    p.set_defaults(func=cmd_command_center)

    p = sub.add_parser("teardown"); dbarg(p)
    p.add_argument("--company", required=True)
    p.add_argument("--observation", required=True)
    p.add_argument("--hypothesis", required=True)
    p.add_argument("--metric", required=True)
    p.add_argument("--output")
    p.set_defaults(func=cmd_teardown)

    p = sub.add_parser("experiment-add"); dbarg(p)
    p.add_argument("--experiment-id", required=True)
    p.add_argument("--hypothesis", required=True)
    p.add_argument("--primary-metric", required=True)
    p.add_argument("--success-threshold", type=float, required=True)
    p.add_argument("--review-threshold", type=float, required=True)
    p.add_argument("--minimum-sample", type=int, required=True)
    p.add_argument("--evidence-id", action="append", default=[])
    p.add_argument("--market", default="")
    p.add_argument("--buyer", default="")
    p.add_argument("--problem", default="")
    p.add_argument("--channel", default="")
    p.add_argument("--control", default="")
    p.add_argument("--variant", default="")
    p.add_argument("--variable", default="", help="the one variable control and variant differ on")
    p.add_argument("--secondary-metric", action="append", default=[])
    p.add_argument("--economic-metric", default="")
    p.add_argument("--budget-pence", type=int, default=0)
    p.add_argument("--start-date", default="")
    p.add_argument("--end-date", default="")
    p.set_defaults(func=cmd_experiment_add)

    p = sub.add_parser("experiment-result"); dbarg(p)
    p.add_argument("--experiment-id", required=True)
    p.add_argument("--sample-size", type=int, required=True)
    p.add_argument("--observed-value", type=float, required=True)
    p.add_argument("--learning", default="")
    p.set_defaults(func=cmd_experiment_result)

    p = sub.add_parser("outreach-record"); dbarg(p)
    p.add_argument("--company", required=True)
    p.add_argument("--identity", required=True)
    p.add_argument("--meaningful-reply", action="store_true")
    p.add_argument("--discovery", action="store_true")
    p.add_argument("--diagnostic-proposed", action="store_true")
    p.add_argument("--proposal", action="store_true")
    p.add_argument("--paid", action="store_true")
    p.add_argument("--collected-revenue", type=float, default=0.0)
    p.add_argument("--notes", default="")
    p.set_defaults(func=cmd_outreach_record)

    p = sub.add_parser("source-add"); dbarg(p)
    p.add_argument("--prospect-id", type=int, required=True)
    p.add_argument("--source-url", required=True)
    p.add_argument("--label", default="")
    p.set_defaults(func=cmd_source_add)

    p = sub.add_parser("discover-sources"); dbarg(p)
    p.add_argument("--save", action="store_true",
                   help="keep a source for each prospect that published a commercial role")
    p.add_argument("--pause-seconds", type=float, default=1.5)
    p.add_argument("--include-disqualified", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.set_defaults(func=cmd_discover_sources)

    p = sub.add_parser("sweep-sources"); dbarg(p)
    p.add_argument("--min-interval-hours", type=float, default=DEFAULT_MIN_INTERVAL_HOURS,
                   help="skip a source fetched more recently than this (default: %(default)s)")
    p.add_argument("--pause-seconds", type=float, default=2.0,
                   help="wait between requests that go out (default: %(default)s)")
    p.add_argument("--max-age-days", type=int, default=45)
    p.set_defaults(func=cmd_sweep_sources)

    p = sub.add_parser("sourcing-funnel"); dbarg(p)
    p.add_argument("--run-id", default=None, help="default: the most recent run")
    p.set_defaults(func=cmd_sourcing_funnel)

    p = sub.add_parser("cohort"); dbarg(p)
    p.add_argument("--cohort-id", default="EXP-ACQ-0003")
    p.set_defaults(func=cmd_cohort)

    p = sub.add_parser("invitation-record"); dbarg(p)
    p.add_argument("--cohort-id", default="EXP-ACQ-0003")
    p.add_argument("--prospect-id", type=int, required=True)
    p.add_argument("--outcome", required=True,
                   choices=["not_submitted", "pending", "accepted", "withdrawn",
                            "restricted", "undeliverable"])
    p.add_argument("--submitted-at", default="")
    p.add_argument("--accepted-at", default="")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_invitation_record)

    p = sub.add_parser("access-result"); dbarg(p)
    p.add_argument("--cohort-id", default="EXP-ACQ-0003")
    p.set_defaults(func=cmd_access_result)

    p = sub.add_parser("suppress"); dbarg(p)
    p.add_argument("--identity", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_suppress)

    p = sub.add_parser("events-import-outreach"); dbarg(p); p.add_argument("csv_path")
    p.add_argument("--experiment-id", required=True)
    p.add_argument("--campaign-id", default="")
    p.add_argument("--arm", default="")
    p.set_defaults(func=cmd_events_import_outreach)

    p = sub.add_parser("events-import-invitations"); dbarg(p)
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--experiment-id", default="")
    p.set_defaults(func=cmd_events_import_invitations)

    p = sub.add_parser("event-record"); dbarg(p)
    p.add_argument("--event-type", required=True)
    p.add_argument("--occurred-at", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--source-record-id", required=True)
    p.add_argument("--provenance", default="operator_recorded", choices=PROVENANCES)
    for name in ("company", "person-id", "campaign-id", "creative-id", "audience-id", "channel",
                 "experiment-id", "arm", "currency", "note"):
        p.add_argument(f"--{name}", default="")
    p.add_argument("--company-id", type=int, default=None)
    p.add_argument("--value-pence", type=int, default=0)
    p.add_argument("--quantity", type=int, default=1)
    p.set_defaults(func=cmd_event_record)

    p = sub.add_parser("event-correct"); dbarg(p)
    p.add_argument("--event-id", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_event_correct)

    p = sub.add_parser("marketing-engineer"); dbarg(p)
    p.add_argument("action", choices=["status", "diagnose", "next-experiment", "money-graph", "customer", "problems",
                                      "segments", "target", "offer", "route", "change"])
    p.add_argument("--baseline", default="", help="change: START:END (ISO dates)")
    p.add_argument("--comparison", default="", help="change: START:END (ISO dates)")
    p.add_argument("--baseline-arm", default="")
    p.add_argument("--comparison-arm", default="")
    p.add_argument("--segment", default="", help="change: dimension=value")
    p.add_argument("--dimension", default="acquisition_route",
                   help="icp, buyer_role, audience_type, offer, price, campaign, experiment, channel, "
                        "recipient_route, acquisition_route")
    p.add_argument("--company", default="")
    p.add_argument("--campaign-id", default="")
    p.add_argument("--experiment-id", default="")
    p.add_argument("--as-of", default="", help="YYYY-MM-DD; defaults to today")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_marketing_engineer)

    p = sub.add_parser("experiment-execution-mode"); dbarg(p)
    p.add_argument("--experiment-id", required=True)
    p.add_argument("--mode", required=True, choices=["PREREGISTERED", "DESCRIPTIVE_FROZEN_COHORT"])
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_experiment_execution_mode)

    p = sub.add_parser("experiment-backfill-variable"); dbarg(p)
    p.add_argument("--experiment-id", required=True)
    p.add_argument("--variable", required=True)
    p.add_argument("--source", required=True,
                   choices=["declared_at_registration", "retrospective_from_preregistration"])
    p.add_argument("--note", required=True)
    p.set_defaults(func=cmd_experiment_backfill_variable)

    p = sub.add_parser("events-import-stripe"); dbarg(p); p.add_argument("json_path")
    p.set_defaults(func=cmd_events_import_stripe)

    p = sub.add_parser("evidence-record"); dbarg(p)
    p.add_argument("--statement", required=True, help="the buyer's words, verbatim unless --paraphrase")
    p.add_argument("--category", action="append", required=True, help="repeat for each category it establishes")
    p.add_argument("--source", required=True)
    p.add_argument("--source-record-id", required=True)
    p.add_argument("--occurred-at", required=True)
    p.add_argument("--provenance", default="operator_recorded", choices=PROVENANCES)
    for name in ("company", "person-id", "source-event-id", "experiment-id", "campaign-id", "offer-id"):
        p.add_argument(f"--{name}", default="")
    p.add_argument("--paraphrase", action="store_true", help="a source-backed paraphrase, not the buyer's words")
    p.set_defaults(func=cmd_evidence_record)

    p = sub.add_parser("evidence-interpret"); dbarg(p)
    p.add_argument("--link-id", required=True)
    p.add_argument("--theme", required=True)
    p.add_argument("--interpretation", required=True)
    p.add_argument("--confidence", type=float, required=True)
    p.add_argument("--by", required=True)
    p.set_defaults(func=cmd_evidence_interpret)

    p = sub.add_parser("adapter-specs")
    p.add_argument("--platform", default="")
    p.set_defaults(func=cmd_adapter_specs)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
