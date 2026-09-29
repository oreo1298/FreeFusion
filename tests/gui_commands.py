# SPDX-License-Identifier: LGPL-2.1-or-later
"""Run every FF_* command once (modal dialogs auto-dismissed) and report errors.

Run through tests/run_gui.sh with TEST=gui_commands.py.
"""

import os
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
ERRORS = []


def log(*a):
    LOG.write(" ".join(str(x) for x in a) + "\n")
    LOG.flush()


def check(name, cond, info=""):
    RESULTS.append((name, bool(cond)))
    log("%s %s %s" % ("PASS" if cond else "FAIL", name, info))


def pump(ms=200):
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec_() if hasattr(loop, "exec_") else loop.exec()


def no_modal():
    """Make every modal dialog return immediately."""
    QtWidgets.QDialog.exec_ = lambda self, *a: (QtCore.QTimer.singleShot(0, self.reject), 0)[1]
    QtWidgets.QDialog.exec = QtWidgets.QDialog.exec_
    QtWidgets.QMessageBox.question = staticmethod(lambda *a, **k: QtWidgets.QMessageBox.No)
    QtWidgets.QMessageBox.information = staticmethod(lambda *a, **k: QtWidgets.QMessageBox.Ok)
    QtWidgets.QMessageBox.warning = staticmethod(lambda *a, **k: QtWidgets.QMessageBox.Ok)
    QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
    QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
    QtWidgets.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
    QtWidgets.QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
    QtWidgets.QMenu.exec_ = lambda self, *a: None
    QtWidgets.QMenu.exec = QtWidgets.QMenu.exec_


_procs = []


def external_watchdog():
    """C++ modal dialogs block Python timers, so an external xdotool loop presses Escape
    on every window that is not the main FreeCAD window."""
    import subprocess
    script = r"""
    while true; do
      for w in $(xdotool search --onlyvisible --name '.' 2>/dev/null); do
        n=$(xdotool getwindowname $w 2>/dev/null)
        case "$n" in *FreeCAD*|""|"Qt Selection Owner"*) ;; *)
          echo "watchdog: $n" >> "$FF_OUT/watchdog.txt"; xdotool key --window $w Escape ;; esac
      done
      sleep 2
    done"""
    return subprocess.Popen(["bash", "-c", script])


def catch_errors():
    orig = App.Console.PrintError

    def err(msg, *a):
        ERRORS.append(msg)
        return orig(msg, *a)
    App.Console.PrintError = err


def close_everything():
    for _ in range(3):
        if Gui.Control.activeDialog():
            try:
                from freefusion.ui import keys
                keys.cancel_active_dialog()
            except Exception:
                pass
            pump(150)
        if Gui.Control.activeDialog():
            try:
                Gui.Control.closeDialog()
            except Exception:
                pass
        try:
            if Gui.ActiveDocument and Gui.ActiveDocument.getInEdit():
                Gui.ActiveDocument.resetEdit()
        except Exception:
            pass
        for w in QtWidgets.QApplication.topLevelWidgets():
            try:
                if w.isVisible() and w.objectName() in ("FFShortcutBox", "FFMarkingMenu"):
                    w.close()
                if isinstance(w, QtWidgets.QDialog) and w.isVisible() and w is not Gui.getMainWindow():
                    w.reject()
            except RuntimeError:
                pass
        pump(100)


# FF_Delete would remove the fixture; the others open FreeCAD's own native modal
# dialogs (file pickers, macro/preferences dialogs) that cannot be dismissed from Python.
SKIP = {"FF_Delete", "FF_Export", "FF_Open", "FF_Save", "FF_SaveAs", "FF_InsertCAD", "FF_Canvas",
        "FF_Scripts", "FF_RecordMacro", "FF_FreeCADPreferences", "FF_AddonManager", "FF_InsertMesh",
        "FF_InsertSVG", "FF_InsertDXF"}


def steps():
    no_modal()
    _procs.append(external_watchdog())
    catch_errors()
    Gui.getMainWindow().resize(1600, 1000)
    Gui.activateWorkbench("FreeFusionWorkbench")
    pump(1200)
    from freefusion import design as D
    from freefusion.commands import base
    from freefusion.features import extrude as X
    doc = App.ActiveDocument
    root = D.root_component(doc)
    sk = D.new_sketch(doc, root, support=[(D.origin_feature(root, "XY_Plane"), "")])
    pts = [V(0, 0, 0), V(40, 0, 0), V(40, 20, 0), V(0, 20, 0)]
    for i in range(4):
        sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
    doc.recompute()
    X.create(doc, [(sk, [])], {"distance": 10})
    doc.recompute()
    body = D.design_bodies(doc)[0]
    names = sorted(base.REGISTRY)
    check("registry.size", len(names) > 150, len(names))
    failures = []
    for name in names:
        if name in SKIP:
            continue
        spec = base.REGISTRY[name]
        close_everything()
        sketch_cmd = name.startswith("FF_Sk") or name.startswith("FF_C") and name[4:5].isupper() \
            or name == "FF_FinishSketch"
        if sketch_cmd:
            try:
                Gui.ActiveDocument.setEdit(sk.Name)
                pump(300)
            except Exception:
                pass
        else:
            Gui.Selection.clearSelection()
            tip = body.Tip if D.is_body(body) and body in doc.Objects else None
            if tip is not None:
                Gui.Selection.addSelection(doc.Name, tip.Name, "Face6")
        n_err = len(ERRORS)
        log("RUN", name)
        try:
            ok_res = Gui.Command.get(name).getInfo() is not None
            Gui.runCommand(name, 0)
            pump(400)
        except Exception as e:
            ok_res = False
            ERRORS.append("%s raised %s" % (name, e))
        new = ERRORS[n_err:]
        bad = [e for e in new if "FreeFusion" in e or "Traceback" in e or "raised" in e]
        if bad or not ok_res:
            failures.append((name, bad[:2]))
        close_everything()
        if sketch_cmd and base.in_sketch():
            Gui.ActiveDocument.resetEdit()
            pump(200)
        if body not in doc.Objects or not body.isValid():
            doc.undo() if hasattr(doc, "undo") else None
            pump(200)
    for name, errs in failures:
        log("CMDFAIL", name, errs)
    check("commands.no.errors", not failures, [f[0] for f in failures])
    check("workbench.still.active", Gui.activeWorkbench().name() == "FreeFusionWorkbench",
          Gui.activeWorkbench().name())


def main():
    try:
        steps()
    except Exception:
        log("EXCEPTION\n" + traceback.format_exc())
        RESULTS.append(("exception", False))
    failed = [n for n, ok in RESULTS if not ok]
    log("SUMMARY %s %d/%d" % ("ok" if not failed else "failed", len(RESULTS) - len(failed), len(RESULTS)))
    LOG.close()
    for p in _procs:
        p.kill()
    QtCore.QTimer.singleShot(200, lambda: os._exit(0))


QtCore.QTimer.singleShot(2500, main)
