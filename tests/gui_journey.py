# SPDX-License-Identifier: LGPL-2.1-or-later
"""A first-use journey with real input, logging what a user would see at each step.

Run with tests/run_wayland.sh (native Wayland) or tests/run_gui.sh (X11), TEST=gui_journey.py.
"""

import os
import sys
import traceback

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtWidgets
from pivy import coin  # noqa: F401  (getCameraNode needs the SWIG wrappers)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inputlib as I  # noqa: E402

OUT = os.environ.get("FF_OUT", "/tmp/ff_gui")
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, "gui_log.txt"), "w")
RESULTS = []


def log(*a):
    LOG.write(" ".join(str(x) for x in a) + "\n")
    LOG.flush()


def check(name, cond, info=""):
    RESULTS.append((name, bool(cond)))
    log("%s %s %s" % ("PASS" if cond else "FAIL", name, info))


def pump(ms=300):
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec_() if hasattr(loop, "exec_") else loop.exec()


def shot(name):
    QtWidgets.QApplication.processEvents()
    Gui.getMainWindow().grab().save(os.path.join(OUT, name + ".png"))


def vp():
    return Gui.ActiveDocument.ActiveView.graphicsView().viewport()


def gpos(x, y):
    p = vp().mapToGlobal(QtCore.QPoint(int(x), int(y)))
    return p.x(), p.y()


def move_to(x, y, steps=4):
    for k in range(1, steps + 1):
        I.move(*gpos(x - (steps - k) * 3, y - (steps - k) * 2))
        pump(60)


def view_size():
    cam = Gui.ActiveDocument.ActiveView.getCameraNode()
    try:
        return round(cam.height.getValue(), 2)
    except Exception:
        return round(cam.heightAngle.getValue(), 3), [round(v, 1) for v in cam.position.getValue()]


def geo(sk):
    out = []
    for g in sk.Geometry:
        if isinstance(g, Part.LineSegment):
            out.append(("L", [round(v, 4) for v in (g.StartPoint.x, g.StartPoint.y, g.EndPoint.x, g.EndPoint.y)]))
        else:
            out.append((type(g).__name__,))
    return out


