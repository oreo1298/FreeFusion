# SPDX-License-Identifier: LGPL-2.1-or-later
"""The 'S' key toolbox: type to search every FreeFusion and FreeCAD command."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from .. import params
from ..commands import base
from . import keys, theme

PINNED_DEFAULT = ["FF_Extrude", "FF_CreateSketch", "FF_Fillet", "FF_PressPull", "FF_Combine", "FF_Hole",
                  "FF_OffsetPlane", "FF_Measure", "FF_Parameters", "FF_Move"]


def pinned():
    raw = params.get_string("Pinned", "")
    return [p for p in raw.split(",") if p] or list(PINNED_DEFAULT)


def set_pinned(names):
    params.set_string("Pinned", ",".join(names))


def _all_commands():
    out = []
    seen = set()
    for name, spec in base.REGISTRY.items():
        out.append((name, spec.menu, spec.tooltip, spec.keywords, spec.icon, True))
        seen.add(name)
    for name in Gui.listCommands():
        if name in seen or name.startswith("Std_Test") or name.startswith("Std_MDITest") or \
                name.startswith("Std_ViewExample"):
            continue
        try:
            info = Gui.Command.get(name).getInfo()
            menu = info.get("menuText", name).replace("&", "")
            tip = info.get("toolTip", "")
            out.append((name, menu, tip, "", info.get("pixmap", ""), False))
        except Exception:
            continue
    return out


class ShortcutBox(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super(ShortcutBox, self).__init__(parent, QtCore.Qt.Popup)
        self.setObjectName("FFShortcutBox")
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.resize(420, 460)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(1, 1, 1, 1)
        v.setSpacing(0)
        self.edit = QtWidgets.QLineEdit()
        self.edit.setPlaceholderText("Search commands (e.g. extrude, fillet, plane)")
        self.edit.textChanged.connect(self._filter)
        self.edit.installEventFilter(self)
        v.addWidget(self.edit)
        self.list = QtWidgets.QListWidget()
        self.list.setIconSize(QtCore.QSize(20, 20))
        self.list.itemActivated.connect(self._run_item)
        self.list.itemClicked.connect(self._run_item)
        self.list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context)
        v.addWidget(self.list, 1)
        self._cmds = _all_commands()
        self._filter("")

    def _add(self, name, menu, tip, icon, ours, header=None):
        key = keys.shortcut_for(name)
        it = QtWidgets.QListWidgetItem(theme.icon(icon) if (icon and ours) else self._fc_icon(name, icon),
                                       "%s%s" % (menu, ("      " + key) if key else ""))
        it.setToolTip(tip)
        it.setData(QtCore.Qt.UserRole, name)
        if not ours:
            it.setForeground(QtGui.QColor(theme.tokens()["text_dim"]))
        self.list.addItem(it)

    def _fc_icon(self, name, pix):
        act = base.qaction(name)
        if act is not None and not act.icon().isNull():
            return act.icon()
        return theme.icon(pix) if pix else QtGui.QIcon()

    def _header(self, text):
        it = QtWidgets.QListWidgetItem(text)
        it.setFlags(QtCore.Qt.NoItemFlags)
        f = it.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 0.85)
        it.setFont(f)
        it.setForeground(QtGui.QColor(theme.tokens()["text_dim"]))
        self.list.addItem(it)

    def _filter(self, text):
        self.list.clear()
        text = text.strip().lower()
        if not text:
            self._header("PINNED")
            for n in pinned():
                spec = base.spec(n)
                if spec:
                    self._add(n, spec.menu, spec.tooltip, spec.icon, True)
            last = base.last_command()
            if last and base.spec(last):
                self._header("RECENT")
                s = base.spec(last)
                self._add(last, s.menu, s.tooltip, s.icon, True)
        else:
            words = text.split()
            scored = []
            for name, menu, tip, kw, icon, ours in self._cmds:
                hay = ("%s %s %s %s" % (menu, name, kw, tip)).lower()
                if all(w in hay for w in words):
                    score = (0 if menu.lower().startswith(text) else 1 if text in menu.lower() else 2,
                             0 if ours else 1, menu)
                    scored.append((score, name, menu, tip, icon, ours))
            scored.sort()
            for _, name, menu, tip, icon, ours in scored[:60]:
                self._add(name, menu, tip, icon, ours)
        for i in range(self.list.count()):
            if self.list.item(i).flags() & QtCore.Qt.ItemIsEnabled:
                self.list.setCurrentRow(i)
                break

    def eventFilter(self, obj, ev):
        if obj is self.edit and ev.type() == QtCore.QEvent.KeyPress:
            k = ev.key()
            if k in (QtCore.Qt.Key_Down, QtCore.Qt.Key_Up):
                row = self.list.currentRow()
                step = 1 if k == QtCore.Qt.Key_Down else -1
                n = self.list.count()
                r = row
                for _ in range(n):
                    r = (r + step) % max(n, 1)
                    if self.list.item(r).flags() & QtCore.Qt.ItemIsEnabled:
                        self.list.setCurrentRow(r)
                        break
                return True
            if k in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                it = self.list.currentItem()
                if it is not None:
                    self._run_item(it)
                return True
            if k == QtCore.Qt.Key_Escape:
                self.close()
                return True
        return False

    def _run_item(self, it):
        name = it.data(QtCore.Qt.UserRole)
        if not name:
            return
        self.close()
        QtCore.QTimer.singleShot(0, lambda: base.run(name))

    def _context(self, pos):
        it = self.list.itemAt(pos)
        if it is None or not it.data(QtCore.Qt.UserRole):
            return
        name = it.data(QtCore.Qt.UserRole)
        m = QtWidgets.QMenu(self)
        p = pinned()
        if name in p:
            m.addAction("Unpin", lambda: (set_pinned([x for x in p if x != name]), self._filter(self.edit.text())))
        else:
            m.addAction("Pin to Toolbox", lambda: (set_pinned(p + [name]), self._filter(self.edit.text())))
        m.exec_(self.list.mapToGlobal(pos)) if hasattr(m, "exec_") else m.exec(self.list.mapToGlobal(pos))


def show():
    box = ShortcutBox(Gui.getMainWindow())
    pos = QtGui.QCursor.pos() - QtCore.QPoint(40, 20)
    screen = QtWidgets.QApplication.screenAt(pos) if hasattr(QtWidgets.QApplication, "screenAt") else None
    if screen is not None:
        geo = screen.availableGeometry()
        pos.setX(min(max(geo.left(), pos.x()), geo.right() - box.width()))
        pos.setY(min(max(geo.top(), pos.y()), geo.bottom() - box.height()))
    box.move(pos)
    box.show()
    box.edit.setFocus()
    return box
