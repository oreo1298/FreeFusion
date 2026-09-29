# SPDX-License-Identifier: LGPL-2.1-or-later
"""Window layout: Browser left, command dialogs right, navigation + timeline bottom.

FreeCAD's own panels (model tree, property editor, report view, Python console)
are hidden while FreeFusion is active and can be toggled back from UTILITIES.
Their previous visibility is restored when switching to another workbench.
"""

import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from .. import params
from . import browser, timeline_ui

FC_DOCKS = {
    "tree": ("Model", "Tree view", "Combo View", "ComboView"),
    "properties": ("Property view",),
    "console": ("Python console", "Report view"),
    "tasks": ("Tasks",),
    "selection": ("Selection view",),
}

_state = {"browser": None, "bottom": None, "saved": {}, "tasks_area": None, "menubar": None,
          "mdi_tabs": None}


def _mw():
    return Gui.getMainWindow()


def _alive(w):
    """False for wrappers whose C++ object is gone (FreeCAD recreates some docks)."""
    try:
        w.objectName()
        return True
    except RuntimeError:
        return False


def _find(names):
    out = []
    for d in _mw().findChildren(QtWidgets.QDockWidget):
        try:
            if d.objectName() in names:
                out.append(d)
        except RuntimeError:
            continue
    return out


def in_overlay(dock):
    """True when FreeCAD 1.1's overlay manager hosts the dock (floating over the 3D view)."""
    try:
        return dock.parent() is not _mw()
    except RuntimeError:
        return False


def show_overlay_for(dock, visible):
    """Show/hide the overlay panel (e.g. 'OverlayRight') that hosts dock."""
    try:
        w = dock.parent()
        while w is not None and w is not _mw() and not w.objectName().startswith("Overlay"):
            w = w.parent()
        if w is None or w is _mw():
            return
        if w.isVisible() != visible:
            w.setVisible(visible)
    except RuntimeError:
        pass


def _dock(name, title, widget, area):
    mw = _mw()
    d = mw.findChild(QtWidgets.QDockWidget, name)
    if d is None:
        d = QtWidgets.QDockWidget(title, mw)
        d.setObjectName(name)
        d.setWidget(widget)
        d.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetClosable)
        mw.addDockWidget(area, d)
    return d


def setup():
    mw = _mw()
    if _state["browser"] is None:
        b = browser.create()
        dock = _dock("FreeFusionBrowser", "Browser", b, QtCore.Qt.LeftDockWidgetArea)
        dock.setTitleBarWidget(QtWidgets.QWidget())   # the browser draws its own header
        dock.setMinimumWidth(230)
        _state["browser"] = dock
    if _state["bottom"] is None:
        bottom = timeline_ui.create()
        dock = _dock("FreeFusionTimeline", "Timeline", bottom, QtCore.Qt.BottomDockWidgetArea)
        dock.setTitleBarWidget(QtWidgets.QWidget())
        dock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        _state["bottom"] = dock
    try:
        mw.setCorner(QtCore.Qt.BottomLeftCorner, QtCore.Qt.LeftDockWidgetArea)
        mw.setCorner(QtCore.Qt.BottomRightCorner, QtCore.Qt.RightDockWidgetArea)
    except Exception:
        pass
    return _state["browser"], _state["bottom"]


def activate():
    browser_dock, bottom = setup()
    mw = _mw()
    saved = {}
    for key in ("tree", "properties", "console", "selection"):
        for d in _find(FC_DOCKS[key]):
            saved[d.objectName()] = d.isVisible()
            if not params.get_bool("Show_" + key, False):
                d.hide()
    _state["saved"] = saved
    # command dialogs on the right like Fusion's floating dialogs
    for d in _find(FC_DOCKS["tasks"]):
        if in_overlay(d):
            # FreeCAD 1.1 floats the task panel; give it a Fusion dialog-like width
            import FreeCAD as App
            grp = App.ParamGet("User parameter:BaseApp/MainWindow/DockWindows/OverlayRight")
            width = grp.GetInt("Width", 0)
            if width <= 0 or width > 600:
                grp.SetInt("Width", 380)
            continue
        _state["tasks_area"] = mw.dockWidgetArea(d)
        if mw.dockWidgetArea(d) != QtCore.Qt.RightDockWidgetArea:
            mw.addDockWidget(QtCore.Qt.RightDockWidgetArea, d)
    browser_dock.show()
    bottom.show()
    # document tabs on top, like Fusion
    mdi = mw.findChild(QtWidgets.QMdiArea)
    if mdi is not None:
        _state["mdi_tabs"] = mdi.tabPosition()
        mdi.setTabPosition(QtWidgets.QTabWidget.North)
        mdi.setTabsClosable(True)
    set_menubar(not params.get_bool("HideMenuBar", True), remember=False)
    browser.instance().rebuild()
    timeline_ui.instance().timeline.refresh()


def deactivate():
    mw = _mw()
    for d in _find(FC_DOCKS["tasks"]):
        if in_overlay(d):
            show_overlay_for(d, True)
    if _state["browser"] is not None:
        _state["browser"].hide()
    if _state["bottom"] is not None:
        _state["bottom"].hide()
    for d in mw.findChildren(QtWidgets.QDockWidget):
        try:
            if _state["saved"].get(d.objectName()):
                d.show()
        except RuntimeError:
            continue
    for d in _find(FC_DOCKS["tasks"]):
        if in_overlay(d):
            continue
        area = _state["tasks_area"]
        if area is not None and area != QtCore.Qt.RightDockWidgetArea:
            mw.addDockWidget(area, d)
    mdi = mw.findChild(QtWidgets.QMdiArea)
    if mdi is not None and _state["mdi_tabs"] is not None:
        mdi.setTabPosition(_state["mdi_tabs"])
    set_menubar(True, remember=False)


def toggle(key):
    docks = _find(FC_DOCKS.get(key, ()))
    if not docks:
        return
    show = not any(d.isVisible() for d in docks)
    for d in docks:
        d.setVisible(show)
        if show:
            d.raise_()
    params.set_bool("Show_" + key, show)


def set_menubar(on, remember=True):
    mw = _mw()
    mb = mw.menuBar()
    if not on:
        # keep the menu shortcuts alive while the bar itself is hidden
        for act in mb.actions():
            menu = act.menu()
            if menu is not None:
                for a in menu.actions():
                    if not a.shortcut().isEmpty() and a not in mw.actions():
                        mw.addAction(a)
    mb.setVisible(on)
    if remember:
        params.set_bool("HideMenuBar", not on)
