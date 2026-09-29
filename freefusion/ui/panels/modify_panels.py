# SPDX-License-Identifier: LGPL-2.1-or-later
"""PRESS PULL, COMBINE, SPLIT BODY, SCALE and CONSTRUCT dialogs."""

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtWidgets

from ... import design as D
from ...features import bodies as B
from ...features import common as C
from ...features import construct as K
from ...features import dressup as DU
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
        self._update_arrow(refs)

    def _update_arrow(self, refs):
        if self._closing or not refs:
            self.clear_arrows()
            return
        obj, faces = refs[0]
        try:
            f = obj.getSubObject(faces[0])
            f = f.Faces[0]
            c = f.CenterOfMass
            u, v = f.Surface.parameter(c)
            n = f.normalAt(u, v)
        except Exception:
            return
        self.set_arrow("distance", c, n, self.distance)

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
        if self.key == "OffsetPlane":
            self._update_arrow()

    def _update_arrow(self):
        obj = self._obj
        if self._closing or obj is None or not obj.isValid():
            self.clear_arrows()
            return
        try:
            pl = obj.getGlobalPlacement() if hasattr(obj, "getGlobalPlacement") else obj.Placement
            n = pl.Rotation.multVec(App.Vector(0, 0, 1))
            base = K._plane_of(self.slots[0].items[0])[0]
            # project onto the reference plane (the datum sits `value` above it)
            base = base + n * ((pl.Base - base).dot(n) - (self.value.value() or 0.0))
        except Exception:
            return
        self.set_arrow("value", base, n, self.value, flip_with_sign=False)

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


# ---------------------------------------------------------------------------
# FILLET / CHAMFER


def _edge_or_face(obj, sub):
    if not (sub.startswith("Edge") or sub.startswith("Face")):
        return False
    return D.body_of(obj) is not None


class _DressUpPanel(W.FormPanel):
    kind = DU.FILLET

    def __init__(self, items=None, gid=None):
        self.gid = gid
        self.edit = gid is not None
        self._built = None
        super(_DressUpPanel, self).__init__()
        if self.edit:
            refs, prm = DU.load(self.doc, gid)
            self.load_params(prm)
            items = [(o, s) for o, subs in refs for s in subs]
            self._built = gid
        if items:
            self.edges.set_items(items)
            self.preview()
        else:
            self.edges.set_active(True)
            self.set_hint("Select edges (or faces) to %s." % self.kind.lower())

    def build(self):
        self.edges = self.row("Edges", W.SelectionField(_edge_or_face, True, "Select edges"))
        self.edges.changed.connect(self.preview)
        self.chain = self.row("Tangent Chain", QtWidgets.QCheckBox())
        self.chain.setChecked(True)
        self.chain.toggled.connect(lambda *_: self.preview())
        self.build_values()

    def addSelection(self, doc, obj, sub, pnt):
        """Clicks on this command's own preview map back to the edge before it."""
        if self._built is not None and not self._busy:
            leaf, el = W.resolve(doc, obj, sub)
            own = D.group_members(self.doc, self._built)
            if leaf is not None and leaf in own:
                base = getattr(leaf, "BaseFeature", None)
                mapped = DU.map_element(leaf, el, base) if base is not None else None
                Gui.Selection.clearSelection()
                if mapped is None:
                    self.set_hint("That edge is created by this %s." % self.kind.lower())
                    return
                field = self.active_field()
                if field is not None:
                    field.toggle(base, mapped)      # emits changed -> preview
                return
        super(_DressUpPanel, self).addSelection(doc, obj, sub, pnt)

    def preview(self):
        if self._busy:
            return
        refs = self.edges.refs()
        prm = self.params()
        self._busy = True
        try:
            if not refs:
                if self._built and not self.edit:
                    C.remove_group(self.doc, self._built)
                    self._built = None
                    self.doc.recompute()
                self.clear_arrows()
                return
            if self.edit:
                # keep the base bodies visible: features re-attach at their old place
                DU.update(self.doc, self._built, self.kind, refs, prm)
            elif self._built is None:
                label, gid = D.new_group_id(self.doc, self.kind)
                DU.create(self.doc, self.kind, refs, prm, label=label, gid=gid)
                self._built = gid
            else:
                DU.update(self.doc, self._built, self.kind, refs, prm)
            bad = [f for f in D.group_members(self.doc, self._built) if not f.isValid()]
            self.set_hint("The %s could not be computed with these values." % self.kind.lower()
                          if bad else "", bool(bad))
        except Exception as e:
            self.set_hint(str(e), error=True)
        finally:
            self._busy = False
        self._update_arrow(refs)

    def _update_arrow(self, refs):
        if self._closing:
            return
        edge = None
        for o, subs in refs:
            for s in subs:
                if s.startswith("Edge"):
                    edge = (o, s)
                    break
            if edge:
                break
        if edge is None:
            self.clear_arrows()
            return
        try:
            mid, inward = DU.edge_frame(*edge)
        except Exception:
            return
        if inward is None:
            return
        # the arrow sits on the rounded surface and points out of the material
        self.set_arrow("value", mid, inward * -1, self.value_field(), scale=-0.3,
                       minimum=0.0, flip_with_sign=False)

    def finish(self):
        if self._built is None:
            self.preview()
        if self._built is None or not D.group_members(self.doc, self._built):
            raise ValueError(self.hint.text() or "Select edges first")
        bad = [f for f in D.group_members(self.doc, self._built) if not f.isValid()]
        if bad:
            raise ValueError("The %s could not be computed with these values." % self.kind.lower())
        return True


