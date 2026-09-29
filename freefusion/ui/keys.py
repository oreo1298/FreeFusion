# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion 360 single-key shortcuts, context aware (model vs. sketch).

Implemented as an application event filter so the keys win over FreeCAD's own
multi-key accelerators (e.g. "V, F") while the 3D view has focus, and never fire
while the user types in a text field.
"""

import json

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from .. import params

MODEL = {
    "E": "FF_Extrude", "Q": "FF_PressPull", "F": "FF_Fillet", "H": "FF_Hole", "M": "FF_Move",
    "J": "FF_Joint", "I": "FF_Measure", "A": "FF_Appearance", "S": "FF_Toolbox",
    "V": "FF_ToggleVisibility", "L": "sketch:FF_SkLine", "R": "sketch:FF_SkRect2Point",
    "C": "sketch:FF_SkCircle", "D": "sketch:FF_SkDimension", "P": "sketch:FF_SkProject",
    "F6": "FF_Fit", "Shift+J": "FF_AsBuiltJoint", "Ctrl+B": "FF_ComputeAll", "Ctrl+N": "FF_NewDesign",
}
SKETCH = {
    "L": "FF_SkLine", "R": "FF_SkRect2Point", "C": "FF_SkCircle", "D": "FF_SkDimension",
    "P": "FF_SkProject", "T": "FF_SkTrim", "O": "FF_SkOffset", "X": "FF_SkConstruction",
    "E": "finish:FF_Extrude", "S": "FF_Toolbox", "I": "FF_Measure", "F6": "FF_Fit",
    "Ctrl+N": "FF_NewDesign",
}
KEY_GROUP = params.ROOT + "/Keys"


def _load(ctx, defaults):
    raw = App.ParamGet(KEY_GROUP).GetString(ctx, "")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except ValueError:
            pass
    return dict(defaults)


def keymap(ctx):
    return _load(ctx, MODEL if ctx == "model" else SKETCH)


def save_keymap(ctx, mapping):
    App.ParamGet(KEY_GROUP).SetString(ctx, json.dumps(mapping, sort_keys=True))


def reset_keymaps():
    App.ParamGet(KEY_GROUP).RemString("model")
    App.ParamGet(KEY_GROUP).RemString("sketch")


def shortcut_for(name):
    for ctx in ("model", "sketch"):
        for k, v in keymap(ctx).items():
            if v.split(":")[-1] == name:
                return k
    return ""


def _key_string(ev):
    key = ev.key()
    mods = ev.modifiers()
    name = QtGui.QKeySequence(key).toString()
    if not name:
        return ""
    parts = []
    if mods & QtCore.Qt.ControlModifier:
        parts.append("Ctrl")
    if mods & QtCore.Qt.AltModifier:
        parts.append("Alt")
    if mods & QtCore.Qt.ShiftModifier and (name.isalpha() or len(name) > 1):
        parts.append("Shift")
    if mods & QtCore.Qt.MetaModifier:
        return ""
    parts.append(name.upper() if len(name) == 1 else name)
    return "+".join(parts)


_TEXT_WIDGETS = (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox, QtWidgets.QTextEdit,
                 QtWidgets.QPlainTextEdit, QtWidgets.QKeySequenceEdit)


def _typing():
    app = QtWidgets.QApplication.instance()
    fw = app.focusWidget()
    if fw is None:
        return False
    if isinstance(fw, _TEXT_WIDGETS):
        return True
    if isinstance(fw, QtWidgets.QComboBox) and fw.isEditable():
        return True
    if isinstance(fw, QtWidgets.QAbstractItemView) and fw.state() == QtWidgets.QAbstractItemView.EditingState:
        return True
    # FreeCAD's python console / report view
    name = type(fw).__name__
    if "Console" in name or "Editor" in name:
        return True
    return False


def _in_main_window():
    app = QtWidgets.QApplication.instance()
    if app.activePopupWidget() is not None or app.activeModalWidget() is not None:
        return False
    w = app.activeWindow()
    return w is not None and w is Gui.getMainWindow()


class KeyFilter(QtCore.QObject):
    def __init__(self):
        super(KeyFilter, self).__init__()
        self.enabled = True
        self.pending = None   # command to run once a sketch is open

    def _resolve(self, ev):
        from ..commands.base import in_sketch
        ks = _key_string(ev)
        if not ks:
            return None
        ctx = "sketch" if in_sketch() else "model"
        return keymap(ctx).get(ks)

    def eventFilter(self, obj, ev):
        t = ev.type()
        if not self.enabled or t not in (QtCore.QEvent.ShortcutOverride, QtCore.QEvent.KeyPress):
            return False
        try:
            if ev.isAutoRepeat() or _typing() or not _in_main_window():
                return False
            if ev.key() == QtCore.Qt.Key_Escape and ev.modifiers() == QtCore.Qt.NoModifier:
                return self._escape(t)
            if ev.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and \
                    ev.modifiers() in (QtCore.Qt.NoModifier, QtCore.Qt.KeypadModifier):
                return self._enter(t)
            target = self._resolve(ev)
        except Exception:
            return False
        if not target:
            return False
        if t == QtCore.QEvent.ShortcutOverride:
            ev.accept()
            return True
        QtCore.QTimer.singleShot(0, lambda: self.dispatch(target))
        return True

    def _escape(self, etype):
        """Fusion: Esc cancels the running command (task dialog)."""
        from ..commands.base import in_sketch
        if in_sketch() or not Gui.Control.activeDialog():
            return False
        if etype == QtCore.QEvent.ShortcutOverride:
            return False
        QtCore.QTimer.singleShot(0, cancel_active_dialog)
        return True

    def _enter(self, etype):
        """Fusion: Enter confirms the running command (OK)."""
        from ..commands.base import in_sketch
        if in_sketch() or not Gui.Control.activeDialog():
            return False
        if etype == QtCore.QEvent.ShortcutOverride:
            return False
        QtCore.QTimer.singleShot(0, accept_active_dialog)
        return True

    def dispatch(self, target):
        from ..commands import base
        if Gui.Control.activeDialog() and not target.endswith("FF_Toolbox") \
                and not base.in_sketch():
            return
        if target.startswith("sketch:"):
            # Fusion: pressing L outside a sketch asks for a plane first
            self.pending = target.split(":", 1)[1]
            base.run("FF_CreateSketch")
            return
        if target.startswith("finish:"):
            from . import sketching
            sketching.finish_sketch()
            QtCore.QTimer.singleShot(50, lambda: base.run(target.split(":", 1)[1]))
            return
        base.run(target)

    def sketch_opened(self):
        if self.pending:
            name, self.pending = self.pending, None
            QtCore.QTimer.singleShot(150, lambda: Gui.runCommand(name, 0))


def accept_active_dialog():
    """Press the task panel's OK button."""
    mw = Gui.getMainWindow()
    for box in mw.findChildren(QtWidgets.QDialogButtonBox):
        try:
            if not box.isVisible():
                continue
            b = box.button(QtWidgets.QDialogButtonBox.Ok)
            if b is not None and b.isVisible() and b.isEnabled():
                b.click()
                return
        except RuntimeError:
            continue


def cancel_active_dialog():
    """Press the task panel's Cancel/Close button (works for every FreeCAD dialog)."""
    from . import widgets as W
    panel = W._last_panel
    if panel is not None and not panel._closing:
        try:
            panel.form.objectName()
            if panel.form.isVisible():
                panel.reject()
                return
        except RuntimeError:
            pass
    mw = Gui.getMainWindow()
    for box in mw.findChildren(QtWidgets.QDialogButtonBox):
        try:
            if not box.isVisible():
                continue
            for role in (QtWidgets.QDialogButtonBox.Cancel, QtWidgets.QDialogButtonBox.Close):
                b = box.button(role)
                if b is not None and b.isVisible() and b.isEnabled():
                    b.click()
                    return
        except RuntimeError:
            continue
    try:
        Gui.Control.closeDialog()
    except Exception:
        pass


_filter = {"obj": None}


def install():
    if _filter["obj"] is None:
        f = KeyFilter()
        QtWidgets.QApplication.instance().installEventFilter(f)
        _filter["obj"] = f
    _filter["obj"].enabled = True
    return _filter["obj"]


def set_enabled(on):
    if _filter["obj"] is not None:
        _filter["obj"].enabled = on


def instance():
    return _filter["obj"]
