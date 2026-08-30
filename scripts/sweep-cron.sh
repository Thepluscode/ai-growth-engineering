#!/usr/bin/env bash
# Install, show or remove the daily source-sweep cron entry.
#
#   scripts/sweep-cron.sh install   # add or replace the entry
#   scripts/sweep-cron.sh show      # print the entry, if any
#   scripts/sweep-cron.sh remove    # take it out again
#
# The entry is greppable by its marker so install is idempotent and removal is
# exact. It records nothing as a signal: a sweep stores candidates as pending
# proposals and a human still reviews them.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-/opt/homebrew/bin/python3}"
MARKER="# age:sweep-sources"

read -r -d '' ENTRY <<ENTRY_END || true
$MARKER Revenue intelligence source sweep (FEATURE_TRACKER.md). Daily 07:00.
$MARKER Records NOTHING as a signal: candidates land as pending proposals for review.
$MARKER --min-interval-hours 20 means a re-run cannot re-fetch a careers page the same
$MARKER day, so a crash-looping schedule cannot turn into a crawl.
0 7 * * * cd $ROOT && mkdir -p $ROOT/.age/cron && PYTHONPATH=$ROOT/src $PY -m ai_growth_engineering.cli sweep-sources --db $ROOT/.age/growth.db --min-interval-hours 20 --pause-seconds 2 >> $ROOT/.age/cron/sweep.log 2>&1 $MARKER
ENTRY_END

current() { crontab -l 2>/dev/null || true; }
without_entry() { current | grep -v -F "$MARKER" || true; }

case "${1:-show}" in
  install)
    [ -x "$PY" ] || { echo "python not found at $PY (set PYTHON=...)" >&2; exit 1; }
    { without_entry; echo "$ENTRY"; } | crontab -
    echo "installed:"; crontab -l | grep -F "$MARKER"
    ;;
  remove)
    without_entry | crontab -
    echo "removed; remaining entries with the marker: $(current | grep -c -F "$MARKER" || true)"
    ;;
  show)
    if current | grep -q -F "$MARKER"; then current | grep -F "$MARKER"; else echo "not installed"; fi
    ;;
  *) echo "usage: $0 {install|show|remove}" >&2; exit 2 ;;
esac
