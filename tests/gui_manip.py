# SPDX-License-Identifier: LGPL-2.1-or-later
"""Real input test for sketch snapping and the on-canvas drag arrows (X11 or Wayland).

Run through tests/run_gui.sh with TEST=gui_manip.py.
"""

import os
import sys
import traceback

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtWidgets

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inputlib as I  # noqa: E402

OUT = os.environ.get("FF_OUT", "/tmp/ff_gui")
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, "gui_log.txt"), "w")
RESULTS = []
V = App.Vector


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


def xdo(*args):
    I.xdo(*args)
    pump(200)


def shot(name):
    QtWidgets.QApplication.processEvents()
    Gui.getMainWindow().grab().save(os.path.join(OUT, name + ".png"))


def vp_widget():
    return Gui.ActiveDocument.ActiveView.graphicsView().viewport()


def glob(w, x, y):
    p = w.mapToGlobal(QtCore.QPoint(int(round(x)), int(round(y))))
    return p.x(), p.y()


def glide(x0, y0, x1, y1, n=6):
    for k in range(1, n + 1):
        xdo("mousemove", int(x0 + (x1 - x0) * k / n), int(y0 + (y1 - y0) * k / n))


def sketch_click(sk, u, v):
    """Move to sketch point (u, v) in a few steps and click."""
    from freefusion.ui.sketch_snap import Projector
    w = vp_widget()
    pr = Projector(Gui.ActiveDocument.ActiveView, w, sk)
    x, y = pr.to_screen(u, v)
    gx, gy = glob(w, x, y)
    xdo("mousemove", gx - 12, gy + 9)
    glide(gx - 12, gy + 9, gx, gy, 3)
    pump(150)
    xdo("click", 1)
    pump(250)


def lines(sk):
    return [(g.StartPoint, g.EndPoint) for g in sk.Geometry if isinstance(g, Part.LineSegment)]


def exact(p, x, y):
    return abs(p.x - x) < 1e-7 and abs(p.y - y) < 1e-7


def has_line(sk, a, b):
    for s, e in lines(sk):
        if (exact(s, *a) and exact(e, *b)) or (exact(s, *b) and exact(e, *a)):
            return True
    return False


