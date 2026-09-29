# SPDX-License-Identifier: LGPL-2.1-or-later
"""EXTRUDE and REVOLVE dialogs with live preview and Fusion's operation list."""

import FreeCAD as App
import FreeCADGui as Gui
import Part

from ... import design as D
from ...features import common as C
from ...features import extrude as X
from ...features import profiles as P
from ...features import revolve as R
from .. import widgets as W

OPERATION_ITEMS = [
    (C.JOIN, "Join", "Combine"),
    (C.CUT, "Cut", "ExtrudeCut"),
    (C.INTERSECT, "Intersect", "Interference"),
    (C.NEW_BODY, "New Body", "Body"),
    (C.NEW_COMPONENT, "New Component", "NewComponent"),
]


def accept_profile(obj, sub):
    if D.is_sketch(obj):
        return True
    if sub.startswith("Face"):
        try:
            f = obj.getSubObject(sub)
            return f is not None and isinstance(f.Faces[0].Surface, Part.Plane)
        except Exception:
            return False
    return False


def accept_body(obj, sub):
    b = D.body_of(obj) or (obj if D.role(obj) == D.ROLE_BODY else None)
    return b is not None


def accept_face(obj, sub):
    return sub.startswith("Face") or D.is_datum(obj) or obj.isDerivedFrom("App::Plane")


def accept_axis(obj, sub):
    if sub.startswith("Edge"):
        return True
    return obj.isDerivedFrom("App::Line") or obj.isDerivedFrom("Part::DatumLine") \
        or obj.isDerivedFrom("PartDesign::Line")


class _ProfilePanel(W.FormPanel):
    module = X
    base = "Extrude"

    def __init__(self, refs=None, gid=None):
        self.gid = gid
        self.edit = gid is not None
        self.op_user = False
        self.targets_user = False
        self._built_gid = None
        self._init_refs = refs or []
        super(_ProfilePanel, self).__init__()
        if self.edit:
            loaded = self.module.load(self.doc, gid)
            if loaded:
                refs, prm, op, targets = loaded
                self._init_refs = refs
                self.load_params(prm)
                self.op.set_key(op)
                self.targets.set_items([(t, "") for t in targets])
                self.op_user = True
                self.targets_user = True
                self._built_gid = gid
                for o, _ in refs:
                    if D.is_sketch(o):
                        D.show_object(o)
        self.profile.set_items([(o, s) for o, subs in self._init_refs for s in (subs or [""])])
        if not self.profile.items:
            self.profile.set_active(True)
            self.set_hint("Select sketch profiles or planar faces.")
        else:
            self.preview()

    def params(self):
        raise NotImplementedError

    def load_params(self, prm):
        pass

    def _operation_row(self):
        self.op = self.row("Operation", W.IconCombo(OPERATION_ITEMS))
        self.op.currentIndexChanged.connect(self._op_changed)
        self.targets = self.row("Objects", W.SelectionField(accept_body, True, "All intersecting"),
                                key="targets")
        self.targets.changed.connect(self._targets_changed)

    def _op_changed(self, *_):
        self.op_user = True
        self._update_rows()
        self.preview()

    def _targets_changed(self):
        self.targets_user = bool(self.targets.items)
        self.preview()

    def _update_rows(self):
        op = self.op.key()
        self.show_row("targets", op in (C.JOIN, C.CUT, C.INTERSECT))
        label = self._rows["targets"][0]
        label.setText("Target Body" if op == C.JOIN else "Objects to Cut" if op == C.CUT
                      else "Objects")

    def _target_bodies(self):
        out = []
        for o in self.targets.objects():
            b = D.body_of(o) or o
            if b not in out:
                out.append(b)
        return out

    def _tool_shape(self, refs, prm):
        return self.module.tool_shape(refs, prm) if self.module is X else \
            self.module.tool_shape(self.doc, refs, prm)

    def preview(self):
        if self._busy:
            return
        refs = self.profile.refs()
        if not refs:
            self._remove()
            return
        prm = self.params()
        if prm is None:
            return
        shape = None
        own = self._own_bodies()
        if not self.op_user:
            shape = self._tool_shape(refs, prm)
            sign = 1.0 if prm.get("distance", 1.0) >= 0 else -1.0
            auto = C.auto_operation(self.doc, refs, shape, sign, exclude=own)
            self.op.blockSignals(True)
            self.op.set_key(auto)
            self.op.blockSignals(False)
            self._update_rows()
        op = self.op.key()
        if self.targets_user:
            targets = self._target_bodies()
        else:
            if shape is None:
                shape = self._tool_shape(refs, prm)
            targets = C.default_targets(self.doc, refs, op, shape, exclude=own)
            self.targets.set_items([(t, "") for t in targets])
        self._busy = True
        try:
            if self._built_gid is None:
                label, gid = D.new_group_id(self.doc, self.base)
                res = self.module.create(self.doc, refs, prm, op, targets, label=label, gid=gid,
                                         hide=False)
                self._built_gid = gid
            else:
                self.module.update(self.doc, self._built_gid, refs, prm, op, targets, hide=False)
            self.set_hint("")
            for o, _ in refs:
                if D.is_sketch(o):
                    D.show_object(o)
        except Exception as e:
            self.set_hint(str(e), error=True)
            self._remove()
        finally:
            self._busy = False

    def _own_bodies(self):
        """Bodies created by this dialog's own preview (never targets of itself)."""
        if self._built_gid is None or self.edit:
            return ()
        return tuple(o for o in D.group_members(self.doc, self._built_gid) if D.is_body(o))

    def _remove(self):
        if self._built_gid is not None and not self.edit:
            C.remove_group(self.doc, self._built_gid)
            self._built_gid = None
            self.doc.recompute()

    def finish(self):
        if self._built_gid is None:
            self.preview()
        if self._built_gid is None or not D.group_members(self.doc, self._built_gid):
            raise ValueError(self.hint.text() or "Select a profile first")
        X.hide_profiles(self.profile.refs())
        return True


