# SPDX-License-Identifier: LGPL-2.1-or-later
"""Create Sketch (plane picker), Finish Sketch and the Hole placement flow."""

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtWidgets

from .. import design as D
from ..features import parameters as PR
from . import notify, theme
from . import widgets as W


def _is_plane_ref(obj, sub):
    if obj is None:
        return False
    if not sub:
        return obj.isDerivedFrom("App::Plane") or obj.isDerivedFrom("Part::DatumPlane") \
            or obj.isDerivedFrom("PartDesign::Plane")
    if sub.startswith("Face"):
        try:
            return isinstance(obj.getSubObject(sub).Faces[0].Surface, Part.Plane)
        except Exception:
            return False
    return False


def _support_for(obj, sub):
    if D.is_body(obj):
        obj = obj.Tip
    return [(obj, sub or "")]


def new_sketch_on(obj, sub, edit=True):
    doc = obj.Document
    doc.openTransaction("Create Sketch")
    comp = D.active_component(doc)
    sk = D.new_sketch(doc, comp, support=_support_for(obj, sub))
    doc.commitTransaction()
    doc.recompute()
    if edit:
        edit_sketch(sk)
    return sk


def edit_sketch(sk):
    gd = Gui.getDocument(sk.Document.Name)
    D.keep_sketch_in_workbench(sk)
    D.show_object(sk)
    gd.setEdit(sk.Name)


def finish_sketch():
    gd = Gui.ActiveDocument
    if gd is None:
        return
    from ..commands.base import editing_object
    sk = editing_object()
    if Gui.Control.activeDialog():
        try:
            Gui.Control.closeDialog()
        except Exception:
            pass
    gd.resetEdit()
    if sk is not None and sk.isDerivedFrom("Sketcher::SketchObject"):
        try:
            PR.name_dimensions(sk)
        except Exception:
            pass
        sk.Document.recompute()
        _last_sketch["name"] = (sk.Document.Name, sk.Name)
        # like Fusion, go back to the home view after the first sketch of a design
        if not D.design_bodies(sk.Document, visible_only=True):
            try:
                gd.ActiveView.viewIsometric()
                gd.ActiveView.fitAll()
            except Exception:
                pass


_last_sketch = {"name": None}


def last_finished_sketch():
    ref = _last_sketch["name"]
    if not ref:
        return None
    try:
        return App.getDocument(ref[0]).getObject(ref[1])
    except Exception:
        return None


class SketchPlanePanel(object):
    """Task panel shown by Create Sketch until a plane or planar face is clicked."""

    def __init__(self, doc, on_pick=None, title="Create Sketch"):
        self.doc = doc
        self.on_pick = on_pick or (lambda o, s: new_sketch_on(o, s))
        self.comp = D.active_component(doc)
        self.form = QtWidgets.QWidget()
        self.form.setObjectName("FFPanel")
        self.form.setWindowTitle(title)
        self.form.setWindowIcon(theme.icon("CreateSketch"))
        lay = QtWidgets.QVBoxLayout(self.form)
        lab = QtWidgets.QLabel("Select a plane or planar face.")
        lab.setObjectName("FFHint")
        lay.addWidget(lab)
        row = QtWidgets.QHBoxLayout()
        for role, text in (("XY_Plane", "XY"), ("XZ_Plane", "XZ"), ("YZ_Plane", "YZ")):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(lambda _=False, r=role: self._pick_origin(r))
            row.addWidget(b)
        lay.addLayout(row)
        self._origin_vis = None
        self._show_origin(True)
        self._done = False
        Gui.Selection.clearSelection()
        Gui.Selection.addObserver(self)

    def _show_origin(self, on):
        origin = D.origin_of(self.comp)
        if origin is None or not App.GuiUp:
            return
        try:
            vo = origin.ViewObject
            if on:
                self._origin_vis = vo.Visibility
                vo.Visibility = True
                for f in origin.OriginFeatures:
                    if f.Role.endswith("Plane"):
                        f.ViewObject.Visibility = True
            elif self._origin_vis is not None:
                vo.Visibility = self._origin_vis
        except Exception:
            pass

    def _pick_origin(self, role):
        f = D.origin_feature(self.comp, role)
        if f is not None:
            self._picked(f, "")

    def _picked(self, obj, sub):
        if self._done:
            return
        self._done = True
        self._close()
        QtCore.QTimer.singleShot(0, lambda: self.on_pick(obj, sub))

    def addSelection(self, doc, obj, sub, pnt):
        leaf, el = W.resolve(doc, obj, sub)
        if _is_plane_ref(leaf, el):
            self._picked(leaf, el)
        else:
            Gui.Selection.clearSelection()
            notify.status("Select a plane or a planar face")

    def removeSelection(self, *a):
        pass

    def setSelection(self, *a):
        pass

    def clearSelection(self, *a):
        pass

    def _close(self):
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass
        self._show_origin(False)
        Gui.Selection.clearSelection()
        Gui.Control.closeDialog()

    def getStandardButtons(self):
        return QtWidgets.QDialogButtonBox.Cancel

    def reject(self):
        self._done = True
        self._close()
        return True

    def accept(self):
        return self.reject()