def steps():
    from freefusion import design as D
    from freefusion.commands import base
    from freefusion.ui import manipulator as M
    from freefusion.ui import sketching, sketch_snap
    from freefusion.ui import widgets as W
    mw = Gui.getMainWindow()
    mw.resize(1600, 1000)
    mw.move(0, 0)
    Gui.activateWorkbench("FreeFusionWorkbench")
    pump(1500)
    xdo("windowfocus", int(mw.winId()))
    doc = App.ActiveDocument
    root = D.root_component(doc)

    # ---------------------------------------------------------------- snapping
    check("nice.steps", [sketch_snap.nice_step(x, 10) for x in (0.01, 0.03, 0.26, 0.6, 1.2)]
          == [0.1, 0.5, 5.0, 10.0, 20.0], [sketch_snap.nice_step(x, 10) for x in (0.01, 0.03, 0.26, 0.6, 1.2)])
    sk = D.new_sketch(doc, root, support=[(D.origin_feature(root, "XY_Plane"), "")])
    doc.recompute()
    sketching.edit_sketch(sk)
    pump(800)
    view = Gui.ActiveDocument.ActiveView
    view.setCameraType("Orthographic")
    view.viewTop()
    cam = view.getCameraNode()
    cam.height.setValue(120.0)
    cam.position.setValue(40.0, 15.0, 100.0)
    pump(400)
    check("sketch.grid.shown", sk.ViewObject.ShowGrid)
    Gui.runCommand("FF_SkLine", 0)
    pump(600)
    sketch_click(sk, 20.4, 10.6)
    sketch_click(sk, 60.3, 9.5)
    step = sketch_snap.current_step()
    log("INFO step", step, "grid", sk.ViewObject.GridSize, "lines", lines(sk))
    xdo("key", "Escape")
    pump(300)
    xdo("key", "Escape")
    pump(400)
    doc.recompute()
    check("snap.round.values", has_line(sk, (20, 10), (60, 10)), lines(sk))
    shot("m01_snap_line")
    # start a second line near the midpoint of the first: it locks onto the midpoint
    Gui.runCommand("FF_SkLine", 0)
    pump(600)
    sketch_click(sk, 40.9, 10.8)
    sketch_click(sk, 40.4, 29.3)
    xdo("key", "Escape")
    pump(300)
    xdo("key", "Escape")
    pump(400)
    doc.recompute()
    check("snap.midpoint", has_line(sk, (40, 10), (40, 30)), lines(sk))
    # Ctrl turns snapping off
    xdo("mousemove", 800, 500)
    check("snap.ctrl.off", sketch_snap.snap(vp_widget(), 300, 300, QtCore.Qt.ControlModifier) is None)
    Gui.runCommand("FF_FinishSketch", 0)
    pump(600)
    check("sketch.finished", not base.in_sketch())

    # ---------------------------------------------------------------- extrude arrow
    sk2 = D.new_sketch(doc, root, support=[(D.origin_feature(root, "XY_Plane"), "")])
    pts = [V(0, 0, 0), V(40, 0, 0), V(40, 20, 0), V(0, 20, 0)]
    for i in range(4):
        sk2.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
    doc.recompute()
    sk.ViewObject.Visibility = False
    view.viewIsometric()
    view.fitAll()
    pump(400)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(sk2)
    Gui.runCommand("FF_Extrude", 0)
    pump(800)
    panel = W._last_panel
    arrows = M.arrows()
    check("extrude.arrow.shown", len(arrows) == 1, arrows)
    check("extrude.valuebox.focus", arrows and QtWidgets.QApplication.focusWidget() is arrows[0].box,
          QtWidgets.QApplication.focusWidget())
    shot("m02_extrude_arrow")
    if arrows:
        a = arrows[0]
        _, b, h = a.screen_segment()
        w = vp_widget()
        mx, my = (b.x() + h.x()) / 2, (b.y() + h.y()) / 2
        dx, dy = (h.x() - b.x()), (h.y() - b.y())
        gx, gy = glob(w, mx, my)
        v0 = panel.distance.value()
        xdo("mousemove", gx, gy)
        pump(200)
        check("arrow.hover", a.hover)
        xdo("mousedown", 1)
        glide(gx, gy, gx + dx * 0.8, gy + dy * 0.8, 6)
        xdo("mouseup", 1)
        pump(500)
        v1 = panel.distance.value()
        check("arrow.drag.changes", v1 > v0, (v0, v1))
        check("arrow.drag.round", abs(v1 - round(v1)) < 1e-9, v1)
        shot("m03_extrude_dragged")
        body_before = len(D.design_bodies(doc))
        # type a value with the 3D view focused: it goes to the value box; Enter = OK
        xdo("key", "2")
        xdo("key", "5")
        pump(500)
        check("typed.into.box", a.box is not None and a.box.text() == "25", a.box.text() if a.box else None)
        xdo("key", "Return")
        pump(900)
        bodies = D.design_bodies(doc)
        check("extrude.enter.ok", not Gui.Control.activeDialog() and len(bodies) == body_before, len(bodies))
        top = max(b.Shape.BoundBox.ZMax for b in bodies) if bodies else None
        check("extrude.typed.distance", top is not None and abs(top - 25) < 1e-6, top)
        check("arrows.removed", not M.arrows())

    # ---------------------------------------------------------------- fillet arrow
    body = D.design_bodies(doc)[0]
    tip = body.Tip
    edge = None
    for i, e in enumerate(tip.Shape.Edges):
        u0, u1 = e.ParameterRange
        if (e.valueAt((u0 + u1) / 2) - V(20, 0, 25)).Length < 1e-6:
            edge = "Edge%d" % (i + 1)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, tip.Name, edge)
    xdo("mousemove", 400, 900)
    xdo("key", "f")
    pump(900)
    panel = W._last_panel
    check("fillet.panel", panel is not None and type(panel).__name__ == "FilletPanel", panel)
    check("fillet.arrow", len(M.arrows()) == 1)
    shot("m04_fillet")
    xdo("key", "BackSpace")
    xdo("type", "3")
    xdo("key", "Return")
    pump(900)
    fil = body.Tip
    check("fillet.created", fil.TypeId == "PartDesign::Fillet" and abs(fil.Radius.Value - 3) < 1e-9,
          (fil.TypeId, getattr(fil, "Radius", None)))
    check("fillet.closed", not Gui.Control.activeDialog())

    # ---------------------------------------------------------------- press pull arrow
    tip = body.Tip
    face = None
    for i, f in enumerate(tip.Shape.Faces):
        if abs(f.CenterOfMass.x - 40) < 1e-6:
            face = "Face%d" % (i + 1)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, tip.Name, face)
    Gui.runCommand("FF_PressPull", 0)
    pump(900)
    arrows = M.arrows()
    check("presspull.arrow", len(arrows) == 1, arrows)
    if arrows:
        a = arrows[0]
        _, b, h = a.screen_segment()
        w = vp_widget()
        gx, gy = glob(w, (b.x() + h.x()) / 2, (b.y() + h.y()) / 2)
        dx, dy = h.x() - b.x(), h.y() - b.y()
        v0 = W._last_panel.distance.value()
        xdo("mousemove", gx, gy)
        xdo("mousedown", 1)
        glide(gx, gy, gx + dx, gy + dy, 6)
        xdo("mouseup", 1)
        pump(600)
        v1 = W._last_panel.distance.value()
        check("presspull.drag", v1 > v0 and abs(v1 - round(v1)) < 1e-9, (v0, v1))
        shot("m05_presspull")
        xdo("key", "Escape")
        pump(600)
        check("presspull.cancel", not Gui.Control.activeDialog() and not M.arrows())


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


QtCore.QTimer.singleShot(2500, main)
