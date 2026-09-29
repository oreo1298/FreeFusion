# SPDX-License-Identifier: LGPL-2.1-or-later
"""On-canvas drag arrows with a value box, like Fusion's command manipulators.

A command dialog adds an `Arrow` for each distance it edits. Dragging the arrow
changes the value along the arrow's axis (snapped to round steps); the value box
next to the arrow takes typed values and expressions, and Enter confirms the whole
command. Typing a number while the 3D view has focus goes to the value box too.
"""

import math

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from . import theme

ARROW_PX = 64        # arrow length on screen
HIT_PX = 10
DRAG_MIN_PX = 10     # snapping step of a drag, in pixels

_active = []
_timer = {"t": None}


def _coin():
    from pivy import coin
    return coin


def _viewer_widget():
    try:
        return Gui.ActiveDocument.ActiveView.graphicsView().viewport()
    except Exception:
        return None


class _Camera(object):
    """Projection of 3D points to viewport pixels for the active view."""

    def __init__(self, view, widget):
        coin = _coin()
        self.coin = coin
        self.w = max(1, widget.width())
        self.h = max(1, widget.height())
        cam = view.getCameraNode()
        self.vv = cam.getViewVolume(float(self.w) / self.h)
        rot = cam.orientation.getValue()
        self.right = App.Vector(*rot.multVec(coin.SbVec3f(1, 0, 0)).getValue())
        self.up = App.Vector(*rot.multVec(coin.SbVec3f(0, 1, 0)).getValue())

    def screen(self, p):
        from .sketch_snap import project_point
        nx, ny = project_point(self.vv, p)
        return QtCore.QPointF(nx * self.w, self.h - 1 - ny * self.h)

    def mm_per_px(self, p):
        a = self.screen(p)
        b = self.screen(p + self.right * 10.0)
        d = math.hypot(b.x() - a.x(), b.y() - a.y())
        return 10.0 / d if d > 1e-9 else 1.0


def _rotation_from_y(d):
    coin = _coin()
    return coin.SbRotation(coin.SbVec3f(0, 1, 0), coin.SbVec3f(d.x, d.y, d.z))


def _seg_dist(p, a, b):
    ax, ay, bx, by, px, py = a.x(), a.y(), b.x(), b.y(), p.x(), p.y()
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L < 1e-9 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(ax + t * dx - px, ay + t * dy - py)


class ValueBox(QtWidgets.QLineEdit):
    """Floating value input shown next to an arrow."""

    def __init__(self, arrow, parent):
        super(ValueBox, self).__init__(parent)
        self.arrow = arrow
        self.setObjectName("FFValueBox")
        t = theme.tokens()
        self.setStyleSheet(
            "QLineEdit#FFValueBox { background: %s; color: %s; border: 1px solid %s;"
            " border-radius: 2px; padding: 1px 4px; font-size: 12px; min-width: 72px; }"
            "QLineEdit#FFValueBox:focus { border: 1px solid %s; }"
            "QLineEdit#FFValueBox[invalid=\"true\"] { border: 1px solid %s; }"
            % (t["panel"], t["text"], t["border"], t["accent"], t["danger"]))
        self.setFixedWidth(96)

    def keyPressEvent(self, ev):
        k = ev.key()
        if k in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            if self.arrow.commit_text(self.text()):
                QtCore.QTimer.singleShot(0, self.arrow.confirm)
            return
        if k == QtCore.Qt.Key_Escape:
            from . import keys
            QtCore.QTimer.singleShot(0, keys.cancel_active_dialog)
            return
        if k == QtCore.Qt.Key_Tab:
            if self.isModified():
                self.arrow.commit_text(self.text())
            nxt = next_box(self.arrow)
            if nxt is not None:
                nxt.focus()
            return
        super(ValueBox, self).keyPressEvent(ev)

    def focusOutEvent(self, ev):
        try:
            if self.isModified():
                self.arrow.commit_text(self.text())
        except Exception:
            pass
        super(ValueBox, self).focusOutEvent(ev)


