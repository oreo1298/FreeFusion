# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion 360 marking menu: 8 radial commands + a context list below.

Right-click opens it; right-drag in a direction (a "flick") runs that command
immediately. The widget uses a mask rather than translucency so it also works on
window managers without a compositor.
"""

import math

import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from ..commands import base
from . import layout, theme

RADIUS = 110
SIZE = 2 * RADIUS + 190


def _label(name):
    if name == "FF_Repeat":
        last = base.last_command()
        spec = base.spec(last) if last else None
        return "Repeat %s" % spec.menu if spec else "Repeat"
    spec = base.spec(name)
    return spec.menu if spec else name


def _icon(name):
    if name == "FF_Repeat":
        last = base.last_command()
        spec = base.spec(last) if last else None
        return theme.icon(spec.icon if spec else "ComputeAll")
    spec = base.spec(name)
    return theme.icon(spec.icon) if spec else QtGui.QIcon()


def _active(name):
    try:
        cmd = Gui.Command.get(name)
        return cmd.isActive() if cmd is not None and hasattr(cmd, "isActive") else True
    except Exception:
        return True


class Pill(QtWidgets.QToolButton):
    def __init__(self, name, parent):
        super(Pill, self).__init__(parent)
        self.name = name
        self.setText(_label(name))
        self.setIcon(_icon(name))
        self.setIconSize(QtCore.QSize(18, 18))
        self.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.setEnabled(_active(name))
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setProperty("hot", False)
        t = theme.tokens()
        self.setStyleSheet(
            "QToolButton { background: %(panel)s; border: 1px solid %(border_strong)s; border-radius: 13px;"
            " padding: 3px 10px 3px 6px; color: %(text)s; }"
            "QToolButton:hover, QToolButton[hot=\"true\"] { background: %(accent)s; color: white;"
            " border-color: %(accent)s; }"
            "QToolButton:disabled { color: %(text_dim)s; }" % t)
        self.adjustSize()

    def set_hot(self, on):
        if self.property("hot") != on:
            self.setProperty("hot", on)
            self.style().unpolish(self)
            self.style().polish(self)


class MarkingMenu(QtWidgets.QWidget):
    def __init__(self, gpos, gesture, native=None):
        super(MarkingMenu, self).__init__(None, QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.setObjectName("FFMarkingMenu")
        self.gesture = gesture
        self.native = native
        self.hot = None
        sketch = base.in_sketch()
        ring = layout.MARKING_SKETCH if sketch else layout.MARKING_MODEL
        listing = layout.MARKING_SKETCH_LIST if sketch else layout.MARKING_MODEL_LIST
        self.pills = []
        for name in ring:
            self.pills.append(Pill(name, self))
        # context list
        self.listframe = QtWidgets.QFrame(self)
        t = theme.tokens()
        self.listframe.setStyleSheet(
            "QFrame { background: %(panel)s; border: 1px solid %(border_strong)s; border-radius: 4px; }"
            "QToolButton { border: none; border-radius: 0; padding: 4px 10px; text-align: left; color: %(text)s; }"
            "QToolButton:hover { background: %(accent)s; color: white; }"
            "QToolButton:disabled { color: %(text_dim)s; }" % t)
        lv = QtWidgets.QVBoxLayout(self.listframe)
        lv.setContentsMargins(0, 4, 0, 4)
        lv.setSpacing(0)
        for name in listing:
            if name == "-":
                line = QtWidgets.QFrame()
                line.setFixedHeight(1)
                line.setStyleSheet("background: %s; border: none;" % t["border"])
                lv.addWidget(line)
                continue
            b = QtWidgets.QToolButton()
            b.setText(_label(name))
            b.setIcon(_icon(name))
            b.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            b.setEnabled(_active(name))
            b.clicked.connect(lambda *_, n=name: self._run(n))
            lv.addWidget(b)
        if native is not None:
            b = QtWidgets.QToolButton()
            b.setText("More (FreeCAD menu)...")
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            b.clicked.connect(self._native)
            lv.addWidget(b)
        self.listframe.setFixedWidth(210)
        self.listframe.adjustSize()
        h = SIZE + self.listframe.height()
        self.resize(SIZE, h)
        self.center = QtCore.QPoint(SIZE // 2, SIZE // 2 - 30)
        for i, p in enumerate(self.pills):
            p.clicked.connect(lambda *_, n=p.name: self._run(n))
            ang = math.radians(-90 + 45 * i)
            cx = self.center.x() + RADIUS * math.cos(ang)
            cy = self.center.y() + RADIUS * 0.82 * math.sin(ang)
            w, hh = p.width(), p.height()
            if abs(math.cos(ang)) < 0.2:
                x = cx - w / 2
            elif math.cos(ang) > 0:
                x = cx - 14
            else:
                x = cx - w + 14
            p.move(int(x), int(cy - hh / 2))
        self.listframe.move(self.center.x() - 105, self.center.y() + int(RADIUS * 0.82) + 30)
        # mask: pills + list + center disk
        region = QtGui.QRegion(QtCore.QRect(self.center.x() - 16, self.center.y() - 16, 32, 32),
                               QtGui.QRegion.Ellipse)
        for p in self.pills:
            region = region.united(QtGui.QRegion(p.geometry().adjusted(-1, -1, 1, 1)))
        region = region.united(QtGui.QRegion(self.listframe.geometry()))
        self.setMask(region)
        self.move(gpos - self.center)
        self.setMouseTracking(True)

    def paintEvent(self, ev):
        t = theme.tokens()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.setBrush(QtGui.QColor(t["panel"]))
        p.setPen(QtGui.QPen(QtGui.QColor(t["border_strong"]), 1.5))
        p.drawEllipse(self.center, 14, 14)
        if self.hot is not None:
            ang = -90 + 45 * self.hot
            p.setBrush(QtGui.QColor(t["accent"]))
            p.setPen(QtCore.Qt.NoPen)
            p.drawPie(QtCore.QRectF(self.center.x() - 14, self.center.y() - 14, 28, 28),
                      int((-ang - 22.5) * 16), int(45 * 16))
        p.end()

    def _sector(self, gpos):
        d = self.mapFromGlobal(gpos) - self.center
        if d.x() * d.x() + d.y() * d.y() < 20 * 20:
            return None
        ang = math.degrees(math.atan2(d.y(), d.x())) + 90
        return int(round(ang / 45.0)) % 8

    def track(self, gpos):
        s = self._sector(gpos)
        if s != self.hot:
            self.hot = s
            for i, p in enumerate(self.pills):
                p.set_hot(i == s)
            self.update()

    def release(self, gpos):
        s = self._sector(gpos)
        self.close()
        if s is not None and s < len(self.pills) and self.pills[s].isEnabled():
            self._run(self.pills[s].name)

    def mouseMoveEvent(self, ev):
        g = ev.globalPosition().toPoint() if hasattr(ev, "globalPosition") else ev.globalPos()
        if self.gesture or ev.buttons() & QtCore.Qt.RightButton:
            self.track(g)
        super(MarkingMenu, self).mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        g = ev.globalPosition().toPoint() if hasattr(ev, "globalPosition") else ev.globalPos()
        if ev.button() == QtCore.Qt.RightButton and self.gesture:
            self.release(g)
            return
        super(MarkingMenu, self).mouseReleaseEvent(ev)

    def mousePressEvent(self, ev):
        if not self.mask().contains(ev.pos()):
            self.close()
            return
        super(MarkingMenu, self).mousePressEvent(ev)

    def keyPressEvent(self, ev):
        if ev.key() == QtCore.Qt.Key_Escape:
            self.close()
            return
        super(MarkingMenu, self).keyPressEvent(ev)

    def _run(self, name):
        self.close()
        QtCore.QTimer.singleShot(0, lambda: base.run(name))

    def _native(self):
        gpos = self.mapToGlobal(self.center)
        self.close()
        if self.native is not None:
            QtCore.QTimer.singleShot(0, lambda: self.native(gpos))


_current = {"menu": None}


def show(gpos, gesture=False, native=None):
    m = MarkingMenu(gpos, gesture, native)
    _current["menu"] = m
    m.show()
    return m