def create_sketch():
    doc = App.ActiveDocument
    if doc is None:
        doc = App.newDocument("Untitled")
    refs = W.selection_refs()
    for obj, subs in refs:
        for s in (subs or [""]):
            if _is_plane_ref(obj, s):
                Gui.Selection.clearSelection()
                return new_sketch_on(obj, s)
    W.show(SketchPlanePanel(doc))


# ---------------------------------------------------------------------------
# HOLE: click a face (and optionally a point) -> sketch point + PartDesign::Hole


def _hole_on(obj, sub, point=None):
    doc = obj.Document
    body = D.body_of(obj)
    if body is None:
        notify.error("Holes are placed on faces of bodies")
        return
    feat = obj if not D.is_body(obj) else obj.Tip
    label, gid = D.new_group_id(doc, "Hole")
    doc.openTransaction("Hole")
    sk = body.newObject("Sketcher::SketchObject", "HoleSketch")
    sk.AttachmentSupport = [(feat, sub)]
    sk.MapMode = "FlatFace"
    doc.recompute()
    if point is None:
        face = feat.getSubObject(sub)
        point = face.CenterOfMass
    local = sk.getGlobalPlacement().inverse().multVec(point)
    # a circle's center locates the hole in every FreeCAD version (points need 1.1)
    sk.addGeometry(Part.Circle(App.Vector(local.x, local.y, 0), App.Vector(0, 0, 1), 3.0), False)
    sk.Label = label + " Sketch"
    doc.recompute()
    D.tag(sk, group=gid)
    hole = body.newObject("PartDesign::Hole", "Hole")
    hole.Profile = sk
    hole.Diameter = 6.0
    hole.Depth = 10.0
    try:
        hole.Refine = True
    except Exception:
        pass
    hole.Label = label
    D.tag(hole, role=D.ROLE_FEATURE, group=gid, op="Hole", data={"type": "Hole"})
    doc.recompute()
    D.hide_object(sk)
    doc.commitTransaction()
    Gui.getDocument(doc.Name).setEdit(hole.Name)


def hole():
    doc = App.ActiveDocument
    if doc is None:
        return
    sel = Gui.Selection.getSelectionEx("", 0)
    for s in sel:
        for i, sub in enumerate(s.SubElementNames):
            leaf, el = W.resolve(doc.Name, s.Object.Name, sub)
            if el.startswith("Face") and _is_plane_ref(leaf, el):
                pts = s.PickedPoints
                Gui.Selection.clearSelection()
                return _hole_on(leaf, el, pts[i] if i < len(pts) else None)

    class _Pick(SketchPlanePanel):
        def addSelection(self, docname, obj, sub, pnt):
            leaf, el = W.resolve(docname, obj, sub)
            if el.startswith("Face") and _is_plane_ref(leaf, el):
                p = App.Vector(*pnt) if pnt else None
                if self._done:
                    return
                self._done = True
                self._close()
                QtCore.QTimer.singleShot(0, lambda: _hole_on(leaf, el, p))
            else:
                Gui.Selection.clearSelection()
                notify.status("Click a planar face of a body to place the hole")

    panel = _Pick(doc, title="Hole")
    panel.form.findChild(QtWidgets.QLabel).setText("Click a planar face where the hole goes.")
    for b in panel.form.findChildren(QtWidgets.QPushButton):
        b.hide()
    panel._show_origin(False)
    W.show(panel)