class Arrow(object):
    """A drag arrow at ``origin + direction * value * scale``.

    field: the dialog's ValueField this arrow edits (kept in sync both ways).
    on_change(): called (throttled) after the value changed by dragging/typing.
    """

    def __init__(self, origin, direction, field, on_change=None, scale=1.0, label="",
                 minimum=None, flip_with_sign=True):
        self.origin = App.Vector(origin)
        d = App.Vector(direction)
        self.direction = d.normalize() if d.Length > 1e-12 else App.Vector(0, 0, 1)
        self.field = field
        self.on_change = on_change
        self.scale = scale
        self.label = label
        self.minimum = minimum
        self.flip_with_sign = flip_with_sign
        self.hover = False
        self.drag = None
        self.node = None
        self.view = None
        self.widget = None
        self.box = None
        self._size = None
        self._pending = False
        self._build()
        try:
            field.changed.connect(self._field_changed)
        except Exception:
            pass

    # -- scene -------------------------------------------------------------
    def _build(self):
        coin = _coin()
        try:
            view = Gui.ActiveDocument.ActiveView
        except Exception:
            return
        self.view = view
        self.widget = _viewer_widget()
        root = coin.SoAnnotation() if hasattr(coin, "SoAnnotation") else coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        root.addChild(pick)
        self.xf = coin.SoTransform()
        root.addChild(self.xf)
        self.mat = coin.SoMaterial()
        root.addChild(self.mat)
        shaft = coin.SoSeparator()
        t = coin.SoTranslation()
        t.translation = (0, 0.36, 0)
        c = coin.SoCylinder()
        c.radius = 0.045
        c.height = 0.72
        shaft.addChild(t)
        shaft.addChild(c)
        root.addChild(shaft)
        head = coin.SoSeparator()
        t2 = coin.SoTranslation()
        t2.translation = (0, 0.86, 0)
        cone = coin.SoCone()
        cone.bottomRadius = 0.13
        cone.height = 0.28
        head.addChild(t2)
        head.addChild(cone)
        root.addChild(head)
        base = coin.SoSphere()
        base.radius = 0.07
        root.addChild(base)
        self.node = root
        try:
            view.getSceneGraph().addChild(root)
        except Exception:
            self.node = None
        self._color()
        parent = self.widget.parentWidget() if self.widget is not None else None
        if parent is not None:
            self.box = ValueBox(self, parent)
            self.box.setText(self.field.text())
            self.box.show()
        self.update()

    def _color(self):
        if self.node is None:
            return
        if self.hover or self.drag is not None:
            self.mat.diffuseColor = (0.20, 0.62, 1.0)
            self.mat.emissiveColor = (0.10, 0.30, 0.55)
        else:
            self.mat.diffuseColor = (0.16, 0.42, 0.78)
            self.mat.emissiveColor = (0.05, 0.16, 0.34)

    def value(self):
        v = self.field.value()
        return v if v is not None else 0.0

    def base_point(self):
        return self.origin + self.direction * (self.value() * self.scale)

    def axis(self):
        if self.flip_with_sign and self.value() < 0:
            return self.direction * -1
        return self.direction

    def update(self):
        """Place the arrow and value box; keeps the arrow a constant size on screen."""
        if self.view is None or self.widget is None:
            return
        try:
            cam = _Camera(self.view, self.widget)
        except Exception:
            return
        p = self.base_point()
        a = self.axis()
        size = ARROW_PX * cam.mm_per_px(p)
        if self.node is not None:
            key = (round(p.x, 6), round(p.y, 6), round(p.z, 6), round(a.x, 6), round(a.y, 6),
                   round(a.z, 6), round(size, 4))
            if key != self._size:
                self._size = key
                self.xf.translation = (p.x, p.y, p.z)
                self.xf.rotation = _rotation_from_y(a)
                self.xf.scaleFactor = (size, size, size)
        if self.box is not None:
            tip = cam.screen(p + a * size)
            mid = cam.screen(p + a * (size * 0.5))
            local = self.widget.mapTo(self.box.parentWidget(), QtCore.QPoint(int(tip.x()), int(tip.y())))
            dx = 14 if tip.x() >= mid.x() else -14 - self.box.width()
            x = local.x() + dx
            y = local.y() - self.box.height() // 2
            pw = self.box.parentWidget()
            x = max(4, min(pw.width() - self.box.width() - 4, x))
            y = max(4, min(pw.height() - self.box.height() - 4, y))
            if self.box.pos() != QtCore.QPoint(x, y):
                self.box.move(x, y)

    def screen_segment(self):
        cam = _Camera(self.view, self.widget)
        p = self.base_point()
        size = ARROW_PX * cam.mm_per_px(p)
        return cam, cam.screen(p), cam.screen(p + self.axis() * size)

    def hit(self, pos):
        try:
            _, a, b = self.screen_segment()
        except Exception:
            return False
        return _seg_dist(QtCore.QPointF(pos), a, b) <= HIT_PX

    # -- values ------------------------------------------------------------
    def _field_changed(self):
        # follow the dialog unless the user is typing in the box right now
        if self.box is not None and not self.box.isModified():
            self.box.setText(self.field.text())
            if self.box.hasFocus():
                self.box.selectAll()
        self.update()

    def set_value(self, v):
        if self.minimum is not None:
            v = max(self.minimum, v)
        self.field.set_value(v)
        if self.box is not None:
            self.box.setText(self.field.text())
        self._changed()

    def _changed(self):
        self.update()
        if self._pending:
            return
        self._pending = True
        QtCore.QTimer.singleShot(30, self._flush)

    def _flush(self):
        self._pending = False
        try:
            self.field.changed.emit()
        except RuntimeError:
            return
        if self.on_change is not None:
            self.on_change()
        self.update()

    def commit_text(self, text):
        """Apply typed text (units/expressions allowed). Returns False when invalid."""
        if self.box is not None:
            self.box.setModified(False)
        if text.strip() == self.field.text().strip():
            return True
        self.field.setText(text)
        self.field._commit()
        ok = "border-color" not in (self.field.styleSheet() or "")
        if self.box is not None:
            self.box.setProperty("invalid", not ok)
            self.box.setToolTip("" if ok else "Not a valid value")
            self.box.style().unpolish(self.box)
            self.box.style().polish(self.box)
        self.update()
        return ok

    def confirm(self):
        from . import keys
        keys.accept_active_dialog()

    def focus(self):
        if self.box is not None:
            self.box.setFocus(QtCore.Qt.OtherFocusReason)
            self.box.selectAll()

    # -- mouse -------------------------------------------------------------
    def press(self, pos):
        cam, a, b = self.screen_segment()
        p0 = self.base_point()
        s0 = cam.screen(p0)
        s1 = cam.screen(p0 + self.direction * (10.0 * self.scale))
        axis = QtCore.QPointF(s1.x() - s0.x(), s1.y() - s0.y())
        px_per_unit = math.hypot(axis.x(), axis.y()) / 10.0
        self.drag = {"pos": QtCore.QPointF(pos), "v0": self.value(), "axis": axis,
                     "ppu": px_per_unit, "mm_px": cam.mm_per_px(p0)}
        self._color()

    def move(self, pos):
        d = self.drag
        ppu = d["ppu"]
        dx = pos.x() - d["pos"].x()
        dy = pos.y() - d["pos"].y()
        if ppu > 0.15:
            ax = d["axis"]
            n = math.hypot(ax.x(), ax.y())
            delta = (dx * ax.x() + dy * ax.y()) / n / ppu
            unit_px = ppu
        else:
            # looking straight down the axis: drag up/down instead
            delta = -dy * d["mm_px"] / max(self.scale, 1e-9)
            unit_px = 1.0 / max(d["mm_px"], 1e-9)
        from .sketch_snap import nice_step
        step = nice_step(1.0 / unit_px, DRAG_MIN_PX)
        v = round((d["v0"] + delta) / step) * step
        if abs(v - self.value()) > 1e-12:
            self.set_value(v)

    def release(self):
        self.drag = None
        self._color()
        self.focus()

    def remove(self):
        try:
            self.field.changed.disconnect(self._field_changed)
        except Exception:
            pass
        if self.node is not None:
            try:
                self.view.getSceneGraph().removeChild(self.node)
            except Exception:
                pass
            self.node = None
        if self.box is not None:
            try:
                self.box.hide()
                self.box.deleteLater()
            except RuntimeError:
                pass
            self.box = None