def steps():
    from freefusion import design as D
    from freefusion.commands import base
    mw = Gui.getMainWindow()
    log("INFO platform", QtWidgets.QApplication.platformName(), "wayland" if I.WAYLAND else "x11")
    pump(2500)
    doc = App.ActiveDocument
    check("design.open", doc is not None)
    shot("j00_start")
    log("INFO start view", view_size())
    check("start.scale", isinstance(view_size(), float) and 100 <= view_size() <= 1000, view_size())
    w = vp()
    cx, cy = w.width() // 2, w.height() // 2
    # --- L: line, asks for a plane first
    move_to(cx, cy)
    I.click(1)
    pump(300)
    I.key("l")
    pump(800)
    check("L.plane.picker", Gui.Control.activeDialog())
    shot("j01_plane_picker")
    btn = [b for b in mw.findChildren(QtWidgets.QPushButton) if b.text() == "XY" and b.isVisible()]
    if btn:
        p = btn[0].mapToGlobal(btn[0].rect().center())
        I.move(p.x(), p.y())
        pump(100)
        I.click(1)
    pump(2000)
    check("sketch.open", base.in_sketch())
    sk = base.editing_object()
    log("INFO sketch view", view_size(), "grid", getattr(sk.ViewObject, "GridSize", None))
    from freefusion.ui import grid as G
    check("sketch.grid.step", G.sketch_step() is not None and G.sketch_step() >= 1, G.sketch_step())
    pal = mw.findChild(QtWidgets.QFrame, "FFSketchPalette")
    check("sketch.palette", pal is not None and pal.isVisible())
    shot("j02_sketch_open")
    # --- draw two segments with the line tool
    for i, (x, y) in enumerate(((cx - 200, cy + 100), (cx + 150, cy + 100), (cx + 150, cy - 120))):
        move_to(x + 3, y - 2)
        pump(150)
        shot("j03_hover_%d" % i)
        I.click(1)
        pump(300)
    move_to(cx - 50, cy - 50)
    shot("j04_rubberband")
    I.key("Escape")
    pump(300)
    I.key("Escape")
    pump(500)
    log("INFO geometry", geo(sk))
    segs = [g for g in sk.Geometry if isinstance(g, Part.LineSegment)]
    check("lines.drawn", len(segs) == 2, geo(sk))
    check("lines.chained", len(segs) == 2 and (segs[0].EndPoint - segs[1].StartPoint).Length < 1e-9, geo(sk))
    check("lines.round", all(abs(v / 5.0 - round(v / 5.0)) < 1e-6 or abs(v / 2.0 - round(v / 2.0)) < 1e-6
                             for g in segs for v in (g.StartPoint.x, g.StartPoint.y, g.EndPoint.x, g.EndPoint.y)),
          geo(sk))
    # --- dimension the first line: D, click line, place -> value box, type, Enter
    from freefusion.ui import sketch_dims
    lines = [i for i, g in enumerate(sk.Geometry) if isinstance(g, Part.LineSegment)]
    first = sk.Geometry[lines[0]]
    from freefusion.ui.sketch_snap import Projector
    pr = Projector(Gui.ActiveDocument.ActiveView, w, sk)
    mid = (first.StartPoint + first.EndPoint) * 0.5
    mx, my = pr.to_screen(mid.x, mid.y)
    I.key("d")
    pump(600)
    move_to(mx + 30, my)
    pump(200)
    I.click(1)
    pump(300)
    move_to(mx + 30, my + 50)
    I.click(1)
    pump(800)
    box = sketch_dims.active_box()
    tops = [x for x in QtWidgets.QApplication.topLevelWidgets()
            if x.isVisible() and isinstance(x, QtWidgets.QDialog)]
    check("dimension.no.dialog", not tops, [x.windowTitle() for x in tops])
    check("dimension.value.box", box is not None and box.hasFocus(), box)
    shot("j05_dimension")
    for x in tops:
        x.reject()
    if box is not None:
        I.type_text("25")
        I.key("Return")
        pump(600)
        dims = [c for c in sk.Constraints if c.Type in ("Distance", "DistanceX", "DistanceY")]
        log("INFO dims", [(c.Type, round(c.Value, 4)) for c in dims])
        check("dimension.typed", any(abs(c.Value - 25) < 1e-7 for c in dims))
        g = sk.Geometry[lines[0]]
        check("dimension.applied", abs((g.EndPoint - g.StartPoint).Length - 25) < 1e-6 or
              any(abs(c.Value - 25) < 1e-7 for c in dims), g)
    I.key("Escape")
    pump(300)
    I.key("Escape")
    pump(300)
    shot("j05b_dimensioned")
    Gui.runCommand("FF_FinishSketch", 0)
    pump(800)
    shot("j06_finished")
    log("INFO after finish view", view_size())
    # --- add a closed rectangle via code, extrude it and look at selection
    sk2 = D.new_sketch(doc, D.root_component(doc), support=[(D.origin_feature(D.root_component(doc), "XY_Plane"), "")])
    V = App.Vector
    pts = [V(0, 0, 0), V(40, 0, 0), V(40, 20, 0), V(0, 20, 0)]
    for i in range(4):
        sk2.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
    doc.recompute()
    from freefusion.features import extrude as X
    X.create(doc, [(sk2, [])], {"distance": 10})
    doc.recompute()
    Gui.SendMsgToActiveView("ViewFit")
    pump(500)
    shot("j07_body")
    view = Gui.ActiveDocument.ActiveView
    body = D.design_bodies(doc)[0]
    def selected_names():
        out = []
        for x in Gui.Selection.getSelectionEx("", 0):
            out.append(x.ObjectName)
            out += [n.rstrip(".").split(".")[-1] for n in x.SubElementNames]
        return out

    def drag(ax, ay, bx, by):
        move_to(ax, ay)
        I.down(1)
        for k in range(1, 7):
            I.move(*gpos(ax + (bx - ax) * k / 6, ay + (by - ay) * k / 6))
            pump(60)
        I.up(1)
        pump(400)

    # click on the top face, then Shift+click the front face: both selected (Fusion)
    from freefusion.ui.manipulator import _Camera

    def screen(p):
        q = _Camera(view, vp()).screen(p)      # logical pixels (HiDPI safe)
        return int(round(q.x())), int(round(q.y()))
    Gui.Selection.clearSelection()
    fx, fy = screen(V(20, 10, 10))
    move_to(fx, fy)
    pump(300)
    shot("j08_preselect")
    I.click(1)
    pump(400)
    sx, sy = screen(V(20, 0, 5))
    move_to(sx, sy)
    pump(300)
    I.hold("shift")
    I.click(1)
    I.hold("shift", False)
    pump(400)
    sel = [(s.ObjectName, list(s.SubElementNames)) for s in Gui.Selection.getSelectionEx("", 0)]
    n_subs = sum(len(x[1]) for x in sel)
    log("INFO click + shift click", sel)
    check("shift.click.adds", n_subs == 2, sel)
    # empty canvas click clears
    move_to(30, 30)
    I.click(1)
    pump(300)
    check("click.empty.clears", not Gui.Selection.getSelectionEx("", 0))
    # box left -> right around the whole body: window selection
    pts = [screen(V(x, y, z)) for x in (0, 40) for y in (0, 20) for z in (0, 10)]
    x0, x1 = min(p[0] for p in pts) - 25, max(p[0] for p in pts) + 25
    y0, y1 = min(p[1] for p in pts) - 25, max(p[1] for p in pts) + 25
    move_to(x0, y0)
    I.down(1)
    for k in range(1, 7):
        I.move(*gpos(x0 + (x1 - x0) * k / 6, y0 + (y1 - y0) * k / 6))
        pump(60)
    shot("j09_window_drag")
    I.up(1)
    pump(400)
    sel = selected_names()
    log("INFO window select", sel)
    check("window.select.body", body.Name in sel, sel)
    # right -> left from outside to the middle of the body: crossing selects it
    Gui.Selection.clearSelection()
    mx2, my2 = screen(V(20, 10, 5))
    drag(x1, y0, mx2, my2)
    shot("j09b_crossing")
    check("crossing.select.body", body.Name in selected_names(), selected_names())
    # the same box left -> right (window) only partly covers the body: nothing
    Gui.Selection.clearSelection()
    drag(x0, y0, mx2, my2)
    check("window.partial.none", not selected_names(), selected_names())
    # orbit: Shift + middle drag turns around the design center, which stays put on screen
    from freefusion.ui import navigation
    center = navigation.pivot(doc)
    before = screen(center)
    cam0 = view.getCameraOrientation()
    move_to(cx, cy)
    I.hold("shift")
    pump(100)
    I.down(2)
    for k in range(1, 8):
        I.move(*gpos(cx + 25 * k, cy + 8 * k))
        pump(60)
    shot("j10_orbit")
    I.up(2)
    I.hold("shift", False)
    pump(300)
    after = screen(center)
    log("INFO orbit pivot screen", before, after)
    check("orbit.rotates", not view.getCameraOrientation().isSame(cam0, 1e-6))
    check("orbit.pivot.fixed", abs(before[0] - after[0]) <= 2 and abs(before[1] - after[1]) <= 2,
          (before, after))
    shot("j11_end")


def main():
    try:
        steps()
    except Exception:
        log("EXCEPTION\n" + traceback.format_exc())
        RESULTS.append(("exception", False))
    failed = [n for n, ok in RESULTS if not ok]
    log("SUMMARY %s %d/%d" % ("ok" if not failed else "failed", len(RESULTS) - len(failed), len(RESULTS)))
    LOG.close()
    QtCore.QTimer.singleShot(200, lambda: os._exit(0))


QtCore.QTimer.singleShot(3000, main)
