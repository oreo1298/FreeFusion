# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion's Line tool: lines chain from the last end point until you close a shape or press Esc.

FreeCAD's single Line tool shows the length/angle input boxes Fusion has (its
polyline tool does not), but starts every line from scratch. After each new line,
FreeFusion clicks its end point for you, so the next line starts there (with a
coincident constraint), exactly like Fusion.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

_chain = {"on": False, "sketch": None, "count": 0, "pending": False}


def _editing_sketch():
    from ..commands.base import editing_object, in_sketch
    if not in_sketch():
        return None
    sk = editing_object()
    if sk is not None and sk.isDerivedFrom("Sketcher::SketchObject"):
        return sk
    return None


def line():
    """Start the chained line tool (the L key)."""
    sk = _editing_sketch()
    if sk is None:
        return
    _chain.update(on=True, sketch=(sk.Document.Name, sk.Name), count=len(sk.Geometry))
    Gui.runCommand("Sketcher_CreateLine", 0)


def stop():
    _chain["on"] = False


def active():
    return _chain["on"]


def _viewport():
    try:
        return Gui.ActiveDocument.ActiveView.graphicsView().viewport()
    except Exception:
        return None


def _tool_running(w):
    try:
        return w.cursor().shape() == QtCore.Qt.BitmapCursor
    except Exception:
        return False


def geometry_changed(obj):
    """Document observer hook: a sketch's Geometry property changed."""
    if not _chain["on"] or _chain["pending"]:
        return
    if (obj.Document.Name, obj.Name) != _chain["sketch"]:
        return
    _chain["pending"] = True
    # let the line tool finish (it resets to 'pick first point' after creating the line)
    QtCore.QTimer.singleShot(60, lambda: _after_change(obj))


def _endpoints(g):
    out = []
    for name in ("StartPoint", "EndPoint"):
        if hasattr(g, name):
            out.append(getattr(g, name))
    return out


def _after_change(sk):
    import Part
    _chain["pending"] = False
    try:
        geos = sk.Geometry
    except Exception:
        stop()
        return
    n = len(geos)
    added = n - _chain["count"]
    _chain["count"] = n
    if added != 1 or not isinstance(geos[-1], Part.LineSegment):
        return
    w = _viewport()
    if w is None or not _tool_running(w) or _editing_sketch() is not sk:
        stop()
        return
    new = geos[-1]
    end = new.EndPoint
    # the line closed a shape or ended on existing geometry: the chain ends there
    for g in geos[:-1]:
        for p in _endpoints(g):
            if (p - end).Length < 1e-7:
                return
    if (new.StartPoint - end).Length < 1e-9:
        return
    _click_at(sk, w, end)


def _click_at(sk, w, point):
    from .sketch_snap import Projector
    from .viewport import _mouse_event
    try:
        pr = Projector(Gui.ActiveDocument.ActiveView, w, sk)
        x, y = pr.to_screen(point.x, point.y)
    except Exception:
        return
    local = QtCore.QPoint(int(round(x)), int(round(y)))
    glob = w.mapToGlobal(local)
    app = QtWidgets.QApplication
    nb, left = QtCore.Qt.NoButton, QtCore.Qt.LeftButton
    mods = QtCore.Qt.NoModifier
    # hover first so FreeCAD pre-selects the end point (-> coincident constraint)
    for etype, btn, btns in ((QtCore.QEvent.MouseMove, nb, nb),
                             (QtCore.QEvent.MouseMove, nb, nb),
                             (QtCore.QEvent.MouseButtonPress, left, left),
                             (QtCore.QEvent.MouseButtonRelease, left, nb)):
        app.sendEvent(w, _mouse_event(etype, local, glob, btn, btns, mods))
    # FreeCAD draws the rubber band from there as soon as the real mouse moves again
    cur = QtGui.QCursor.pos()
    lp = w.mapFromGlobal(cur)
    if w.rect().contains(lp):
        app.sendEvent(w, _mouse_event(QtCore.QEvent.MouseMove, lp, cur, nb, nb, mods))