# ---------------------------------------------------------------------------
# registry


def add(arrow):
    _active.append(arrow)
    _ensure_timer()
    return arrow


def remove(arrow):
    if arrow in _active:
        _active.remove(arrow)
    arrow.remove()


def clear():
    for a in list(_active):
        remove(a)


def arrows():
    return list(_active)


def active_box():
    for a in _active:
        if a.box is not None and a.box.isVisible():
            return a
    return None


def next_box(arrow):
    if arrow not in _active or len(_active) < 2:
        return None
    return _active[(_active.index(arrow) + 1) % len(_active)]


def _ensure_timer():
    if _timer["t"] is None:
        t = QtCore.QTimer()
        t.setInterval(60)
        t.timeout.connect(_tick)
        _timer["t"] = t
    if not _timer["t"].isActive():
        _timer["t"].start()


def _tick():
    if not _active:
        _timer["t"].stop()
        return
    if not Gui.Control.activeDialog():
        clear()
        return
    for a in list(_active):
        try:
            if a.drag is None:
                a.update()
        except Exception:
            remove(a)


def handle_event(widget, ev, t):
    """Called by the viewport filter; returns True when an arrow used the event."""
    if not _active:
        return False
    if t == QtCore.QEvent.KeyPress:
        return False
    pos = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()
    mine = [a for a in _active if a.widget is widget]
    if not mine:
        return False
    dragging = [a for a in mine if a.drag is not None]
    if dragging:
        a = dragging[0]
        if t == QtCore.QEvent.MouseMove:
            a.move(pos)
            return True
        if t == QtCore.QEvent.MouseButtonRelease and ev.button() == QtCore.Qt.LeftButton:
            a.release()
            return True
        return True
    if t == QtCore.QEvent.MouseMove and not ev.buttons():
        hit = None
        for a in mine:
            h = hit is None and a.hit(pos)
            if h:
                hit = a
            if h != a.hover:
                a.hover = h
                a._color()
        if hit is not None:
            widget.setCursor(QtCore.Qt.PointingHandCursor)
        elif widget.cursor().shape() == QtCore.Qt.PointingHandCursor:
            widget.unsetCursor()
        return False
    if t == QtCore.QEvent.MouseButtonPress and ev.button() == QtCore.Qt.LeftButton:
        for a in mine:
            if a.hit(pos):
                a.hover = True
                a.press(pos)
                return True
    if t == QtCore.QEvent.MouseButtonDblClick and ev.button() == QtCore.Qt.LeftButton:
        return any(a.hit(pos) for a in mine)
    return False


def type_into_box(text):
    """Keys typed while the 3D view has focus: start editing the value box."""
    a = active_box()
    if a is None:
        return False
    a.box.setFocus(QtCore.Qt.OtherFocusReason)
    a.box.setText(text)
    a.box.setModified(True)
    return True
