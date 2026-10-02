# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion's orbit and canvas selection, on top of FreeCAD's navigation.

Orbit (Shift + middle drag) turns the view around a pivot shown as a green dot: the
center of the design, or a point you picked with Shift + middle click on the model.
FreeCAD's own styles orbit around the point under the cursor instead.

Selection: dragging on empty canvas draws a selection box. Left to right selects what
is completely inside (blue box), right to left also what it touches (green, dashed).
Shift adds to the selection, Ctrl toggles, a plain click on empty canvas clears it.
Shift + click on a face/edge/body adds it (FreeCAD would replace the selection).
"""


import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from .. import params

DEG_PER_PX = 0.35
DRAG_PX = 4
_state = {"pivot": {}, "orbit": None, "band": None, "dot": None}


def _view():
    try:
        return Gui.ActiveDocument.ActiveView
    except Exception:
        return None


def _coin():
    from pivy import coin
    return coin


def _pick(view, widget, pos):
    """FreeCAD's pick info under a widget pixel (dict) or None."""
    try:
        dpr = widget.devicePixelRatioF() if hasattr(widget, "devicePixelRatioF") else 1.0
        x = int(pos.x() * dpr)
        y = int((widget.height() - 1 - pos.y()) * dpr)
        return view.getObjectInfo((x, y))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# orbit


def design_center(doc):
    from .viewport import _design_bbox
    bb = _design_bbox(doc)
    return bb.Center if bb is not None else App.Vector(0, 0, 0)


def pivot(doc):
    p = _state["pivot"].get(doc.Name)
    return p if p is not None else design_center(doc)


def reset_pivot(doc=None):
    if doc is None:
        _state["pivot"].clear()
    else:
        _state["pivot"].pop(doc.Name, None)


def _show_dot(view, p):
    coin = _coin()
    _hide_dot()
    root = coin.SoAnnotation() if hasattr(coin, "SoAnnotation") else coin.SoSeparator()
    pick = coin.SoPickStyle()
    pick.style = coin.SoPickStyle.UNPICKABLE
    col = coin.SoBaseColor()
    col.rgb = (0.18, 0.75, 0.25)
    co = coin.SoCoordinate3()
    co.point.setValues(0, 1, [(p.x, p.y, p.z)])
    m = coin.SoMarkerSet()
    m.markerIndex = coin.SoMarkerSet.CIRCLE_FILLED_9_9
    for n in (pick, col, co, m):
        root.addChild(n)
    view.getSceneGraph().addChild(root)
    _state["dot"] = (view, root)


def _hide_dot():
    d = _state["dot"]
    _state["dot"] = None
    if d is not None:
        try:
            d[0].getSceneGraph().removeChild(d[1])
        except Exception:
            pass


def _rotate(view, center, dx, dy):
    coin = _coin()
    cam = view.getCameraNode()
    q = cam.orientation.getValue().getValue()
    rot = App.Rotation(q[0], q[1], q[2], q[3])
    pos = App.Vector(*cam.position.getValue().getValue())
    right = rot.multVec(App.Vector(1, 0, 0))
    yaw = App.Rotation(App.Vector(0, 0, 1), -dx * DEG_PER_PX)
    pitch = App.Rotation(right, -dy * DEG_PER_PX)
    delta = yaw.multiply(pitch)
    new_rot = delta.multiply(rot)
    # do not roll over the top or the bottom
    view_dir = new_rot.multVec(App.Vector(0, 0, -1))
    if abs(view_dir.z) > 0.9995:
        delta = yaw
        new_rot = delta.multiply(rot)
    new_pos = center + delta.multVec(pos - center)
    nq = new_rot.Q
    cam.orientation.setValue(coin.SbRotation(nq[0], nq[1], nq[2], nq[3]))
    cam.position.setValue(new_pos.x, new_pos.y, new_pos.z)


