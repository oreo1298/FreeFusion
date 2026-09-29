# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion 360 style application bar + tabbed toolbar (ribbon)."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from ..commands import base
from . import keys, layout, theme

BIG = 30
QAction = getattr(QtGui, "QAction", None) or QtWidgets.QAction  # Qt6 / Qt5


def _is_active(name):
    try:
        cmd = Gui.Command.get(name)
        if cmd is not None and hasattr(cmd, "isActive"):
            return bool(cmd.isActive())
    except Exception:
        pass
    spec = base.spec(name)
    if spec is not None:
        try:
            return bool(spec.active()) if spec.active else base.doc_open()
        except Exception:
            return False
    return True


def _info(name):
    spec = base.spec(name)
    if spec is not None:
        return spec.menu, spec.tooltip, spec.icon
    try:
        info = Gui.Command.get(name).getInfo()
        return info.get("menuText", name), info.get("toolTip", ""), info.get("pixmap", "")
    except Exception:
        return name, "", ""


def _command_icon(name):
    menu, tip, ic = _info(name)
    icon = theme.icon(ic) if ic else QtGui.QIcon()
    if icon.isNull():
        act = base.qaction(name)
        if act is not None:
            icon = act.icon()
    return icon


def make_action(name, parent, with_shortcut=True):
    menu, tip, ic = _info(name)
    key = keys.shortcut_for(name) if with_shortcut else ""
    act = QAction(_command_icon(name), menu + ("\t" + key if key else ""), parent)
    act.setToolTip(_tooltip(name))
    act.setStatusTip(tip)
    act.setData(name)
    act.triggered.connect(lambda *_: base.run(name))
    return act


def _tooltip(name):
    menu, tip, _ = _info(name)
    key = keys.shortcut_for(name)
    t = theme.tokens()
    return ("<div style='min-width:180px'><b>%s</b>%s<br><span style='color:%s'>%s</span></div>"
            % (menu, ("&nbsp;&nbsp;<span style='color:%s'>%s</span>" % (t["accent"], key)) if key else "",
               "#dddddd", tip))


def build_menu(entries, parent_menu):
    for e in entries:
        if e == "-":
            parent_menu.addSeparator()
        elif isinstance(e, tuple):
            sub = parent_menu.addMenu(_command_icon(e[1][0]), e[0])
            build_menu(e[1], sub)
        else:
            parent_menu.addAction(make_action(e, parent_menu))
    parent_menu.aboutToShow.connect(lambda m=parent_menu: _refresh_menu(m))


def _refresh_menu(menu):
    for a in menu.actions():
        name = a.data()
        if name:
            a.setEnabled(_is_active(name))


class RibbonButton(QtWidgets.QToolButton):
    def __init__(self, name, parent=None):
        super(RibbonButton, self).__init__(parent)
        self.name = name
        self.setObjectName("FFRibbonBig")
        self.setIconSize(QtCore.QSize(BIG, BIG))
        self.setAutoRaise(True)
        self.setDefaultAction(make_action(name, self))
        self.setToolTip(_tooltip(name))
        self.setFocusPolicy(QtCore.Qt.NoFocus)


class RibbonGroup(QtWidgets.QFrame):
    def __init__(self, title, quick, entries, parent=None):
        super(RibbonGroup, self).__init__(parent)
        self.setObjectName("FFRibbonGroup")
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(4, 2, 4, 0)
        v.setSpacing(0)
        h = QtWidgets.QHBoxLayout()
        h.setSpacing(1)
        self.buttons = []
        for name in quick:
            b = RibbonButton(name)
            self.buttons.append(b)
            h.addWidget(b)
        h.addStretch(0)
        v.addLayout(h)
        lab = QtWidgets.QToolButton()
        lab.setObjectName("FFGroupLabel")
        lab.setText(title + " ▾")
        lab.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        lab.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        lab.setFocusPolicy(QtCore.Qt.NoFocus)
        menu = QtWidgets.QMenu(lab)
        build_menu(entries, menu)
        lab.setMenu(menu)
        v.addWidget(lab, 0, QtCore.Qt.AlignHCenter)
        self.menu = menu


