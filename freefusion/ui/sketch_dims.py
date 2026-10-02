# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion-style dimension input: a small value box at the dimension, no pop-up dialog.

FreeCAD's Dimension tool asks for the value in a modal dialog
(ShowDialogOnDistanceConstraint). FreeFusion turns that off and, as soon as a
dimension is placed, shows an in-canvas box with the value selected: type a number,
a unit or a parameter expression and press Enter (Esc keeps the measured value).
Double-clicking an existing dimension opens the same box.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from . import theme

SKETCHER = "User parameter:BaseApp/Preferences/Mod/Sketcher"
DIMENSIONAL = ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle")
_state = {"counts": {}, "box": None, "saved": None, "pending": None}


def set_enabled(on):
    grp = App.ParamGet(SKETCHER)
    if on:
        if _state["saved"] is None:
            _state["saved"] = grp.GetBool("ShowDialogOnDistanceConstraint", True)
        grp.SetBool("ShowDialogOnDistanceConstraint", False)
    else:
        if _state["saved"] is not None:
            grp.SetBool("ShowDialogOnDistanceConstraint", _state["saved"])
            _state["saved"] = None
        close_box()


def _editing(sk):
    try:
        from ..commands.base import editing_object
        return editing_object() is sk
    except Exception:
        return False


def remember(sk):
    try:
        _state["counts"][(sk.Document.Name, sk.Name)] = len(sk.Constraints)
    except Exception:
        pass


def constraints_changed(sk):
    """Document observer hook: a new driving dimension -> ask for its value."""
    key = (sk.Document.Name, sk.Name)
    try:
        cons = sk.Constraints
    except Exception:
        return
    old = _state["counts"].get(key)
    _state["counts"][key] = len(cons)
    if old is None or len(cons) <= old or not _editing(sk):
        return
    for i in range(len(cons) - 1, old - 1, -1):
        c = cons[i]
        if c.Type in DIMENSIONAL and getattr(c, "Driving", True):
            # FreeCAD's Dimension tool shows a preview first; ask once it is committed
            _state["pending"] = (key, i, len(cons))
            return


def committed(doc):
    """Document observer hook: a transaction was committed (the dimension was placed)."""
    pending = _state.get("pending")
    _state["pending"] = None
    if not pending or pending[0][0] != doc.Name:
        return
    (dname, sname), i, n = pending
    try:
        sk = doc.getObject(sname)
        cons = sk.Constraints
    except Exception:
        return
    if sk is None or i >= len(cons) or cons[i].Type not in DIMENSIONAL:
        return
    QtCore.QTimer.singleShot(30, lambda: edit(sk, i))


def aborted(doc):
    _state["pending"] = None


def _viewer():
    try:
        return Gui.ActiveDocument.ActiveView.graphicsView()
    except Exception:
        return None


def _text_of(sk, i):
    try:
        q = sk.getDatum(i)
        if sk.Constraints[i].Type == "Angle":
            v = q.getValueAs("deg")
            return "%s deg" % _num(getattr(v, "Value", v))
        v = q.getValueAs("mm")
        return "%s mm" % _num(getattr(v, "Value", v))
    except Exception:
        return ""


def _num(v):
    return ("%.4f" % v).rstrip("0").rstrip(".")


def edit(sk, index, pos=None):
    """Show the value box for constraint `index` (at `pos` in viewer coordinates)."""
    viewer = _viewer()
    if viewer is None or not _editing(sk):
        return
    close_box()
    box = DimBox(viewer, sk, index)
    if pos is None:
        pos = viewer.mapFromGlobal(QtGui.QCursor.pos())
    x = max(4, min(viewer.width() - box.width() - 4, pos.x() + 12))
    y = max(4, min(viewer.height() - box.height() - 4, pos.y() - box.height() - 6))
    box.move(x, y)
    box.show()
    box.raise_()
    box.setFocus(QtCore.Qt.OtherFocusReason)
    box.selectAll()
    _state["box"] = box


def close_box():
    box = _state["box"]
    _state["box"] = None
    if box is not None:
        try:
            box.hide()
            box.deleteLater()
        except RuntimeError:
            pass


def active_box():
    return _state["box"]


class DimBox(QtWidgets.QLineEdit):
    def __init__(self, parent, sk, index):
        super(DimBox, self).__init__(parent)
        self.sk = sk
        self.index = index
        self.done = False
        self.setObjectName("FFValueBox")
        t = theme.tokens()
        self.setStyleSheet(
            "QLineEdit#FFValueBox { background: %s; color: %s; border: 1px solid %s;"
            " border-radius: 2px; padding: 1px 4px; font-size: 12px; }"
            % (t["panel"], t["text"], t["accent"]))
        self.setFixedWidth(104)
        self.setText(_text_of(sk, index))

    def keyPressEvent(self, ev):
        k = ev.key()
        if k in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            if self.apply():
                QtCore.QTimer.singleShot(0, close_box)
            return
        if k == QtCore.Qt.Key_Escape:
            self.done = True
            QtCore.QTimer.singleShot(0, close_box)
            return
        super(DimBox, self).keyPressEvent(ev)

    def focusOutEvent(self, ev):
        if not self.done and self.isModified():
            self.apply()
        self.done = True
        QtCore.QTimer.singleShot(0, close_box)
        super(DimBox, self).focusOutEvent(ev)

    def apply(self):
        from ..features import parameters as PR
        sk, i = self.sk, self.index
        text = self.text().strip()
        if not text:
            return False
        try:
            c = sk.Constraints[i]
        except Exception:
            return True
        unit = "deg" if c.Type == "Angle" else "mm"
        try:
            val, expr = PR.parse_value(sk.Document, text, unit)
        except Exception:
            val, expr = None, ""
        if val is None:
            self.setStyleSheet(self.styleSheet() + "QLineEdit#FFValueBox { border-color: %s; }"
                               % theme.tokens()["danger"])
            return False
        self.done = True
        doc = sk.Document
        doc.openTransaction("Dimension")
        try:
            if expr:
                sk.setExpression("Constraints[%d]" % i, expr)
            else:
                try:
                    sk.setExpression("Constraints[%d]" % i, None)
                except Exception:
                    pass
                q = App.Units.Quantity("%r %s" % (val, unit))
                sk.setDatum(i, q)
            doc.commitTransaction()
        except Exception as e:
            doc.abortTransaction()
            from . import notify
            notify.error("Could not set the dimension: %s" % e)
            return True
        doc.recompute()
        return True


def double_click(widget, pos):
    """Viewport hook: double-click on a dimension -> value box. True when handled."""
    try:
        from ..commands.base import editing_object
        sk = editing_object()
        if sk is None or not sk.isDerivedFrom("Sketcher::SketchObject"):
            return False
        pre = Gui.Selection.getPreselection()
        subs = list(getattr(pre, "SubElementNames", []) or [])
    except Exception:
        return False
    for s in subs:
        if s.startswith("Constraint"):
            try:
                i = int(s[len("Constraint"):]) - 1
                c = sk.Constraints[i]
            except Exception:
                continue
            if c.Type in DIMENSIONAL and getattr(c, "Driving", True):
                viewer = _viewer()
                p = widget.mapTo(viewer, pos) if viewer is not None and widget is not viewer else pos
                edit(sk, i, p)
                return True
    return False
