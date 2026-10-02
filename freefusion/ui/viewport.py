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
# ground / sketch grid: see grid.py (adaptive, like Fusion's layout grid)


def grid_visible():
    from . import grid
    return grid.ground_visible()


def set_grid_visible(on):
    from . import grid
    grid.set_ground_visible(on)


def refresh_grids(enabled=True):
    """Turn the adaptive grids on/off in every open 3D view."""
    from . import grid
    if enabled != grid._state["enabled"]:
        grid.set_enabled(enabled)
    else:
        grid.refresh(force=True)


# ---------------------------------------------------------------------------
# camera: Fusion opens a new design at a useful scale (not FreeCAD's 4 mm empty fit)

DEFAULT_VIEW_MM = 250.0
ISOMETRIC = (0.424708, 0.17592, 0.339851, 0.820473)


def _design_extent(doc):
    """Size of the visible design in mm (0 when empty)."""
    bb = _design_bbox(doc)
    return bb.DiagonalLength if bb is not None else 0.0


def _design_bbox(doc):
    """Bounding box of everything visible in the design, or None."""
    try:
        from .. import design as D
        bb = None
        for o in doc.Objects:
            if not hasattr(o, "Shape") or D.is_origin_feature(o):
                continue
            try:
                if not o.ViewObject.Visibility or o.Shape.isNull():
                    continue
                b = o.Shape.BoundBox
            except Exception:
                continue
            if not b.isValid():
                continue
            if bb is None:
                bb = App.BoundBox(b)
            else:
                bb.add(b)
        return bb
    except Exception:
        return None


def default_view(view=None, size=DEFAULT_VIEW_MM, center=None, orientation=ISOMETRIC):
    """Isometric view of `size` mm around the origin (used for empty designs)."""
    from pivy import coin
    try:
        view = view or Gui.ActiveDocument.ActiveView
        cam = view.getCameraNode()
    except Exception:
        return
    center = center or App.Vector(0, 0, 0)
    if orientation is not None:
        cam.orientation.setValue(coin.SbRotation(*orientation))
    rot = cam.orientation.getValue()
    d = App.Vector(*rot.multVec(coin.SbVec3f(0, 0, -1)).getValue())
    if cam.getTypeId().getName().getString() == "OrthographicCamera":
        cam.height.setValue(size)
        dist = size * 2.0
    else:
        dist = (size / 2.0) / math.tan(cam.heightAngle.getValue() / 2.0)
    pos = center - d * dist
    cam.position.setValue(pos.x, pos.y, pos.z)
    cam.focalDistance.setValue(dist)


def fit(view=None):
    """Fit all, or the default scale when there is nothing to fit (Fusion's behaviour)."""
    try:
        view = view or Gui.ActiveDocument.ActiveView
        doc = Gui.ActiveDocument.Document
    except Exception:
        return
    from . import navigation
    navigation.reset_pivot(doc)
    if _design_extent(doc) < 1e-3:
        default_view(view, orientation=None)
    else:
        view.fitAll()


def home(view=None):
    try:
        view = view or Gui.ActiveDocument.ActiveView
    except Exception:
        return
    try:
        view.viewIsometric()
    except Exception:
        pass
    QtCore.QTimer.singleShot(0, lambda: fit(view))


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
        # on-canvas manipulators (drag arrows) come first
        from . import manipulator, navigation
        if manipulator.handle_event(self.widget, ev, t):
            return True
        pos = _pos(ev)[0]
        # Fusion orbit (Shift + middle) around the design center / picked pivot
        if navigation.handle_orbit(self.widget, ev, t, pos):
            return True
        # selection box on empty canvas, Shift + click adds
        if not mode and self._select_box_allowed() and navigation.handle_select(
                self.widget, ev, t, pos, self._in_sketch()):
            return True
        # sketch tools: lock the cursor to round values and key points
        if not mode and self._snap(ev, t, btn):
            return True
        # double click on a sketch dimension: in-canvas value box instead of FreeCAD's dialog
        if t == QtCore.QEvent.MouseButtonDblClick and btn == QtCore.Qt.LeftButton \
                and not self._sketch_tool_active():
            from . import sketch_dims
            if sketch_dims.double_click(self.widget, _pos(ev)[0]):
                return True
        # double middle click = fit all (Fusion)
        if t == QtCore.QEvent.MouseButtonDblClick and btn == QtCore.Qt.MiddleButton:
            fit()
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

    def _in_sketch(self):
        from ..commands.base import in_sketch
        return in_sketch()

    def _select_box_allowed(self):
        if not params.get_bool("WindowSelect", True):
            return False
        try:
            gd = Gui.ActiveDocument
            # a feature in edit (FreeCAD task dialogs) handles its own clicks
            return gd is not None and (gd.getInEdit() is None or self._in_sketch())
        except Exception:
            return False

    def _snap(self, ev, t, btn):
        if t == QtCore.QEvent.MouseMove:
            if ev.buttons() & ~QtCore.Qt.LeftButton:
                return False
        elif btn != QtCore.Qt.LeftButton:
            return False
        from . import sketch_snap
        grid_only = False
        if not self._sketch_tool_active():
            sketch_snap.hide_marker()
            # dragging a sketch point or curve: it locks to the grid too (Fusion)
            if t == QtCore.QEvent.MouseButtonPress:
                self.drag_snap = self._in_sketch() and self._presel_sketch_geometry()
                self.drag_from = _pos(ev)[0]
                return False
            if not getattr(self, "drag_snap", False) or not ev.buttons() & QtCore.Qt.LeftButton \
                    and t == QtCore.QEvent.MouseMove:
                return False
            if t == QtCore.QEvent.MouseButtonRelease:
                self.drag_snap = False
            # a click with a little jitter must not move the point to the grid
            if (_pos(ev)[0] - self.drag_from).manhattanLength() < 5:
                return False
            grid_only = True
        pos, gpos = _pos(ev)
        p = sketch_snap.snap(self.widget, pos.x(), pos.y(), ev.modifiers(), grid_only=grid_only)
        if grid_only:
            sketch_snap.hide_marker()
        if p is None or p == pos:
            return False
        new = _mouse_event(t, p, self.widget.mapToGlobal(p), btn, ev.buttons(), ev.modifiers())
        self.synth = True
        try:
            QtWidgets.QApplication.sendEvent(self.widget, new)
        finally:
            self.synth = False
        return True

    def _presel_sketch_geometry(self):
        try:
            pre = Gui.Selection.getPreselection()
            subs = list(getattr(pre, "SubElementNames", []) or [])
        except Exception:
            return False
        return any(s.split(".")[-1].startswith(("Vertex", "Edge")) for s in subs)

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