def handle_orbit(widget, ev, t, pos):
    """Shift + middle button. Returns True when the event was used."""
    if params.get_string("OrbitPivot", "design") != "design":
        return False
    o = _state["orbit"]
    view = _view()
    if view is None:
        return False
    if t == QtCore.QEvent.MouseButtonPress and ev.button() == QtCore.Qt.MiddleButton \
            and ev.modifiers() & QtCore.Qt.ShiftModifier:
        doc = Gui.ActiveDocument.Document
        _state["orbit"] = {"start": QtCore.QPoint(pos), "last": QtCore.QPoint(pos), "moved": False,
                           "center": pivot(doc), "doc": doc}
        return True
    if o is None:
        return False
    if t == QtCore.QEvent.MouseMove:
        if not ev.buttons() & QtCore.Qt.MiddleButton:
            _end_orbit()
            return False
        if not o["moved"] and (pos - o["start"]).manhattanLength() < DRAG_PX:
            return True
        if not o["moved"]:
            o["moved"] = True
            _show_dot(view, o["center"])
        d = pos - o["last"]
        o["last"] = QtCore.QPoint(pos)
        _rotate(view, o["center"], d.x(), d.y())
        return True
    if t == QtCore.QEvent.MouseButtonRelease and ev.button() == QtCore.Qt.MiddleButton:
        if not o["moved"]:
            # Shift + middle click on the model: new orbit center there
            info = _pick(view, widget, pos)
            if info and "x" in info:
                p = App.Vector(info["x"], info["y"], info["z"])
                _state["pivot"][o["doc"].Name] = p
                _show_dot(view, p)
                QtCore.QTimer.singleShot(700, _hide_dot)
        _end_orbit()
        return True
    if t == QtCore.QEvent.MouseButtonDblClick and ev.button() == QtCore.Qt.MiddleButton:
        return False
    return o is not None


def _end_orbit():
    o = _state["orbit"]
    _state["orbit"] = None
    if o is not None and o["moved"]:
        _hide_dot()


# ---------------------------------------------------------------------------
# selection box


class Band(QtWidgets.QWidget):
    def __init__(self, parent):
        super(Band, self).__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.crossing = False
        self.rect_ = QtCore.QRect()

    def set_rect(self, a, b):
        self.crossing = b.x() < a.x()
        r = QtCore.QRect(a, b).normalized()
        self.rect_ = r
        self.setGeometry(r.adjusted(-1, -1, 2, 2))
        self.update()

    def paintEvent(self, ev):
        p = QtGui.QPainter(self)
        r = QtCore.QRect(1, 1, self.rect_.width(), self.rect_.height())
        if self.crossing:
            fill, line = QtGui.QColor(47, 158, 68, 40), QtGui.QColor(47, 158, 68)
            pen = QtGui.QPen(line, 1, QtCore.Qt.DashLine)
        else:
            fill, line = QtGui.QColor(6, 150, 215, 40), QtGui.QColor(6, 150, 215)
            pen = QtGui.QPen(line, 1)
        p.fillRect(r, fill)
        p.setPen(pen)
        p.drawRect(r)
        p.end()


def _candidates(doc):
    from .. import design as D
    out = []
    for b in D.design_bodies(doc, visible_only=True):
        out.append(b)
    for o in doc.Objects:
        try:
            if D.is_sketch(o) and o.ViewObject.Visibility and o not in out:
                out.append(o)
        except Exception:
            continue
    return out


