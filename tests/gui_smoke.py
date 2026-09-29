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
      try:
        log("DOCK", tag, d.objectName(), "vis=%s float=%s area=%s parent=%s" % (
            d.isVisible(), d.isFloating(), int(mw.dockWidgetArea(d).value) if hasattr(mw.dockWidgetArea(d), "value")
            else mw.dockWidgetArea(d), type(d.parent()).__name__ + ":" + (d.parent().objectName() if d.parent() else "")))
      except RuntimeError:
        pass


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


def more_steps():
    """Exercise the remaining dialogs and commands end to end."""
    from freefusion import design as D
    from freefusion import timeline as T
    from freefusion.commands import base
    from freefusion.features import parameters as PR
    from freefusion.ui import widgets as W, timeline_ui, browser
    from freefusion.ui.panels import profile_panels as PP, modify_panels as MP
    doc = App.ActiveDocument
    root = D.root_component(doc)
    body = D.design_bodies(doc)[0]

    # --- Revolve: profile on XZ, axis = root Z axis -> new body
    sk = D.new_sketch(doc, root, support=[(D.origin_feature(root, "XZ_Plane"), "")])
    pts = [V(60, 0, 0), V(70, 0, 0), V(70, 10, 0), V(60, 10, 0)]
    for i in range(4):
        sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
    doc.recompute()
    panel = W.show(PP.RevolvePanel([(sk, [])]))
    pump(300)
    panel.axis.set_items([(D.origin_feature(root, "Z_Axis"), "")])
    panel.preview()
    pump(300)
    shot("12_revolve")
    panel.accept()
    pump(300)
    check("revolve.body", len(D.design_bodies(doc)) == 2, [b.Label for b in D.design_bodies(doc)])

    # --- Offset plane through the construct dialog
    before = len([o for o in doc.Objects if D.is_datum(o)])
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(D.origin_feature(root, "XY_Plane"))
    Gui.runCommand("FF_OffsetPlane", 0)
    pump(400)
    dlg = Gui.Control.activeDialog()
    check("construct.dialog", dlg)
    shot("13_offset_plane")
    if dlg:
        Gui.Control.activeDialog()
        panel = Gui.Control.activeTaskDialog() if hasattr(Gui.Control, "activeTaskDialog") else None
    # accept via the python panel object kept by W.show
    pump(200)
    cp_panel = W._last_panel
    if cp_panel is not None and not cp_panel.slots[0].items:
        # Qt5/FreeCAD 1.0 does not resolve a programmatic nested selection; feed the slot
        cp_panel.slots[0].set_items([(D.origin_feature(root, "XY_Plane"), "")])
        cp_panel.preview()
        pump(200)
    after = len([o for o in doc.Objects if D.is_datum(o)])
    cp_panel = W._last_panel
    check("construct.preview", after == before + 1, (before, after, cp_panel.hint.text() if cp_panel else None,
                                                      [ (o.Label, s) for f in getattr(cp_panel, "slots", []) for o, s in f.items]))
    Gui.Control.closeDialog()
    pump(300)

    # --- Press pull top face of body1 by 3 mm
    tip = body.Tip
    top = None
    zmax = body.Shape.BoundBox.ZMax
    for i, f in enumerate(tip.Shape.Faces):
        if abs(f.BoundBox.ZMin - zmax) < 1e-6 and abs(f.BoundBox.ZMax - zmax) < 1e-6:
            top = "Face%d" % (i + 1)
    pp = W.show(MP.PressPullPanel([(tip, top)]))
    pp.distance.set_value(3.0)
    pp.distance.changed.emit()
    pump(300)
    pp.accept()
    pump(300)
    check("presspull.gui", abs(body.Shape.BoundBox.ZMax - (zmax + 3)) < 1e-6, body.Shape.BoundBox.ZMax)

    # --- Combine: join an overlapping new body into body1
    skc = D.new_sketch(doc, root, support=[(D.origin_feature(root, "XY_Plane"), "")])
    pts = [V(30, 5, 0), V(55, 5, 0), V(55, 20, 0), V(30, 20, 0)]
    for i in range(4):
        skc.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
    doc.recompute()
    from freefusion.features import extrude as X
    b2 = X.create(doc, [(skc, [])], {"distance": 8}, operation="NewBody").new_bodies[0]
    b1 = D.design_bodies(doc)[0]
    cp = W.show(MP.CombinePanel())
    cp.target.set_items([(b1, "")])
    cp.tools.set_items([(b2, "")])
    cp.op.set_key("Join")
    cp.accept()
    pump(400)
    check("combine.gui", b2 not in D.design_bodies(doc))

    # --- parameters dialog + expression driven extrude edit from the timeline
    PR.set_parameter(doc, "height", "22", "mm")
    items = T.items(doc)
    ext = [i for i in items if i.kind == "Extrude"][0]
    from freefusion.commands.definitions import edit_feature
    edit_feature(ext.primary)
    pump(400)
    dlg = Gui.Control.activeDialog()
    check("timeline.edit.opens", dlg)
    panel = W._last_panel if hasattr(W, "_last_panel") else None
    if panel is not None:
        panel.distance.setText("height")
        panel.distance._commit()
        pump(400)
        shot("14_edit_extrude")
        panel.accept()
        pump(400)
        check("param.drives", abs(ext.primary.Length.Value - 22) < 1e-6, ext.primary.Length)
    else:
        Gui.Control.closeDialog()
    d = __import__("freefusion.ui.dialogs", fromlist=["x"]).ParametersDialog()
    d.show()
    pump(300)
    d.grab().save(os.path.join(OUT, "15_parameters.png"))
    check("params.dialog", d.tree.topLevelItemCount() == 2)
    d.close()

    # --- new component + activation
    Gui.runCommand("FF_NewComponent", 0)
    pump(300)
    comp = D.active_component(doc)
    check("component.active", D.is_component(comp) and D.role(comp) == D.ROLE_COMPONENT, comp.Label)
    D.set_active_component(doc, root)

    # --- coil and thread flows
    from freefusion.features import special as SP
    doc.openTransaction("coil")
    SP.coil(doc, 20, 4, 3, 2)
    doc.commitTransaction()
    doc.recompute()
    check("coil.gui", any(i.kind == "Coil" for i in T.items(doc)))

    # --- hole on the top face at its center
    body = [b for b in D.design_bodies(doc) if D.is_body(b)][0]
    tip = body.Tip
    zmax = body.Shape.BoundBox.ZMax
    top = [("Face%d" % (i + 1)) for i, f in enumerate(tip.Shape.Faces)
           if abs(f.BoundBox.ZMin - zmax) < 1e-6 and abs(f.BoundBox.ZMax - zmax) < 1e-6][0]
    from freefusion.ui import sketching
    sketching._hole_on(tip, top, None)
    pump(600)
    check("hole.dialog", Gui.Control.activeDialog() and Gui.activeWorkbench().name() == "FreeFusionWorkbench")
    shot("16_hole")
    Gui.ActiveDocument.resetEdit()
    pump(300)
    check("hole.feature", any(i.kind == "Hole" for i in T.items(doc)))

    # --- joint command opens the assembly joint dialog inside FreeFusion
    Gui.Selection.clearSelection()
    Gui.runCommand("FF_Joint", 0)
    pump(1200)
    try:
        import UtilsAssembly
        jinfo = (UtilsAssembly.activeAssembly(), UtilsAssembly.isAssemblyGrounded()
                 if hasattr(UtilsAssembly, "isAssemblyGrounded") else "?",
                 [o.Name for o in D.root_component(doc).Group][:12],
                 Gui.Command.get("Assembly_CreateJointRevolute").isActive())
    except Exception as e:
        jinfo = repr(e)
    check("joint.dialog", Gui.Control.activeDialog() and Gui.activeWorkbench().name() == "FreeFusionWorkbench",
          (Gui.activeWorkbench().name(), jinfo))
    shot("17_joint")
    try:
        Gui.Control.activeDialog() and Gui.Control.closeDialog()
    except Exception:
        pass
    pump(800)
    if Gui.ActiveDocument.getInEdit():
        Gui.ActiveDocument.resetEdit()
    pump(300)

    # --- data panel lists the projects folder
    from freefusion.ui import datapanel
    os.makedirs(datapanel.projects_dir(), exist_ok=True)
    fn = os.path.join(datapanel.projects_dir(), "smoke_test_part.FCStd")
    doc.saveAs(fn)
    datapanel.toggle()
    pump(500)
    dp = datapanel._state["dock"]
    names = [dp.widget().list.item(i).text() for i in range(dp.widget().list.count())]
    check("datapanel.lists", "smoke_test_part" in names, names)
    shot("19_datapanel")
    datapanel.toggle()

    # --- nav bar orbit mode translates left drags
    from freefusion.ui import viewport
    viewport.set_nav_mode("orbit")
    check("navmode.set", viewport._state["mode"] == "orbit")
    viewport.set_nav_mode(None)

    Gui.activeDocument().activeView().viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    tl = timeline_ui.instance().timeline
    tl.refresh()
    pump(500)
    shot("18_final")
    bad = [o.Label for o in doc.Objects if "Invalid" in o.State or "Error" in o.State]
    check("doc.valid", not bad, bad)


def main():
    catcher = ConsoleCatcher()
    try:
        App.Console.AddObserver(catcher) if hasattr(App.Console, "AddObserver") else None
    except Exception:
        pass
    try:
        steps()
        more_steps()
    except Exception:
        log("EXCEPTION\n" + traceback.format_exc())
        RESULTS.append(("exception", False))
    failed = [n for n, ok in RESULTS if not ok]
    log("CONSOLE_ERRORS", catcher.errors[:30])
    log("SUMMARY %s %d/%d" % ("ok" if not failed else "failed", len(RESULTS) - len(failed), len(RESULTS)))
    LOG.close()
    QtCore.QTimer.singleShot(200, lambda: os._exit(0))


QtCore.QTimer.singleShot(2500, main)
