# SPDX-License-Identifier: LGPL-2.1-or-later
"""3D view integration: ground grid, navigation modes, right-click marking menu."""

import math

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from .. import params

VIEW = "User parameter:BaseApp/Preferences/View"
NAV_STYLES = [
    ("Fusion 360 (middle pan, Shift+middle orbit)", "Gui::RevitNavigationStyle"),
    ("FreeCAD CAD", "Gui::CADNavigationStyle"),
    ("SolidWorks", "Gui::SolidWorksNavigationStyle"),
    ("Inventor", "Gui::InventorNavigationStyle"),
    ("Blender", "Gui::BlenderNavigationStyle"),
    ("Siemens NX", "Gui::SiemensNXNavigationStyle"),
    ("Touchpad", "Gui::TouchpadNavigationStyle"),
    ("Gesture", "Gui::GestureNavigationStyle"),
]
nav_mode_changed = []


def current_nav_style():
    return App.ParamGet(VIEW).GetString("NavigationStyle", "Gui::CADNavigationStyle")


def set_nav_style(style):
    App.ParamGet(VIEW).SetString("NavigationStyle", style)


def set_draw_style(mode):
    try:
        Gui.ActiveDocument.ActiveView.setDrawStyle(mode)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# ground grid (Coin), like Fusion's layout grid


def _coin():
    from pivy import coin
    return coin


_grids = {}


