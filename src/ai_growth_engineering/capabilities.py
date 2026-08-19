from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

STATUSES = ("IMPLEMENTED", "SPECIFIED", "HYPOTHESIS")

# The map lives at the repo root so it reads as architecture, not as a code detail.
DEFAULT_MAP = Path(__file__).resolve().parents[2] / "capability_map.json"


def load(path: str | Path | None = None) -> dict:
    with open(path or DEFAULT_MAP, encoding="utf-8") as handle:
        return json.load(handle)


def validate(data: dict) -> None:
    """Fail loudly on a malformed map. An empty or statusless map is a failed load,
    not a clean one — see the vacuous-pass trap in the project doctrine."""
    domains = data.get("domains") or {}
    if len(domains) < 8:
        raise ValueError(f"expected at least 8 domains, found {len(domains)}")
    for key, domain in domains.items():
        caps = domain.get("capabilities") or {}
        if not caps:
            raise ValueError(f"domain {key!r} declares no capabilities")
        for name, status in caps.items():
            if status not in STATUSES:
                raise ValueError(f"{key}.{name} has invalid status {status!r}")


def counts(data: dict) -> Counter:
    return Counter(
        status
        for domain in data["domains"].values()
        for status in domain["capabilities"].values()
    )


def render(data: dict) -> str:
    lines = []
    for key, domain in data["domains"].items():
        caps = domain["capabilities"]
        built = sum(1 for s in caps.values() if s == "IMPLEMENTED")
        lines.append(f"{domain['title']}  [{built}/{len(caps)} implemented]")
        for name, status in caps.items():
            lines.append(f"    {status:12} {name}")
    totals = counts(data)
    lines.append("")
    lines.append(
        "  ".join(f"{status}: {totals.get(status, 0)}" for status in STATUSES)
        + f"  |  total: {sum(totals.values())}"
    )
    return "\n".join(lines)
