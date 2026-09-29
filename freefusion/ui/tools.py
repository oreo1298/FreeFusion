# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI flows for Press Pull, Move/Copy, Coil, Thread, Pipe and file insertion."""

import os

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtWidgets

from .. import design as D
from ..features import special as SP
from . import notify
from . import widgets as W


def press_pull():
    """Faces -> Press Pull dialog; edges -> Fillet (like Fusion's context aware Q)."""
    from .panels.modify_panels import PressPullPanel
    items = [(o, s) for o, subs in W.selection_refs() for s in subs]
    edges = [(o, s) for o, s in items if s.startswith("Edge")]
    if edges and len(edges) == len(items):
        return dress_up("Fillet")
    faces = [(o, s) for o, s in items if s.startswith("Face")]
    Gui.Selection.clearSelection()
    W.show(PressPullPanel(faces))


def dress_up(kind):
    """FILLET / CHAMFER dialog with the selected edges and faces."""
    from .panels.modify_panels import ChamferPanel, FilletPanel
    items = [(o, s) for o, subs in W.selection_refs() for s in subs
             if s.startswith("Edge") or s.startswith("Face")]
    Gui.Selection.clearSelection()
    W.show((FilletPanel if kind == "Fillet" else ChamferPanel)(items))


def move():
    """Move/Copy: Fusion moves whole bodies/components, so lift faces to their body."""
    refs = W.selection_refs()
    targets = []
    for o, _ in refs:
        t = D.body_of(o) or o
        if D.is_pd_feature(t):
            t = D.body_of(t) or t
        if t not in targets:
            targets.append(t)
    if not targets:
        notify.error("Select a body or component to move")
        return
    Gui.Selection.clearSelection()
    for t in targets:
        Gui.Selection.addSelection(t)
    from ..commands import base
    base.run_target("Std_TransformManip")


class _ValuesPanel(W.FormPanel):
    """Small dialog: selection slots + numeric fields, runs ``build_fn`` on OK."""

    def __init__(self, title, icon, slots, values, build_fn, preselected=None):
        self.title, self.icon, self.transaction = title, icon, title.title()
        self._slots, self._values, self._build_fn = slots, values, build_fn
        super(_ValuesPanel, self).__init__()
        pre = list(preselected or [])
        for f in self.slot_fields:
            if pre:
                f.set_items([pre.pop(0)])
        empty = [f for f in self.slot_fields if not f.items]
        if empty:
            empty[0].set_active(True)

    def build(self):
        self.slot_fields = [self.row(lab, W.SelectionField(acc, multi, "Select"))
                            for lab, acc, multi in self._slots]
        self.value_fields = [self.row(lab, W.ValueField(val, unit, step))
                             for lab, val, unit, step in self._values]

    def on_selection(self, field):
        pass

    def finish(self):
        for f in self.slot_fields:
            if not f.items:
                raise ValueError("Complete the selection first")
        self._build_fn(self.doc, [f.items for f in self.slot_fields],
                       [v.value() for v in self.value_fields])
        return True


def coil():
    doc = App.ActiveDocument or App.newDocument("Untitled")

    def build(doc, sel, vals):
        SP.coil(doc, *vals)
    W.show(_ValuesPanel("COIL", "Coil", [], [("Diameter", 20.0, "mm", 1.0), ("Pitch", 5.0, "mm", 0.5),
                                             ("Revolutions", 5.0, "", 1.0), ("Section Size", 2.0, "mm", 0.5)],
                        build))


def _cyl_face(obj, sub):
    try:
        return sub.startswith("Face") and isinstance(obj.getSubObject(sub).Faces[0].Surface, Part.Cylinder)
    except Exception:
        return False


def thread():
    pre = [(o, s) for o, subs in W.selection_refs() for s in subs if _cyl_face(o, s)]
    Gui.Selection.clearSelection()

    def build(doc, sel, vals):
        obj, sub = sel[0][0]
        if D.is_body(obj):
            obj = obj.Tip
        SP.thread(doc, obj, sub, pitch=vals[0] or None)
    panel = _ValuesPanel("THREAD", "Thread", [("Faces", _cyl_face, False)],
                         [("Pitch (0 = ISO)", 0.0, "mm", 0.25)], build, pre)
    panel.set_hint("Select a cylindrical face. The pitch defaults to ISO metric coarse.")
    W.show(panel)


def pipe():
    pre = [(o, s) for o, subs in W.selection_refs() for s in (subs or [""])]
    Gui.Selection.clearSelection()

    def build(doc, sel, vals):
        refs = {}
        for o, s in sel[0]:
            refs.setdefault(o, []).append(s) if s else refs.setdefault(o, [])
        SP.pipe(doc, list(refs.items()), vals[0])
    W.show(_ValuesPanel("PIPE", "Pipe", [("Path", lambda o, s: s.startswith("Edge") or D.is_sketch(o), True)],
                        [("Section Size", 5.0, "mm", 0.5)], build, pre))


def insert_file(filt):
    fn, _ = QtWidgets.QFileDialog.getOpenFileName(Gui.getMainWindow(), "Insert", os.path.expanduser("~"), filt)
    if not fn:
        return
    doc = App.ActiveDocument or App.newDocument("Untitled")
    before = set(o.Name for o in doc.Objects)
    ext = os.path.splitext(fn)[1].lower()
    doc.openTransaction("Insert")
    if ext == ".svg":
        import importSVG
        importSVG.insert(fn, doc.Name)
    elif ext == ".dxf":
        import importDXF
        importDXF.insert(fn, doc.Name)
    else:
        import Mesh
        Mesh.insert(fn, doc.Name)
    comp = D.active_component(doc)
    for o in doc.Objects:
        if o.Name not in before and getattr(o, "getParentGeoFeatureGroup", None) \
                and o.getParentGeoFeatureGroup() is None and not o.InList:
            try:
                D.add_to(comp, o)
            except Exception:
                pass
    doc.commitTransaction()
    doc.recompute()
    Gui.SendMsgToActiveView("ViewFit")