class ExtrudePanel(_ProfilePanel):
    title = "EXTRUDE"
    icon = "Extrude"
    transaction = "Extrude"
    module = X
    base = "Extrude"

    def build(self):
        self.profile = self.row("Profiles", W.SelectionField(accept_profile, True, "Select profiles"))
        self.profile.changed.connect(self.preview)
        self.direction = self.row("Direction", W.IconCombo([
            (X.ONE_SIDE, "One Side", ""), (X.TWO_SIDES, "Two Sides", ""), (X.SYMMETRIC, "Symmetric", "")]))
        self.extent = self.row("Extent Type", W.IconCombo([
            (X.EXTENT_DISTANCE, "Distance", ""), (X.EXTENT_ALL, "All", ""), (X.EXTENT_TO, "To Object", "")]))
        self.distance = self.row("Distance", W.ValueField(10.0, "mm"), key="distance")
        self.distance2 = self.row("Distance 2", W.ValueField(10.0, "mm"), key="distance2")
        self.taper = self.row("Taper Angle", W.ValueField(0.0, "deg"), key="taper")
        self.to = self.row("To Object", W.SelectionField(accept_face, False, "Select face"), key="to")
        self._operation_row()
        for w in (self.direction, self.extent):
            w.currentIndexChanged.connect(self._layout_changed)
        for w in (self.distance, self.distance2, self.taper):
            w.changed.connect(self.preview)
        self.to.changed.connect(self.preview)
        self._layout_changed()

    def _layout_changed(self, *_):
        ext = self.extent.key()
        self.show_row("distance", ext == X.EXTENT_DISTANCE)
        self.show_row("distance2", ext == X.EXTENT_DISTANCE and self.direction.key() == X.TWO_SIDES)
        self.show_row("to", ext == X.EXTENT_TO)
        self._update_rows()
        if not self._busy and hasattr(self, "profile"):
            self.preview()

    def load_params(self, prm):
        self.direction.set_key(prm.get("direction", X.ONE_SIDE))
        self.extent.set_key(prm.get("extent", X.EXTENT_DISTANCE))
        self.distance.set_value(prm.get("distance", 10.0), prm.get("expr", ""))
        self.distance2.set_value(prm.get("distance2", 10.0), prm.get("expr2", ""))
        self.taper.set_value(prm.get("taper", 0.0))
        if prm.get("to"):
            o = self.doc.getObject(prm["to"][0])
            if o:
                self.to.set_items([(o, prm["to"][1])])
        self._layout_changed()

    def preview(self):
        super(ExtrudePanel, self).preview()
        self._update_arrows()

    def _update_arrows(self):
        refs = self.profile.refs() if hasattr(self, "profile") else []
        if self._closing or not refs or self.extent.key() != X.EXTENT_DISTANCE:
            self.clear_arrows()
            return
        try:
            center = P.profile_center(refs)
            normal = P.profile_normal(refs)
        except Exception:
            center = normal = None
        if center is None or normal is None:
            self.clear_arrows()
            return
        direction = self.direction.key()
        self.set_arrow("distance", center, normal, self.distance,
                       scale=0.5 if direction == X.SYMMETRIC else 1.0)
        if direction == X.TWO_SIDES:
            self.set_arrow("distance2", center, normal * -1, self.distance2, minimum=0.0,
                           flip_with_sign=False)
        else:
            self.drop_arrow("distance2")

    def params(self):
        prm = X.default_params()
        prm["direction"] = self.direction.key()
        prm["extent"] = self.extent.key()
        prm["distance"] = self.distance.value() or 0.0
        prm["expr"] = self.distance.expression()
        prm["distance2"] = self.distance2.value() or 0.0
        prm["expr2"] = self.distance2.expression()
        prm["taper"] = self.taper.value() or 0.0
        if prm["extent"] == X.EXTENT_TO:
            if not self.to.items:
                self.set_hint("Select the face or plane to extrude to.")
                return None
            o, s = self.to.items[0]
            prm["to"] = [o.Name, s]
        if prm["extent"] == X.EXTENT_DISTANCE and abs(prm["distance"]) < 1e-9:
            self.set_hint("Distance must not be zero.", error=True)
            return None
        return prm