def _make_grid(size=500.0, minor=10.0, major=50.0):
    coin = _coin()
    t = params.get_string("Theme", "light")
    root = coin.SoType.fromName("SoSkipBoundingGroup").createInstance()
    try:
        root.mode = 1   # EXCLUDE_BBOX: do not influence 'fit all'
    except Exception:
        pass
    body = coin.SoSeparator()      # keeps pick style / light model local to the grid
    root.addChild(body)
    pick = coin.SoPickStyle()
    pick.style = coin.SoPickStyle.UNPICKABLE
    body.addChild(pick)
    light = coin.SoLightModel()
    light.model = coin.SoLightModel.BASE_COLOR
    body.addChild(light)
    for step, color, width in ((minor, (0.84, 0.86, 0.89) if t == "light" else (0.33, 0.35, 0.38), 1),
                               (major, (0.72, 0.75, 0.79) if t == "light" else (0.42, 0.45, 0.49), 1.5)):
        sep = coin.SoSeparator()
        col = coin.SoBaseColor()
        col.rgb = color
        style = coin.SoDrawStyle()
        style.lineWidth = width
        pts = []
        n = int(size / step)
        for i in range(-n, n + 1):
            v = i * step
            if step == minor and abs(round(v / major) * major - v) < 1e-9:
                continue
            pts += [(v, -size, 0), (v, size, 0), (-size, v, 0), (size, v, 0)]
        coords = coin.SoCoordinate3()
        coords.point.setValues(0, len(pts), pts)
        lines = coin.SoLineSet()
        lines.numVertices.setValues(0, len(pts) // 2, [2] * (len(pts) // 2))
        sep.addChild(col)
        sep.addChild(style)
        sep.addChild(coords)
        sep.addChild(lines)
        body.addChild(sep)
    return root


def grid_visible():
    return params.get_bool("ShowGrid", True)


def set_grid_visible(on):
    params.set_bool("ShowGrid", on)
    refresh_grids()


def refresh_grids(enabled=True):
    """Add/remove the grid in every open 3D view."""
    show = enabled and grid_visible()
    for gdoc in _gui_documents():
        for view in _views(gdoc):
            key = id(view)
            try:
                sg = view.getSceneGraph()
            except Exception:
                continue
            node = _grids.get(key)
            if show and node is None:
                node = _make_grid()
                sg.insertChild(node, 0)
                _grids[key] = (node, sg)
            elif not show and node is not None:
                try:
                    node[1].removeChild(node[0])
                except Exception:
                    pass
                _grids.pop(key, None)


def _gui_documents():
    out = []
    for name in App.listDocuments():
        try:
            out.append(Gui.getDocument(name))
        except Exception:
            pass
    return out


def _views(gdoc):
    try:
        views = gdoc.mdiViewsOfType("Gui::View3DInventor")
        return views
    except Exception:
        try:
            return [gdoc.ActiveView]
        except Exception:
            return []


# ---------------------------------------------------------------------------
# mouse handling on the GL widget


_state = {"mode": None, "filters": {}}


def set_nav_mode(mode):
    _state["mode"] = mode
    for w in list(_state["filters"].keys()):
        try:
            w.setCursor(QtCore.Qt.OpenHandCursor if mode == "pan" else
                        QtCore.Qt.SizeAllCursor if mode == "orbit" else
                        QtCore.Qt.SizeVerCursor if mode == "zoom" else QtCore.Qt.ArrowCursor)
            if mode is None:
                w.unsetCursor()
        except Exception:
            pass
    for cb in nav_mode_changed:
        try:
            cb(mode)
        except Exception:
            pass


def _mouse_event(etype, pos, gpos, button, buttons, mods):
    try:
        return QtGui.QMouseEvent(etype, QtCore.QPointF(pos), QtCore.QPointF(gpos), button, buttons, mods)
    except TypeError:
        return QtGui.QMouseEvent(etype, QtCore.QPointF(pos), button, buttons, mods)


def _pos(ev):
    if hasattr(ev, "position"):
        return ev.position().toPoint(), ev.globalPosition().toPoint()
    return ev.pos(), ev.globalPos()


class ViewFilter(QtCore.QObject):
    """Installed on each 3D viewport."""

    def __init__(self, widget):
        super(ViewFilter, self).__init__(widget)
        self.widget = widget
        self.rmb_press = None
        self.rmb_gesture = False
        self.synth = False
        self.enabled = True
        self.menu = None

    def _sketch_tool_active(self):
        try:
            return self.widget.cursor().shape() == QtCore.Qt.BitmapCursor
        except Exception:
            return False

    def _translate(self, ev, etype):
        """Nav modes: turn a left drag into Fusion's middle-button gestures."""
        mode = _state["mode"]
        mods = {"orbit": QtCore.Qt.ShiftModifier, "pan": QtCore.Qt.NoModifier,
                "zoom": QtCore.Qt.ControlModifier}[mode]
        pos, gpos = _pos(ev)
        buttons = QtCore.Qt.MiddleButton if (etype != QtCore.QEvent.MouseButtonRelease) else QtCore.Qt.NoButton
        new = _mouse_event(etype, pos, gpos, QtCore.Qt.MiddleButton if etype != QtCore.QEvent.MouseMove
                           else QtCore.Qt.NoButton, buttons, mods)
        self.synth = True
        try:
            QtWidgets.QApplication.sendEvent(self.widget, new)
        finally:
            self.synth = False

    def eventFilter(self, obj, ev):
        if self.synth or not self.enabled:
            return False
        t = ev.type()
        if t not in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease,
                     QtCore.QEvent.MouseMove, QtCore.QEvent.MouseButtonDblClick, QtCore.QEvent.KeyPress):
            return False
        try:
            return self._handle(ev, t)
        except Exception as e:
            App.Console.PrintLog("FreeFusion view filter: %s\n" % e)
            return False

    def _handle(self, ev, t):
        mode = _state["mode"]
        if t == QtCore.QEvent.KeyPress:
            if ev.key() == QtCore.Qt.Key_Escape and mode:
                set_nav_mode(None)
                return True
            return False
        btn = ev.button() if t != QtCore.QEvent.MouseMove else QtCore.Qt.NoButton
        # double middle click = fit all (Fusion)
        if t == QtCore.QEvent.MouseButtonDblClick and btn == QtCore.Qt.MiddleButton:
            Gui.SendMsgToActiveView("ViewFit")
            return True
        # navigation tool modes from the nav bar
        if mode:
            if t == QtCore.QEvent.MouseButtonPress and btn == QtCore.Qt.LeftButton:
                self._translate(ev, QtCore.QEvent.MouseButtonPress)
                return True
            if t == QtCore.QEvent.MouseMove and ev.buttons() & QtCore.Qt.LeftButton:
                self._translate(ev, QtCore.QEvent.MouseMove)
                return True
            if t == QtCore.QEvent.MouseButtonRelease and btn == QtCore.Qt.LeftButton:
                self._translate(ev, QtCore.QEvent.MouseButtonRelease)
                return True
            if t == QtCore.QEvent.MouseButtonPress and btn == QtCore.Qt.RightButton:
                set_nav_mode(None)
                return True
        if not params.get_bool("MarkingMenu", True):
            return False
        # right click -> marking menu
        if t == QtCore.QEvent.MouseButtonPress and btn == QtCore.Qt.RightButton:
            if self._pass_right_click():
                return False
            self.rmb_press = _pos(ev)[1]
            self.rmb_gesture = False
            return True
        if t == QtCore.QEvent.MouseMove and self.rmb_press is not None and ev.buttons() & QtCore.Qt.RightButton:
            g = _pos(ev)[1]
            if not self.rmb_gesture and (g - self.rmb_press).manhattanLength() > 14:
                self.rmb_gesture = True
                self._open_menu(self.rmb_press, gesture=True)
            if self.menu is not None:
                self.menu.track(g)
            return True
        if t == QtCore.QEvent.MouseButtonRelease and btn == QtCore.Qt.RightButton and self.rmb_press is not None:
            press = self.rmb_press
            self.rmb_press = None
            if self.rmb_gesture and self.menu is not None:
                self.menu.release(_pos(ev)[1])
            else:
                self._open_menu(press, gesture=False)
            return True
        return False

    def _pass_right_click(self):
        from ..commands.base import in_sketch
        if in_sketch():
            return self._sketch_tool_active()
        if Gui.Control.activeDialog():
            return True
        return False

    def _open_menu(self, gpos, gesture):
        from . import marking_menu
        self.menu = marking_menu.show(gpos, gesture, native=self._native_menu)

    def _native_menu(self, gpos):
        """Hand a right click to FreeCAD to get its own context menu."""
        local = self.widget.mapFromGlobal(gpos)
        self.synth = True
        try:
            for et in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease):
                e = _mouse_event(et, local, gpos, QtCore.Qt.RightButton,
                                 QtCore.Qt.RightButton if et == QtCore.QEvent.MouseButtonPress else QtCore.Qt.NoButton,
                                 QtCore.Qt.NoModifier)
                QtWidgets.QApplication.sendEvent(self.widget, e)
        finally:
            self.synth = False


def _gl_widget(view):
    """The OpenGL viewport that receives the mouse events of a 3D view."""
    try:
        return view.graphicsView().viewport()
    except Exception:
        pass
    try:
        return view.getViewer().getGLWidget()
    except Exception:
        return None


def install_filters(enabled=True):
    for gdoc in _gui_documents():
        for view in _views(gdoc):
            w = _gl_widget(view)
            if w is None:
                continue
            f = _state["filters"].get(w)
            if f is None:
                f = ViewFilter(w)
                w.installEventFilter(f)
                _state["filters"][w] = f
                try:
                    w.destroyed.connect(lambda *_, ww=w: _state["filters"].pop(ww, None))
                except Exception:
                    pass
            f.enabled = enabled


def set_enabled(on):
    for f in list(_state["filters"].values()):
        try:
            f.enabled = on
        except Exception:
            pass
    if not on:
        set_nav_mode(None)