class FinishSketchGroup(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super(FinishSketchGroup, self).__init__(parent)
        self.setObjectName("FFRibbonGroup")
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(6, 2, 6, 0)
        v.setSpacing(0)
        b = RibbonButton("FF_FinishSketch")
        v.addWidget(b, 0, QtCore.Qt.AlignHCenter)
        lab = QtWidgets.QToolButton()
        lab.setObjectName("FFFinishSketch")
        lab.setText("FINISH SKETCH")
        lab.setAutoRaise(True)
        lab.clicked.connect(lambda: base.run("FF_FinishSketch"))
        v.addWidget(lab, 0, QtCore.Qt.AlignHCenter)
        self.buttons = [b]


def workspace_menu(parent):
    menu = QtWidgets.QMenu(parent)
    wbs = Gui.listWorkbenches()
    for label, wb, icon in layout.WORKSPACES:
        act = menu.addAction(theme.icon(icon), label.title())
        act.setEnabled(wb in wbs)
        if wb not in wbs:
            act.setToolTip("Install the matching add-on to enable this workspace")
        act.triggered.connect(lambda *_, w=wb: switch_workspace(w))
    menu.addSeparator()
    other = menu.addMenu("All FreeCAD Workbenches")
    for name in sorted(wbs, key=lambda n: getattr(wbs[n], "MenuText", n)):
        if name in ("NoneWorkbench",):
            continue
        wbobj = wbs[name]
        act = other.addAction(getattr(wbobj, "MenuText", name))
        act.triggered.connect(lambda *_, w=name: switch_workspace(w))
    return menu


def switch_workspace(wb):
    try:
        from . import workbench
        workbench.real_activate_workbench(wb)
    except Exception as e:
        App.Console.PrintError("FreeFusion: cannot activate %s: %s\n" % (wb, e))


def workspace_label():
    try:
        cur = Gui.activeWorkbench().name()
    except Exception:
        cur = ""
    for label, wb, icon in layout.WORKSPACES:
        if wb == cur:
            return label, icon
    try:
        return getattr(Gui.activeWorkbench(), "MenuText", cur).upper(), "Generic"
    except Exception:
        return "DESIGN", "WSDesign"


class WorkspaceButton(QtWidgets.QToolButton):
    def __init__(self, parent=None):
        super(WorkspaceButton, self).__init__(parent)
        self.setObjectName("FFWorkspaceButton")
        self.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.setIconSize(QtCore.QSize(20, 20))
        self.setMenu(workspace_menu(self))
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.refresh()

    def refresh(self, label=None):
        if label is None:
            label, icon = workspace_label()
        else:
            icon = dict((l, i) for l, w, i in layout.WORKSPACES).get(label, "Generic")
        self.setText(label)
        self.setIcon(theme.icon(icon))


class AppBar(QtWidgets.QWidget):
    """File menu, save, undo/redo, document title, search and settings."""

    def __init__(self, parent=None):
        super(AppBar, self).__init__(parent)
        self.setObjectName("FFAppBar")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(6, 2, 6, 2)
        h.setSpacing(2)
        self.file_button = QtWidgets.QToolButton()
        self.file_button.setObjectName("FFFileButton")
        self.file_button.setIcon(theme.icon("File"))
        self.file_button.setText("File")
        self.file_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.file_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.file_button.setIconSize(QtCore.QSize(18, 18))
        self.file_menu = QtWidgets.QMenu(self.file_button)
        self.file_menu.aboutToShow.connect(self._fill_file_menu)
        self.file_button.setMenu(self.file_menu)
        h.addWidget(self.file_button)
        for name in ("FF_Save", "FF_Undo", "FF_Redo"):
            b = QtWidgets.QToolButton()
            b.setDefaultAction(make_action(name, b, with_shortcut=False))
            b.setIconSize(QtCore.QSize(18, 18))
            b.setAutoRaise(True)
            b.setFocusPolicy(QtCore.Qt.NoFocus)
            h.addWidget(b)
            setattr(self, name, b)
        h.addStretch(1)
        self.title = QtWidgets.QLabel("")
        self.title.setObjectName("FFDocTitle")
        h.addWidget(self.title)
        h.addStretch(1)
        for name in ("FF_Toolbox", "FF_Parameters", "FF_Preferences"):
            b = QtWidgets.QToolButton()
            b.setDefaultAction(make_action(name, b, with_shortcut=False))
            b.setIconSize(QtCore.QSize(18, 18))
            b.setAutoRaise(True)
            b.setFocusPolicy(QtCore.Qt.NoFocus)
            h.addWidget(b)
        self.help = QtWidgets.QToolButton()
        self.help.setIcon(theme.icon("Help"))
        self.help.setIconSize(QtCore.QSize(18, 18))
        self.help.setAutoRaise(True)
        self.help.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        hm = QtWidgets.QMenu(self.help)
        hm.addAction("FreeFusion Quick Start", lambda: __import__(
            "freefusion.ui.preferences", fromlist=["x"]).show_help())
        hm.addAction("Keyboard Shortcuts", lambda: base.run("FF_Shortcuts"))
        hm.addSeparator()
        for cmd in ("Std_OnlineHelp", "Std_FreeCADForum", "Std_About"):
            act = base.qaction(cmd)
            if act is not None:
                hm.addAction(act)
        self.help.setMenu(hm)
        h.addWidget(self.help)

    def set_title(self, text):
        self.title.setText(text)

    def _fill_file_menu(self):
        m = self.file_menu
        m.clear()
        for name in ("FF_NewDesign", "FF_Open"):
            m.addAction(make_action(name, m))
        recent = m.addMenu("Recent Designs")
        self._fill_recent(recent)
        m.addSeparator()
        for name in ("FF_Save", "FF_SaveAs", "FF_Export", "FF_Print3D"):
            a = make_action(name, m)
            a.setEnabled(_is_active(name))
            m.addAction(a)
        m.addSeparator()
        close = base.qaction("Std_CloseActiveWindow")
        if close is not None:
            m.addAction(close)
        m.addSeparator()
        # everything FreeCAD's own menu bar offers
        allm = m.addMenu("FreeCAD Menus")
        mb = Gui.getMainWindow().menuBar()
        for act in mb.actions():
            if act.menu() is not None:
                allm.addMenu(act.menu())
        tog = m.addAction("Show Menu Bar")
        tog.setCheckable(True)
        tog.setChecked(mb.isVisible())
        tog.toggled.connect(lambda on: __import__("freefusion.ui.docks", fromlist=["x"]).set_menubar(on))
        m.addSeparator()
        quit_ = base.qaction("Std_Quit")
        if quit_ is not None:
            m.addAction(quit_)

    def _fill_recent(self, menu):
        grp = App.ParamGet("User parameter:BaseApp/Preferences/RecentFiles")
        n = grp.GetInt("RecentFiles", 0)
        files = []
        for i in range(max(n, 10)):
            f = grp.GetString("MRU%d" % i, "")
            if f:
                files.append(f)
        if not files:
            a = menu.addAction("(none)")
            a.setEnabled(False)
        for f in files:
            menu.addAction(f, lambda fn=f: App.openDocument(fn) if not _already_open(fn) else None)


def _already_open(fn):
    for d in App.listDocuments().values():
        if d.FileName == fn:
            return True
    return False


class Ribbon(QtWidgets.QWidget):
    """Workspace switcher + tab strip + groups; a SKETCH contextual tab while sketching."""

    def __init__(self, parent=None):
        super(Ribbon, self).__init__(parent)
        self.setObjectName("FFRibbon")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(6, 3, 6, 2)
        outer.setSpacing(8)
        ws_col = QtWidgets.QVBoxLayout()
        ws_col.setContentsMargins(0, 0, 0, 0)
        self.workspace = WorkspaceButton()
        ws_col.addStretch(1)
        ws_col.addWidget(self.workspace)
        ws_col.addStretch(1)
        outer.addLayout(ws_col)
        right = QtWidgets.QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        tabs = QtWidgets.QWidget()
        tabs.setObjectName("FFRibbonTabs")
        self.tab_layout = QtWidgets.QHBoxLayout(tabs)
        self.tab_layout.setContentsMargins(0, 0, 0, 0)
        self.tab_layout.setSpacing(0)
        self.stack = QtWidgets.QStackedWidget()
        self.tab_group = QtWidgets.QButtonGroup(self)
        self.tab_group.setExclusive(True)
        self.tab_buttons = {}
        self.pages = {}
        self.all_buttons = []
        for title, groups in layout.TABS:
            self._add_tab(title, groups)
        self._add_tab(layout.SKETCH_TAB[0], layout.SKETCH_TAB[1], contextual=True)
        self.tab_layout.addStretch(1)
        right.addWidget(tabs)
        right.addWidget(self.stack)
        outer.addLayout(right, 1)
        self.current = "SOLID"
        self.select("SOLID")
        self.set_sketch_mode(False)
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(600)
        self._timer.timeout.connect(self.refresh_state)
        self._timer.start()

    def _add_tab(self, title, groups, contextual=False):
        b = QtWidgets.QToolButton()
        b.setText(title)
        b.setCheckable(True)
        b.setFocusPolicy(QtCore.Qt.NoFocus)
        b.setProperty("contextual", "true" if contextual else "false")
        b.clicked.connect(lambda *_, t=title: self.select(t))
        self.tab_group.addButton(b)
        self.tab_layout.addWidget(b)
        self.tab_buttons[title] = b
        page = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(page)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        for gtitle, quick, entries in groups:
            g = RibbonGroup(gtitle, quick, entries)
            self.all_buttons.extend(g.buttons)
            h.addWidget(g)
        if contextual:
            g = FinishSketchGroup()
            self.all_buttons.extend(g.buttons)
            h.addWidget(g)
        h.addStretch(1)
        self.stack.addWidget(page)
        self.pages[title] = page

    def select(self, title):
        if title not in self.pages:
            return
        self.tab_buttons[title].setChecked(True)
        self.stack.setCurrentWidget(self.pages[title])
        if title != "SKETCH":
            self.current = title
        self.refresh_state()

    def set_sketch_mode(self, on):
        sk = self.tab_buttons["SKETCH"]
        sk.setVisible(on)
        for title, b in self.tab_buttons.items():
            if title not in ("SKETCH", "SOLID"):
                b.setVisible(not on)
        if on:
            self.select("SKETCH")
        else:
            self.select(self.current if self.current != "SKETCH" else "SOLID")

    def refresh_state(self):
        if not self.isVisible():
            return
        page = self.stack.currentWidget()
        for b in self.all_buttons:
            if b.isVisible() or b.parent() is page:
                b.setEnabled(_is_active(b.name))


class RibbonBar(QtWidgets.QToolBar):
    """The toolbar that hosts the app bar and the ribbon at the top of the window."""

    def __init__(self, parent=None):
        super(RibbonBar, self).__init__("FreeFusion", parent)
        self.setObjectName("FreeFusionRibbon")
        self.setMovable(False)
        self.setFloatable(False)
        self.toggleViewAction().setVisible(False)
        self.setContextMenuPolicy(QtCore.Qt.PreventContextMenu)
        host = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(host)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.appbar = AppBar()
        self.ribbon = Ribbon()
        v.addWidget(self.appbar)
        v.addWidget(self.ribbon)
        host.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.addWidget(host)
        self.setStyleSheet("QToolBar#FreeFusionRibbon { padding: 0; margin: 0; border: none; spacing: 0; }")


class WorkspaceBar(QtWidgets.QToolBar):
    """Shown in other workbenches so there is always a way back to DESIGN."""

    def __init__(self, parent=None):
        super(WorkspaceBar, self).__init__("FreeFusion Workspace", parent)
        self.setObjectName("FreeFusionWorkspace")
        self.setMovable(False)
        self.toggleViewAction().setVisible(False)
        self.button = WorkspaceButton()
        w = QtWidgets.QWidget()
        w.setObjectName("FFRibbon")
        l = QtWidgets.QHBoxLayout(w)
        l.setContentsMargins(4, 2, 4, 2)
        l.addWidget(self.button)
        self.addWidget(w)