class RevolvePanel(_ProfilePanel):
    title = "REVOLVE"
    icon = "Revolve"
    transaction = "Revolve"
    module = R
    base = "Revolve"

    def build(self):
        self.profile = self.row("Profiles", W.SelectionField(accept_profile, True, "Select profiles"))
        self.profile.changed.connect(self._profile_changed)
        self.axis = self.row("Axis", W.SelectionField(accept_axis, False, "Select axis"))
        self.axis.changed.connect(self.preview)
        self.extent = self.row("Type", W.IconCombo([(R.FULL, "Full", ""), (R.ANGLE, "Angle", "")]))
        self.direction = self.row("Direction", W.IconCombo([
            (R.ONE_SIDE, "One Side", ""), (R.TWO_SIDES, "Two Sides", ""), (R.SYMMETRIC, "Symmetric", "")]),
            key="direction")
        self.angle = self.row("Angle", W.ValueField(90.0, "deg", 5.0), key="angle")
        self.angle2 = self.row("Angle 2", W.ValueField(90.0, "deg", 5.0), key="angle2")
        self._operation_row()
        for w in (self.extent, self.direction):
            w.currentIndexChanged.connect(self._layout_changed)
        for w in (self.angle, self.angle2):
            w.changed.connect(self.preview)
        self._layout_changed()

    def _profile_changed(self):
        if self.profile.items and not self.axis.items:
            self.axis.set_active(True)
            self.set_hint("Select an axis: a sketch line, an edge or an origin/construction axis.")
            return
        self.preview()

    def _layout_changed(self, *_):
        full = self.extent.key() == R.FULL
        self.show_row("direction", not full)
        self.show_row("angle", not full)
        self.show_row("angle2", not full and self.direction.key() == R.TWO_SIDES)
        self._update_rows()
        if hasattr(self, "profile") and not self._busy:
            self.preview()

    def load_params(self, prm):
        self.extent.set_key(prm.get("extent", R.FULL))
        self.direction.set_key(prm.get("direction", R.ONE_SIDE))
        self.angle.set_value(prm.get("angle", 90.0), prm.get("expr", ""))
        self.angle2.set_value(prm.get("angle2", 90.0))
        ax = prm.get("axis")
        if ax:
            o = self.doc.getObject(ax[0])
            if o is not None:
                self.axis.set_items([(o, ax[1] if len(ax) > 1 else "")])
        self._layout_changed()

    def params(self):
        if not self.axis.items:
            return None
        o, s = self.axis.items[0]
        prm = R.default_params()
        prm["axis"] = [o.Name, s]
        prm["extent"] = self.extent.key()
        prm["direction"] = self.direction.key()
        prm["angle"] = self.angle.value() or 90.0
        prm["expr"] = self.angle.expression()
        prm["angle2"] = self.angle2.value() or 90.0
        return prm
