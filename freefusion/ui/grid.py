# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion-style adaptive grid: on the ground (XY) plane, and on the sketch plane while sketching.

The spacing follows the zoom: minor lines are at least MINOR_PX apart and land on
round values (1, 2, 5 x 10^n), every 5th (or 10th) line is a major line, and the grid
always fills the view. While sketching, the minor spacing is also the snapping step,
so the cursor locks to the lines you see.
"""

import math

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from .. import params

MINOR_PX = 16
MAX_LINES = 900
SKETCH_GRID = "User parameter:BaseApp/Preferences/Mod/Sketcher/General"

_state = {"grids": {}, "timer": None, "enabled": False, "saved": None}


def _coin():
    from pivy import coin
    return coin


def ground_visible():
    return params.get_bool("ShowGrid", True)


def set_ground_visible(on):
    params.set_bool("ShowGrid", on)
    refresh(force=True)


def sketch_visible():
    return params.get_bool("SketchGrid", True)


def set_sketch_visible(on):
    params.set_bool("SketchGrid", on)
    refresh(force=True)


def nice(value):
    """Smallest 1/2/5 x 10^n that is >= value."""
    if value <= 0 or not math.isfinite(value):
        return 1.0
    e = math.floor(math.log10(value))
    for k in (e, e + 1):
        for n in (1.0, 2.0, 5.0):
            s = n * 10 ** k
            if s >= value * 0.999:
                return float(s)
    return float(10 ** (e + 1))


def major_of(minor):
    lead = round(minor / 10 ** math.floor(math.log10(minor) + 1e-9))
    return minor * (5 if lead in (1, 2) else 10)


# ---------------------------------------------------------------------------
# view geometry


def _widget(view):
    try:
        return view.graphicsView().viewport()
    except Exception:
        return None


def plane_frame(view, placement):
    """Visible region of a plane: (minor, major, umin, umax, vmin, vmax, mm_per_px) or None."""
    from .sketch_snap import project_line
    w = _widget(view)
    if w is None:
        return None
    W, H = max(1, w.width()), max(1, w.height())
    cam = view.getCameraNode()
    vv = cam.getViewVolume(float(W) / H)
    n = placement.Rotation.multVec(App.Vector(0, 0, 1))
    o = placement.Base
    inv = placement.inverse()

    def hit(nx, ny):
        p, d = project_line(vv, nx, ny)
        den = d.dot(n)
        if abs(den) < 1e-9:
            return None
        t = (o - p).dot(n) / den
        if t < 0:
            return None
        return inv.multVec(p + d * t)

    c = hit(0.5, 0.5)
    c2 = hit(0.5 + 10.0 / W, 0.5)
    c3 = hit(0.5, 0.5 + 10.0 / H)
    if c is None or c2 is None or c3 is None:
        return None
    mm_px = max((c2 - c).Length, (c3 - c).Length) / 10.0
    if mm_px <= 0 or not math.isfinite(mm_px):
        return None
    minor = nice(MINOR_PX * mm_px)
    major = major_of(minor)
    limit = 60 * major
    pts = [c]
    for nx, ny in ((0, 0), (1, 0), (0, 1), (1, 1), (0.5, 0), (0.5, 1), (0, 0.5), (1, 0.5)):
        p = hit(nx, ny)
        if p is None:
            # the plane runs to the horizon on this side: draw up to `limit`
            continue
        pts.append(p)
    umin = max(min(p.x for p in pts), c.x - limit)
    umax = min(max(p.x for p in pts), c.x + limit)
    vmin = max(min(p.y for p in pts), c.y - limit)
    vmax = min(max(p.y for p in pts), c.y + limit)
    if len(pts) < 9:
        # some corners see the sky: extend the visible side to the limit
        umin, umax = min(umin, c.x - limit / 3), max(umax, c.x + limit / 3)
        vmin, vmax = min(vmin, c.y - limit / 3), max(vmax, c.y + limit / 3)
    pad = major
    umin = math.floor((umin - pad) / major) * major
    umax = math.ceil((umax + pad) / major) * major
    vmin = math.floor((vmin - pad) / major) * major
    vmax = math.ceil((vmax + pad) / major) * major
    return minor, major, umin, umax, vmin, vmax, mm_px


# ---------------------------------------------------------------------------
# scene graph


def _colors():
    dark = params.get_string("Theme", "light") == "dark"
    if dark:
        return (0.29, 0.31, 0.34), (0.39, 0.42, 0.46)
    return (0.84, 0.86, 0.89), (0.71, 0.74, 0.78)


class PlaneGrid(object):
    def __init__(self, view):
        coin = _coin()
        self.view = view
        self.root = coin.SoType.fromName("SoSkipBoundingGroup").createInstance()
        # createInstance() hands out an unreferenced node: hold a reference, or Coin
        # frees it the first time it is detached and re-attaching it crashes
        self.root.ref()
        try:
            self.root.mode = 1     # EXCLUDE_BBOX: never influences 'fit all'
        except Exception:
            pass
        body = coin.SoSeparator()
        self.root.addChild(body)
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        body.addChild(pick)
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        body.addChild(light)
        self.xf = coin.SoTransform()
        body.addChild(self.xf)
        self.parts = []
        minor_c, major_c = _colors()
        for color, width in ((minor_c, 1), (major_c, 1)):
            sep = coin.SoSeparator()
            col = coin.SoBaseColor()
            col.rgb = color
            style = coin.SoDrawStyle()
            style.lineWidth = width
            coords = coin.SoCoordinate3()
            lines = coin.SoLineSet()
            for x in (col, style, coords, lines):
                sep.addChild(x)
            body.addChild(sep)
            self.parts.append((col, coords, lines))
        self.key = None
        self.minor = None
        self.attached = False

    def attach(self):
        if not self.attached:
            self.view.getSceneGraph().insertChild(self.root, 0)
            self.attached = True

    def detach(self):
        if self.attached:
            try:
                self.view.getSceneGraph().removeChild(self.root)
            except Exception:
                pass
            self.attached = False
        self.key = None

    def recolor(self):
        for (col, _, _), c in zip(self.parts, _colors()):
            col.rgb = c

    def show(self, placement, z_offset_px=0.0):
        frame = plane_frame(self.view, placement)
        if frame is None:
            self.detach()
            self.minor = None
            return None
        minor, major, umin, umax, vmin, vmax, mm_px = frame
        self.minor = minor
        key = (minor, umin, umax, vmin, vmax, tuple(round(x, 6) for x in placement.Base),
               tuple(round(x, 6) for x in placement.Rotation.Q), round(z_offset_px * mm_px, 3))
        self.attach()
        if key == self.key:
            return minor
        self.key = key
        z = -z_offset_px * mm_px
        q = placement.Rotation.Q
        self.xf.translation = tuple(placement.Base)
        self.xf.rotation.setValue(q[0], q[1], q[2], q[3])
        nminor = (umax - umin) / minor + (vmax - vmin) / minor
        draw_minor = nminor <= MAX_LINES
        minor_pts, major_pts = [], []
        k0, k1 = int(round(umin / minor)), int(round(umax / minor))
        ratio = int(round(major / minor))
        for k in range(k0, k1 + 1):
            u = k * minor
            seg = [(u, vmin, z), (u, vmax, z)]
            if k % ratio == 0:
                major_pts += seg
            elif draw_minor:
                minor_pts += seg
        k0, k1 = int(round(vmin / minor)), int(round(vmax / minor))
        for k in range(k0, k1 + 1):
            v = k * minor
            seg = [(umin, v, z), (umax, v, z)]
            if k % ratio == 0:
                major_pts += seg
            elif draw_minor:
                minor_pts += seg
        for (_, coords, lines), pts in zip(self.parts, (minor_pts, major_pts)):
            coords.point.setNum(0)
            if pts:
                coords.point.setValues(0, len(pts), pts)
            lines.numVertices.setNum(0)
            if pts:
                lines.numVertices.setValues(0, len(pts) // 2, [2] * (len(pts) // 2))
        return minor


# ---------------------------------------------------------------------------
# driver


def _views():
    out = []
    for name in App.listDocuments():
        try:
            gdoc = Gui.getDocument(name)
            out += list(gdoc.mdiViewsOfType("Gui::View3DInventor"))
        except Exception:
            continue
    return out


def _editing_sketch(gdoc_view=None):
    try:
        from ..commands.base import editing_object, in_sketch
        if in_sketch():
            obj = editing_object()
            if obj is not None and obj.isDerivedFrom("Sketcher::SketchObject"):
                return obj
    except Exception:
        pass
    return None


def sketch_step():
    """Minor spacing of the sketch grid in the active view (the snapping step)."""
    try:
        view = Gui.ActiveDocument.ActiveView
    except Exception:
        return None
    g = _state["grids"].get(id(view))
    if g is not None and g.minor and g.attached and getattr(g, "is_sketch", False):
        return g.minor
    sk = _editing_sketch()
    if sk is None:
        return None
    frame = plane_frame(view, sk.getGlobalPlacement())
    return frame[0] if frame else None


def _sync_freecad_grid(sk, step):
    """FreeCAD's own (invisible) sketch grid rounds snapped points to exact values."""
    if sk is None or step is None:
        return
    try:
        vo = sk.ViewObject
        if not vo.ShowGrid:
            vo.ShowGrid = True
        if vo.GridAuto:
            vo.GridAuto = False
        if abs(vo.GridSize.Value - step) > 1e-12:
            vo.GridSize = step
    except Exception:
        pass


