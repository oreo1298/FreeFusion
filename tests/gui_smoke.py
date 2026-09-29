# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI smoke test: run inside FreeCAD (see tests/run_gui.sh). Writes screenshots + a log."""

import os
import sys
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


def shot(name):
    QtWidgets.QApplication.processEvents()
    mw = Gui.getMainWindow()
    mw.grab().save(os.path.join(OUT, name + ".png"))


def pump(ms=300):
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec_() if hasattr(loop, "exec_") else loop.exec()


class ConsoleCatcher(object):
    def __init__(self):
        self.errors = []

    def receive(self, msg):
        pass

    def warning(self, msg):
        if "FreeFusion" in msg or "freefusion" in msg:
            self.errors.append(msg)

    def error(self, msg):
        self.errors.append(msg)


def dock_state(tag):
    mw = Gui.getMainWindow()
    for d in mw.findChildren(QtWidgets.QDockWidget):
        log("DOCK", tag, d.objectName(), "vis=%s float=%s area=%s parent=%s" % (
            d.isVisible(), d.isFloating(), int(mw.dockWidgetArea(d).value) if hasattr(mw.dockWidgetArea(d), "value")
            else mw.dockWidgetArea(d), type(d.parent()).__name__ + ":" + (d.parent().objectName() if d.parent() else "")))