def _sample_points(obj, limit=600):
    try:
        shape = obj.Shape
    except Exception:
        return []
    if shape.isNull():
        return []
    try:
        to_global = obj.getGlobalPlacement().multiply(obj.Placement.inverse())
    except Exception:
        to_global = App.Placement()
    pts = [v.Point for v in shape.Vertexes[:limit]]
    for e in shape.Edges[:limit // 4]:
        try:
            pts += e.discretize(Number=6)
        except Exception:
            continue
    return [to_global.multVec(p) for p in pts]


def objects_in_rect(view, widget, rect, crossing):
    from .manipulator import _Camera
    doc = Gui.ActiveDocument.Document
    cam = _Camera(view, widget)
    rectf = QtCore.QRectF(rect)
    chosen = []
    for obj in _candidates(doc):
        pts = _sample_points(obj)
        if not pts:
            continue
        inside = [rectf.contains(cam.screen(p)) for p in pts]
        if (crossing and any(inside)) or (not crossing and all(inside)):
            chosen.append(obj)
    if crossing:
        # a box drawn completely inside a face still crosses that body
        from .. import design as D
        from . import widgets as W
        for pt in (rect.center(), rect.topLeft(), rect.bottomRight(), rect.topRight(), rect.bottomLeft()):
            info = _pick(view, widget, pt)
            if not info or "Object" not in info:
                continue
            parent = info.get("ParentObject")
            if parent is not None and info.get("SubName"):
                pname = parent if isinstance(parent, str) else parent.Name
                leaf, _ = W.resolve(doc.Name, pname, info["SubName"])
            else:
                leaf = doc.getObject(info["Object"]) if isinstance(info["Object"], str) else info["Object"]
            body = D.body_of(leaf) if leaf is not None else None
            target = body or leaf
            if target is not None and target in _candidates(doc) and target not in chosen:
                chosen.append(target)
    return chosen


def handle_select(widget, ev, t, pos, in_sketch):
    """Left button on empty canvas: selection box. Returns True when the event was used."""
    b = _state["band"]
    if t == QtCore.QEvent.MouseButtonPress and ev.button() == QtCore.Qt.LeftButton:
        if in_sketch or ev.buttons() & ~QtCore.Qt.LeftButton:
            return False
        view = _view()
        if view is None:
            return False
        mods = ev.modifiers()
        if mods & QtCore.Qt.ShiftModifier and not mods & QtCore.Qt.ControlModifier:
            # Fusion: Shift + click adds to the selection
            pre = Gui.Selection.getPreselection()
            if getattr(pre, "ObjectName", ""):
                subs = list(getattr(pre, "SubElementNames", []) or [""])
                for s in subs:
                    Gui.Selection.addSelection(pre.DocumentName, pre.ObjectName, s)
                _state["band"] = {"start": QtCore.QPoint(pos), "widget": None, "shift_click": True}
                return True
        info = _pick(view, widget, pos)
        if info:
            return False
        _state["band"] = {"start": QtCore.QPoint(pos), "widget": None, "mods": mods}
        return True
    if b is None:
        return False
    if b.get("shift_click"):
        if t == QtCore.QEvent.MouseButtonRelease and ev.button() == QtCore.Qt.LeftButton:
            _state["band"] = None
        return True
    if t == QtCore.QEvent.MouseMove:
        if not ev.buttons() & QtCore.Qt.LeftButton:
            _cancel_band()
            return False
        if b["widget"] is None and (pos - b["start"]).manhattanLength() >= DRAG_PX:
            parent = widget.parentWidget() or widget
            b["widget"] = Band(parent)
            b["offset"] = widget.mapTo(parent, QtCore.QPoint(0, 0))
            b["widget"].show()
        if b["widget"] is not None:
            off = b["offset"]
            b["widget"].set_rect(b["start"] + off, pos + off)
        return True
    if t == QtCore.QEvent.MouseButtonRelease and ev.button() == QtCore.Qt.LeftButton:
        _state["band"] = None
        mods = b.get("mods", QtCore.Qt.NoModifier)
        add = bool(mods & QtCore.Qt.ShiftModifier)
        toggle = bool(mods & QtCore.Qt.ControlModifier)
        if b["widget"] is None:
            if not add and not toggle:
                Gui.Selection.clearSelection()
            return True
        crossing = b["widget"].crossing
        rect = QtCore.QRect(b["start"], pos).normalized()
        b["widget"].hide()
        b["widget"].deleteLater()
        try:
            objs = objects_in_rect(_view(), widget, rect, crossing)
        except Exception as e:
            App.Console.PrintLog("FreeFusion window select: %s\n" % e)
            objs = []
        if not add and not toggle:
            Gui.Selection.clearSelection()
        for o in objs:
            try:
                if toggle and Gui.Selection.isSelected(o):
                    Gui.Selection.removeSelection(o)
                else:
                    Gui.Selection.addSelection(o)
            except Exception:
                continue
        return True
    return True


def _cancel_band():
    b = _state["band"]
    _state["band"] = None
    if b and b.get("widget") is not None:
        try:
            b["widget"].hide()
            b["widget"].deleteLater()
        except RuntimeError:
            pass
