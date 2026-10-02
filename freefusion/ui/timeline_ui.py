# SPDX-License-Identifier: LGPL-2.1-or-later
"""Timeline (design history) strip and navigation bar at the bottom of the canvas."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from .. import design as D
from .. import timeline as T
from . import theme

CELL = 28
ICONS = {
    "Sketch": "CreateSketch", "Plane": "OffsetPlane", "Axis": "AxisTwoPoints", "Point": "PointVertex",
    "Component": "NewComponent", "Split": "SplitBody", "Generic": "Generic",
}


def item_icon(kind):
    return theme.icon(ICONS.get(kind, kind))


class TimelineStrip(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(TimelineStrip, self).__init__(parent)
        self.setMouseTracking(True)
        self.items = []
        self.marker = None
        self.hover = -1
        self.selected = set()
        self.dragging = False
        self.drag_pos = None
        self.setMinimumHeight(CELL + 10)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        self._icons = {}

    # model --------------------------------------------------------------------
    def set_items(self, items, marker):
        self.items = items
        self.marker = marker
        self.setMinimumWidth(len(items) * CELL + 40)
        self.updateGeometry()
        self.update()

    def marker_index(self):
        return len(self.items) if self.marker is None else self.marker

    def _x(self, i):
        return 8 + i * CELL

    def _index_at(self, x):
        i = int((x - 8) // CELL)
        return i if 0 <= i < len(self.items) else -1

    def _marker_x(self, idx=None):
        idx = self.marker_index() if idx is None else idx
        return self._x(idx) - 1

    def sizeHint(self):
        return QtCore.QSize(len(self.items) * CELL + 40, CELL + 10)

    # painting -----------------------------------------------------------------
    def _icon(self, kind):
        if kind not in self._icons:
            self._icons[kind] = item_icon(kind).pixmap(20, 20)
        return self._icons[kind]

    def paintEvent(self, ev):
        t = theme.tokens()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        y = 5
        mark = self.drag_pos if self.dragging and self.drag_pos is not None else self.marker_index()
        for i, it in enumerate(self.items):
            x = self._x(i)
            rect = QtCore.QRectF(x + 1, y, CELL - 2, CELL - 2)
            rolled = i >= mark
            if it.key in self.selected:
                p.setBrush(QtGui.QColor(t["accent_soft"]))
                p.setPen(QtGui.QPen(QtGui.QColor(t["accent"]), 1.2))
            elif i == self.hover:
                p.setBrush(QtGui.QColor(t["hover"]))
                p.setPen(QtGui.QPen(QtGui.QColor(t["border_strong"]), 1))
            else:
                p.setBrush(QtGui.QColor(t["panel"]))
                p.setPen(QtGui.QPen(QtGui.QColor(t["border"]), 1))
            p.drawRoundedRect(rect, 3, 3)
            p.setOpacity(0.3 if rolled else 1.0)
            p.drawPixmap(int(x + (CELL - 20) / 2), int(y + (CELL - 2 - 20) / 2), self._icon(it.kind))
            p.setOpacity(1.0)
            if it.suppressed:
                p.setPen(QtGui.QPen(QtGui.QColor(t["danger"]), 1.6))
                p.drawLine(QtCore.QPointF(x + 4, y + CELL - 6), QtCore.QPointF(x + CELL - 5, y + 3))
            if not rolled and not it.suppressed and not self._valid(it):
                p.setBrush(QtGui.QColor(t["danger"]))
                p.setPen(QtCore.Qt.NoPen)
                p.drawEllipse(QtCore.QPointF(x + CELL - 6, y + 5), 3.5, 3.5)
        # history marker
        mx = self._marker_x(mark)
        col = QtGui.QColor(t["accent"])
        p.setPen(QtGui.QPen(col, 3))
        p.drawLine(QtCore.QPointF(mx, 2), QtCore.QPointF(mx, CELL + 6))
        p.setBrush(col)
        p.setPen(QtCore.Qt.NoPen)
        p.drawRoundedRect(QtCore.QRectF(mx - 4, 0, 8, 7), 2, 2)
        p.end()

    def _valid(self, it):
        for o in it.objects:
            try:
                if "Invalid" in o.State or "Error" in o.State:
                    return False
            except Exception:
                pass
        return True

    # interaction ----------------------------------------------------------------
    def mouseMoveEvent(self, ev):
        x = ev.position().x() if hasattr(ev, "position") else ev.x()
        if self.dragging:
            self.drag_pos = max(0, min(len(self.items), int(round((x - 8) / float(CELL)))))
            self.update()
            return
        near_marker = abs(x - self._marker_x()) < 6
        self.setCursor(QtCore.Qt.SizeHorCursor if near_marker else QtCore.Qt.ArrowCursor)
        i = self._index_at(x)
        if i != self.hover:
            self.hover = i
            if i >= 0:
                it = self.items[i]
                self.setToolTip("<b>%s</b><br>%s%s" % (it.label, it.kind,
                                                        " (suppressed)" if it.suppressed else ""))
            else:
                self.setToolTip("")
            self.update()

    def leaveEvent(self, ev):
        self.hover = -1
        self.update()

    def mousePressEvent(self, ev):
        x = ev.position().x() if hasattr(ev, "position") else ev.x()
        if ev.button() == QtCore.Qt.LeftButton and abs(x - self._marker_x()) < 6:
            self.dragging = True
            self.drag_pos = self.marker_index()
            return
        i = self._index_at(x)
        if ev.button() == QtCore.Qt.LeftButton:
            if i < 0:
                self.selected.clear()
                Gui.Selection.clearSelection()
            else:
                key = self.items[i].key
                if ev.modifiers() & QtCore.Qt.ControlModifier:
                    self.selected ^= {key}
                else:
                    self.selected = {key}
                self._select_in_3d()
            self.update()
        elif ev.button() == QtCore.Qt.RightButton and i >= 0:
            if self.items[i].key not in self.selected:
                self.selected = {self.items[i].key}
                self.update()
            self._context_menu(i, ev.globalPosition().toPoint() if hasattr(ev, "globalPosition")
                               else ev.globalPos())

    def mouseReleaseEvent(self, ev):
        if self.dragging:
            self.dragging = False
            pos = self.drag_pos
            self.drag_pos = None
            if pos is not None and pos != self.marker_index():
                self.parent_bar().roll_to(pos)
            self.update()

    def mouseDoubleClickEvent(self, ev):
        x = ev.position().x() if hasattr(ev, "position") else ev.x()
        i = self._index_at(x)
        if i >= 0:
            from ..commands.definitions import edit_feature
            edit_feature(self.items[i].primary)

    def parent_bar(self):
        w = self.parent()
        while w is not None and not isinstance(w, TimelineBar):
            w = w.parent()
        return w

    def _select_in_3d(self):
        Gui.Selection.clearSelection()
        for it in self.items:
            if it.key in self.selected:
                prim = it.primary
                try:
                    if D.is_pd_feature(prim):
                        Gui.Selection.addSelection(prim)
                    elif prim is not None:
                        Gui.Selection.addSelection(prim)
                except Exception:
                    pass

    def _context_menu(self, i, gpos):
        it = self.items[i]
        doc = App.ActiveDocument
        m = QtWidgets.QMenu(self)
        from ..commands.definitions import edit_feature
        m.addAction(theme.icon(ICONS.get(it.kind, it.kind)), "Edit Feature",
                    lambda: edit_feature(it.primary))
        prof = D.data(it.primary).get("profiles") if it.primary is not None else None
        if prof:
            sk = doc.getObject(prof[0][0])
            if sk is not None and D.is_sketch(sk):
                from . import sketching
                m.addAction(theme.icon("CreateSketch"), "Edit Profile Sketch", lambda: sketching.edit_sketch(sk))
        m.addSeparator()
        bar = self.parent_bar()
        m.addAction("Roll History Marker Here", lambda: bar.roll_to(i + 1))
        m.addAction("Roll History Marker Before", lambda: bar.roll_to(i))
        if any("Suppressed" in o.PropertiesList for o in it.objects):
            m.addAction("Unsuppress Features" if it.suppressed else "Suppress Features",
                        lambda: bar.suppress(it.key, not it.suppressed))
        m.addSeparator()
        m.addAction(theme.icon("Delete"), "Delete", lambda: bar.delete(it.key))
        m.addAction("Rename", lambda: bar.rename(it))
        m.addAction(theme.icon("Folder"), "Find in Browser",
                    lambda: __import__("freefusion.ui.browser", fromlist=["x"]).instance().reveal(
                        D.body_of(it.primary) or it.primary))
        m.exec_(gpos) if hasattr(m, "exec_") else m.exec(gpos)


class TimelineBar(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(TimelineBar, self).__init__(parent)
        self.setObjectName("FFTimeline")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(6, 2, 6, 2)
        h.setSpacing(1)
        for icon, tip, fn in (("TLStart", "Go to beginning", lambda: self.roll_to(0)),
                              ("TLBack", "Step back", lambda: self.step(-1)),
                              ("TLForward", "Step forward", lambda: self.step(1)),
                              ("TLEnd", "Go to end", lambda: self.roll_to(None))):
            b = QtWidgets.QToolButton()
            b.setIcon(theme.icon(icon))
            b.setIconSize(QtCore.QSize(14, 14))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.setFocusPolicy(QtCore.Qt.NoFocus)
            b.clicked.connect(fn)
            h.addWidget(b)
        self.strip = TimelineStrip()
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidget(self.strip)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(CELL + 22)
        self.scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        h.addWidget(self.scroll, 1)
        gear = QtWidgets.QToolButton()
        gear.setIcon(theme.icon("Settings"))
        gear.setIconSize(QtCore.QSize(16, 16))
        gear.setAutoRaise(True)
        gear.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        gm = QtWidgets.QMenu(gear)
        gm.addAction("Compute All", lambda: App.ActiveDocument and App.ActiveDocument.recompute(None, True, True))
        gm.addAction("Show Model Tree", lambda: __import__("freefusion.ui.docks", fromlist=["x"]).toggle("tree"))
        gear.setMenu(gm)
        h.addWidget(gear)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self.refresh)

    def schedule(self):
        self._timer.start()

    def refresh(self):
        doc = App.ActiveDocument
        if doc is None:
            self.strip.set_items([], None)
            return
        try:
            items = T.items(doc)
            mark = T.marker(doc)
        except Exception as e:
            App.Console.PrintLog("FreeFusion timeline: %s\n" % e)
            items, mark = [], None
        keys = set(i.key for i in items)
        self.strip.selected &= keys
        at_end = self.scroll.horizontalScrollBar().value() >= self.scroll.horizontalScrollBar().maximum() - 4
        self.strip.set_items(items, mark)
        if at_end:
            QtCore.QTimer.singleShot(0, lambda: self.scroll.horizontalScrollBar().setValue(
                self.scroll.horizontalScrollBar().maximum()))

    def roll_to(self, pos):
        doc = App.ActiveDocument
        if doc is None:
            return
        if Gui.ActiveDocument and Gui.ActiveDocument.getInEdit():
            Gui.ActiveDocument.resetEdit()
        T.roll_to(doc, pos)
        self.refresh()

    def step(self, delta):
        doc = App.ActiveDocument
        if doc is not None:
            T.step(doc, delta)
            self.refresh()

    def suppress(self, key, state):
        doc = App.ActiveDocument
        doc.openTransaction("Suppress")
        T.suppress_item(doc, key, state)
        doc.commitTransaction()
        self.refresh()

    def delete(self, key):
        doc = App.ActiveDocument
        doc.openTransaction("Delete Feature")
        T.delete_item(doc, key)
        doc.commitTransaction()
        self.refresh()

    def rename(self, it):
        text, ok = QtWidgets.QInputDialog.getText(self, "Rename", "Name:", text=it.label)
        if ok and text and it.primary is not None:
            it.primary.Document.openTransaction("Rename")
            it.primary.Label = text
            it.primary.Document.commitTransaction()
            self.refresh()


# ---------------------------------------------------------------------------
# navigation bar


class NavBar(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(NavBar, self).__init__(parent)
        self.setObjectName("FFNavBar")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(6, 1, 6, 1)
        h.setSpacing(1)
        from . import viewport
        self.mode_buttons = {}
        for mode, icon, tip in (("orbit", "Orbit", "Orbit (Shift + middle mouse)"),
                                ("pan", "Pan", "Pan (middle mouse)"),
                                ("zoom", "Zoom", "Zoom (mouse wheel)")):
            b = self._button(icon, tip)
            b.setCheckable(True)
            b.toggled.connect(lambda on, m=mode: viewport.set_nav_mode(m if on else None))
            self.mode_buttons[mode] = b
        self._button("LookAt", "Look At", lambda: Gui.runCommand("FF_LookAt", 0))
        self._button("Fit", "Fit (F6)", lambda: __import__("freefusion.ui.viewport", fromlist=["x"]).fit())
        self._button("Home", "Home view", lambda: __import__("freefusion.ui.viewport", fromlist=["x"]).home())
        self._sep()
        self._menu_button("DisplayMode", "Display Settings", self._display_menu)
        self._menu_button("Grid", "Grid and Snaps", self._grid_menu)
        self._menu_button("Viewports", "Viewports", self._viewport_menu)
        viewport.nav_mode_changed.append(self._mode_changed)

    def _mode_changed(self, mode):
        for m, b in self.mode_buttons.items():
            b.blockSignals(True)
            b.setChecked(m == mode)
            b.blockSignals(False)

    def _button(self, icon, tip, fn=None):
        b = QtWidgets.QToolButton()
        b.setIcon(theme.icon(icon))
        b.setIconSize(QtCore.QSize(18, 18))
        b.setToolTip(tip)
        b.setAutoRaise(True)
        b.setFocusPolicy(QtCore.Qt.NoFocus)
        if fn:
            b.clicked.connect(fn)
        self.layout().addWidget(b)
        return b

    def _sep(self):
        f = QtWidgets.QFrame()
        f.setFrameShape(QtWidgets.QFrame.VLine)
        f.setStyleSheet("color: %s;" % theme.tokens()["border"])
        self.layout().addWidget(f)

    def _menu_button(self, icon, tip, filler):
        b = self._button(icon, tip)
        b.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        m = QtWidgets.QMenu(b)
        m.aboutToShow.connect(lambda: (m.clear(), filler(m)))
        b.setMenu(m)
        b.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        return b

    def _display_menu(self, m):
        from . import viewport
        vs = m.addMenu("Visual Style")
        for label, mode in (("Shaded", "As Is"), ("Shaded with Hidden Edges", "Hidden line"),
                            ("Shaded without Edges", "No shading"), ("Wireframe", "Wireframe"),
                            ("Flat Lines", "Flat lines"), ("Points", "Points")):
            a = vs.addAction(label)
            a.triggered.connect(lambda *_, md=mode: viewport.set_draw_style(md))
        cam = m.addMenu("Camera")
        cam.addAction("Orthographic", lambda: Gui.runCommand("Std_OrthographicCamera", 0))
        cam.addAction("Perspective", lambda: Gui.runCommand("Std_PerspectiveCamera", 0))
        m.addSeparator()
        a = m.addAction("ViewCube")
        a.setCheckable(True)
        a.setChecked(App.ParamGet("User parameter:BaseApp/Preferences/View").GetBool("ShowNaviCube", True))
        a.toggled.connect(lambda on: App.ParamGet("User parameter:BaseApp/Preferences/View").SetBool(
            "ShowNaviCube", on))
        nav = m.addMenu("Navigation")
        for label, style in viewport.NAV_STYLES:
            a = nav.addAction(label)
            a.setCheckable(True)
            a.setChecked(viewport.current_nav_style() == style)
            a.triggered.connect(lambda *_, s=style: viewport.set_nav_style(s))
        m.addSeparator()
        m.addAction("Section Analysis", lambda: Gui.runCommand("FF_SectionAnalysis", 0))
        m.addAction("Toggle Dark Theme", lambda: Gui.runCommand("FF_ToggleTheme", 0))

    def _grid_menu(self, m):
        from . import viewport
        a = m.addAction("Layout Grid")
        a.setCheckable(True)
        a.setChecked(viewport.grid_visible())
        a.toggled.connect(viewport.set_grid_visible)
        if Gui.ActiveDocument and Gui.ActiveDocument.getInEdit():
            m.addSeparator()
            from . import sketch_snap
            for label, on, fn in (("Sketch Grid", sketch_snap.grid_shown(), sketch_snap.toggle_grid),
                                  ("Snap", sketch_snap.enabled(), sketch_snap.toggle_snap)):
                act = m.addAction(label)
                act.setCheckable(True)
                act.setChecked(on)
                act.triggered.connect(lambda *_, f=fn: f())

    def _viewport_menu(self, m):
        m.addAction("New Window", lambda: Gui.runCommand("Std_ViewCreate", 0))
        m.addAction("Full Screen", lambda: Gui.runCommand("Std_ViewFullscreen", 0))


class BottomPanel(QtWidgets.QWidget):
    """Navigation bar centered above the timeline (dock contents)."""

    def __init__(self, parent=None):
        super(BottomPanel, self).__init__(parent)
        self.setObjectName("FFTimelineDock")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 3, 0, 0)
        v.setSpacing(3)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        self.navbar = NavBar()
        row.addWidget(self.navbar)
        row.addStretch(1)
        v.addLayout(row)
        self.timeline = TimelineBar()
        v.addWidget(self.timeline)


_instance = {"w": None}


def create(parent=None):
    if _instance["w"] is None:
        _instance["w"] = BottomPanel(parent)
    return _instance["w"]


def instance():
    return _instance["w"]


def recreate():
    """Rebuild the bottom panel (after a theme change)."""
    old = _instance["w"]
    if old is None:
        return None
    dock = old.parent()
    while dock is not None and not isinstance(dock, QtWidgets.QDockWidget):
        dock = dock.parent()
    _instance["w"] = BottomPanel()
    if dock is not None:
        dock.setWidget(_instance["w"])
    old.deleteLater()
    _instance["w"].timeline.refresh()
    return _instance["w"]