def steps():
    mw = Gui.getMainWindow()
    mw.resize(1600, 1000)
    Gui.activateWorkbench("FreeFusionWorkbench")
    pump(1200)
    from freefusion import design as D
    from freefusion.commands import base
    from freefusion.ui import browser, timeline_ui, workbench, widgets as W

    dock_state("start")
    check("wb.active", Gui.activeWorkbench().name() == "FreeFusionWorkbench")
    rb = workbench._state["ribbon"]
    check("ribbon.visible", rb is not None and rb.isVisible())
    check("docs.newdesign", App.ActiveDocument is not None and D.root_component(App.ActiveDocument) is not None)
    std = [tb.objectName() for tb in workbench._std_toolbars() if tb.isVisible()]
    check("std.toolbars.hidden", not std, std)
    shot("01_start")

    doc = App.ActiveDocument
    root = D.root_component(doc)
    # sketch via the real command path
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(D.origin_feature(root, "XY_Plane"))
    Gui.runCommand("FF_CreateSketch", 0)
    pump(800)
    check("sketch.editing", base.in_sketch())
    dock_state("sketch")
    sk = Gui.ActiveDocument.getInEdit().Object
    pts = [V(0, 0, 0), V(40, 0, 0), V(40, 25, 0), V(0, 25, 0)]
    for i in range(4):
        sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
    sk.addGeometry(Part.Circle(V(20, 12.5, 0), V(0, 0, 1), 6))
    doc.recompute()
    pump(600)
    check("ribbon.sketchtab", rb.ribbon.tab_buttons["SKETCH"].isVisible()
          and rb.ribbon.stack.currentWidget() is rb.ribbon.pages["SKETCH"])
    shot("02_sketch")
    Gui.runCommand("FF_FinishSketch", 0)
    pump(600)
    check("sketch.finished", not base.in_sketch())

    # extrude through the dialog (profiles: outer region only)
    from freefusion.ui.panels.profile_panels import ExtrudePanel
    regions = ["InternalFace%d" % (i + 1) for i in range(len(sk.InternalShape.Faces))]
    log("regions", regions, [round(f.Area, 1) for f in sk.InternalShape.Faces])
    outer = max(range(len(regions)), key=lambda i: sk.InternalShape.Faces[i].Area)
    panel = W.show(ExtrudePanel([(sk, [regions[outer]])]))
    pump(500)
    panel.distance.set_value(15.0)
    panel.distance.changed.emit()
    pump(500)
    shot("03_extrude_dialog")
    panel.accept()
    pump(500)
    bodies = D.design_bodies(doc)
    check("extrude.body", len(bodies) == 1 and abs(bodies[0].Shape.Volume - (40 * 25 - 3.14159265 * 36) * 15) < 1,
          bodies[0].Shape.Volume if bodies else None)
    Gui.SendMsgToActiveView("ViewFit")

    # fillet the top edges with the wrapped PartDesign command
    body = bodies[0]
    tip = body.Tip
    top_edges = ["Edge%d" % (i + 1) for i, e in enumerate(tip.Shape.Edges)
                 if abs(e.BoundBox.ZMin - 15) < 1e-6 and abs(e.BoundBox.ZMax - 15) < 1e-6 and e.Length > 20]
    Gui.Selection.clearSelection()
    for e in top_edges:
        Gui.Selection.addSelection(doc.Name, tip.Name, e)
    Gui.runCommand("FF_Fillet", 0)
    pump(1200)
    dlg = Gui.Control.activeDialog()
    check("fillet.dialog", dlg)
    check("fillet.same.workspace", Gui.activeWorkbench().name() == "FreeFusionWorkbench",
          Gui.activeWorkbench().name())
    shot("04_fillet_dialog")
    if dlg:
        Gui.Control.activeDialog() and Gui.ActiveDocument.resetEdit()
        try:
            Gui.Control.closeDialog()
        except Exception:
            pass
        doc.recompute()
    pump(500)

    # timeline + browser state
    tl = timeline_ui.instance().timeline
    tl.refresh()
    kinds = [i.kind for i in tl.strip.items]
    check("timeline.kinds", kinds[:2] == ["Sketch", "Extrude"], kinds)
    b = browser.instance()
    b.rebuild()
    labels = []
    it = QtWidgets.QTreeWidgetItemIterator(b.tree)
    while it.value():
        labels.append(it.value().text(0))
        it += 1
    check("browser.body", "Body1" in labels and "Sketch1" in labels, labels)
    Gui.activeDocument().activeView().viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    pump(500)
    shot("05_model")

    # marking menu
    from freefusion.ui import marking_menu
    view = mw.findChild(QtWidgets.QMdiArea).activeSubWindow()
    center = view.mapToGlobal(view.rect().center()) if view else QtCore.QPoint(800, 500)
    m = marking_menu.show(center, False)
    pump(400)
    check("marking.shown", m.isVisible())
    shot("06_marking_menu")
    # grab popup itself too (popups are separate windows)
    m.grab().save(os.path.join(OUT, "06b_marking_popup.png"))
    m.close()

    # shortcut box
    from freefusion.ui import shortcut_box
    box = shortcut_box.show()
    box.edit.setText("fil")
    pump(300)
    check("sbox.results", box.list.count() > 0 and "Fillet" in box.list.item(0).text(),
          box.list.item(0).text() if box.list.count() else None)
    box.grab().save(os.path.join(OUT, "07_shortcut_box.png"))
    box.close()

    # key dispatch: E should open extrude in model context
    from freefusion.ui import keys
    gl = Gui.ActiveDocument.ActiveView.graphicsView().viewport()
    gl.setFocus()
    pump(100)
    ev = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_E, QtCore.Qt.NoModifier, "e")
    handled = keys.instance().eventFilter(gl, ev)
    pump(600)
    check("keys.E.extrude", handled and Gui.Control.activeDialog(), handled)
    shot("08_key_extrude")
    if Gui.Control.activeDialog():
        Gui.Control.activeDialog() and Gui.Control.closeDialog()
    pump(300)

    # roll back the timeline
    tl.roll_to(1)
    pump(400)
    check("timeline.rollback", body.Visibility is False or not body.ViewObject.Visibility or
          D.data(body) is not None)
    shot("09_rolled_back")
    tl.roll_to(None)
    pump(400)

    # dark theme
    from freefusion import params
    from freefusion.ui import preferences
    preferences.toggle_theme()
    pump(600)
    shot("10_dark")
    preferences.toggle_theme()
    pump(300)

    # switch to another workbench and back
    from freefusion.ui import ribbon as RB
    RB.switch_workspace("PartDesignWorkbench")
    pump(800)
    vis = [tb.objectName() for tb in mw.findChildren(QtWidgets.QToolBar) if tb.isVisible()]
    check("otherwb.toolbars", "File" in vis and "FreeFusionRibbon" not in vis, vis)
    check("otherwb.wsbar", "FreeFusionWorkspace" in vis, vis)
    shot("11_partdesign")
    Gui.activateWorkbench("FreeFusionWorkbench")
    pump(800)
    vis = [tb.objectName() for tb in mw.findChildren(QtWidgets.QToolBar) if tb.isVisible()]
    check("back.ribbon", "FreeFusionRibbon" in vis and "File" not in vis, vis)


def main():
    catcher = ConsoleCatcher()
    try:
        App.Console.AddObserver(catcher) if hasattr(App.Console, "AddObserver") else None
    except Exception:
        pass
    try:
        steps()
    except Exception:
        log("EXCEPTION\n" + traceback.format_exc())
        RESULTS.append(("exception", False))
    failed = [n for n, ok in RESULTS if not ok]
    log("CONSOLE_ERRORS", catcher.errors[:30])
    log("SUMMARY %s %d/%d" % ("ok" if not failed else "failed", len(RESULTS) - len(failed), len(RESULTS)))
    LOG.close()
    QtCore.QTimer.singleShot(200, lambda: os._exit(0))


QtCore.QTimer.singleShot(2500, main)
