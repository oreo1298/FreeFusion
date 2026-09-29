# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion-style snapping while a sketch tool runs.

FreeCAD only snaps when the cursor is already very close to the grid or to geometry.
Fusion locks the cursor to round increments that follow the zoom level and pulls it
onto nearby endpoints, midpoints and centers. The view filter asks `snap()` for the
position every mouse event of a sketch tool should have, and sends FreeCAD that
position instead. To get exact values (a pixel is never exactly 10 mm) FreeCAD's own
grid snap is set to the same step, so it rounds the last fraction of a pixel away.
"""

import math

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from .. import params

SNAP = "User parameter:BaseApp/Preferences/Mod/Sketcher/Snap"
KEY_RADIUS = 11      # px: endpoints, midpoints and centers win inside this radius
EDGE_RADIUS = 6      # px: near a curve FreeCAD's own snap puts the point on it
NICE = (1.0, 2.0, 5.0)

_state = {"step": None, "sketch": None, "last": None}


def enabled():
    return params.get_bool("SketchSnap", True) and App.ParamGet(SNAP).GetBool("Snap", True)


def min_pixels():
    return max(6, params.get_int("SnapPixels", 20))


def nice_step(mm_per_px, min_px=None):
    """Smallest 1/2/5 x 10^n step that is at least `min_px` pixels on screen."""
    want = (min_px or min_pixels()) * mm_per_px
    if want <= 0 or not math.isfinite(want):
        return 1.0
    e = math.floor(math.log10(want))
    for k in (e, e + 1):
        for n in NICE:
            s = n * 10 ** k
            if s >= want * 0.999:
                return float(s)
    return float(10 ** (e + 1))


def _sketch():
    from ..commands.base import editing_object, in_sketch
    if not in_sketch():
        return None
    sk = editing_object()
    if sk is None or not sk.isDerivedFrom("Sketcher::SketchObject"):
        return None
    return sk


# ---------------------------------------------------------------------------
# screen <-> sketch plane


def project_point(vv, p):
    """World point -> normalized screen coordinates (x, y), y up."""
    from pivy import coin
    src = coin.SbVec3f(p.x, p.y, p.z)
    try:
        out = vv.projectToScreen(src)
    except TypeError:
        out = coin.SbVec3f()
        vv.projectToScreen(src, out)
    x, y, _ = out.getValue()
    return x, y


def project_line(vv, nx, ny):
    """Normalized screen point -> (point, direction) of the view ray."""
    from pivy import coin
    pt = coin.SbVec2f(nx, ny)
    try:
        res = vv.projectPointToLine(pt)
    except TypeError:
        res = coin.SbLine()
        vv.projectPointToLine(pt, res)
    if isinstance(res, (tuple, list)):
        a = App.Vector(*res[0].getValue())
        b = App.Vector(*res[1].getValue())
        return a, (b - a).normalize()
    return App.Vector(*res.getPosition().getValue()), App.Vector(*res.getDirection().getValue())


class Projector(object):
    """Maps widget pixels to sketch coordinates and back with the live camera."""

    def __init__(self, view, widget, sketch):
        from pivy import coin
        self.coin = coin
        self.w = max(1, widget.width())
        self.h = max(1, widget.height())
        cam = view.getCameraNode()
        self.vv = cam.getViewVolume(float(self.w) / self.h)
        pl = sketch.getGlobalPlacement()
        self.pl = pl
        self.inv = pl.inverse()
        self.origin = pl.Base
        self.normal = pl.Rotation.multVec(App.Vector(0, 0, 1))

    def to_sketch(self, x, y):
        """Widget pixel -> (u, v) in sketch coordinates, or None."""
        coin = self.coin
        nx = float(x) / self.w
        ny = float(self.h - 1 - y) / self.h
        p, d = project_line(self.vv, nx, ny)
        den = d.dot(self.normal)
        if abs(den) < 1e-9:
            return None
        t = (self.origin - p).dot(self.normal) / den
        loc = self.inv.multVec(p + d * t)
        return loc.x, loc.y

    def to_screen(self, u, v):
        """Sketch coordinates -> widget pixel (floats)."""
        coin = self.coin
        g = self.pl.multVec(App.Vector(u, v, 0))
        nx, ny = project_point(self.vv, g)
        return nx * self.w, self.h - 1 - ny * self.h


# ---------------------------------------------------------------------------
# geometry


def _curves(sk):
    out = []
    try:
        out += [(g, i) for i, g in enumerate(sk.Geometry)]
    except Exception:
        pass
    try:
        ext = sk.ExternalGeo
        out += [(g, -3 - i) for i, g in enumerate(ext[2:])]   # 0 and 1 are the axes
    except Exception:
        pass
    return out


def key_points(sk):
    """Endpoints, midpoints and centers in sketch coordinates."""
    import Part
    pts = [(0.0, 0.0)]
    for g, _ in _curves(sk):
        try:
            if isinstance(g, Part.Point):
                pts.append((g.X, g.Y))
                continue
            if hasattr(g, "Center"):
                c = g.Center
                pts.append((c.x, c.y))
            if isinstance(g, (Part.Circle, Part.Ellipse)):
                continue
            if hasattr(g, "StartPoint"):
                a, b = g.StartPoint, g.EndPoint
                pts += [(a.x, a.y), (b.x, b.y)]
                if isinstance(g, Part.LineSegment):
                    pts.append(((a.x + b.x) / 2, (a.y + b.y) / 2))
                else:
                    m = g.value((g.FirstParameter + g.LastParameter) / 2)
                    pts.append((m.x, m.y))
        except Exception:
            continue
    return pts


def distance_to_curves(sk, u, v):
    p = App.Vector(u, v, 0)
    best = None
    for g, _ in _curves(sk):
        try:
            if not hasattr(g, "parameter"):
                continue
            t = g.parameter(p)
            if hasattr(g, "StartPoint"):
                t = min(max(t, g.FirstParameter), g.LastParameter)
            d = (g.value(t) - p).Length
        except Exception:
            continue
        if best is None or d < best:
            best = d
    return best


# ---------------------------------------------------------------------------


def _set_grid(sk, step):
    vo = sk.ViewObject
    try:
        if vo.GridAuto:
            vo.GridAuto = False
        if abs(vo.GridSize.Value - step) > 1e-9:
            vo.GridSize = step
    except Exception:
        pass
    # exact values come from FreeCAD's grid snap, which only works while the grid is drawn
    try:
        want = bool(vo.ShowGrid)
        grp = App.ParamGet(SNAP)
        if grp.GetBool("SnapToGrid", False) != want:
            grp.SetBool("SnapToGrid", want)
    except Exception:
        pass


def snap(widget, x, y, modifiers=None):
    """Return the snapped widget position (QPoint) for pixel (x, y), or None."""
    if not enabled():
        return None
    if modifiers is not None and modifiers & QtCore.Qt.ControlModifier:
        return None
    sk = _sketch()
    if sk is None:
        return None
    try:
        view = Gui.ActiveDocument.ActiveView
        pr = Projector(view, widget, sk)
    except Exception as e:
        App.Console.PrintLog("FreeFusion snap: %s\n" % e)
        return None
    here = pr.to_sketch(x, y)
    there = pr.to_sketch(x + 10, y)
    there2 = pr.to_sketch(x, y + 10)
    if here is None or there is None or there2 is None:
        return None
    mm_per_px = max(math.hypot(there[0] - here[0], there[1] - here[1]),
                    math.hypot(there2[0] - here[0], there2[1] - here[1])) / 10.0
    if mm_per_px <= 0:
        return None
    step = nice_step(mm_per_px)
    _state["step"] = step
    _set_grid(sk, step)
    u, v = here
    # 1. key points
    best, best_d = None, KEY_RADIUS * mm_per_px
    for (a, b) in key_points(sk):
        d = math.hypot(a - u, b - v)
        if d < best_d:
            best, best_d = (a, b), d
    if best is None:
        # 2. near a curve: let FreeCAD put the point on it
        d = distance_to_curves(sk, u, v)
        if d is not None and d < EDGE_RADIUS * mm_per_px:
            _state["last"] = None
            return None
        # 3. round increments
        best = (round(u / step) * step, round(v / step) * step)
    sx, sy = pr.to_screen(*best)
    _state["last"] = best
    return QtCore.QPoint(int(round(sx)), int(round(sy)))


def last_point():
    return _state["last"]


def current_step():
    return _state["step"]


def sketch_opened(sk):
    """Show the sketch grid (Fusion shows it by default)."""
    if sk is None or not params.get_bool("SketchGridOnOpen", True):
        return
    try:
        vo = sk.ViewObject
        vo.ShowGrid = True
        vo.GridAuto = False
    except Exception:
        pass
