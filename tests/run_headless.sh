#!/usr/bin/env bash
# Run the GUI-independent test-suite with FreeCAD's console application.
# Usage: tests/run_headless.sh [path-to-freecadcmd]
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
FCCMD="${1:-${FREECADCMD:-$(command -v freecadcmd || command -v FreeCADCmd || true)}}"
if [ -z "$FCCMD" ]; then
    echo "freecadcmd not found; pass its path as first argument" >&2
    exit 2
fi
OUT="$(mktemp)"
FF_REPO="$HERE" "$FCCMD" -c "import sys; sys.path.insert(0, '$HERE'); exec(open('$HERE/tests/test_headless.py').read())" >"$OUT" 2>&1 || true
grep -E '^(PASS|FAIL|ERROR|SUMMARY)' "$OUT" || { cat "$OUT"; exit 1; }
grep -q '^SUMMARY ok' "$OUT"
