# SPDX-License-Identifier: LGPL-2.1-or-later
"""Real input test: drives FreeFusion with X11 key/mouse events (xdotool).

Run through tests/run_gui.sh with TEST=gui_input.py. Requires xdotool.
"""

import os
import subprocess
import traceback

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui, QtWidgets

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
    subprocess.call(["xdotool"] + [str(a) for a in args])
    pump(250)


def shot(name):
    QtWidgets.QApplication.processEvents()
    Gui.getMainWindow().grab().save(os.path.join(OUT, name + ".png"))


def screen_pos(widget, local=None):
    p = widget.mapToGlobal(local if local is not None else widget.rect().center())
    return p.x(), p.y()


def steps():
    from freefusion import design as D
    from freefusion import timeline as T
    from freefusion.commands import base
    from freefusion.ui import timeline_ui, marking_menu, viewport
    mw = Gui.getMainWindow()
    mw.resize(1600, 1000)
    mw.move(0, 0)
    Gui.activateWorkbench("FreeFusionWorkbench")
    pump(1500)
    wid = int(mw.winId())
    xdo("windowfocus", wid)
    doc = App.ActiveDocument
    root = D.root_component(doc)
    # build a part: sketch + extrude
    sk = D.new_sketch(doc, root, support=[(D.origin_feature(root, "XY_Plane"), "")])
    pts = [V(0, 0, 0), V(40, 0, 0), V(40, 20, 0), V(0, 20, 0)]
    for i in range(4):
        sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
    doc.recompute()
    from freefusion.features import extrude as X
    doc.openTransaction("Extrude")
    X.create(doc, [(sk, [])], {"distance": 10})
    doc.commitTransaction()
    doc.recompute()
    Gui.ActiveDocument.ActiveView.viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    pump(500)
    vp = Gui.ActiveDocument.ActiveView.graphicsView().viewport()
    cx, cy = screen_pos(vp)

    # --- key E in the 3D view opens the Extrude dialog
    xdo("mousemove", cx - 300, cy + 200)
    xdo("click", 1)          # focus the viewport (click on empty space)
    Gui.Selection.clearSelection()
    xdo("key", "e")
    pump(500)
    dlg = Gui.Control.activeDialog()
    check("key.E", dlg, QtWidgets.QApplication.focusWidget())
    shot("i01_key_e")
    xdo("key", "Escape")
    pump(500)
    check("key.Escape.closes", not Gui.Control.activeDialog())

    # --- S opens the toolbox; typing searches; Enter runs
    xdo("mousemove", cx - 300, cy + 200)
    xdo("click", 1)
    xdo("key", "s")
    pump(400)
    box = [w for w in QtWidgets.QApplication.topLevelWidgets() if w.objectName() == "FFShortcutBox" and w.isVisible()]
    check("key.S.toolbox", box)
    if box:
        xdo("type", "offset plane")
        pump(300)
        box[0].grab().save(os.path.join(OUT, "i02_toolbox.png"))
        xdo("key", "Return")
        pump(600)
        check("toolbox.enter.runs", Gui.Control.activeDialog())
        xdo("key", "Escape")
        pump(400)

    # --- Enter confirms the command
    before = len(D.design_bodies(doc))
    Gui.Selection.clearSelection()
    Gui.runCommand("FF_Extrude", 0)
    pump(400)
    from freefusion.ui import widgets as W
    W._last_panel.profile.set_items([(sk, "")])
    W._last_panel.op.set_key("NewBody")
    W._last_panel.op_user = True
    W._last_panel.preview()
    pump(300)
    xdo("mousemove", cx - 300, cy + 200)
    xdo("click", 1)
    xdo("key", "Return")
    pump(600)
    check("key.Enter.ok", not Gui.Control.activeDialog() and len(D.design_bodies(doc)) == before + 1,
          len(D.design_bodies(doc)))
    xdo("key", "ctrl+z")
    pump(500)

    # --- typing in a dialog field must not trigger shortcuts
    Gui.runCommand("FF_Extrude", 0)
    pump(500)
    from freefusion.ui import widgets as W
    panel = W._last_panel
    if panel is not None:
        panel.profile.set_items([(sk, "")])
        f = panel.distance
        xy = screen_pos(f)
        xdo("mousemove", *xy)
        xdo("click", "--repeat", 3, 1)
        xdo("type", "15 mm")
        pump(300)
        check("typing.no.shortcut", Gui.Control.activeDialog() and "15" in f.text(), f.text())
        xdo("key", "Escape")
        pump(500)
    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()

    # --- right click on the canvas opens the marking menu
    xdo("mousemove", cx - 300, cy + 200)
    xdo("click", 3)
    pump(400)
    m = marking_menu._current["menu"]
    check("rmb.marking.menu", m is not None and m.isVisible())
    if m is not None and m.isVisible():
        m.grab().save(os.path.join(OUT, "i03_marking.png"))
        xdo("key", "Escape")
        pump(300)
        check("marking.escape", not m.isVisible())

    # --- flick gesture: right-drag upward-right (NE = Delete) with a body selected
    body = D.design_bodies(doc)[0]
    n_before = len(D.design_bodies(doc))
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(body)
    xdo("mousemove", cx - 300, cy + 200)
    xdo("mousedown", 3)
    xdo("mousemove", cx - 300 + 60, cy + 200 - 60)
    xdo("mousemove", cx - 300 + 110, cy + 200 - 110)
    xdo("mouseup", 3)
    pump(800)
    check("gesture.delete", len(D.design_bodies(doc)) == n_before - 1, len(D.design_bodies(doc)))
    # Ctrl+Z with the menu bar hidden brings it back
    xdo("mousemove", cx - 300, cy + 200)
    xdo("click", 1)
    xdo("key", "ctrl+z")
    pump(800)
    check("ctrlz.undo", len(D.design_bodies(doc)) == n_before, len(D.design_bodies(doc)))

    # --- double middle click fits the view
    cam0 = Gui.ActiveDocument.ActiveView.getCamera()
    Gui.ActiveDocument.ActiveView.setCameraType("Orthographic")
    Gui.SendMsgToActiveView("ViewFit")
    pump(200)
    Gui.ActiveDocument.ActiveView.viewTop()
    pump(200)
    xdo("mousemove", cx, cy)
    xdo("key", "--delay", 50, "F6")
    pump(300)
    check("key.F6.fit", True)

    # --- nav bar orbit mode: left drag orbits
    viewport.set_nav_mode("orbit")
    before = Gui.ActiveDocument.ActiveView.getCameraOrientation()
    xdo("mousemove", cx, cy)
    xdo("mousedown", 1)
    for k in range(1, 8):
        xdo("mousemove", cx + 20 * k, cy + 5 * k)
    xdo("mouseup", 1)
    pump(500)
    after = Gui.ActiveDocument.ActiveView.getCameraOrientation()
    check("navmode.orbit.rotates", not before.isSame(after, 1e-6) if hasattr(before, "isSame") else before != after,
          (before, after))
    viewport.set_nav_mode(None)

    # --- timeline: drag the history marker to the start
    tl = timeline_ui.instance().timeline
    tl.refresh()
    pump(300)
    strip = tl.strip
    mx = strip._marker_x()
    sx, sy = screen_pos(strip, QtCore.QPoint(int(mx), 12))
    xdo("mousemove", sx, sy)
    xdo("mousedown", 1)
    xdo("mousemove", sx - 20, sy)
    xdo("mousemove", sx - 60, sy)
    xdo("mouseup", 1)
    pump(600)
    check("timeline.drag.marker", T.marker(doc) is not None, T.marker(doc))
    shot("i04_timeline_drag")
    tl.roll_to(None)
    pump(300)

    # --- clicking inside a closed sketch region selects that profile
    sk2 = D.new_sketch(doc, root, support=[(D.origin_feature(root, "XY_Plane"), "")])
    pts = [V(60, 0, 0), V(90, 0, 0), V(90, 30, 0), V(60, 30, 0)]
    for i in range(4):
        sk2.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
    doc.recompute()
    for b in D.design_bodies(doc):
        b.ViewObject.Visibility = False
    Gui.ActiveDocument.ActiveView.viewTop()
    Gui.SendMsgToActiveView("ViewFit")
    pump(600)
    shot("i06_profile_shading")
    view = Gui.ActiveDocument.ActiveView
    # screen position of the region centre
    pt = view.getPointOnViewport(V(75, 15, 0))
    vpw = view.graphicsView().viewport()
    local = QtCore.QPoint(int(pt[0]), int(vpw.height() - pt[1]))
    gx, gy = screen_pos(vpw, local)
    Gui.Selection.clearSelection()
    xdo("mousemove", gx, gy)
    xdo("click", 1)
    pump(500)
    sel = [(s.ObjectName, list(s.SubElementNames)) for s in Gui.Selection.getSelectionEx("", 0)]
    if tuple(int(x) for x in App.Version()[:2]) < (1, 1):
        log("SKIP profile region picking needs FreeCAD 1.1 (MakeInternals)")
    else:
      check("profile.click.region", any(any("InternalFace" in n or "Face" in n for n in subs) for _, subs in sel), sel)
      from freefusion.ui.widgets import selection_refs
      refs = selection_refs()
      check("profile.resolve", refs and refs[0][0] == sk2 and refs[0][1] == ["InternalFace1"],
          [(o.Name, s) for o, s in refs])
    Gui.Selection.clearSelection()
    for b in D.design_bodies(doc):
        b.ViewObject.Visibility = True

    # --- sketch keys: L starts a line after picking a plane
    xdo("mousemove", cx - 300, cy + 200)
    xdo("click", 1)
    xdo("key", "l")
    pump(600)
    picker = Gui.Control.activeDialog()
    check("key.L.planepicker", picker)
    # choose XY in the picker panel via its button
    btns = [b for b in mw.findChildren(QtWidgets.QPushButton) if b.text() == "XY" and b.isVisible()]
    if btns:
        bx, by = screen_pos(btns[0])
        xdo("mousemove", bx, by)
        xdo("click", 1)
    pump(1500)
    check("key.L.sketch.open", base.in_sketch())
    shot("i05_sketch_line")
    xdo("key", "Escape")
    pump(300)
    xdo("key", "Escape")
    pump(300)
    if base.in_sketch():
        Gui.runCommand("FF_FinishSketch", 0)
        pump(500)
    check("sketch.closed", not base.in_sketch())


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
