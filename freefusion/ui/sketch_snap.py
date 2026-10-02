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
# key points are cached briefly: snap() runs on every mouse move


_cache = {"key": None, "time": 0.0, "points": None}


def _cached_points(sk):
    import time
    now = time.monotonic()
    key = (sk.Document.Name, sk.Name)
    if _cache["key"] != key or now - _cache["time"] > 0.15:
        _cache.update(key=key, time=now, points=key_points_typed(sk))
    return _cache["points"]


def key_points_typed(sk):
    """[(u, v, kind)] with kind 'end', 'mid', 'center' or 'cross' (line intersections)."""
    import Part
    out = [(0.0, 0.0, "end")]
    segs = []
    for g, _ in _curves(sk):
        try:
            if isinstance(g, Part.Point):
                out.append((g.X, g.Y, "end"))
                continue
            if hasattr(g, "Center"):
                c = g.Center
                out.append((c.x, c.y, "center"))
            if isinstance(g, (Part.Circle, Part.Ellipse)):
                continue
            if hasattr(g, "StartPoint"):
                a, b = g.StartPoint, g.EndPoint
                out += [(a.x, a.y, "end"), (b.x, b.y, "end")]
                if isinstance(g, Part.LineSegment):
                    out.append(((a.x + b.x) / 2, (a.y + b.y) / 2, "mid"))
                    segs.append((a.x, a.y, b.x, b.y))
                else:
                    m = g.value((g.FirstParameter + g.LastParameter) / 2)
                    out.append((m.x, m.y, "mid"))
        except Exception:
            continue
    # intersections of line segments (not at their ends)
    if len(segs) <= 150:
        for i in range(len(segs)):
            x1, y1, x2, y2 = segs[i]
            for j in range(i + 1, len(segs)):
                x3, y3, x4, y4 = segs[j]
                den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
                if abs(den) < 1e-12:
                    continue
                t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
                u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / den
                if 1e-6 < t < 1 - 1e-6 and 1e-6 < u < 1 - 1e-6:
                    out.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1), "cross"))
    return out


# ---------------------------------------------------------------------------
# snap marker: shows where the point will go (the mouse pointer itself is not moved)


class _Marker(object):
    KINDS = {"end": "SQUARE_LINE_9_9", "mid": "TRIANGLE_LINE_9_9", "center": "CIRCLE_LINE_9_9",
             "cross": "CROSS_9_9", "grid": "CIRCLE_FILLED_5_5"}

    def __init__(self):
        self.view = None
        self.root = None

    def _build(self, view):
        from pivy import coin
        self.view = view
        root = coin.SoAnnotation() if hasattr(coin, "SoAnnotation") else coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        root.addChild(pick)
        self.xf = coin.SoTransform()
        root.addChild(self.xf)
        self.color = coin.SoBaseColor()
        root.addChild(self.color)
        self.coords = coin.SoCoordinate3()
        root.addChild(self.coords)
        self.markers = coin.SoMarkerSet()
        root.addChild(self.markers)
        self.root = root
        view.getSceneGraph().addChild(root)

    def show(self, view, sk, u, v, kind):
        from pivy import coin
        if self.root is None or self.view is not view:
            self.hide()
            self._build(view)
        pl = sk.getGlobalPlacement()
        q = pl.Rotation.Q
        self.xf.translation = tuple(pl.Base)
        self.xf.rotation.setValue(q[0], q[1], q[2], q[3])
        self.coords.point.setValues(0, 1, [(u, v, 0.02)])
        self.markers.markerIndex = getattr(coin.SoMarkerSet, self.KINDS.get(kind, "CIRCLE_FILLED_5_5"))
        self.color.rgb = (0.92, 0.45, 0.05) if kind != "grid" else (0.02, 0.59, 0.84)

    def hide(self):
        if self.root is not None:
            try:
                self.view.getSceneGraph().removeChild(self.root)
            except Exception:
                pass
        self.root = None
        self.view = None


_marker = _Marker()


def hide_marker():
    _marker.hide()


def _snap_to_grid_param():
    grp = App.ParamGet(SNAP)
    if not grp.GetBool("SnapToGrid", False):
        grp.SetBool("SnapToGrid", True)


def snap(widget, x, y, modifiers=None, grid_only=False):
    """Return the snapped widget position (QPoint) for pixel (x, y), or None.

    grid_only: dragging existing geometry (its own end points must not catch it)."""
    if not enabled():
        hide_marker()
        return None
    if modifiers is not None and modifiers & QtCore.Qt.ControlModifier:
        hide_marker()
        return None
    sk = _sketch()
    if sk is None:
        hide_marker()
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
    from . import grid
    step = grid.sketch_step() or nice_step(mm_per_px)
    _state["step"] = step
    _snap_to_grid_param()
    u, v = here
    # 1. key points: ends, midpoints, centers, intersections
    best, best_d, kind = None, KEY_RADIUS * mm_per_px, None
    for (a, b, k) in (() if grid_only else _cached_points(sk)):
        d = math.hypot(a - u, b - v)
        if d < best_d - 1e-9 or (best is not None and abs(d - best_d) < 1e-9 and k == "end"):
            best, best_d, kind = (a, b), d, k
    if best is None and not grid_only:
        # 2. near a curve: let FreeCAD put the point on it
        d = distance_to_curves(sk, u, v)
        if d is not None and d < EDGE_RADIUS * mm_per_px:
            _state["last"] = None
            hide_marker()
            return None
    if best is None:
        # 3. the grid
        best, kind = (round(u / step) * step, round(v / step) * step), "grid"
    sx, sy = pr.to_screen(*best)
    _state["last"] = best
    try:
        _marker.show(view, sk, best[0], best[1], kind)
    except Exception as e:
        App.Console.PrintLog("FreeFusion snap marker: %s\n" % e)
    return QtCore.QPoint(int(round(sx)), int(round(sy)))


def last_point():
    return _state["last"]


def current_step():
    return _state["step"]


def sketch_opened(sk):
    """FreeCAD's sketch grid stays on (drawn invisibly) so snapped points are exact."""
    if sk is None:
        return
    try:
        vo = sk.ViewObject
        vo.ShowGrid = True
        vo.GridAuto = False
    except Exception:
        pass


def grid_shown():
    from . import grid
    return grid.sketch_visible()


def toggle_grid():
    from . import grid
    grid.set_sketch_visible(not grid.sketch_visible())


def toggle_snap():
    """Fusion's Snap toggle: our round-value snapping and FreeCAD's object snapping."""
    on = not enabled()
    params.set_bool("SketchSnap", on)
    App.ParamGet(SNAP).SetBool("Snap", on)
    if not on:
        hide_marker()
    from . import notify
    notify.status("Snap %s" % ("on" if on else "off"))
