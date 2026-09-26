"""Markets as first-class objects, with evidence held in independent layers.

The project could rank prospects inside one market and could not compare two, so after a
run of exposures it could not say whether the message or the market was wrong. This module
answers the narrower question it can answer honestly: for one evidence layer, what has each
market shown, and is that comparable?

Invariants:
- Five layers - RESEARCH, ACCESS, DEMAND, COMMERCIAL, PAID - and a layer is TESTED only by
  an experiment linked to it at that layer. Nothing is inferred from another layer: a market
  with tested access and untested demand reads as exactly that.
- Counts are derived from the effective event log (corrections applied, synthetic excluded),
  never typed into the registry.
- One event type of one experiment counts in at most one layer. Counting the same fact as
  both access and demand would be inference wearing a second label.
- Comparison never pools across protocols. Two markets are compared only on a protocol both
  ran at that layer, each at or above the minimum exposure count; otherwise the answer is
  NOT_ENOUGH_EVIDENCE with the reason. It reports rates and never names a winner.
"""
from __future__ import annotations

from collections import defaultdict

from . import registries
from .funnel_events import effective_events

LAYERS = ("RESEARCH", "ACCESS", "DEMAND", "COMMERCIAL", "PAID")
UNTESTED, TESTED = "UNTESTED", "TESTED"
COMPARABLE, NOT_ENOUGH_EVIDENCE = "COMPARABLE", "NOT_ENOUGH_EVIDENCE"
DEFAULT_MIN_EXPOSURES = 30          # below this a rate is noise; override per call, floor 1


class MarketError(ValueError):
    pass


def _links(db_path: str, market_id: str) -> list[dict]:
    if not any(m["market_id"] == market_id for m in registries.rows(db_path, "markets")):
        raise MarketError(f"unknown market {market_id!r}")
    links = [l for l in registries.rows(db_path, "market_experiments") if l["market_id"] == market_id]
    seen: dict[tuple[str, str], str] = {}
    for link in links:
        for event_type in (link["exposure_event"], link["positive_event"]):
            key = (link["experiment_id"], event_type)
            if key in seen and seen[key] != link["layer"]:
                raise MarketError(
                    f"{link['experiment_id']} {event_type} is linked to both {seen[key]} and "
                    f"{link['layer']} in {market_id}; one fact counts in one layer")
            seen[key] = link["layer"]
    return links


def _counts(events: list[dict], experiment_id: str, event_type: str) -> int:
    return sum(int(e.get("quantity") or 1) for e in events
               if e["experiment_id"] == experiment_id and e["event_type"] == event_type)


def layer_evidence(db_path: str, market_id: str) -> dict:
    """{layer: {"status", "protocols": {protocol: {"experiments", "exposures", "positives"}}}}.

    Within one market, layer and protocol, experiments are summed: an identical protocol is
    what makes them the same measurement. Across protocols nothing is summed.
    """
    links = _links(db_path, market_id)
    events = effective_events(db_path)
    out = {layer: {"status": UNTESTED, "protocols": {}} for layer in LAYERS}
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for link in links:
        grouped[(link["layer"], link["protocol"])].append(link)
    for (layer, protocol), group in sorted(grouped.items()):
        exposures = sum(_counts(events, l["experiment_id"], l["exposure_event"]) for l in group)
        positives = sum(_counts(events, l["experiment_id"], l["positive_event"]) for l in group)
        out[layer]["protocols"][protocol] = {
            "experiments": sorted(l["experiment_id"] for l in group),
            "exposures": exposures, "positives": positives}
        out[layer]["status"] = TESTED
    return out


def compare(db_path: str, market_a: str, market_b: str, layer: str,
            min_exposures: int = DEFAULT_MIN_EXPOSURES) -> dict:
    """Compare two markets on one layer. Never pools protocols; never picks a winner."""
    if layer not in LAYERS:
        raise MarketError(f"layer must be one of {LAYERS}")
    if market_a == market_b:
        raise MarketError("a market compared with itself tells you nothing")
    min_exposures = max(1, int(min_exposures))
    a = layer_evidence(db_path, market_a)[layer]["protocols"]
    b = layer_evidence(db_path, market_b)[layer]["protocols"]
    result = {"layer": layer, "markets": [market_a, market_b], "min_exposures": min_exposures}

    missing = [m for m, side in ((market_a, a), (market_b, b)) if not side]
    if missing:
        return {**result, "verdict": NOT_ENOUGH_EVIDENCE,
                "reason": f"{layer} untested in {', '.join(missing)}", "comparisons": []}
    shared = sorted(set(a) & set(b))
    if not shared:
        return {**result, "verdict": NOT_ENOUGH_EVIDENCE,
                "reason": f"no protocol run at {layer} in both markets; different protocols are not pooled",
                "comparisons": []}

    comparisons = []
    for protocol in shared:
        sides = []
        for market, data in ((market_a, a[protocol]), (market_b, b[protocol])):
            n, k = data["exposures"], data["positives"]
            sides.append({"market": market, "experiments": data["experiments"], "exposures": n,
                          "positives": k, "rate": round(k / n, 4) if n else None})
        short = [s["market"] for s in sides if s["exposures"] < min_exposures]
        comparisons.append({"protocol": protocol, "sides": sides,
                            "verdict": NOT_ENOUGH_EVIDENCE if short else COMPARABLE,
                            "reason": (f"below {min_exposures} exposures: {', '.join(short)}"
                                       if short else "")})
    comparable = [c for c in comparisons if c["verdict"] == COMPARABLE]
    return {**result, "verdict": COMPARABLE if comparable else NOT_ENOUGH_EVIDENCE,
            "reason": "" if comparable else "every shared protocol is below the minimum sample",
            "comparisons": comparisons}
