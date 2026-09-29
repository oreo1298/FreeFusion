# SPDX-License-Identifier: LGPL-2.1-or-later
"""PRESS PULL, COMBINE, SPLIT BODY, SCALE and CONSTRUCT dialogs."""

import FreeCAD as App
import FreeCADGui as Gui
import Part

from ... import design as D
from ...features import bodies as B
from ...features import common as C
from ...features import construct as K
from ...features import extrude as X
from .. import widgets as W
from .profile_panels import OPERATION_ITEMS, accept_body


def _planar_face(obj, sub):
    if not sub.startswith("Face"):
        return False
    try:
        return isinstance(obj.getSubObject(sub).Faces[0].Surface, Part.Plane)
    except Exception:
        return False


def _body_of_sel(obj):
    return D.body_of(obj) or (obj if D.role(obj) in (D.ROLE_BODY, D.ROLE_CONSUMED) else None)


class PressPullPanel(W.FormPanel):
    title = "PRESS PULL"
    icon = "PressPull"
    transaction = "Press Pull"

    def __init__(self, items=None):
        self._gid = None
        super(PressPullPanel, self).__init__()
        if items:
            self.faces.set_items(items)
            self.preview()
        else:
            self.faces.set_active(True)
            self.set_hint("Select planar faces to push or pull.")

    def build(self):
        self.faces = self.row("Faces", W.SelectionField(_planar_face, True, "Select faces"))
        self.faces.changed.connect(self.preview)
        self.distance = self.row("Distance", W.ValueField(5.0, "mm"))
        self.distance.changed.connect(self.preview)

    def preview(self):
        if self._busy:
            return
        refs = self.faces.refs()
        self._busy = True
        try:
            if self._gid is not None:
                C.remove_group(self.doc, self._gid)
                self._gid = None
                self.doc.recompute()
            if not refs:
                return
            d = self.distance.value() or 0.0
            if abs(d) < 1e-9:
                self.set_hint("Distance must not be zero.", error=True)
                return
            obj, faces = refs[0]
            res = B.press_pull(self.doc, obj, faces, d, self.distance.expression())
            self._gid = D.group_id(res.primary)
            self.set_hint("")
        except Exception as e:
            self.set_hint(str(e), error=True)
        finally:
            self._busy = False

    def finish(self):
        if self._gid is None:
            raise ValueError(self.hint.text() or "Select a face")
        return True


class CombinePanel(W.FormPanel):
    title = "COMBINE"
    icon = "Combine"
    transaction = "Combine"

    def build(self):
        self.target = self.row("Target Body", W.SelectionField(accept_body, False, "Select body"))
        self.tools = self.row("Tool Bodies", W.SelectionField(accept_body, True, "Select bodies"))
        self.op = self.row("Operation", W.IconCombo(OPERATION_ITEMS[:3]))
        from PySide import QtWidgets
        self.keep = self.row("Keep Tools", QtWidgets.QCheckBox())
        self.target.changed.connect(self._target_changed)
        self.target.set_active(True)
        self.set_hint("Select the target body, then the tool bodies.")

    def _target_changed(self):
        if self.target.items and not self.tools.items:
            self.tools.set_active(True)

    def on_selection(self, field):
        pass

    def finish(self):
        target = _body_of_sel(self.target.objects()[0]) if self.target.items else None
        tools = []
        for o in self.tools.objects():
            b = _body_of_sel(o)
            if b is not None and b not in tools and b != target:
                tools.append(b)
        B.combine(self.doc, target, tools, self.op.key(), self.keep.isChecked())
        return True


class SplitBodyPanel(W.FormPanel):
    title = "SPLIT BODY"
    icon = "SplitBody"
    transaction = "Split Body"

    def build(self):
        self.body = self.row("Body to Split", W.SelectionField(accept_body, False, "Select body"))
        self.tool = self.row("Splitting Tool", W.SelectionField(
            lambda o, s: True, True, "Select plane, face or body"))
        self.body.changed.connect(lambda: self.body.items and self.tool.set_active(True))
        self.body.set_active(True)

    def on_selection(self, field):
        pass

    def finish(self):
        if not self.body.items or not self.tool.items:
            raise ValueError("Select a body and a splitting tool")
        body = _body_of_sel(self.body.objects()[0])
        tools = []
        for o, s in self.tool.items:
            t = _body_of_sel(o) or o
            if t not in tools:
                tools.append(t)
        B.split_body(self.doc, body, tools)
        return True


