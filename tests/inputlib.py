# SPDX-License-Identifier: LGPL-2.1-or-later
"""Real input for GUI tests: xdotool on X11, a virtual pointer/keyboard on Wayland.

On Wayland the tests run inside a headless sway (tests/run_wayland.sh) with FreeCAD
fullscreen at (0, 0), so the window-relative coordinates Qt reports are also the
compositor's coordinates. Input goes through tests/wayland/wlinput.py.
"""

import os
import socket
import subprocess

WAYLAND = bool(os.environ.get("WAYLAND_DISPLAY")) and os.environ.get("QT_QPA_PLATFORM", "") == "wayland"


def _run(args):
    subprocess.call(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


_conn = {"f": None}


def _wl(*cmd):
    if _conn["f"] is None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(os.environ["FF_WLINPUT"])
        _conn["f"] = s.makefile("rw")
    f = _conn["f"]
    f.write(" ".join(str(c) for c in cmd) + "\n")
    f.flush()
    return f.readline().strip()


def move(x, y):
    if WAYLAND:
        _wl("move", int(x), int(y))
    else:
        _run(["xdotool", "mousemove", str(int(x)), str(int(y))])


def down(button=1):
    if WAYLAND:
        _wl("down", button)
    else:
        _run(["xdotool", "mousedown", str(button)])


def up(button=1):
    if WAYLAND:
        _wl("up", button)
    else:
        _run(["xdotool", "mouseup", str(button)])


def click(button=1, repeat=1):
    for _ in range(repeat):
        down(button)
        up(button)


def key(name, mods=()):
    """Press a key; `name` is an X keysym name ('e', 'Return', 'ctrl+z' also works on X11)."""
    if "+" in name and not mods:
        parts = name.split("+")
        mods, name = parts[:-1], parts[-1]
    if WAYLAND:
        _wl("key", name, *[m.lower() for m in mods])
    else:
        _run(["xdotool", "key", "+".join(list(mods) + [name])])


def type_text(text):
    if WAYLAND:
        _wl("type", text)
    else:
        _run(["xdotool", "type", text])


def hold(mod, on=True):
    """Keep a modifier (shift/ctrl/alt) pressed while moving the mouse."""
    if WAYLAND:
        _wl("hold" if on else "release", mod)
    else:
        _run(["xdotool", "keydown" if on else "keyup", mod])


def wheel(n):
    """Scroll n notches (positive = away from the user)."""
    if WAYLAND:
        _wl("wheel", -n)
    else:
        for _ in range(abs(n)):
            _run(["xdotool", "click", "4" if n > 0 else "5"])


def focus_window(win_id=None):
    if not WAYLAND and win_id is not None:
        _run(["xdotool", "windowfocus", str(win_id)])
