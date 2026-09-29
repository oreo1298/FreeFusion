# SPDX-License-Identifier: LGPL-2.1-or-later
"""Building blocks for Fusion style command dialogs (task panels)."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from ..features import parameters as PR
from . import theme


def resolve(docname, objname, sub):
    """Resolve a selection (top object + dotted sub name) to (leaf object, element)."""
    doc = App.getDocument(docname)
    top = doc.getObject(objname)
    if top is None:
        return None, ""
    sub = sub or ""
    if "." in sub:
        parts = sub.split(".")
        element = parts[-1]
        path = ".".join(parts[:-1]) + "."
        leaf = None
        try:
            leaf = top.getSubObject(path, retType=1)
        except Exception:
            leaf = None
        if isinstance(leaf, tuple):
            leaf = leaf[0]
        if leaf is None:
            leaf = doc.getObject(parts[-2]) if len(parts) >= 2 else top
        return leaf, element
    return top, sub


def selection_refs():
    """Current selection as [(leaf_obj, [elements])] resolved through containers."""
    out = []
    for s in Gui.Selection.getSelectionEx("", 0):
        top = s.Object
        subs = list(s.SubElementNames) or [""]
        for sub in subs:
            leaf, el = resolve(top.Document.Name, top.Name, sub)
            if leaf is None:
                continue
            for i, (o, els) in enumerate(out):
                if o == leaf:
                    if el and el not in els:
                        els.append(el)
                    break
            else:
                out.append((leaf, [el] if el else []))
    return out


class SelectionField(QtWidgets.QWidget):
    """Fusion style 'Select' field: toggled active, collects clicked geometry."""

    changed = QtCore.Signal()
    activated = QtCore.Signal(object)

    def __init__(self, accept=None, multi=True, placeholder="Select", parent=None):
        super(SelectionField, self).__init__(parent)
        self.accept = accept or (lambda obj, sub: True)
        self.multi = multi
        self.items = []  # [(obj, sub)]
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.button = QtWidgets.QToolButton()
        self.button.setCheckable(True)
        self.button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.button.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.button.setMinimumHeight(24)
        self.button.clicked.connect(self._toggled)
        self.clear_button = QtWidgets.QToolButton()
        self.clear_button.setText("✕")
        self.clear_button.setToolTip("Clear selection")
        self.clear_button.clicked.connect(self.clear)
        lay.addWidget(self.button, 1)
        lay.addWidget(self.clear_button)
        self.placeholder = placeholder
        self._refresh()

    def set_active(self, on):
        self.button.setChecked(on)
        self._refresh()
        if on:
            self.activated.emit(self)
            self.highlight()

    def is_active(self):
        return self.button.isChecked()

    def _toggled(self):
        self.set_active(self.button.isChecked())

    def _refresh(self):
        n = len(self.items)
        if n == 0:
            text = self.placeholder
        elif n == 1:
            o, s = self.items[0]
            text = "%s%s" % (o.Label, (" • " + s) if s else "")
        else:
            text = "%d selected" % n
        self.button.setText(text)
        acc = theme.tokens()["accent"]
        if self.is_active():
            self.button.setStyleSheet("QToolButton { border: 1px solid %s; background: %s;"
                                      " border-radius: 3px; text-align: left; padding: 2px 6px; }"
                                      % (acc, theme.tokens()["accent_soft"]))
        else:
            self.button.setStyleSheet("QToolButton { border: 1px solid %s; border-radius: 3px;"
                                      " text-align: left; padding: 2px 6px; }"
                                      % theme.tokens()["border_strong"])
        self.clear_button.setEnabled(n > 0)

    def toggle(self, obj, sub):
        key = (obj, sub)
        if not self.accept(obj, sub):
            return False
        if key in self.items:
            self.items.remove(key)
        else:
            if not self.multi:
                self.items = []
            self.items.append(key)
        self._refresh()
        self.changed.emit()
        return True

    def set_items(self, items):
        self.items = [(o, s) for o, s in items if o is not None]
        self._refresh()

    def clear(self):
        self.items = []
        self._refresh()
        self.changed.emit()
        if self.is_active():
            self.highlight()

    def refs(self):
        """Grouped [(obj, [subs])]."""
        out = []
        for o, s in self.items:
            for i, (oo, subs) in enumerate(out):
                if oo == o:
                    if s:
                        subs.append(s)
                    break
            else:
                out.append((o, [s] if s else []))
        return out

    def objects(self):
        seen = []
        for o, _ in self.items:
            if o not in seen:
                seen.append(o)
        return seen

    def highlight(self):
        Gui.Selection.clearSelection()
        for o, s in self.items:
            try:
                Gui.Selection.addSelection(o.Document.Name, o.Name, s or "")
            except Exception:
                pass


class ValueField(QtWidgets.QLineEdit):
    """Numeric input with units and user-parameter expressions ('width/2')."""

    changed = QtCore.Signal()

    def __init__(self, value=0.0, unit="mm", step=1.0, parent=None):
        super(ValueField, self).__init__(parent)
        self.unit = unit
        self.step = step
        self._value = value
        self._expr = ""
        self.setText(self._fmt(value))
        self.setMinimumWidth(90)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self._commit)
        self.textEdited.connect(lambda *_: self._timer.start())
        self.editingFinished.connect(self._commit)

    def _fmt(self, v):
        if v is None:
            return ""
        if self.unit == "":
            return ("%g" % v)
        return "%s %s" % (("%.4f" % v).rstrip("0").rstrip("."), self.unit)

    def set_value(self, v, expr=""):
        self._value = v
        self._expr = expr or ""
        self.setText(self._display_expr(expr) if expr else self._fmt(v))

    def _display_expr(self, expr):
        return expr.replace(PR.SHEET_NAME + ".", "")

    def _commit(self):
        self._timer.stop()
        doc = App.ActiveDocument
        text = self.text().strip()
        if not text:
            return
        try:
            val, expr = PR.parse_value(doc, text, self.unit) if doc else (float(text), "")
        except Exception:
            val, expr = None, ""
        ok = val is not None
        pal_color = theme.tokens()["danger"] if not ok else ""
        self.setStyleSheet("QLineEdit { border-color: %s; }" % pal_color if pal_color else "")
        if not ok:
            return
        if val != self._value or expr != self._expr:
            self._value, self._expr = val, expr
            self.changed.emit()

    def value(self):
        return self._value

    def expression(self):
        return self._expr

    def _bump(self, k):
        self._expr = ""
        self._value = (self._value or 0.0) + k * self.step
        self.setText(self._fmt(self._value))
        self.changed.emit()

    def keyPressEvent(self, ev):
        if ev.key() == QtCore.Qt.Key_Up:
            self._bump(1)
            return
        if ev.key() == QtCore.Qt.Key_Down:
            self._bump(-1)
            return
        super(ValueField, self).keyPressEvent(ev)

    def wheelEvent(self, ev):
        if self.hasFocus():
            self._bump(1 if ev.angleDelta().y() > 0 else -1)
            ev.accept()
        else:
            super(ValueField, self).wheelEvent(ev)


class IconCombo(QtWidgets.QComboBox):
    def __init__(self, items, parent=None):
        """items: [(key, label, icon_name)]"""
        super(IconCombo, self).__init__(parent)
        for key, label, ic in items:
            self.addItem(theme.icon(ic) if ic else QtGui.QIcon(), label, key)

    def key(self):
        return self.currentData()

    def set_key(self, key):
        i = self.findData(key)
        if i >= 0:
            self.setCurrentIndex(i)


class FormPanel(object):
    """Base class of FreeFusion task panels (Fusion command dialogs).

    Subclasses call ``self.row(label, widget)`` in ``build()`` and implement
    ``preview()``, ``finish()`` and optionally ``on_selection()``.
    """

    title = "COMMAND"
    icon = "Generic"
    transaction = "FreeFusion"

    def __init__(self):
        self.doc = App.ActiveDocument
        self.form = QtWidgets.QWidget()
        self.form.setObjectName("FFPanel")
        self.form.setWindowTitle(self.title.title())
        self.form.setWindowIcon(theme.icon(self.icon))
        self.grid = QtWidgets.QGridLayout(self.form)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(6)
        self.grid.setColumnStretch(1, 1)
        self._rows = {}
        self.fields = []
        self.hint = QtWidgets.QLabel("")
        self.hint.setObjectName("FFHint")
        self.hint.setWordWrap(True)
        self._closing = False
        self._busy = False
        if self.doc is not None:
            self.doc.openTransaction(self.transaction)
        self.build()
        self.grid.addWidget(self.hint, self.grid.rowCount(), 0, 1, 2)
        Gui.Selection.addObserver(self)
        for f in self.fields:
            f.activated.connect(self._field_activated)

    # layout helpers ---------------------------------------------------------
    def row(self, label, widget, key=None):
        r = self.grid.rowCount()
        lab = QtWidgets.QLabel(label)
        lab.setProperty("role", "caption")
        self.grid.addWidget(lab, r, 0)
        self.grid.addWidget(widget, r, 1)
        if isinstance(widget, SelectionField):
            self.fields.append(widget)
        self._rows[key or label] = (lab, widget)
        return widget

    def show_row(self, key, visible):
        if key in self._rows:
            for w in self._rows[key]:
                w.setVisible(visible)

    def set_hint(self, text, error=False):
        self.hint.setText(text)
        self.hint.setStyleSheet("color: %s;" % theme.tokens()["danger"] if error else "")

    def _field_activated(self, field):
        for f in self.fields:
            if f is not field and f.is_active():
                f.button.setChecked(False)
                f._refresh()

    def active_field(self):
        for f in self.fields:
            if f.is_active():
                return f
        return None

    # selection observer ------------------------------------------------------
    def addSelection(self, doc, obj, sub, pnt):
        if self._busy or self._closing:
            return
        try:
            field = self.active_field()
        except RuntimeError:
            # the dialog was closed from outside (Gui.Control.closeDialog)
            self._cleanup()
            return
        if field is None:
            return
        leaf, el = resolve(doc, obj, sub)
        if leaf is None:
            return
        self._busy = True
        try:
            field.toggle(leaf, el)
            field.highlight()
        finally:
            self._busy = False
        self.on_selection(field)

    def removeSelection(self, doc, obj, sub):
        pass

    def setSelection(self, doc):
        pass

    def clearSelection(self, doc):
        pass

    def on_selection(self, field):
        self.preview()

    # task panel protocol -----------------------------------------------------
    def getStandardButtons(self):
        return QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel

    def _cleanup(self):
        self._closing = True
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass
        Gui.Selection.clearSelection()

    def accept(self):
        try:
            ok = self.finish()
        except Exception as e:
            self.set_hint(str(e), error=True)
            return False
        if ok is False:
            return False
        self._cleanup()
        if self.doc is not None:
            self.doc.commitTransaction()
            self.doc.recompute()
        Gui.Control.closeDialog()
        self.after_close(True)
        return True

    def reject(self):
        self._cleanup()
        if self.doc is not None:
            self.doc.abortTransaction()
            self.doc.recompute()
        Gui.Control.closeDialog()
        self.after_close(False)
        return True

    def after_close(self, accepted):
        pass

    def build(self):
        raise NotImplementedError

    def preview(self):
        pass

    def finish(self):
        return True


_last_panel = None


def show(panel):
    global _last_panel
    if Gui.Control.activeDialog():
        prev = _last_panel
        closed = False
        if prev is not None and not prev._closing:
            try:
                prev.form.objectName()
                prev.reject()          # proper cleanup + abort its preview
                closed = True
            except RuntimeError:
                pass
        if not closed and Gui.Control.activeDialog():
            Gui.Control.closeDialog()
    Gui.Control.showDialog(panel)
    _last_panel = panel
    return panel
