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
from .models import ExperimentSpec
from .registry import (
    add_experiment,
    import_outreach,
    reply_rate_by_route,
    seed_registries,
    record_experiment_result,
    scoreboard,
    seed_prospects,
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
    from .command_center import serve_command_center

    serve_command_center(
        args.db, host=args.host, port=args.port, open_browser=args.open_browser
    )


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

    p = sub.add_parser("suppress"); dbarg(p)
    p.add_argument("--identity", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_suppress)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
