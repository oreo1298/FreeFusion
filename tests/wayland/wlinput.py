#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Persistent virtual pointer + keyboard for Wayland GUI tests (sway/wlroots).

Started by tests/run_wayland.sh with the system python (needs `pywayland` and
libxkbcommon). Reads one command per line on a unix socket and answers "ok":

  move X Y | down B | up B | wheel N | key NAME [MOD...] | hold MOD | release MOD | type TEXT

B is 1 (left), 2 (middle) or 3 (right); MOD is shift, ctrl or alt.
"""

import ctypes
import os
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BUTTONS = {1: 0x110, 2: 0x112, 3: 0x111}
MODS = {"shift": (42, 1), "ctrl": (29, 4), "alt": (56, 8)}
KEYS = {"Escape": 1, "BackSpace": 14, "Tab": 15, "Return": 28, "space": 57, "minus": 12,
        "equal": 13, "period": 52, "comma": 51, "slash": 53, "Delete": 111,
        "F1": 59, "F2": 60, "F3": 61, "F4": 62, "F5": 63, "F6": 64, "F7": 65, "F8": 66}
for i, ch in enumerate("qwertyuiop"):
    KEYS[ch] = 16 + i
for i, ch in enumerate("asdfghjkl"):
    KEYS[ch] = 30 + i
for i, ch in enumerate("zxcvbnm"):
    KEYS[ch] = 44 + i
for i, ch in enumerate("1234567890"):
    KEYS[ch] = 2 + i
CHARS = {" ": ("space", False), "-": ("minus", False), ".": ("period", False), ",": ("comma", False),
         "/": ("slash", False), "=": ("equal", False), "+": ("equal", True), "*": ("8", True),
         "(": ("9", True), ")": ("0", True)}


def generate_bindings():
    out = tempfile.mkdtemp(prefix="ffwlgen")
    pkg = os.path.join(out, "ffwlgen")
    os.makedirs(pkg)
    open(os.path.join(pkg, "__init__.py"), "w").close()
    core = "/usr/share/wayland/wayland.xml"
    subprocess.check_call([sys.executable, "-m", "pywayland.scanner", "-i", core,
                           os.path.join(HERE, "wlr-virtual-pointer-unstable-v1.xml"),
                           os.path.join(HERE, "virtual-keyboard-unstable-v1.xml"), "-o", pkg],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sys.path.insert(0, out)


def keymap_string():
    xkb = ctypes.CDLL("libxkbcommon.so.0")
    xkb.xkb_context_new.restype = ctypes.c_void_p
    xkb.xkb_keymap_new_from_names.restype = ctypes.c_void_p
    xkb.xkb_keymap_new_from_names.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    xkb.xkb_keymap_get_as_string.restype = ctypes.c_void_p
    xkb.xkb_keymap_get_as_string.argtypes = [ctypes.c_void_p, ctypes.c_int]
    ctx = xkb.xkb_context_new(0)
    km = xkb.xkb_keymap_new_from_names(ctx, None, 0)
    ptr = xkb.xkb_keymap_get_as_string(km, 1)
    return ctypes.string_at(ptr)


class Input(object):
    def __init__(self, width, height):
        from pywayland.client import Display
        from ffwlgen.wayland import WlSeat
        from ffwlgen.wlr_virtual_pointer_unstable_v1 import ZwlrVirtualPointerManagerV1
        from ffwlgen.virtual_keyboard_unstable_v1 import ZwpVirtualKeyboardManagerV1
        self.w, self.h = width, height
        self.display = Display()
        self.display.connect()
        found = {}
        registry = self.display.get_registry()

        def on_global(reg, name, interface, version):
            for cls in (WlSeat, ZwlrVirtualPointerManagerV1, ZwpVirtualKeyboardManagerV1):
                if interface == cls.name and cls.name not in found:
                    found[cls.name] = reg.bind(name, cls, min(version, cls.version))
        registry.dispatcher["global"] = on_global
        self.display.roundtrip()
        seat = found["wl_seat"]
        self.pointer = found[ZwlrVirtualPointerManagerV1.name].create_virtual_pointer(seat)
        self.keyboard = found[ZwpVirtualKeyboardManagerV1.name].create_virtual_keyboard(seat)
        data = keymap_string() + b"\0"
        fd, path = tempfile.mkstemp()
        os.write(fd, data)
        os.lseek(fd, 0, 0)
        self.keyboard.keymap(1, fd, len(data))
        os.unlink(path)
        self.mods = 0
        self.held = set()
        self.display.roundtrip()

    def _t(self):
        return int(time.monotonic() * 1000) & 0xFFFFFFFF

    def _sync(self):
        self.display.flush()
        self.display.roundtrip()

    def move(self, x, y):
        self.pointer.motion_absolute(self._t(), max(0, int(x)), max(0, int(y)), self.w, self.h)
        self.pointer.frame()
        self._sync()

    def button(self, b, pressed):
        self.pointer.button(self._t(), BUTTONS[b], 1 if pressed else 0)
        self.pointer.frame()
        self._sync()

    def wheel(self, n):
        self.pointer.axis_source(0)
        self.pointer.axis_discrete(self._t(), 0, 15.0 * n, n)
        self.pointer.frame()
        self._sync()

    def _mod(self, name, on):
        code, mask = MODS[name]
        self.keyboard.key(self._t(), code, 1 if on else 0)
        self.mods = (self.mods | mask) if on else (self.mods & ~mask)
        self.keyboard.modifiers(self.mods, 0, 0, 0)
        self._sync()

    def key(self, name, mods=()):
        for m in mods:
            self._mod(m, True)
        code = KEYS[name] if name in KEYS else KEYS[name.lower()]
        self.keyboard.key(self._t(), code, 1)
        self._sync()
        self.keyboard.key(self._t(), code, 0)
        self._sync()
        for m in mods:
            if m not in self.held:
                self._mod(m, False)

    def type(self, text):
        for ch in text:
            if ch in CHARS:
                name, shift = CHARS[ch]
            else:
                name, shift = ch.lower(), ch.isupper()
            self.key(name, ("shift",) if shift else ())

    def hold(self, name, on):
        if on:
            self.held.add(name)
        else:
            self.held.discard(name)
        self._mod(name, on)


def main():
    sock_path, width, height = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    generate_bindings()
    inp = Input(width, height)
    if os.path.exists(sock_path):
        os.unlink(sock_path)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(4)
    print("ready", flush=True)
    while True:
        conn, _ = srv.accept()
        f = conn.makefile("rw")
        for line in f:
            parts = line.rstrip("\n").split(" ")
            cmd, args = parts[0], parts[1:]
            try:
                if cmd == "move":
                    inp.move(float(args[0]), float(args[1]))
                elif cmd in ("down", "up"):
                    inp.button(int(args[0]), cmd == "down")
                elif cmd == "wheel":
                    inp.wheel(int(args[0]))
                elif cmd == "key":
                    inp.key(args[0], args[1:])
                elif cmd in ("hold", "release"):
                    inp.hold(args[0], cmd == "hold")
                elif cmd == "type":
                    inp.type(line.rstrip("\n")[5:])
                elif cmd == "quit":
                    return
                f.write("ok\n")
            except Exception as e:  # report and keep serving
                f.write("error %s\n" % e)
            f.flush()
        conn.close()


if __name__ == "__main__":
    main()
