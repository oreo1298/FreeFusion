#!/usr/bin/env bash
# Run the GUI smoke test under a virtual X server.
# Usage: tests/run_gui.sh [freecad-binary] [output-dir] [managed|plain]
#   managed: start through scripts/freefusion (own profile, like end users)
#   plain:   load the add-on into a stock FreeCAD profile
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
FC="${1:-$(command -v freecad || command -v FreeCAD)}"
OUT="${2:-${TMPDIR:-/tmp}/ff_gui}"
MODE="${3:-managed}"
mkdir -p "$OUT"
rm -rf "$OUT/profile" "$OUT"/*.png "$OUT/gui_log.txt"
export FF_OUT="$OUT" LANG=C.UTF-8 QT_QPA_PLATFORM=xcb
if [ "$MODE" = managed ]; then
    CMD=(env FREECAD="$FC" FREEFUSION_CONFIG="$OUT/profile" FREEFUSION_DIR="$HERE" "$HERE/scripts/freefusion")
else
    mkdir -p "$OUT/profile"
    CMD=("$FC" -M "$HERE" -u "$OUT/profile/user.cfg")
fi
timeout 240 xvfb-run -a -s "-screen 0 1600x1000x24" "${CMD[@]}" \
    --log-file "$OUT/freecad.log" "$HERE/tests/gui_smoke.py" >"$OUT/stdout.txt" 2>&1
grep -E "^(PASS|FAIL|EXCEPTION|SUMMARY|CONSOLE)" "$OUT/gui_log.txt" 2>/dev/null || { tail -40 "$OUT/stdout.txt"; exit 1; }
grep -q "^SUMMARY ok" "$OUT/gui_log.txt"