def refresh(force=False):
    if not _state["enabled"]:
        for g in _state["grids"].values():
            g.detach()
        return
    sk = _editing_sketch()
    alive = set()
    for view in _views():
        key = id(view)
        alive.add(key)
        g = _state["grids"].get(key)
        if g is None:
            try:
                g = PlaneGrid(view)
            except Exception as e:
                App.Console.PrintLog("FreeFusion grid: %s\n" % e)
                continue
            _state["grids"][key] = g
        if force:
            g.key = None
            g.recolor()
        try:
            if sk is not None and Gui.ActiveDocument is not None and view is Gui.ActiveDocument.ActiveView:
                g.is_sketch = True
                if sketch_visible():
                    step = g.show(sk.getGlobalPlacement())
                else:
                    g.detach()
                    frame = plane_frame(view, sk.getGlobalPlacement())
                    step = frame[0] if frame else None
                _sync_freecad_grid(sk, step)
            elif ground_visible() and sk is None:
                g.is_sketch = False
                g.show(App.Placement(), z_offset_px=0.6)
            else:
                g.detach()
        except Exception as e:
            App.Console.PrintLog("FreeFusion grid: %s\n" % e)
    for key in list(_state["grids"]):
        if key not in alive:
            g = _state["grids"].pop(key, None)
            try:
                g.root.unref()
            except Exception:
                pass


def _tick():
    try:
        refresh()
    except Exception:
        pass


def hide_freecad_sketch_grid(on):
    """Keep FreeCAD's sketch grid working (exact snapping) but draw it invisibly."""
    grp = App.ParamGet(SKETCH_GRID)
    if on:
        if _state["saved"] is None:
            _state["saved"] = (grp.GetInt("GridLinePattern", 0x0f0f), grp.GetInt("GridDivLinePattern", 0xffff))
        grp.SetInt("GridLinePattern", 0)
        grp.SetInt("GridDivLinePattern", 0)
    elif _state["saved"] is not None:
        a, b = _state["saved"]
        _state["saved"] = None
        grp.SetInt("GridLinePattern", a or 0x0f0f)
        grp.SetInt("GridDivLinePattern", b or 0xffff)


def set_enabled(on):
    _state["enabled"] = on
    hide_freecad_sketch_grid(on)
    t = _state["timer"]
    if t is None:
        t = QtCore.QTimer()
        t.setInterval(50)
        t.timeout.connect(_tick)
        _state["timer"] = t
    if on:
        t.start()
    else:
        t.stop()
    refresh(force=True)
