#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Generate FreeFusion's SVG icon set.

The icons are original artwork in a flat isometric style (grey-blue solids, blue
sketch strokes, orange construction geometry) so the UI reads like a modern
parametric CAD ribbon. Run:  python3 tools/make_icons.py
"""

import math
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "freefusion", "resources",
                   "icons")

# palette -------------------------------------------------------------------
TOP = "#dfe6ee"
LEFT = "#b3c0cd"
RIGHT = "#8c9db0"
EDGE = "#4b5866"
BLUE = "#1c7ed6"
BLUE_D = "#1864ab"
PROFILE = "#ffd8a8"
ORANGE = "#f08c00"
PLANE = "#ffc078"
GREEN = "#2f9e44"
RED = "#e03131"
DARK = "#343a40"
GREY = "#868e96"
YELLOW = "#fcc419"
WHITE = "#ffffff"

C30 = math.cos(math.radians(30))
S30 = 0.5


class Icon(object):
    def __init__(self, cx=16, cy=16, s=1.0):
        self.parts = []
        self.defs = []
        self.cx, self.cy, self.s = cx, cy, s

    # iso projection: x to the lower right, y to the lower left, z up
    def p(self, x, y, z):
        return (self.cx + (x - y) * C30 * self.s, self.cy + ((x + y) * S30 - z) * self.s)

    def add(self, svg):
        if svg.startswith("<defs>"):
            self.defs.append(svg[6:-7])
        else:
            self.parts.append(svg)
        return self

    def poly(self, pts, fill="none", stroke=EDGE, sw=0.9, extra=""):
        d = " ".join("%.2f,%.2f" % p for p in pts)
        return self.add('<polygon points="%s" fill="%s" stroke="%s" stroke-width="%s" '
                        'stroke-linejoin="round" %s/>' % (d, fill, stroke, sw, extra))

    def line(self, a, b, stroke=EDGE, sw=1.0, extra=""):
        return self.add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="%s" '
                        'stroke-linecap="round" %s/>' % (a[0], a[1], b[0], b[1], stroke, sw, extra))

    def path(self, d, fill="none", stroke=EDGE, sw=1.0, extra=""):
        return self.add('<path d="%s" fill="%s" stroke="%s" stroke-width="%s" stroke-linejoin="round" '
                        'stroke-linecap="round" %s/>' % (d, fill, stroke, sw, extra))

    def circle(self, c, r, fill="none", stroke=EDGE, sw=1.0, extra=""):
        return self.add('<circle cx="%.2f" cy="%.2f" r="%.2f" fill="%s" stroke="%s" stroke-width="%s" %s/>'
                        % (c[0], c[1], r, fill, stroke, sw, extra))

    def ellipse(self, c, rx, ry, fill="none", stroke=EDGE, sw=1.0, extra=""):
        return self.add('<ellipse cx="%.2f" cy="%.2f" rx="%.2f" ry="%.2f" fill="%s" stroke="%s" '
                        'stroke-width="%s" %s/>' % (c[0], c[1], rx, ry, fill, stroke, sw, extra))

    def text(self, xy, t, size=9, fill=DARK, weight="bold"):
        return self.add('<text x="%.2f" y="%.2f" font-family="DejaVu Sans, Arial, sans-serif" '
                        'font-size="%s" font-weight="%s" fill="%s" text-anchor="middle">%s</text>'
                        % (xy[0], xy[1], size, weight, fill, t))

    # solids ----------------------------------------------------------------
    def box(self, x0, y0, z0, dx, dy, dz, top=TOP, left=LEFT, right=RIGHT, sw=0.9):
        x1, y1, z1 = x0 + dx, y0 + dy, z0 + dz
        p = self.p
        self.poly([p(x0, y1, z0), p(x1, y1, z0), p(x1, y1, z1), p(x0, y1, z1)], left, sw=sw)
        self.poly([p(x1, y0, z0), p(x1, y1, z0), p(x1, y1, z1), p(x1, y0, z1)], right, sw=sw)
        self.poly([p(x0, y0, z1), p(x1, y0, z1), p(x1, y1, z1), p(x0, y1, z1)], top, sw=sw)
        return self

    def rect_xy(self, x0, y0, z, dx, dy, fill=PROFILE, stroke=BLUE, sw=1.1, extra=""):
        p = self.p
        return self.poly([p(x0, y0, z), p(x0 + dx, y0, z), p(x0 + dx, y0 + dy, z), p(x0, y0 + dy, z)],
                         fill, stroke, sw, extra)

    def iso_ellipse(self, x, y, z, r):
        c = self.p(x, y, z)
        return c, r * math.sqrt(2) * C30 * self.s, r * math.sqrt(2) * S30 * self.s

    def cylinder(self, x, y, z0, r, h, top=TOP, side=LEFT, sw=0.9):
        c0, rx, ry = self.iso_ellipse(x, y, z0, r)
        c1, _, _ = self.iso_ellipse(x, y, z0 + h, r)
        self.path("M%.2f,%.2f L%.2f,%.2f A%.2f,%.2f 0 0 0 %.2f,%.2f L%.2f,%.2f Z" % (
            c1[0] - rx, c1[1], c0[0] - rx, c0[1], rx, ry, c0[0] + rx, c0[1], c1[0] + rx, c1[1]),
            fill="url(#cyl)" if side == "grad" else side, sw=sw)
        self.ellipse(c1, rx, ry, top, sw=sw)
        return self

    def arrow(self, a, b, color=BLUE, sw=1.6, head=4.0):
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        l = math.hypot(b[0] - a[0], b[1] - a[1])
        end = (a[0] + math.cos(ang) * (l - head * 0.8), a[1] + math.sin(ang) * (l - head * 0.8))
        self.line(a, end, color, sw)
        left = (b[0] - head * math.cos(ang - 0.45), b[1] - head * math.sin(ang - 0.45))
        right = (b[0] - head * math.cos(ang + 0.45), b[1] - head * math.sin(ang + 0.45))
        self.poly([b, left, right], color, color, 0.6)
        return self

    def badge(self, kind, x=25, y=25):
        if kind == "plus":
            self.circle((x, y), 5.2, GREEN, WHITE, 1.2)
            self.line((x - 2.8, y), (x + 2.8, y), WHITE, 1.6)
            self.line((x, y - 2.8), (x, y + 2.8), WHITE, 1.6)
        elif kind == "minus":
            self.circle((x, y), 5.2, RED, WHITE, 1.2)
            self.line((x - 2.8, y), (x + 2.8, y), WHITE, 1.6)
        elif kind == "star":
            self.circle((x, y), 5.2, ORANGE, WHITE, 1.2)
            self.text((x, y + 3.2), "*", 10, WHITE)
        return self

    def plane(self, z=0.0, size=11, fill=PLANE, stroke=ORANGE, dx=0.0, opacity=0.85):
        p = self.p
        h = size / 2.0
        return self.poly([p(-h + dx, -h, z), p(h + dx, -h, z), p(h + dx, h, z), p(-h + dx, h, z)], fill,
                         stroke, 1.0, 'fill-opacity="%s"' % opacity)

    def vplane(self, x=0.0, size=11, fill=PLANE, stroke=ORANGE, opacity=0.85):
        """Plane standing up (YZ plane at x)."""
        p = self.p
        h = size / 2.0
        return self.poly([p(x, -h, -h), p(x, h, -h), p(x, h, h), p(x, -h, h)], fill, stroke, 1.0,
                         'fill-opacity="%s"' % opacity)

    def svg(self):
        defs = ('<defs><linearGradient id="cyl" x1="0" x2="1" y1="0" y2="0">'
                '<stop offset="0" stop-color="%s"/><stop offset="0.55" stop-color="%s"/>'
                '<stop offset="1" stop-color="%s"/></linearGradient>%s</defs>'
                % (LEFT, TOP, RIGHT, "".join(self.defs)))
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">'
                + defs + "".join(self.parts) + "</svg>\n")


ICONS = {}


def icon(name):
    def deco(fn):
        ICONS[name] = fn
        return fn
    return deco


# ---------------------------------------------------------------------------
# general


@icon("FreeFusion")
def _logo():
    i = Icon(16, 17, 1.25)
    i.add('<rect x="1" y="1" width="30" height="30" rx="6" fill="#ff6b00"/>')
    i.box(-5, -5, -4, 10, 10, 9, top="#ffe8cc", left="#ffc078", right="#fd7e14")
    i.text((16, 21), "F", 11, "#7a2e00")
    return i


@icon("Generic")
def _generic():
    return Icon(16, 17, 1.1).box(-6, -6, -5, 12, 12, 10)


@icon("Body")
def _body():
    return Icon(16, 16, 1.0).box(-6, -6, -5, 12, 12, 10)


@icon("Component")
def _component():
    i = Icon(16, 16, 1.0)
    i.box(-7, -7, -6, 14, 14, 12, top="#ffffff", left="#e9ecef", right="#ced4da")
    i.box(-3, -3, 6, 6, 6, 0.01, top=BLUE, left=BLUE, right=BLUE)
    return i


@icon("NewComponent")
def _newcomp():
    return _component().badge("plus", 25, 8)


@icon("Folder")
def _folder():
    i = Icon()
    i.path("M4,9 L12,9 L14,11 L28,11 L28,25 L4,25 Z", fill="#ffd43b", stroke="#e0a800")
    i.path("M4,13 L28,13", stroke="#e0a800")
    return i


@icon("Origin")
def _origin():
    i = Icon(16, 16, 1.0)
    o = i.p(0, 0, 0)
    i.arrow(o, i.p(11, 0, 0), RED, 1.4, 3.5)
    i.arrow(o, i.p(0, 11, 0), GREEN, 1.4, 3.5)
    i.arrow(o, i.p(0, 0, 11), BLUE, 1.4, 3.5)
    i.circle(o, 2, YELLOW, DARK, 0.8)
    return i


@icon("Eye")
def _eye():
    i = Icon()
    i.path("M3,16 Q16,5 29,16 Q16,27 3,16 Z", fill=WHITE, stroke=DARK, sw=1.6)
    i.circle((16, 16), 4.5, DARK, DARK)
    return i


@icon("EyeOff")
def _eyeoff():
    i = Icon()
    i.path("M3,16 Q16,5 29,16 Q16,27 3,16 Z", fill=WHITE, stroke=GREY, sw=1.6)
    i.circle((16, 16), 4.5, GREY, GREY)
    i.line((6, 26), (26, 6), GREY, 2)
    return i


@icon("Radio")
def _radio():
    i = Icon()
    i.circle((16, 16), 9, WHITE, GREY, 1.8)
    return i


@icon("RadioOn")
def _radio_on():
    i = Icon()
    i.circle((16, 16), 9, WHITE, BLUE, 1.8)
    i.circle((16, 16), 5, BLUE, BLUE)
    return i


@icon("DocSettings")
def _docsettings():
    i = Icon()
    i.path("M8,4 L20,4 L26,10 L26,28 L8,28 Z", fill=WHITE, stroke=DARK)
    i.path("M20,4 L20,10 L26,10", stroke=DARK)
    _gear(i, 19, 21, 5.5)
    return i


def _gear(i, cx, cy, r, color=GREY):
    pts = []
    for k in range(16):
        a = k * math.pi / 8
        rr = r if k % 2 == 0 else r * 0.72
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    i.poly(pts, color, DARK, 0.7)
    i.circle((cx, cy), r * 0.35, WHITE, DARK, 0.7)


@icon("Settings")
def _settings():
    i = Icon()
    _gear(i, 16, 16, 11)
    return i


@icon("NamedViews")
def _namedviews():
    i = Icon()
    i.path("M4,9 L28,9 L28,25 L4,25 Z", fill=WHITE, stroke=DARK)
    i.circle((16, 17), 5, "#a5d8ff", BLUE_D)
    i.circle((16, 17), 2, BLUE_D, BLUE_D)
    return i


# ---------------------------------------------------------------------------
# create


@icon("CreateSketch")
def _sketch():
    i = Icon(16, 18, 1.0)
    i.rect_xy(-9, -9, 0, 18, 18, fill="#e7f5ff", stroke=GREY, sw=0.8)
    i.rect_xy(-6, -6, 0, 9, 7, fill=PROFILE, stroke=BLUE)
    c, rx, ry = i.iso_ellipse(4, 3, 0, 3.2)
    i.ellipse(c, rx, ry, PROFILE, BLUE, 1.1)
    i.path("M24,3 L29,8 L17,20 L12,21 L13,16 Z", fill=YELLOW, stroke=DARK, sw=0.8)
    return i


@icon("Extrude")
def _extrude():
    i = Icon(15, 19, 1.0)
    i.rect_xy(-8, -8, 0, 16, 16, fill="none", stroke=BLUE, sw=1.2)
    i.box(-6, -6, 0, 12, 12, 8)
    i.arrow(i.p(0, 0, 8), i.p(0, 0, 17), BLUE, 1.8, 4)
    return i


@icon("ExtrudeCut")
def _extrude_cut():
    i = Icon(15, 16, 1.0)
    i.box(-8, -8, -6, 16, 16, 10)
    i.rect_xy(-4, -4, 4, 8, 8, fill="#5c6b7a", stroke=BLUE_D)
    i.arrow(i.p(0, 0, 13), i.p(0, 0, 4), RED, 1.8, 4)
    return i


@icon("Revolve")
def _revolve():
    i = Icon(16, 18, 1.0)
    i.cylinder(0, 0, -4, 7, 10, side="grad")
    c, rx, ry = i.iso_ellipse(0, 0, 6, 3)
    i.ellipse(c, rx, ry, RIGHT, EDGE, 0.8)
    i.line(i.p(0, 0, -9), i.p(0, 0, 13), ORANGE, 1.3, 'stroke-dasharray="3,1.5"')
    i.path("M22,5 A9,4 0 1 1 11,4", stroke=BLUE, sw=1.5)
    i.poly([(11, 1.5), (11, 6.5), (7.5, 4)], BLUE, BLUE, 0.5)
    return i


@icon("RevolveCut")
def _revolve_cut():
    return _revolve().badge("minus")


@icon("Sweep")
def _sweep():
    i = Icon()
    i.path("M5,26 C8,10 20,24 26,8", stroke=BLUE, sw=1.4, extra='stroke-dasharray="2.5,1.5"')
    i.path("M3,27 C6,11 18,25 24,9 L29,11 C23,27 11,13 8,29 Z", fill=LEFT, stroke=EDGE, sw=0.9)
    i.ellipse((26.5, 10), 2.8, 1.6, TOP, EDGE, 0.8)
    i.ellipse((5.5, 28), 2.8, 1.6, PROFILE, BLUE, 1.0)
    return i


@icon("Loft")
def _loft():
    i = Icon()
    i.path("M6,26 L10,8 L22,8 L26,26 Z", fill=LEFT, stroke=EDGE, sw=0.9)
    i.ellipse((16, 8), 6, 2.4, TOP, BLUE, 1.2)
    i.path("M6,26 L10,23 L22,23 L26,26 L22,29 L10,29 Z", fill=PROFILE, stroke=BLUE, sw=1.2)
    return i


@icon("Rib")
def _rib():
    i = Icon(16, 18, 0.9)
    i.box(-10, -10, -6, 20, 4, 12)
    i.box(-10, -6, -6, 4, 16, 12)
    i.poly([i.p(-6, -6, 6), i.p(4, -6, -6), i.p(-6, 4, -6)], PROFILE, BLUE, 1.1)
    return i


@icon("Hole")
def _hole():
    i = Icon(16, 16, 1.0)
    i.box(-9, -9, -5, 18, 18, 9)
    c, rx, ry = i.iso_ellipse(0, 0, 4, 4)
    i.ellipse(c, rx, ry, "#3d4a57", EDGE, 0.9)
    i.path("M%.2f,%.2f L%.2f,%.2f" % (c[0] - rx, c[1], c[0] - rx, c[1] + 4), stroke="#3d4a57", sw=0)
    return i


@icon("Thread")
def _thread():
    i = Icon(16, 18, 1.0)
    i.cylinder(0, 0, -7, 5, 16, side="grad")
    for k in range(6):
        y = 25 - k * 3.0
        i.line((10.2, y), (21.8, y - 2.2), EDGE, 1.0)
    return i


@icon("Box")
def _box():
    return Icon(16, 17, 1.0).box(-7, -7, -6, 14, 14, 12)


@icon("Cylinder")
def _cyl():
    return Icon(16, 16, 1.0).cylinder(0, 0, -7, 7.5, 13, side="grad")


@icon("Sphere")
def _sphere():
    i = Icon()
    i.add('<defs><radialGradient id="sph" cx="0.35" cy="0.35" r="0.7"><stop offset="0" stop-color="#ffffff"/>'
          '<stop offset="0.6" stop-color="%s"/><stop offset="1" stop-color="%s"/></radialGradient></defs>'
          % (LEFT, RIGHT))
    i.circle((16, 16), 12, "url(#sph)", EDGE, 0.9)
    i.ellipse((16, 16), 12, 4, "none", EDGE, 0.5, 'stroke-dasharray="1.5,1.5"')
    return i


@icon("Torus")
def _torus():
    i = Icon()
    i.ellipse((16, 17), 13.5, 8.5, LEFT, EDGE, 0.9)
    i.ellipse((16, 15), 5.5, 2.8, WHITE, EDGE, 0.9)
    i.path("M5,15 Q16,7 27,15", stroke=TOP, sw=2.5)
    return i


@icon("Coil")
def _coil():
    i = Icon()
    for k in range(4):
        y = 7 + k * 5.5
        i.ellipse((16, y), 10, 3, "none", RIGHT, 2.6)
        i.path("M6,%.2f A10,3 0 0 0 26,%.2f" % (y, y), stroke=LEFT, sw=2.6)
    return i


@icon("Pipe")
def _pipe():
    i = Icon()
    i.path("M6,26 C6,12 12,8 26,8", stroke=RIGHT, sw=7)
    i.path("M6,26 C6,12 12,8 26,8", stroke=TOP, sw=3)
    i.ellipse((26, 8), 2, 3.6, "#495057", EDGE, 0.8)
    return i


def _minibox(i, x, y, s=0.45):
    j = Icon(x, y, s)
    j.box(-6, -6, -5, 12, 12, 10)
    i.parts.extend(j.parts)


@icon("RectPattern")
def _rectpattern():
    i = Icon()
    for (x, y) in ((9, 9), (23, 9), (9, 23), (23, 23)):
        _minibox(i, x, y, 0.5)
    i.arrow((9, 16), (27, 16), BLUE, 1.2, 3)
    return i


@icon("CircPattern")
def _circpattern():
    i = Icon()
    i.circle((16, 16), 10, "none", BLUE, 1.1, 'stroke-dasharray="2,1.5"')
    for k in range(6):
        a = k * math.pi / 3
        _minibox(i, 16 + 10 * math.cos(a), 16 + 10 * math.sin(a), 0.32)
    i.circle((16, 16), 1.8, ORANGE, ORANGE)
    return i


@icon("PathPattern")
def _pathpattern():
    i = Icon()
    i.path("M4,24 C10,4 22,30 28,8", stroke=BLUE, sw=1.1, extra='stroke-dasharray="2,1.5"')
    for (x, y) in ((6, 20), (16, 17), (26, 12)):
        _minibox(i, x, y, 0.38)
    return i


@icon("Mirror")
def _mirror():
    i = Icon()
    _minibox(i, 8.5, 17, 0.55)
    j = Icon(23.5, 17, 0.55)
    j.box(-6, -6, -5, 12, 12, 10, top=TOP, left="#d0d8e0", right="#b9c5d1")
    i.parts.extend(j.parts)
    i.line((16, 3), (16, 29), ORANGE, 1.6, 'stroke-dasharray="3,2"')
    return i


@icon("Thicken")
def _thicken():
    i = Icon()
    i.path("M4,20 Q16,8 28,20 L28,25 Q16,13 4,25 Z", fill=LEFT, stroke=EDGE)
    i.path("M4,20 Q16,8 28,20", stroke=BLUE, sw=1.4)
    i.arrow((16, 16), (16, 5), BLUE, 1.4, 3.2)
    return i


# ---------------------------------------------------------------------------
# modify


@icon("PressPull")
def _presspull():
    i = Icon(14, 19, 1.0)
    i.box(-7, -7, -5, 14, 14, 8)
    i.rect_xy(-7, -7, 3, 14, 14, fill="#a5d8ff", stroke=BLUE)
    i.arrow(i.p(0, 0, 3), i.p(0, 0, 13), BLUE, 1.8, 4)
    i.arrow((26, 22), (26, 30), BLUE, 1.2, 3)
    i.arrow((26, 22), (26, 14), BLUE, 1.2, 3)
    return i


@icon("Fillet")
def _fillet():
    i = Icon(16, 17, 1.0)
    p = i.p
    x0, y0, z0, x1, y1, z1, r = -7, -7, -6, 7, 7, 6, 5
    i.poly([p(x0, y1, z0), p(x1, y1, z0), p(x1, y1, z1 - r), p(x1 - r, y1, z1), p(x0, y1, z1)], LEFT)
    i.poly([p(x1, y0, z0), p(x1, y1, z0), p(x1, y1, z1 - r), p(x1, y0, z1 - r)], RIGHT)
    i.poly([p(x1, y0, z1 - r), p(x1, y1, z1 - r), p(x1 - r, y1, z1), p(x1 - r, y0, z1)], "#a5d8ff",
           BLUE, 1.0)
    i.poly([p(x0, y0, z1), p(x1 - r, y0, z1), p(x1 - r, y1, z1), p(x0, y1, z1)], TOP)
    return i


@icon("Chamfer")
def _chamfer():
    i = Icon(16, 17, 1.0)
    p = i.p
    x0, y0, z0, x1, y1, z1, r = -7, -7, -6, 7, 7, 6, 5
    i.poly([p(x0, y1, z0), p(x1, y1, z0), p(x1, y1, z1 - r), p(x1 - r, y1, z1), p(x0, y1, z1)], LEFT)
    i.poly([p(x1, y0, z0), p(x1, y1, z0), p(x1, y1, z1 - r), p(x1, y0, z1 - r)], RIGHT)
    i.poly([p(x1, y0, z1 - r), p(x1, y1, z1 - r), p(x1 - r, y1, z1), p(x1 - r, y0, z1)], "#ffd8a8",
           ORANGE, 1.0)
    i.poly([p(x0, y0, z1), p(x1 - r, y0, z1), p(x1 - r, y1, z1), p(x0, y1, z1)], TOP)
    return i


@icon("Shell")
def _shell():
    i = Icon(16, 17, 1.0)
    i.box(-8, -8, -6, 16, 16, 12)
    i.box(-6, -6, -4, 12, 12, 0.01, top="#5c6b7a", left="#5c6b7a", right="#5c6b7a", sw=0.6)
    i.poly([i.p(-6, -6, 6), i.p(6, -6, 6), i.p(6, 6, 6), i.p(-6, 6, 6)], "#495867", EDGE, 0.8)
    i.poly([i.p(-6, 6, 6), i.p(6, 6, 6), i.p(6, 6, -2), i.p(-6, 6, -2)], "#6c7a89", EDGE, 0.6)
    return i


@icon("Draft")
def _draft():
    i = Icon(16, 17, 1.0)
    p = i.p
    i.poly([p(-7, 7, -6), p(7, 7, -6), p(5, 5, 6), p(-7, 5, 6)], LEFT)
    i.poly([p(7, -7, -6), p(7, 7, -6), p(5, 5, 6), p(5, -7, 6)], "#a5d8ff", BLUE, 1.0)
    i.poly([p(-7, -7, 6), p(5, -7, 6), p(5, 5, 6), p(-7, 5, 6)], TOP)
    return i


@icon("Scale")
def _scale():
    i = Icon()
    _minibox(i, 11, 20, 0.55)
    i.path("M13,4 L28,4 L28,19", stroke=BLUE, sw=1.2, extra='stroke-dasharray="2,1.5"')
    i.arrow((18, 14), (27, 5), BLUE, 1.6, 3.5)
    return i


@icon("Combine")
def _combine():
    i = Icon()
    j = Icon(12, 19, 0.7)
    j.box(-6, -6, -5, 12, 12, 10)
    k = Icon(20, 13, 0.7)
    k.box(-6, -6, -5, 12, 12, 10, top="#d0ebff", left="#a5d8ff", right="#74c0fc")
    i.parts.extend(j.parts + k.parts)
    return i


@icon("SplitBody")
def _splitbody():
    i = Icon(16, 17, 1.0)
    i.box(-7, -7, -6, 14, 7, 12)
    i.box(-7, 1, -6, 14, 6, 12)
    i.poly([i.p(-10, 0.5, -9), i.p(10, 0.5, -9), i.p(10, 0.5, 9), i.p(-10, 0.5, 9)], PLANE, ORANGE, 0.9,
           'fill-opacity="0.55"')
    return i


@icon("SplitFace")
def _splitface():
    i = Icon(16, 17, 1.0)
    i.box(-7, -7, -6, 14, 14, 12)
    i.line(i.p(-7, -7, 6), i.p(7, 7, 6), ORANGE, 1.6)
    return i


@icon("Move")
def _move():
    i = Icon()
    for a in (0, 90, 180, 270):
        r = math.radians(a)
        i.arrow((16, 16), (16 + 13 * math.cos(r), 16 + 13 * math.sin(r)), BLUE, 1.8, 4.5)
    i.circle((16, 16), 3.5, WHITE, BLUE_D, 1.4)
    return i


@icon("Align")
def _align():
    i = Icon()
    _minibox(i, 9, 21, 0.5)
    _minibox(i, 22, 10, 0.5)
    i.arrow((21, 13), (12, 19), BLUE, 1.4, 3.5)
    i.circle((22, 13), 1.8, ORANGE, ORANGE)
    i.circle((9, 18), 1.8, ORANGE, ORANGE)
    return i


@icon("Delete")
def _delete():
    i = Icon()
    i.path("M9,10 L23,10 L22,28 L10,28 Z", fill="#f1f3f5", stroke=DARK, sw=1.3)
    i.line((6, 8), (26, 8), DARK, 1.8)
    i.path("M13,8 L13,5 L19,5 L19,8", stroke=DARK, sw=1.3)
    for x in (13, 16, 19):
        i.line((x, 13), (x, 25), GREY, 1.1)
    return i


@icon("Material")
def _material():
    i = Icon()
    i.add('<defs><radialGradient id="mat" cx="0.35" cy="0.3" r="0.8"><stop offset="0" stop-color="#ffffff"/>'
          '<stop offset="0.5" stop-color="#adb5bd"/><stop offset="1" stop-color="#495057"/></radialGradient></defs>')
    i.circle((16, 16), 11.5, "url(#mat)", DARK, 0.8)
    return i


@icon("Appearance")
def _appearance():
    i = Icon()
    i.circle((16, 16), 12, "#f8f9fa", DARK, 1)
    for k, col in enumerate(("#fa5252", "#fab005", "#40c057", "#228be6", "#be4bdb")):
        a = -math.pi / 2 + k * 2 * math.pi / 5
        i.circle((16 + 6.5 * math.cos(a), 16 + 6.5 * math.sin(a)), 3, col, "none", 0)
    return i


@icon("Parameters")
def _parameters():
    i = Icon()
    i.path("M4,6 L28,6 L28,26 L4,26 Z", fill=WHITE, stroke=DARK)
    i.text((12, 20), "f", 13, BLUE_D, "bold")
    i.text((21, 20), "x", 11, DARK, "normal")
    i.line((4, 11), (28, 11), GREY, 0.8)
    return i


@icon("ComputeAll")
def _computeall():
    i = Icon()
    i.path("M26,16 A10,10 0 1 1 22,8", stroke=GREEN, sw=2.6)
    i.poly([(18, 3), (26, 5), (21, 11)], GREEN, GREEN, 0.5)
    return i


# ---------------------------------------------------------------------------
# assemble


@icon("Joint")
def _joint():
    i = Icon()
    _minibox(i, 10, 11, 0.5)
    _minibox(i, 22, 21, 0.5)
    i.ellipse((16, 16), 7, 3.5, "none", ORANGE, 1.8)
    i.circle((16, 16), 2.2, WHITE, ORANGE, 1.3)
    return i


@icon("AsBuiltJoint")
def _asbuilt():
    return _joint().badge("star", 26, 26)


@icon("RigidGroup")
def _rigid():
    i = Icon()
    _minibox(i, 11, 13, 0.5)
    _minibox(i, 21, 19, 0.5)
    i.path("M7,4 L25,4 L25,28 L7,28 Z", stroke=ORANGE, sw=1.3, extra='stroke-dasharray="3,2"')
    return i


@icon("Ground")
def _ground():
    i = Icon()
    _minibox(i, 16, 12, 0.6)
    i.line((5, 24), (27, 24), DARK, 1.8)
    for x in range(6, 27, 5):
        i.line((x, 24), (x - 3, 29), DARK, 1)
    return i


@icon("InsertComponent")
def _insertcomp():
    i = _component()
    i.arrow((4, 4), (11, 11), GREEN, 2, 4)
    return i


@icon("ExplodedView")
def _exploded():
    i = Icon()
    _minibox(i, 16, 9, 0.45)
    _minibox(i, 16, 23, 0.45)
    i.arrow((16, 14), (16, 3), BLUE, 1.1, 2.5)
    i.arrow((16, 18), (16, 30), BLUE, 1.1, 2.5)
    return i


@icon("BOM")
def _bom():
    i = Icon()
    i.path("M6,4 L26,4 L26,28 L6,28 Z", fill=WHITE, stroke=DARK)
    for y in (10, 15, 20, 25):
        i.line((9, y), (11, y), BLUE, 2)
        i.line((13, y), (23, y), GREY, 1.2)
    return i


@icon("Motion")
def _motion():
    i = Icon()
    i.circle((16, 16), 12, "none", DARK, 1.3)
    i.poly([(13, 10), (22, 16), (13, 22)], GREEN, GREEN, 0.8)
    return i


# ---------------------------------------------------------------------------
# construct


def _plane_icon(extra=None):
    i = Icon(16, 16, 1.0)
    i.plane(0, 20)
    if extra:
        extra(i)
    return i


@icon("OffsetPlane")
def _offsetplane():
    i = Icon(16, 20, 1.0)
    i.plane(-2, 17, fill="#e9ecef", stroke=GREY, opacity=0.9)
    i.plane(8, 17)
    i.arrow(i.p(0, 0, -2), i.p(0, 0, 8), BLUE, 1.4, 3)
    return i


@icon("PlaneAngle")
def _planeangle():
    i = Icon(16, 18, 1.0)
    i.plane(-2, 17, fill="#e9ecef", stroke=GREY, opacity=0.9)
    p = i.p
    i.poly([p(-8, 0, -2), p(8, 0, -2), p(8, 7, 9), p(-8, 7, 9)], PLANE, ORANGE, 1.0, 'fill-opacity="0.85"')
    i.line(p(-9, 0, -2), p(9, 0, -2), BLUE, 1.8)
    return i


@icon("TangentPlane")
def _tangentplane():
    i = Icon(16, 18, 1.0)
    i.cylinder(0, 0, -7, 5, 12, side="grad")
    p = i.p
    i.poly([p(6, -9, -8), p(6, 9, -8), p(6, 9, 7), p(6, -9, 7)], PLANE, ORANGE, 1.0, 'fill-opacity="0.8"')
    return i


@icon("Midplane")
def _midplane():
    i = Icon(16, 18, 1.0)
    i.box(-8, -8, -7, 16, 16, 3, top="#e9ecef")
    i.plane(1, 16)
    i.box(-8, -8, 5, 16, 16, 3, top="#e9ecef")
    return i


@icon("PlaneTwoEdges")
def _planetwoedges():
    i = _plane_icon()
    i.line(i.p(-9, -9, 0), i.p(9, -9, 0), BLUE, 2)
    i.line(i.p(-9, 9, 0), i.p(9, 9, 0), BLUE, 2)
    return i


@icon("PlaneThreePoints")
def _planethreepoints():
    i = _plane_icon()
    for pt in ((-7, -7, 0), (7, -5, 0), (-3, 7, 0)):
        i.circle(i.p(*pt), 2.2, BLUE, WHITE, 0.8)
    return i


@icon("PlaneTangentAtPoint")
def _planetangentpt():
    i = _tangentplane()
    i.circle(i.p(6, 0, 0), 2.2, BLUE, WHITE, 0.8)
    return i


@icon("PlaneAlongPath")
def _planealongpath():
    i = Icon(16, 16, 1.0)
    i.path("M3,26 C10,26 20,6 29,6", stroke=BLUE, sw=1.6)
    i.poly([(12, 8), (20, 12), (20, 26), (12, 22)], PLANE, ORANGE, 1.0, 'fill-opacity="0.85"')
    return i


def _axis_line(i, a, b):
    i.line(a, b, ORANGE, 1.8, 'stroke-dasharray="4,2"')


@icon("AxisCylinder")
def _axiscyl():
    i = Icon(16, 17, 1.0)
    i.cylinder(0, 0, -6, 6, 10, side="grad")
    _axis_line(i, i.p(0, 0, -11), i.p(0, 0, 13))
    return i


@icon("AxisEdge")
def _axisedge():
    i = Icon(16, 17, 1.0)
    i.box(-7, -7, -6, 14, 14, 12)
    i.line(i.p(7, 7, -6), i.p(7, 7, 6), BLUE, 2)
    _axis_line(i, i.p(7, 7, -11), i.p(7, 7, 12))
    return i


@icon("AxisTwoPlanes")
def _axistwoplanes():
    i = Icon(16, 16, 1.0)
    i.plane(0, 18)
    i.vplane(0, 18)
    _axis_line(i, i.p(0, -12, 0), i.p(0, 12, 0))
    return i


@icon("AxisTwoPoints")
def _axistwopoints():
    i = Icon()
    _axis_line(i, (4, 27), (28, 5))
    i.circle((9, 22), 2.5, BLUE, WHITE, 0.8)
    i.circle((23, 10), 2.5, BLUE, WHITE, 0.8)
    return i


@icon("AxisNormal")
def _axisnormal():
    i = Icon(16, 20, 1.0)
    i.plane(0, 18, fill="#e9ecef", stroke=GREY)
    _axis_line(i, i.p(0, 0, 0), i.p(0, 0, 16))
    i.circle(i.p(0, 0, 0), 2.2, BLUE, WHITE, 0.8)
    return i


@icon("PointVertex")
def _pointvertex():
    i = Icon(16, 17, 1.0)
    i.box(-7, -7, -6, 14, 14, 12)
    i.circle(i.p(7, 7, 6), 3, ORANGE, WHITE, 1)
    return i


@icon("PointTwoEdges")
def _pointtwoedges():
    i = Icon()
    i.line((4, 26), (28, 8), BLUE, 1.6)
    i.line((4, 8), (28, 26), BLUE, 1.6)
    i.circle((16, 17), 3, ORANGE, WHITE, 1)
    return i


@icon("PointThreePlanes")
def _pointthreeplanes():
    i = Icon(16, 16, 1.0)
    i.plane(0, 16)
    i.vplane(0, 16)
    p = i.p
    i.poly([p(-8, 0, -8), p(8, 0, -8), p(8, 0, 8), p(-8, 0, 8)], PLANE, ORANGE, 1.0, 'fill-opacity="0.6"')
    i.circle(i.p(0, 0, 0), 3, BLUE, WHITE, 1)
    return i


@icon("PointCenter")
def _pointcenter():
    i = Icon()
    i.circle((16, 16), 11, "none", BLUE, 1.6)
    i.circle((16, 16), 3, ORANGE, WHITE, 1)
    return i


@icon("PointEdgePlane")
def _pointedgeplane():
    i = Icon(16, 18, 1.0)
    i.plane(0, 18)
    i.line(i.p(-3, -3, -9), i.p(3, 3, 9), BLUE, 1.6)
    i.circle(i.p(0, 0, 0), 3, ORANGE, WHITE, 1)
    return i


@icon("PointAlongPath")
def _pointalongpath():
    i = Icon()
    i.path("M3,26 C10,26 20,6 29,6", stroke=BLUE, sw=1.6)
    i.circle((16, 15.5), 3, ORANGE, WHITE, 1)
    return i


# ---------------------------------------------------------------------------
# inspect / insert / select / utilities


@icon("Measure")
def _measure():
    i = Icon()
    i.path("M3,20 L20,3 L29,12 L12,29 Z", fill=YELLOW, stroke=DARK, sw=1)
    for k in range(6):
        a = (6 + k * 3.4, 17 - k * 3.4)
        i.line(a, (a[0] + (3 if k % 2 else 2), a[1] + (3 if k % 2 else 2)), DARK, 1)
    return i


@icon("Interference")
def _interference():
    i = Icon()
    j = Icon(12, 18, 0.7)
    j.box(-6, -6, -5, 12, 12, 10)
    k = Icon(20, 14, 0.7)
    k.box(-6, -6, -5, 12, 12, 10)
    i.parts.extend(j.parts + k.parts)
    i.poly([(14.5, 11.5), (18.5, 13.5), (18.5, 19), (14.5, 17)], RED, RED, 0.8, 'fill-opacity="0.85"')
    return i


@icon("SectionAnalysis")
def _section():
    i = Icon(16, 17, 1.0)
    p = i.p
    i.poly([p(-7, 7, -6), p(7, 7, -6), p(7, 7, 6), p(-7, 7, 6)], LEFT)
    i.poly([p(0, -7, -6), p(0, 7, -6), p(0, 7, 6), p(0, -7, 6)], "#ff8787", RED, 1)
    i.poly([p(-7, -7, 6), p(0, -7, 6), p(0, 7, 6), p(-7, 7, 6)], TOP)
    i.poly([p(0, -10, -9), p(0, 10, -9), p(0, 10, 9), p(0, -10, 9)], "none", BLUE, 0.8,
           'stroke-dasharray="2,1.5"')
    return i


@icon("CenterOfMass")
def _com():
    i = Icon()
    i.circle((16, 16), 11, WHITE, DARK, 1.4)
    i.path("M16,5 A11,11 0 0 1 27,16 L16,16 Z", fill=DARK)
    i.path("M16,27 A11,11 0 0 1 5,16 L16,16 Z", fill=DARK)
    return i


@icon("Properties")
def _properties():
    i = Icon()
    i.path("M6,4 L26,4 L26,28 L6,28 Z", fill=WHITE, stroke=DARK)
    i.text((16, 21), "i", 14, BLUE, "bold")
    return i


@icon("ComponentColors")
def _compcolors():
    i = Icon()
    for (x, y, c) in ((10, 11, "#ff8787"), (22, 11, "#74c0fc"), (16, 22, "#8ce99a")):
        j = Icon(x, y, 0.45)
        j.box(-6, -6, -5, 12, 12, 10, top=c, left=c, right=c)
        i.parts.extend(j.parts)
    return i


@icon("InsertMesh")
def _insertmesh():
    i = Icon()
    pts = [(16, 4), (28, 11), (28, 23), (16, 29), (4, 23), (4, 11)]
    i.poly(pts, "#d0ebff", BLUE_D, 1)
    for a, b in ((0, 3), (1, 4), (2, 5)):
        i.line(pts[a], pts[b], BLUE_D, 0.8)
    return i


@icon("InsertSVG")
def _insertsvg():
    i = Icon()
    i.path("M5,4 L22,4 L27,9 L27,28 L5,28 Z", fill=WHITE, stroke=DARK)
    i.text((16, 22), "SVG", 7.5, "#e8590c")
    return i


@icon("InsertDXF")
def _insertdxf():
    i = Icon()
    i.path("M5,4 L22,4 L27,9 L27,28 L5,28 Z", fill=WHITE, stroke=DARK)
    i.text((16, 22), "DXF", 7.5, BLUE_D)
    return i


@icon("InsertCAD")
def _insertcad():
    i = Icon()
    i.path("M5,4 L22,4 L27,9 L27,28 L5,28 Z", fill=WHITE, stroke=DARK)
    _minibox(i, 16, 18, 0.5)
    return i


@icon("Canvas")
def _canvas():
    i = Icon()
    i.path("M4,6 L28,6 L28,26 L4,26 Z", fill="#e7f5ff", stroke=DARK)
    i.path("M4,24 L12,14 L18,20 L22,16 L28,22 L28,26 L4,26 Z", fill="#69db7c", stroke="none")
    i.circle((22, 11), 2.5, YELLOW, "none", 0)
    return i


@icon("SelectBody")
def _selbody():
    i = Icon(14, 15, 0.9)
    i.box(-7, -7, -6, 14, 14, 12, top="#a5d8ff", left="#74c0fc", right="#4dabf7")
    _cursor(i)
    return i


@icon("SelectFace")
def _selface():
    i = Icon(14, 15, 0.9)
    i.box(-7, -7, -6, 14, 14, 12)
    i.rect_xy(-7, -7, 6, 14, 14, fill="#74c0fc", stroke=BLUE)
    _cursor(i)
    return i


@icon("SelectEdge")
def _seledge():
    i = Icon(14, 15, 0.9)
    i.box(-7, -7, -6, 14, 14, 12)
    i.line(i.p(-7, 7, 6), i.p(7, 7, 6), BLUE, 2.4)
    _cursor(i)
    return i


@icon("SelectVertex")
def _selvertex():
    i = Icon(14, 15, 0.9)
    i.box(-7, -7, -6, 14, 14, 12)
    i.circle(i.p(7, 7, 6), 2.6, BLUE, WHITE, 1)
    _cursor(i)
    return i


def _cursor(i, x=21, y=18):
    i.path("M%d,%d L%d,%d L%d,%d L%d,%d L%d,%d L%d,%d L%d,%d Z" % (
        x, y, x, y + 11, x + 3, y + 8, x + 5, y + 12, x + 7, y + 11, x + 5, y + 7, x + 9, y + 7),
        fill=WHITE, stroke=DARK, sw=1)


@icon("WindowSelect")
def _winsel():
    i = Icon()
    i.path("M4,5 L24,5 L24,21 L4,21 Z", fill="#d0ebff", stroke=BLUE, sw=1.2, extra='stroke-dasharray="3,2"')
    _cursor(i, 19, 17)
    return i


@icon("SelectAll")
def _selall():
    i = Icon()
    i.path("M4,4 L28,4 L28,28 L4,28 Z", fill="#d0ebff", stroke=BLUE, sw=1.2, extra='stroke-dasharray="3,2"')
    _minibox(i, 16, 17, 0.55)
    return i


@icon("Print3D")
def _print3d():
    i = Icon()
    i.path("M5,4 L27,4 L27,28 L5,28 Z", fill="#f1f3f5", stroke=DARK)
    i.line((5, 9), (27, 9), DARK, 1.2)
    i.path("M13,9 L19,9 L17.5,13 L14.5,13 Z", fill=DARK)
    j = Icon(16, 22, 0.45)
    j.box(-6, -6, -5, 12, 12, 10, top="#ffc078", left="#ffa94d", right="#fd7e14")
    i.parts.extend(j.parts)
    return i


@icon("Scripts")
def _scripts():
    i = Icon()
    i.path("M5,5 L27,5 L27,27 L5,27 Z", fill=DARK, stroke=DARK)
    i.path("M9,11 L14,16 L9,21", stroke="#69db7c", sw=2)
    i.line((16, 22), (23, 22), WHITE, 1.8)
    return i


@icon("AddIns")
def _addins():
    i = Icon()
    i.path("M6,12 L12,12 A3,3 0 1 1 18,12 L24,12 L24,18 A3,3 0 1 1 24,24 L24,28 L6,28 Z",
           fill="#74c0fc", stroke=BLUE_D, sw=1.2)
    return i


@icon("TextCommands")
def _textcmd():
    i = Icon()
    i.path("M3,7 L29,7 L29,25 L3,25 Z", fill=WHITE, stroke=DARK)
    i.text((11, 20), "&gt;_", 9, DARK)
    return i


@icon("Preferences")
def _prefs():
    return _settings()


@icon("Export")
def _export():
    i = Icon()
    i.path("M5,4 L20,4 L25,9 L25,28 L5,28 Z", fill=WHITE, stroke=DARK)
    i.arrow((12, 18), (29, 18), GREEN, 2.2, 5)
    return i


@icon("Shortcuts")
def _shortcuts():
    i = Icon()
    i.path("M3,8 L29,8 L29,25 L3,25 Z", fill="#f8f9fa", stroke=DARK, sw=1.2)
    for x in range(7, 27, 5):
        for y in (12, 17):
            i.path("M%d,%d h3 v3 h-3 Z" % (x, y), fill=GREY, stroke="none")
    i.line((10, 22), (22, 22), GREY, 2)
    return i


@icon("Toolbox")
def _toolbox():
    i = Icon()
    i.circle((13, 13), 8, WHITE, DARK, 1.8)
    i.line((19, 19), (28, 28), DARK, 3)
    return i


@icon("Help")
def _help():
    i = Icon()
    i.circle((16, 16), 12, BLUE, BLUE, 1)
    i.text((16, 21.5), "?", 15, WHITE)
    return i


# ---------------------------------------------------------------------------
# sketch


def _sketch_base():
    return Icon()


def _pt(i, xy, color=BLUE):
    i.circle(xy, 1.9, WHITE, color, 1.1)


@icon("Line")
def _line():
    i = _sketch_base()
    i.path("M5,25 L14,9 L27,19", stroke=BLUE_D, sw=1.8)
    for p in ((5, 25), (14, 9), (27, 19)):
        _pt(i, p)
    return i


@icon("Rect2Point")
def _rect2p():
    i = _sketch_base()
    i.path("M5,8 L27,8 L27,24 L5,24 Z", fill="#e7f5ff", stroke=BLUE_D, sw=1.8)
    _pt(i, (5, 8))
    _pt(i, (27, 24))
    return i


@icon("RectCenter")
def _rectcenter():
    i = _rect2p()
    _pt(i, (16, 16), ORANGE)
    return i


@icon("Rect3Point")
def _rect3p():
    i = _sketch_base()
    i.path("M4,18 L18,6 L28,17 L14,29 Z", fill="#e7f5ff", stroke=BLUE_D, sw=1.8)
    for p in ((4, 18), (18, 6), (28, 17)):
        _pt(i, p)
    return i


@icon("Circle")
def _circle():
    i = _sketch_base()
    i.circle((16, 16), 11, "#e7f5ff", BLUE_D, 1.8)
    _pt(i, (16, 16))
    i.line((16, 16), (24, 8.5), GREY, 1, 'stroke-dasharray="2,1.5"')
    return i


@icon("Circle3Point")
def _circle3p():
    i = _sketch_base()
    i.circle((16, 16), 11, "#e7f5ff", BLUE_D, 1.8)
    for a in (200, 320, 80):
        r = math.radians(a)
        _pt(i, (16 + 11 * math.cos(r), 16 + 11 * math.sin(r)))
    return i


@icon("Arc3Point")
def _arc3p():
    i = _sketch_base()
    i.path("M5,24 A12,12 0 0 1 27,24", stroke=BLUE_D, sw=1.8)
    for p in ((5, 24), (16, 12.6), (27, 24)):
        _pt(i, p)
    return i


@icon("ArcCenter")
def _arccenter():
    i = _sketch_base()
    i.path("M26,22 A11,11 0 1 0 10,26", stroke=BLUE_D, sw=1.8)
    _pt(i, (16, 16), ORANGE)
    _pt(i, (26, 22))
    _pt(i, (10, 26))
    return i


@icon("Polygon")
def _polygon():
    i = _sketch_base()
    pts = [(16 + 12 * math.cos(math.radians(a)), 16 + 12 * math.sin(math.radians(a))) for a in range(-90, 270, 60)]
    i.poly(pts, "#e7f5ff", BLUE_D, 1.8)
    _pt(i, (16, 16), ORANGE)
    return i


@icon("Ellipse")
def _ellipse():
    i = _sketch_base()
    i.ellipse((16, 16), 13, 8, "#e7f5ff", BLUE_D, 1.8)
    _pt(i, (16, 16), ORANGE)
    return i


@icon("Slot")
def _slot():
    i = _sketch_base()
    i.path("M10,10 L22,10 A6,6 0 0 1 22,22 L10,22 A6,6 0 0 1 10,10 Z", fill="#e7f5ff", stroke=BLUE_D, sw=1.8)
    _pt(i, (10, 16), ORANGE)
    _pt(i, (22, 16), ORANGE)
    return i


@icon("Spline")
def _spline():
    i = _sketch_base()
    i.path("M4,24 C10,2 18,30 28,8", stroke=BLUE_D, sw=1.8)
    for p in ((4, 24), (12, 13), (20, 19), (28, 8)):
        _pt(i, p)
    return i


@icon("SplineCP")
def _splinecp():
    i = _sketch_base()
    i.path("M4,26 L10,6 L22,28 L28,8", stroke=GREY, sw=0.9, extra='stroke-dasharray="2,1.5"')
    i.path("M4,26 C10,6 22,28 28,8", stroke=BLUE_D, sw=1.8)
    for p in ((4, 26), (10, 6), (22, 28), (28, 8)):
        i.path("M%.1f,%.1f h3 v3 h-3 Z" % (p[0] - 1.5, p[1] - 1.5), fill=WHITE, stroke=BLUE, sw=1)
    return i


@icon("SketchPoint")
def _skpoint():
    i = _sketch_base()
    i.line((16, 6), (16, 26), GREY, 0.8)
    i.line((6, 16), (26, 16), GREY, 0.8)
    i.circle((16, 16), 3.6, WHITE, BLUE_D, 1.8)
    return i


@icon("SketchText")
def _sktext():
    i = _sketch_base()
    i.text((16, 24), "A", 20, BLUE_D)
    return i


@icon("SketchFillet")
def _skfillet():
    i = _sketch_base()
    i.path("M5,27 L5,15 A10,10 0 0 1 15,5 L27,5", stroke=BLUE_D, sw=1.8)
    i.path("M5,15 L5,5 L15,5", stroke=GREY, sw=0.9, extra='stroke-dasharray="2,1.5"')
    return i


@icon("SketchChamfer")
def _skchamfer():
    i = _sketch_base()
    i.path("M5,27 L5,14 L14,5 L27,5", stroke=BLUE_D, sw=1.8)
    i.path("M5,14 L5,5 L14,5", stroke=GREY, sw=0.9, extra='stroke-dasharray="2,1.5"')
    return i


@icon("Trim")
def _trim():
    i = _sketch_base()
    i.line((4, 16), (28, 16), BLUE_D, 1.8)
    i.line((12, 4), (12, 28), BLUE_D, 1.8)
    i.line((12, 16), (28, 16), RED, 1.8, 'stroke-dasharray="2.5,1.5"')
    i.path("M22,8 L26,12 M26,8 L22,12", stroke=RED, sw=1.6)
    return i


@icon("Extend")
def _extend():
    i = _sketch_base()
    i.line((4, 16), (16, 16), BLUE_D, 1.8)
    i.line((24, 4), (24, 28), BLUE_D, 1.8)
    i.arrow((16, 16), (23, 16), GREEN, 1.6, 3.5)
    return i


@icon("Break")
def _break():
    i = _sketch_base()
    i.line((4, 16), (14, 16), BLUE_D, 1.8)
    i.line((18, 16), (28, 16), BLUE_D, 1.8)
    _pt(i, (14, 16), ORANGE)
    _pt(i, (18, 16), ORANGE)
    return i


@icon("SketchOffset")
def _skoffset():
    i = _sketch_base()
    i.path("M8,26 L8,12 A4,4 0 0 1 12,8 L26,8", stroke=BLUE_D, sw=1.8)
    i.path("M4,26 L4,12 A8,8 0 0 1 12,4 L26,4", stroke=ORANGE, sw=1.4)
    i.path("M13,26 L13,16 A3,3 0 0 1 16,13 L26,13", stroke=GREY, sw=0.9, extra='stroke-dasharray="2,1.5"')
    return i


@icon("SketchMirror")
def _skmirror():
    i = _sketch_base()
    i.poly([(4, 24), (12, 8), (13, 24)], "#e7f5ff", BLUE_D, 1.6)
    i.poly([(28, 24), (20, 8), (19, 24)], "#e7f5ff", BLUE_D, 1.6)
    i.line((16, 3), (16, 29), ORANGE, 1.4, 'stroke-dasharray="3,2"')
    return i


@icon("SketchCircPattern")
def _skcircpat():
    i = _sketch_base()
    i.circle((16, 16), 10, "none", GREY, 0.9, 'stroke-dasharray="2,1.5"')
    for k in range(6):
        a = k * math.pi / 3
        i.circle((16 + 10 * math.cos(a), 16 + 10 * math.sin(a)), 2.6, "#e7f5ff", BLUE_D, 1.3)
    return i


@icon("SketchRectPattern")
def _skrectpat():
    i = _sketch_base()
    for x in (8, 16, 24):
        for y in (9, 19):
            i.path("M%d,%d h5 v5 h-5 Z" % (x - 2.5, y - 2.5 + 2), fill="#e7f5ff", stroke=BLUE_D, sw=1.3)
    return i


@icon("Project")
def _project():
    i = Icon(16, 13, 1.0)
    i.box(-6, -6, -1, 12, 12, 8)
    i.rect_xy(-6, -6, -9, 12, 12, fill="none", stroke="#9c36b5", sw=1.6)
    for (x, y) in ((6, -6), (-6, 6), (6, 6)):
        i.line(i.p(x, y, -1), i.p(x, y, -9), "#9c36b5", 0.9, 'stroke-dasharray="1.5,1.5"')
    return i


@icon("SketchDimension")
def _skdim():
    i = _sketch_base()
    i.line((6, 22), (6, 28), DARK, 1)
    i.line((26, 22), (26, 28), DARK, 1)
    i.arrow((16, 25), (6.5, 25), DARK, 1, 3)
    i.arrow((16, 25), (25.5, 25), DARK, 1, 3)
    i.line((6, 18), (26, 18), BLUE_D, 1.8)
    i.text((16, 13), "10", 9, DARK)
    return i


@icon("Construction")
def _construction():
    i = _sketch_base()
    i.line((5, 26), (27, 6), ORANGE, 1.8, 'stroke-dasharray="4,2.5"')
    _pt(i, (5, 26), ORANGE)
    _pt(i, (27, 6), ORANGE)
    return i


@icon("SketchMove")
def _skmove():
    i = _move()
    return i


@icon("SketchScale")
def _skscale():
    i = _sketch_base()
    i.path("M4,14 L14,14 L14,28 L4,28 Z", fill="#e7f5ff", stroke=BLUE_D, sw=1.6)
    i.path("M4,4 L28,4 L28,28", stroke=GREY, sw=1, extra='stroke-dasharray="2,1.5"')
    i.arrow((14, 14), (26, 6), BLUE, 1.5, 3.5)
    return i


@icon("FinishSketch")
def _finishsketch():
    i = Icon()
    i.circle((16, 16), 13, GREEN, "none", 0)
    i.path("M9,16.5 L14,21.5 L23.5,11", stroke=WHITE, sw=3)
    return i


@icon("Coincident")
def _coincident():
    i = _sketch_base()
    i.line((4, 26), (16, 16), BLUE_D, 1.6)
    i.line((16, 16), (28, 22), BLUE_D, 1.6)
    i.circle((16, 16), 3.2, YELLOW, DARK, 1)
    return i


@icon("HorizontalVertical")
def _horvert():
    i = _sketch_base()
    i.line((4, 22), (22, 22), BLUE_D, 1.8)
    i.line((26, 4), (26, 22), BLUE_D, 1.8)
    i.text((12, 16), "H", 9, DARK)
    return i


@icon("Tangent")
def _tangent():
    i = _sketch_base()
    i.circle((13, 19), 9, "none", BLUE_D, 1.6)
    i.line((4, 10), (29, 10), BLUE_D, 1.6)
    return i


@icon("Equal")
def _equal():
    i = _sketch_base()
    i.line((5, 8), (27, 8), BLUE_D, 1.6)
    i.line((5, 24), (27, 24), BLUE_D, 1.6)
    i.text((16, 20), "=", 13, DARK)
    return i


@icon("Parallel")
def _parallel():
    i = _sketch_base()
    i.line((4, 22), (22, 4), BLUE_D, 1.6)
    i.line((10, 28), (28, 10), BLUE_D, 1.6)
    return i


@icon("Perpendicular")
def _perpendicular():
    i = _sketch_base()
    i.line((6, 26), (28, 26), BLUE_D, 1.6)
    i.line((12, 4), (12, 26), BLUE_D, 1.6)
    i.path("M12,20 L18,20 L18,26", stroke=DARK, sw=1)
    return i


@icon("Fix")
def _fix():
    i = _sketch_base()
    i.path("M9,15 L23,15 L23,28 L9,28 Z", fill=YELLOW, stroke=DARK, sw=1.2)
    i.path("M12,15 L12,10 A4,4 0 0 1 20,10 L20,15", stroke=DARK, sw=1.8)
    return i


@icon("Midpoint")
def _midpoint():
    i = _sketch_base()
    i.line((4, 20), (28, 20), BLUE_D, 1.6)
    i.poly([(16, 14), (20, 22), (12, 22)], YELLOW, DARK, 1)
    return i


@icon("Concentric")
def _concentric():
    i = _sketch_base()
    i.circle((16, 16), 12, "none", BLUE_D, 1.5)
    i.circle((16, 16), 6, "none", BLUE_D, 1.5)
    i.circle((16, 16), 1.8, DARK, DARK)
    return i


@icon("Collinear")
def _collinear():
    i = _sketch_base()
    i.line((3, 26), (13, 17), BLUE_D, 1.8)
    i.line((19, 12), (29, 3), BLUE_D, 1.8)
    i.line((13, 17), (19, 12), GREY, 1, 'stroke-dasharray="2,1.5"')
    return i


@icon("Symmetry")
def _symmetry():
    i = _sketch_base()
    i.line((16, 3), (16, 29), ORANGE, 1.3, 'stroke-dasharray="3,2"')
    _pt(i, (7, 16))
    _pt(i, (25, 16))
    i.text((16, 11), "[ ]", 8, DARK)
    return i


@icon("Horizontal")
def _horizontal():
    i = _sketch_base()
    i.line((4, 20), (28, 20), BLUE_D, 1.8)
    i.text((16, 14), "H", 10, DARK)
    return i


@icon("Vertical")
def _vertical():
    i = _sketch_base()
    i.line((20, 4), (20, 28), BLUE_D, 1.8)
    i.text((11, 20), "V", 10, DARK)
    return i


# ---------------------------------------------------------------------------
# navigation bar / timeline


@icon("Orbit")
def _orbit():
    i = Icon()
    i.ellipse((16, 16), 12, 5, "none", DARK, 1.6)
    i.circle((16, 16), 4.5, BLUE, DARK, 1)
    i.poly([(26, 10), (29.5, 13), (25, 14)], DARK, DARK, 0.5)
    return i


@icon("LookAt")
def _lookat():
    i = Icon(16, 16, 1.0)
    i.rect_xy(-9, -9, 0, 18, 18, fill="#e7f5ff", stroke=DARK, sw=1)
    i.arrow((16, 2), (16, 14), BLUE, 1.8, 4)
    return i


@icon("Pan")
def _pan():
    i = Icon()
    i.path("M11,28 C7,24 5,20 5,16 L5,13 A1.8,1.8 0 0 1 8.6,13 L8.6,17 L10,17 L10,7 A1.8,1.8 0 0 1 13.6,7 "
           "L13.6,16 L15,16 L15,5 A1.8,1.8 0 0 1 18.6,5 L18.6,16 L20,16 L20,7 A1.8,1.8 0 0 1 23.6,7 L23.6,19 "
           "C23.6,23 22,26 20,28 Z", fill=WHITE, stroke=DARK, sw=1.3)
    return i


@icon("Zoom")
def _zoom():
    i = Icon()
    i.circle((13, 13), 9, "#e7f5ff", DARK, 1.8)
    i.line((19.5, 19.5), (28, 28), DARK, 3)
    i.line((9, 13), (17, 13), DARK, 1.5)
    i.line((13, 9), (13, 17), DARK, 1.5)
    return i


@icon("Fit")
def _fit():
    i = Icon()
    for (x, y, dx, dy) in ((4, 4, 1, 1), (28, 4, -1, 1), (4, 28, 1, -1), (28, 28, -1, -1)):
        i.path("M%d,%d L%d,%d M%d,%d L%d,%d" % (x, y, x + 6 * dx, y, x, y, x, y + 6 * dy), stroke=DARK, sw=1.8)
    _minibox(i, 16, 17, 0.45)
    return i


@icon("DisplayMode")
def _displaymode():
    i = Icon()
    i.path("M4,6 L28,6 L28,24 L4,24 Z", fill=WHITE, stroke=DARK, sw=1.4)
    i.line((12, 28), (20, 28), DARK, 1.8)
    _minibox(i, 16, 16, 0.4)
    return i


@icon("Grid")
def _grid():
    i = Icon()
    for k in range(5):
        v = 4 + k * 6
        i.line((v, 4), (v, 28), DARK, 1)
        i.line((4, v), (28, v), DARK, 1)
    return i


@icon("Viewports")
def _viewports():
    i = Icon()
    i.path("M4,4 L28,4 L28,28 L4,28 Z", fill=WHITE, stroke=DARK, sw=1.4)
    i.line((16, 4), (16, 28), DARK, 1.2)
    i.line((4, 16), (28, 16), DARK, 1.2)
    return i


@icon("Home")
def _home():
    i = Icon()
    i.path("M4,16 L16,5 L28,16 M8,13 L8,27 L14,27 L14,20 L18,20 L18,27 L24,27 L24,13", stroke=DARK, sw=1.8)
    return i


@icon("TLStart")
def _tlstart():
    i = Icon()
    i.line((8, 7), (8, 25), DARK, 2.2)
    i.poly([(25, 7), (25, 25), (11, 16)], DARK, DARK, 0.5)
    return i


@icon("TLBack")
def _tlback():
    i = Icon()
    i.poly([(22, 7), (22, 25), (8, 16)], DARK, DARK, 0.5)
    return i


@icon("TLForward")
def _tlforward():
    i = Icon()
    i.poly([(10, 7), (10, 25), (24, 16)], DARK, DARK, 0.5)
    return i


@icon("TLEnd")
def _tlend():
    i = Icon()
    i.poly([(7, 7), (7, 25), (21, 16)], DARK, DARK, 0.5)
    i.line((24, 7), (24, 25), DARK, 2.2)
    return i


@icon("TLPlay")
def _tlplay():
    i = Icon()
    i.poly([(9, 6), (9, 26), (26, 16)], DARK, DARK, 0.5)
    return i


# workspaces


@icon("WSDesign")
def _wsdesign():
    i = Icon(16, 17, 1.0)
    i.box(-7, -7, -6, 14, 14, 12, top="#d0ebff", left="#74c0fc", right="#339af0")
    return i


@icon("WSDrawing")
def _wsdrawing():
    i = Icon()
    i.path("M4,5 L28,5 L28,27 L4,27 Z", fill=WHITE, stroke=DARK)
    i.path("M8,22 L8,12 L16,12 L16,17 L22,17 L22,22 Z", stroke=BLUE_D, sw=1.3)
    i.line((20, 25), (27, 25), DARK, 0.8)
    return i


@icon("WSSimulation")
def _wssimulation():
    i = Icon()
    i.path("M4,24 L28,24 L28,14 L4,14 Z", fill="url(#fem)", stroke=DARK)
    i.add('<defs><linearGradient id="fem" x1="0" x2="1"><stop offset="0" stop-color="#1c7ed6"/>'
          '<stop offset="0.5" stop-color="#40c057"/><stop offset="1" stop-color="#fa5252"/></linearGradient></defs>')
    i.arrow((22, 4), (22, 13), DARK, 1.6, 3.5)
    return i


@icon("WSManufacture")
def _wsmanufacture():
    i = Icon()
    i.path("M13,3 L19,3 L19,14 L16,19 L13,14 Z", fill="#adb5bd", stroke=DARK)
    i.path("M4,22 L28,22 L28,28 L4,28 Z", fill=LEFT, stroke=DARK)
    i.path("M9,22 Q16,16 23,22", fill="#dee2e6", stroke=DARK, sw=0.8)
    return i


@icon("WSRender")
def _wsrender():
    i = Icon()
    i.add('<defs><radialGradient id="rnd" cx="0.3" cy="0.3" r="0.8"><stop offset="0" stop-color="#fff3bf"/>'
          '<stop offset="0.6" stop-color="#fab005"/><stop offset="1" stop-color="#e67700"/></radialGradient></defs>')
    i.circle((16, 16), 11, "url(#rnd)", DARK, 0.8)
    return i


@icon("WSAnimation")
def _wsanimation():
    i = _exploded()
    return i


@icon("WSAssembly")
def _wsassembly():
    return _joint()


@icon("WSGenerative")
def _wsgenerative():
    i = Icon()
    i.path("M4,26 C10,6 22,6 28,26", stroke=GREEN, sw=3)
    i.path("M10,26 C13,14 19,14 22,26", stroke=GREEN, sw=2)
    return i


@icon("DataPanel")
def _datapanel():
    i = Icon()
    for x in (5, 13, 21):
        for y in (5, 13, 21):
            i.path("M%d,%d h6 v6 h-6 Z" % (x, y), fill=DARK, stroke="none")
    return i


@icon("File")
def _file():
    i = Icon()
    i.path("M7,4 L20,4 L26,10 L26,28 L7,28 Z", fill=WHITE, stroke=DARK, sw=1.4)
    i.path("M20,4 L20,10 L26,10", stroke=DARK, sw=1.2)
    return i


@icon("Save")
def _save():
    i = Icon()
    i.path("M5,5 L24,5 L28,9 L28,28 L5,28 Z", fill=BLUE, stroke=BLUE_D, sw=1.2)
    i.path("M10,5 L22,5 L22,12 L10,12 Z", fill=WHITE)
    i.path("M9,18 L24,18 L24,28 L9,28 Z", fill=WHITE)
    return i


@icon("Undo")
def _undo():
    i = Icon()
    i.path("M10,11 L20,11 A7,7 0 0 1 20,25 L12,25", stroke=DARK, sw=2.2)
    i.poly([(4, 11), (11, 5), (11, 17)], DARK, DARK, 0.5)
    return i


@icon("Redo")
def _redo():
    i = Icon()
    i.path("M22,11 L12,11 A7,7 0 0 0 12,25 L20,25", stroke=DARK, sw=2.2)
    i.poly([(28, 11), (21, 5), (21, 17)], DARK, DARK, 0.5)
    return i


@icon("NewDesign")
def _newdesign():
    return _file().badge("plus", 24, 24)


@icon("Open")
def _open():
    i = _folder()
    return i


@icon("Sheetmetal")
def _sheetmetal():
    i = Icon(16, 18, 1.0)
    p = i.p
    i.poly([p(-8, -8, 0), p(8, -8, 0), p(8, 8, 0), p(-8, 8, 0)], TOP)
    i.poly([p(8, -8, 0), p(8, 8, 0), p(8, 8, 1.2), p(8, -8, 1.2)], RIGHT)
    i.poly([p(-8, 8, 0), p(8, 8, 0), p(8, 8, 12), p(-8, 8, 12)], LEFT)
    return i


@icon("Flange")
def _flange():
    return _sheetmetal()


@icon("Unfold")
def _unfold():
    i = Icon(16, 18, 1.0)
    p = i.p
    i.poly([p(-8, -12, 0), p(8, -12, 0), p(8, 12, 0), p(-8, 12, 0)], TOP)
    i.line(p(-8, 0, 0), p(8, 0, 0), ORANGE, 1.2, 'stroke-dasharray="2,1.5"')
    return i


@icon("Surface")
def _surface():
    i = Icon()
    i.path("M3,22 Q10,10 16,16 T29,10 L29,20 Q22,26 16,22 T3,28 Z", fill="#a5d8ff", stroke=BLUE_D, sw=1)
    return i


@icon("Patch")
def _patch():
    i = Icon()
    i.path("M5,22 Q16,4 27,22 Q16,28 5,22 Z", fill="#a5d8ff", stroke=BLUE_D, sw=1)
    i.path("M5,22 Q16,28 27,22", stroke=ORANGE, sw=1.6)
    return i


@icon("Stitch")
def _stitch():
    i = _surface()
    for x in (8, 14, 20, 26):
        i.line((x, 12), (x - 3, 22), ORANGE, 1.2)
    return i


@icon("Mesh")
def _mesh():
    return _insertmesh()


@icon("MeshToBRep")
def _meshtobrep():
    i = Icon()
    pts = [(10, 6), (20, 11), (20, 23), (10, 28), (2, 23), (2, 11)]
    i.poly(pts, "#d0ebff", BLUE_D, 1)
    i.arrow((17, 17), (26, 17), GREEN, 1.8, 4)
    _minibox(i, 26, 10, 0.3)
    return i


@icon("Reduce")
def _reduce():
    i = _insertmesh()
    i.arrow((28, 4), (21, 11), RED, 1.6, 3.5)
    return i


@icon("Repair")
def _repair():
    i = _insertmesh()
    i.path("M20,20 L28,28", stroke=DARK, sw=3)
    i.circle((20, 20), 3, "none", DARK, 1.6)
    return i


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, fn in sorted(ICONS.items()):
        with open(os.path.join(OUT, name + ".svg"), "w") as f:
            f.write(fn().svg())
    print("wrote %d icons to %s" % (len(ICONS), os.path.normpath(OUT)))


if __name__ == "__main__":
    main()
