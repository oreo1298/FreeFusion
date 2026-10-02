#!/usr/bin/env bash
# Run a GUI test natively on Wayland inside a headless sway (no Xwayland).
# Usage: TEST=gui_manip.py tests/run_wayland.sh [freecad-binary] [output-dir]
# Needs: sway, and python3 with pywayland + libxkbcommon for the virtual input device
# (tests/wayland/wlinput.py, used by tests/inputlib.py).
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
FC="${1:-$(command -v freecad || command -v FreeCAD)}"
OUT="${2:-${TMPDIR:-/tmp}/ff_wayland}"
mkdir -p "$OUT"
rm -rf "$OUT/profile" "$OUT"/*.png "$OUT/gui_log.txt"
RUNDIR="$(mktemp -d /tmp/ffwl.XXXX)"   # short path: the sway socket path must be < 108 chars
chmod 700 "$RUNDIR"
cat > "$RUNDIR/sway.cfg" <<'CFG'
output HEADLESS-1 resolution RES position 0 0 scale SCALE
default_border none
default_floating_border none
for_window [app_id=".*"] fullscreen enable
CFG
# FF_WL_SCALE=1.5 tests fractional HiDPI scaling (the layout stays 1600x1000 logical pixels)
SCALE="${FF_WL_SCALE:-1}"
RES="$(python3 -c "s=$SCALE; print('%dx%d' % (round(1600*s), round(1000*s)))")"
sed -i "s/RES/$RES/; s/SCALE/$SCALE/" "$RUNDIR/sway.cfg"
export XDG_RUNTIME_DIR="$RUNDIR"
WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 WLR_HEADLESS_OUTPUTS=1 \
    sway -c "$RUNDIR/sway.cfg" >"$OUT/sway.log" 2>&1 &
SWAY=$!
for _ in $(seq 50); do [ -S "$RUNDIR/wayland-1" ] && break; sleep 0.1; done
export WAYLAND_DISPLAY=wayland-1 SWAYSOCK="$(ls "$RUNDIR"/sway-ipc.*.sock)"
export FF_WLINPUT="$RUNDIR/input.sock"
python3 "$HERE/tests/wayland/wlinput.py" "$FF_WLINPUT" 1600 1000 >"$OUT/wlinput.log" 2>&1 &
INPUT=$!
for _ in $(seq 50); do [ -S "$FF_WLINPUT" ] && break; sleep 0.1; done
export QT_QPA_PLATFORM=wayland FF_OUT="$OUT" LANG=C.UTF-8
# AppImage builds ship an xkbcommon with a build-machine data path
[ -d /usr/share/X11/xkb ] && export XKB_CONFIG_ROOT=/usr/share/X11/xkb
unset DISPLAY
timeout "${TIMEOUT:-240}" env FREECAD="$FC" FREEFUSION_CONFIG="$OUT/profile" FREEFUSION_DIR="$HERE" \
    "$HERE/scripts/freefusion" --log-file "$OUT/freecad.log" "$HERE/tests/${TEST:-gui_smoke.py}" \
    >"$OUT/stdout.txt" 2>&1
kill $INPUT $SWAY 2>/dev/null
rm -rf "$RUNDIR"
grep -E "^(PASS|FAIL|EXCEPTION|SUMMARY|CONSOLE)" "$OUT/gui_log.txt" 2>/dev/null || { tail -40 "$OUT/stdout.txt"; exit 1; }
grep -q "^SUMMARY ok" "$OUT/gui_log.txt"