class ScalePanel(W.FormPanel):
    title = "SCALE"
    icon = "Scale"
    transaction = "Scale"

    def build(self):
        self.body = self.row("Entities", W.SelectionField(accept_body, False, "Select body"))
        self.factor = self.row("Scale Factor", W.ValueField(1.0, "", 0.1))
        self.body.set_active(True)

    def on_selection(self, field):
        pass

    def finish(self):
        if not self.body.items:
            raise ValueError("Select a body")
        B.scale_body(self.doc, _body_of_sel(self.body.objects()[0]), self.factor.value() or 1.0)
        return True


# ---------------------------------------------------------------------------
# CONSTRUCT

CONSTRUCT = {
    # key: (title, icon, [slot labels], value (label, unit, default) or None, builder)
    "OffsetPlane": ("OFFSET PLANE", "OffsetPlane", ["Plane / Face"], ("Distance", "mm", 10.0),
                    lambda d, r, v: K.offset_plane(d, r[0], v)),
    "PlaneAngle": ("PLANE AT ANGLE", "PlaneAngle", ["Line"], ("Angle", "deg", 45.0),
                   lambda d, r, v: K.plane_at_angle(d, r[0], v)),
    "TangentPlane": ("TANGENT PLANE", "TangentPlane", ["Face"], None,
                     lambda d, r, v: K.tangent_plane(d, r[0])),
    "Midplane": ("MIDPLANE", "Midplane", ["First Plane", "Second Plane"], None,
                 lambda d, r, v: K.midplane(d, r[0], r[1])),
    "PlaneTwoEdges": ("PLANE THROUGH TWO EDGES", "PlaneTwoEdges", ["First Edge", "Second Edge"], None,
                      lambda d, r, v: K.plane_two_edges(d, r[0], r[1])),
    "PlaneThreePoints": ("PLANE THROUGH THREE POINTS", "PlaneThreePoints", ["Point 1", "Point 2", "Point 3"],
                         None, lambda d, r, v: K.plane_three_points(d, r[0], r[1], r[2])),
    "PlaneTangentAtPoint": ("PLANE TANGENT TO FACE AT POINT", "PlaneTangentAtPoint", ["Face", "Point"], None,
                            lambda d, r, v: K.tangent_plane(d, r[0], r[1])),
    "PlaneAlongPath": ("PLANE ALONG PATH", "PlaneAlongPath", ["Path"], ("Distance", "", 0.5),
                       lambda d, r, v: K.plane_along_path(d, r[0], v)),
    "AxisCylinder": ("AXIS THROUGH CYLINDER/CONE/TORUS", "AxisCylinder", ["Face"], None,
                     lambda d, r, v: K.axis_through_cylinder(d, r[0])),
    "AxisNormal": ("AXIS PERPENDICULAR AT POINT", "AxisNormal", ["Face", "Point"], None,
                   lambda d, r, v: K.axis_normal_at_point(d, r[0], r[1])),
    "AxisTwoPlanes": ("AXIS THROUGH TWO PLANES", "AxisTwoPlanes", ["First Plane", "Second Plane"], None,
                      lambda d, r, v: K.axis_two_planes(d, r[0], r[1])),
    "AxisTwoPoints": ("AXIS THROUGH TWO POINTS", "AxisTwoPoints", ["First Point", "Second Point"], None,
                      lambda d, r, v: K.axis_two_points(d, r[0], r[1])),
    "AxisEdge": ("AXIS THROUGH EDGE", "AxisEdge", ["Edge"], None,
                 lambda d, r, v: K.axis_through_edge(d, r[0])),
    "PointVertex": ("POINT AT VERTEX", "PointVertex", ["Vertex"], None,
                    lambda d, r, v: K.point_at_vertex(d, r[0])),
    "PointTwoEdges": ("POINT THROUGH TWO EDGES", "PointTwoEdges", ["First Edge", "Second Edge"], None,
                      lambda d, r, v: K.point_two_edges(d, r[0], r[1])),
    "PointThreePlanes": ("POINT THROUGH THREE PLANES", "PointThreePlanes", ["Plane 1", "Plane 2", "Plane 3"],
                         None, lambda d, r, v: K.point_three_planes(d, r[0], r[1], r[2])),
    "PointCenter": ("POINT AT CENTER OF CIRCLE", "PointCenter", ["Circular Edge"], None,
                    lambda d, r, v: K.point_center(d, r[0])),
    "PointEdgePlane": ("POINT AT EDGE AND PLANE", "PointEdgePlane", ["Edge", "Plane"], None,
                       lambda d, r, v: K.point_edge_plane(d, r[0], r[1])),
    "PointAlongPath": ("POINT ALONG PATH", "PointAlongPath", ["Path"], ("Distance", "", 0.5),
                       lambda d, r, v: K.point_along_path(d, r[0], v)),
}