class FilletPanel(_DressUpPanel):
    title = "FILLET"
    icon = "Fillet"
    transaction = "Fillet"
    kind = DU.FILLET

    def build_values(self):
        self.radius = self.row("Radius", W.ValueField(1.0, "mm", 0.5))
        self.radius.changed.connect(self.preview)

    def value_field(self):
        return self.radius

    def load_params(self, prm):
        self.radius.set_value(prm.get("radius", 1.0), prm.get("expr", ""))
        self.chain.setChecked(prm.get("tangent_chain", True))

    def params(self):
        return {"radius": max(self.radius.value() or 0.0, 1e-3), "expr": self.radius.expression(),
                "tangent_chain": self.chain.isChecked()}


class ChamferPanel(_DressUpPanel):
    title = "CHAMFER"
    icon = "Chamfer"
    transaction = "Chamfer"
    kind = DU.CHAMFER

    def build_values(self):
        self.ctype = self.row("Chamfer Type", W.IconCombo([
            (DU.EQUAL, "Equal distance", ""), (DU.TWO_DISTANCES, "Two distances", ""),
            (DU.DISTANCE_ANGLE, "Distance and angle", "")]))
        self.distance = self.row("Distance", W.ValueField(1.0, "mm", 0.5))
        self.distance2 = self.row("Distance 2", W.ValueField(1.0, "mm", 0.5), key="distance2")
        self.angle = self.row("Angle", W.ValueField(45.0, "deg", 5.0), key="angle")
        self.ctype.currentIndexChanged.connect(self._type_changed)
        for f in (self.distance, self.distance2, self.angle):
            f.changed.connect(self.preview)
        self._type_changed()

    def _type_changed(self, *_):
        t = self.ctype.key()
        self.show_row("distance2", t == DU.TWO_DISTANCES)
        self.show_row("angle", t == DU.DISTANCE_ANGLE)
        if hasattr(self, "edges") and not self._busy:
            self.preview()

    def value_field(self):
        return self.distance

    def load_params(self, prm):
        self.ctype.set_key(prm.get("type", DU.EQUAL))
        self.distance.set_value(prm.get("distance", 1.0), prm.get("expr", ""))
        self.distance2.set_value(prm.get("distance2", 1.0))
        self.angle.set_value(prm.get("angle", 45.0))
        self.chain.setChecked(prm.get("tangent_chain", True))
        self._type_changed()

    def params(self):
        return {"type": self.ctype.key(), "distance": max(self.distance.value() or 0.0, 1e-3),
                "expr": self.distance.expression(), "distance2": max(self.distance2.value() or 0.0, 1e-3),
                "angle": self.angle.value() or 45.0, "tangent_chain": self.chain.isChecked()}
