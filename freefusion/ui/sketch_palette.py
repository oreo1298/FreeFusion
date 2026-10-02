# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion's SKETCH PALETTE in place of FreeCAD's constraint and element lists.

While a sketch is open, the task panel keeps FreeCAD's tool options (the box that
appears for the running tool) and shows the palette below it: Construction, Look At,
Sketch Grid, Snap, Slice, Show Profile, the constraint status and FINISH SKETCH.
FreeCAD's lists can be brought back with "Constraint list".
"""

import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from .. import params
from . import theme

HIDDEN = ("SketcherGui::TaskSketcherConstraints", "SketcherGui::TaskSketcherElements",
          "SketcherGui::TaskSketcherMessages")
_state = {"palette": None}


def _task_panel():
    mw = Gui.getMainWindow()
    for w in mw.findChildren(QtWidgets.QWidget):
        try:
            if w.metaObject().className() == "Gui::TaskView::TaskPanel" and w.isVisible():
                return w
        except RuntimeError:
            continue
    return None


def _boxes(panel, names):
    out = []
    for w in panel.findChildren(QtWidgets.QWidget):
        try:
            if w.metaObject().className() in names:
                out.append(w)
        except RuntimeError:
            continue
    return out


def _sketch():
    from ..commands.base import editing_object
    sk = editing_object()
    return sk if sk is not None and sk.isDerivedFrom("Sketcher::SketchObject") else None


class Palette(QtWidgets.QFrame):
    def __init__(self, panel):
        super(Palette, self).__init__(panel)
        self.panel = panel
        self.setObjectName("FFSketchPalette")
        t = theme.tokens()
        self.setStyleSheet(
            "QFrame#FFSketchPalette { background: %s; border: 1px solid %s; border-radius: 3px; }"
            "QLabel#FFPaletteTitle { font-weight: bold; letter-spacing: 1px; color: %s; }"
            "QLabel#FFPaletteStatus { color: %s; }"
            "QPushButton#FFFinish { background: %s; color: white; border: none; padding: 6px;"
            " font-weight: bold; border-radius: 2px; }"
            % (t["panel"], t["border"], t["text"], t["text_dim"], t["ok"]))
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)
        title = QtWidgets.QLabel("SKETCH PALETTE")
        title.setObjectName("FFPaletteTitle")
        lay.addWidget(title)
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        lay.addLayout(grid)
        r = 0

        def row(label, widget):
            nonlocal r
            lab = QtWidgets.QLabel(label)
            lab.setProperty("role", "caption")
            grid.addWidget(lab, r, 0)
            grid.addWidget(widget, r, 1)
            r += 1
            return widget

        cons = QtWidgets.QToolButton()
        cons.setText("Construction")
        cons.setToolTip("Turn the selected curves (or the next ones you draw) into construction lines (X)")
        cons.clicked.connect(lambda: _run("FF_SkConstruction"))
        row("Linetype", cons)
        look = QtWidgets.QToolButton()
        look.setText("Look At")
        look.setToolTip("Look straight at the sketch")
        look.clicked.connect(lambda: _run("FF_SkLookAt"))
        row("View", look)
        from . import grid as G, sketch_snap
        self.grid = row("Sketch Grid", self._check(G.sketch_visible(), G.set_sketch_visible))
        self.snap = row("Snap", self._check(sketch_snap.enabled(), lambda on: sketch_snap.enabled() != on
                                            and sketch_snap.toggle_snap()))
        sk = _sketch()
        self.slice = row("Slice", self._check(bool(getattr(sk.ViewObject, "SectionView", False)) if sk else False,
                                              self._slice))
        self.profile = row("Show Profile", self._check(bool(getattr(sk, "MakeInternals", False)) if sk else False,
                                                       self._profile))
        self.lists = row("Constraint List", self._check(params.get_bool("SketchLists", False), self._lists))
        self.status = QtWidgets.QLabel("")
        self.status.setObjectName("FFPaletteStatus")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        finish = QtWidgets.QPushButton("FINISH SKETCH")
        finish.setObjectName("FFFinish")
        finish.clicked.connect(lambda: _run("FF_FinishSketch"))
        lay.addWidget(finish)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self._sync)
        self.timer.start()
        self._sync()

    def _check(self, on, fn):
        c = QtWidgets.QCheckBox()
        c.setChecked(on)
        c.toggled.connect(lambda v: fn(v))
        return c

    def _slice(self, on):
        sk = _sketch()
        if sk is not None and bool(getattr(sk.ViewObject, "SectionView", False)) != on:
            _run("FF_SkSlice")

    def _profile(self, on):
        sk = _sketch()
        if sk is not None and "MakeInternals" in sk.PropertiesList and sk.MakeInternals != on:
            sk.MakeInternals = on
            sk.Document.recompute()

    def _lists(self, on):
        params.set_bool("SketchLists", on)
        apply_visibility(self.panel)

    def _sync(self):
        try:
            labels = [w for b in _boxes(self.panel, ("SketcherGui::TaskSketcherMessages",))
                      for w in b.findChildren(QtWidgets.QLabel) if w.objectName() == "labelStatus"]
            text = labels[0].text() if labels else ""
        except RuntimeError:
            return
        if text != self.status.text():
            self.status.setText(text)
        apply_visibility(self.panel)


def _run(name):
    from ..commands import base
    base.run(name)


def apply_visibility(panel):
    show = params.get_bool("SketchLists", False)
    for b in _boxes(panel, HIDDEN):
        want = show
        if b.isVisibleTo(panel) != want:
            b.setVisible(want)


def install():
    """Add the palette to the sketch's task panel (called when a sketch opens)."""
    panel = _task_panel()
    if panel is None:
        return False
    old = panel.findChild(QtWidgets.QFrame, "FFSketchPalette")
    if old is not None:
        return True
    apply_visibility(panel)
    pal = Palette(panel)
    lay = panel.layout()
    if lay is not None:
        idx = lay.count()
        for i in range(lay.count() - 1, -1, -1):
            if lay.itemAt(i).spacerItem() is not None:
                idx = i
        lay.insertWidget(idx, pal)
    pal.show()
    _state["palette"] = pal
    # Fusion's button says what it does
    for b in panel.window().findChildren(QtWidgets.QPushButton):
        try:
            if b.text().replace("&", "") == "Close" and b.isVisible() and b.parentWidget().metaObject().className() == "QDialogButtonBox":
                b.setText("Finish Sketch")
        except RuntimeError:
            continue
    return True
