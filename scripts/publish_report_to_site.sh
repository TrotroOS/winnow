#!/usr/bin/env bash
# Copy the newest logs/report_*.html to site/reports/latest.html for optional Vercel deploy.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="${WINNOW_LOGS_DIR:-$ROOT/logs}"
DEST="$ROOT/site/reports"
mkdir -p "$DEST"
shopt -s nullglob
reports=("$LOGS"/report_*.html)
if ((${#reports[@]} == 0)); then
  echo "no report_*.html in $LOGS" >&2
  exit 1
fi
latest="$(ls -t "${reports[@]}" | head -1)"
cp "$latest" "$DEST/latest.html"
echo "published: $DEST/latest.html (from $latest)"