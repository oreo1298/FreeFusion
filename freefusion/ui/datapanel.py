# SPDX-License-Identifier: LGPL-2.1-or-later
"""Local Data Panel: Fusion's project browser, backed by a folder on disk.

Shows designs (.FCStd) with their embedded thumbnails, sub-folders as projects,
and recently opened files. No cloud involved.
"""

import os
import zipfile

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from .. import params
from . import notify, theme

THUMB = 96


def projects_dir():
    d = params.get_string("ProjectsDir", "")
    if not d:
        d = os.path.join(os.path.expanduser("~"), "FreeFusion Projects")
    return d


def recent_files():
    grp = App.ParamGet("User parameter:BaseApp/Preferences/RecentFiles")
    out = []
    for i in range(max(grp.GetInt("RecentFiles", 0), 12)):
        f = grp.GetString("MRU%d" % i, "")
        if f and os.path.exists(f):
            out.append(f)
    return out


_thumb_cache = {}


def thumbnail(path):
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    key = (path, mtime)
    if key in _thumb_cache:
        return _thumb_cache[key]
    pix = None
    try:
        with zipfile.ZipFile(path) as z:
            for name in ("thumbnails/Thumbnail.png", "Thumbnail.png"):
                if name in z.namelist():
                    pix = QtGui.QPixmap()
                    pix.loadFromData(z.read(name))
                    break
    except Exception:
        pix = None
    if pix is None or pix.isNull():
        pix = theme.icon("WSDesign").pixmap(THUMB, THUMB)
    pix = pix.scaled(THUMB, THUMB, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
    _thumb_cache[key] = pix
    return pix


class DataPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(DataPanel, self).__init__(parent)
        self.setObjectName("FFDataPanel")
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head = QtWidgets.QWidget()
        head.setObjectName("FFBrowserHeader")
        head.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        hl = QtWidgets.QHBoxLayout(head)
        hl.setContentsMargins(8, 4, 4, 4)
        hl.addWidget(QtWidgets.QLabel("DATA"))
        hl.addStretch(1)
        for icon, tip, fn in (("NewDesign", "New design", self._new_design),
                              ("Folder", "New project folder", self._new_folder),
                              ("Open", "Choose projects folder", self._choose_root),
                              ("ComputeAll", "Refresh", self.refresh)):
            b = QtWidgets.QToolButton()
            b.setIcon(theme.icon(icon))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.clicked.connect(fn)
            hl.addWidget(b)
        v.addWidget(head)
        nav = QtWidgets.QHBoxLayout()
        nav.setContentsMargins(6, 4, 6, 4)
        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(["Projects", "Recent"])
        self.mode.currentIndexChanged.connect(lambda *_: self.refresh())
        nav.addWidget(self.mode)
        self.up = QtWidgets.QToolButton()
        self.up.setText("↑")
        self.up.setToolTip("Up one folder")
        self.up.clicked.connect(self._go_up)
        nav.addWidget(self.up)
        self.path_label = QtWidgets.QLabel("")
        self.path_label.setObjectName("FFHint")
        nav.addWidget(self.path_label, 1)
        v.addLayout(nav)
        self.list = QtWidgets.QListWidget()
        self.list.setViewMode(QtWidgets.QListView.IconMode)
        self.list.setIconSize(QtCore.QSize(THUMB, THUMB))
        self.list.setGridSize(QtCore.QSize(THUMB + 24, THUMB + 40))
        self.list.setResizeMode(QtWidgets.QListView.Adjust)
        self.list.setMovement(QtWidgets.QListView.Static)
        self.list.setWordWrap(True)
        self.list.itemActivated.connect(self._activate)
        self.list.itemDoubleClicked.connect(self._activate)
        self.list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context)
        v.addWidget(self.list, 1)
        self.current = projects_dir()
        self.refresh()

    def refresh(self):
        self.list.clear()
        recent = self.mode.currentIndex() == 1
        self.up.setVisible(not recent)
        if recent:
            self.path_label.setText("Recently opened")
            for f in recent_files():
                self._add_file(f)
            return
        root = projects_dir()
        if not os.path.isdir(self.current):
            self.current = root
        try:
            os.makedirs(self.current, exist_ok=True)
        except OSError:
            pass
        rel = os.path.relpath(self.current, os.path.dirname(root))
        self.path_label.setText(rel)
        self.path_label.setToolTip(self.current)
        try:
            names = sorted(os.listdir(self.current), key=str.lower)
        except OSError:
            names = []
        for n in names:
            p = os.path.join(self.current, n)
            if os.path.isdir(p) and not n.startswith("."):
                it = QtWidgets.QListWidgetItem(theme.icon("Folder"), n)
                it.setData(QtCore.Qt.UserRole, ("dir", p))
                self.list.addItem(it)
        for n in names:
            if n.lower().endswith(".fcstd"):
                self._add_file(os.path.join(self.current, n))

    def _add_file(self, path):
        name = os.path.splitext(os.path.basename(path))[0]
        it = QtWidgets.QListWidgetItem(QtGui.QIcon(thumbnail(path)), name)
        it.setData(QtCore.Qt.UserRole, ("file", path))
        it.setToolTip(path)
        self.list.addItem(it)

    def _activate(self, it):
        kind, path = it.data(QtCore.Qt.UserRole)
        if kind == "dir":
            self.current = path
            self.refresh()
            return
        for d in App.listDocuments().values():
            if d.FileName == path:
                App.setActiveDocument(d.Name)
                try:
                    Gui.getDocument(d.Name).ActiveView.setFocus()
                except Exception:
                    pass
                return
        try:
            App.openDocument(path)
        except Exception as e:
            notify.error("Cannot open %s: %s" % (path, e))

    def _go_up(self):
        root = projects_dir()
        if os.path.normpath(self.current) != os.path.normpath(root):
            self.current = os.path.dirname(self.current)
            self.refresh()

    def _new_folder(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "New Project", "Project name:")
        if ok and name:
            try:
                os.makedirs(os.path.join(self.current, name), exist_ok=True)
            except OSError as e:
                notify.error(str(e))
            self.refresh()

    def _new_design(self):
        Gui.runCommand("FF_NewDesign", 0)
        params.set_string("LastProjectDir", self.current)

    def _choose_root(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Projects folder", projects_dir())
        if d:
            params.set_string("ProjectsDir", d)
            self.current = d
            self.refresh()

    def _context(self, pos):
        it = self.list.itemAt(pos)
        m = QtWidgets.QMenu(self)
        if it is not None:
            kind, path = it.data(QtCore.Qt.UserRole)
            m.addAction("Open", lambda: self._activate(it))
            m.addAction("Show in File Manager", lambda: QtGui.QDesktopServices.openUrl(
                QtCore.QUrl.fromLocalFile(path if kind == "dir" else os.path.dirname(path))))
        m.addAction("New Project Folder", self._new_folder)
        m.addAction("Refresh", self.refresh)
        m.exec_(self.list.mapToGlobal(pos)) if hasattr(m, "exec_") else m.exec(self.list.mapToGlobal(pos))


_state = {"dock": None}


def toggle():
    mw = Gui.getMainWindow()
    d = _state["dock"]
    if d is None:
        panel = DataPanel()
        d = QtWidgets.QDockWidget("Data", mw)
        d.setObjectName("FreeFusionData")
        d.setWidget(panel)
        d.setTitleBarWidget(QtWidgets.QWidget())
        mw.addDockWidget(QtCore.Qt.LeftDockWidgetArea, d)
        try:
            from . import docks
            b = docks._state.get("browser")
            if b is not None:
                mw.splitDockWidget(d, b, QtCore.Qt.Vertical)
        except Exception:
            pass
        _state["dock"] = d
        d.show()
        return
    d.setVisible(not d.isVisible())
    if d.isVisible():
        d.widget().refresh()


def hide():
    if _state["dock"] is not None:
        _state["dock"].hide()
