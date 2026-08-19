#!/usr/bin/env python3
"""Scope gate — the engine must stay market-neutral.

The Digital Marketing Project may test any market. `EXP-ACQ-0001` happens to be UK
cyber/MSP. That is an experiment, not the architecture, so market-specific vocabulary
belongs under experiments/ and nowhere else in the reusable layer.

Docs may name the active experiment; the engine may not.

    python3 scripts/scope_gate.py           # check the repo
    python3 scripts/scope_gate.py --selftest
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

# The reusable layer. Anything here must work for a paid-media or SEO experiment
# without edits.
ENGINE_DIRS = ("src", "skills", "policies", "templates", "tests")

# Vocabulary that ties code to one market. Word-boundary matched to avoid false hits
# ("msp" inside another word, "cyber" in a URL is still a real hit and wanted).
MARKET_TERMS = (
    r"cyber\w*",
    r"\bMSPs?\b",
    r"managed service provider",
    r"CloudTech24",
    r"Netitude",
    r"Texaport",
    r"Transputec",
    r"Littlefish",
    r"Morcan",
    r"pen(etration)? test",
)
PATTERN = re.compile("|".join(MARKET_TERMS), re.IGNORECASE)

SCANNED_SUFFIXES = {".py", ".md", ".json", ".csv", ".yml", ".yaml", ".txt"}


def scan(root: Path) -> list[tuple[Path, int, str]]:
    hits: list[tuple[Path, int, str]] = []
    files_seen = 0
    for directory in ENGINE_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix not in SCANNED_SUFFIXES or "__pycache__" in path.parts:
                continue
            files_seen += 1
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                match = PATTERN.search(line)
                if match:
                    hits.append((path.relative_to(root), lineno, match.group(0)))
    # A scan that walked nothing is a failed run, not a pass.
    if files_seen < 10:
        raise SystemExit(f"scope gate scanned only {files_seen} files — wrong root?")
    return hits


def selftest() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        src.mkdir()
        for i in range(12):
            (src / f"mod{i}.py").write_text("clean = True\n", encoding="utf-8")
        assert scan(root) == [], "clean tree must pass"

        # Prove the gate fails: a guard never observed failing is decoration.
        (src / "leak.py").write_text("ICP = 'UK cybersecurity MSPs'\n", encoding="utf-8")
        hits = scan(root)
        assert len(hits) == 1, f"expected 1 hit, got {hits}"
        assert hits[0][0].name == "leak.py"

        # An experiment directory is out of scope and must not be flagged.
        exp = root / "experiments"
        exp.mkdir()
        (exp / "notes.md").write_text("CloudTech24 cyber teardown\n", encoding="utf-8")
        assert len(scan(root)) == 1, "experiments/ must be exempt"

        # Too small a tree must raise rather than report a clean pass.
        try:
            scan(root / "src" / "nonexistent")
        except SystemExit:
            pass
        else:  # pragma: no cover
            raise AssertionError("empty scan must fail loudly")
    print("scope_gate selftest: 5 assertions passed")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    root = Path(__file__).resolve().parents[1]
    hits = scan(root)
    if not hits:
        print(f"scope gate: OK — {', '.join(ENGINE_DIRS)} are market-neutral")
        return 0
    print("scope gate: FAILED — market-specific terms in the reusable engine layer:")
    for path, lineno, term in hits:
        print(f"  {path}:{lineno}  {term!r}")
    print("\nMove this into experiments/<EXP-ID>/ or generalise it.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