class ConstructPanel(W.FormPanel):
    """One dialog for every construction tool: N selection slots + optional value."""

    def __init__(self, key, preselected=None):
        self.key = key
        self.spec = CONSTRUCT[key]
        self.title, self.icon = self.spec[0], self.spec[1]
        self.transaction = self.title.title()
        self._obj = None
        super(ConstructPanel, self).__init__()
        pre = list(preselected or [])
        for slot in self.slots:
            if pre:
                slot.set_items([pre.pop(0)])
        empty = [s for s in self.slots if not s.items]
        if empty:
            empty[0].set_active(True)
        self.preview()

    def build(self):
        self.slots = []
        for label in self.spec[2]:
            f = self.row(label, W.SelectionField(None, False, "Select"))
            f.changed.connect(self._slot_changed)
            self.slots.append(f)
        self.value = None
        if self.spec[3]:
            lab, unit, default = self.spec[3]
            self.value = self.row(lab, W.ValueField(default, unit, 1.0 if unit else 0.05))
            self.value.changed.connect(self.preview)

    def _slot_changed(self):
        for s in self.slots:
            if not s.items:
                s.set_active(True)
                return

    def on_selection(self, field):
        self.preview()

    def preview(self):
        if self._busy:
            return
        if any(not s.items for s in self.slots):
            return
        self._busy = True
        try:
            if self._obj is not None:
                D.remove_objects([self._obj])
                self._obj = None
            refs = [s.items[0] for s in self.slots]
            v = self.value.value() if self.value is not None else None
            self._obj = self.spec[4](self.doc, refs, v)
            self.set_hint("" if self._obj.isValid() else "Invalid combination of references",
                          not self._obj.isValid())
        except Exception as e:
            self.set_hint(str(e), error=True)
        finally:
            self._busy = False

    def finish(self):
        if self._obj is None:
            self.preview()
        if self._obj is None:
            raise ValueError(self.hint.text() or "Select the references")
        return True


# ---------------------------------------------------------------------------
# SWEEP / LOFT

class SweepPanel(W.FormPanel):
    title = "SWEEP"
    icon = "Sweep"
    transaction = "Sweep"

    def build(self):
        from .profile_panels import accept_profile
        self.profile = self.row("Profile", W.SelectionField(accept_profile, True, "Select profile"))
        self.path = self.row("Path", W.SelectionField(
            lambda o, s: s.startswith("Edge") or (not s and hasattr(o, "Shape")), True, "Select path"))
        self.orientation = self.row("Orientation", W.IconCombo([
            ("Standard", "Perpendicular", ""), ("Frenet", "Frenet", ""), ("Fixed", "Parallel", "")]))
        self.op = self.row("Operation", W.IconCombo(OPERATION_ITEMS))
        self.op.set_key(C.NEW_BODY)
        self.profile.changed.connect(lambda: self.profile.items and not self.path.items
                                     and self.path.set_active(True))
        self.profile.set_active(True)

    def on_selection(self, field):
        pass

    def finish(self):
        from ...features import sweeploft as SL
        if not self.profile.items or not self.path.items:
            raise ValueError("Select a profile and a path")
        SL.sweep(self.doc, self.profile.refs(), self.path.refs(), self.op.key(), None,
                 self.orientation.key())
        return True


class LoftPanel(W.FormPanel):
    title = "LOFT"
    icon = "Loft"
    transaction = "Loft"

    def build(self):
        from .profile_panels import accept_profile
        self.profiles = self.row("Profiles", W.SelectionField(accept_profile, True,
                                                              "Select profiles in order"))
        from PySide import QtWidgets
        self.ruled = self.row("Ruled", QtWidgets.QCheckBox())
        self.closed = self.row("Closed", QtWidgets.QCheckBox())
        self.op = self.row("Operation", W.IconCombo(OPERATION_ITEMS))
        self.op.set_key(C.NEW_BODY)
        self.profiles.set_active(True)
        self.set_hint("Click the profiles in loft order (one per sketch or face).")

    def on_selection(self, field):
        pass

    def finish(self):
        from ...features import sweeploft as SL
        sections = [[(o, [s] if s else [])] for o, s in self.profiles.items]
        SL.loft(self.doc, sections, self.op.key(), None, self.ruled.isChecked(),
                self.closed.isChecked())
        return True
