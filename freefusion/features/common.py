# SPDX-License-Identifier: LGPL-2.1-or-later
"""Shared machinery for Fusion style profile features (Extrude, Revolve, Sweep...).

Fusion's operation drop-down is implemented here:

  Join          additive feature in the target body
  Cut           subtractive feature in *every* target body
  Intersect     hidden tool body + PartDesign::Boolean(Common) in every target
  New Body      new PartDesign::Body in the profile's component
  New Component new App::Part (+ body) inside the active component
"""

import FreeCAD as App

from .. import design as D
from . import profiles as P

JOIN = "Join"
CUT = "Cut"
INTERSECT = "Intersect"
NEW_BODY = "NewBody"
NEW_COMPONENT = "NewComponent"
OPERATIONS = (JOIN, CUT, INTERSECT, NEW_BODY, NEW_COMPONENT)
OPERATION_LABELS = {
    JOIN: "Join",
    CUT: "Cut",
    INTERSECT: "Intersect",
    NEW_BODY: "New Body",
    NEW_COMPONENT: "New Component",
}


class Built(object):
    """Result of building a profile feature."""

    def __init__(self):
        self.features = []        # additive/subtractive/boolean features
        self.objects = []         # everything created (for cleanup)
        self.primary = None
        self.new_bodies = []
        self.new_components = []

    def add(self, obj):
        if obj not in self.objects:
            self.objects.append(obj)
        return obj


def _container_for_new_body(doc, refs):
    sk = P.sketch_of_refs(refs)
    if sk is not None:
        comp = D.component_of(sk)
        if comp is not None:
            return comp
    return D.active_component(doc)


class TipGuard(object):
    """Insert new features right after ``after`` in body, then restore the Tip.

    PartDesign inserts new features after the body's Tip. When re-building a feature
    that sits in the middle of the history we temporarily move the Tip back.
    """

    def __init__(self, body, after=None):
        self.body = body
        self.after = after
        self.old_tip = None

    def __enter__(self):
        self.old_tip = self.body.Tip
        if self.after is not None and self.after != self.old_tip:
            self.body.Tip = self.after
        return self

    def __exit__(self, *exc):
        if self.after is not None and self.old_tip is not None and self.old_tip != self.after:
            try:
                if self.old_tip in self.body.Group:
                    self.body.Tip = self.old_tip
            except Exception:
                pass
        return False


def build_operation(doc, refs, operation, targets, gid, label, make_add, make_sub,
                    insert_after=None):
    """Create the FreeCAD objects for a profile feature.

    make_add(body, binder) / make_sub(body, binder) create and return a PartDesign
    feature (already added to body). ``targets`` are bodies for Join/Cut/Intersect.
    ``insert_after`` maps body name -> feature to insert after (editing mid-history).
    """
    insert_after = insert_after or {}
    res = Built()
    refs = P.normalize_refs(refs)

    def binder_for(body):
        b = D.make_binder(body, refs, gid)
        res.add(b)
        return b

    def guard(body):
        return TipGuard(body, insert_after.get(body.Name))

    if operation in (NEW_BODY, NEW_COMPONENT):
        container = _container_for_new_body(doc, refs)
        if operation == NEW_COMPONENT:
            comp = D.new_component(doc, parent=D.active_component(doc))
            D.tag(comp, group=gid)
            res.add(comp)
            res.new_components.append(comp)
            container = comp
        body = D.new_body(doc, container)
        D.tag(body, group=gid)
        res.add(body)
        res.new_bodies.append(body)
        feat = make_add(body, binder_for(body))
        res.features.append(res.add(feat))

    elif operation == JOIN:
        body = targets[0] if targets else None
        if body is None:
            body = D.new_body(doc, _container_for_new_body(doc, refs))
            D.tag(body, group=gid)
            res.add(body)
            res.new_bodies.append(body)
        with guard(body):
            feat = make_add(body, binder_for(body))
        res.features.append(res.add(feat))

    elif operation == CUT:
        for body in targets:
            with guard(body):
                feat = make_sub(body, binder_for(body))
            res.features.append(res.add(feat))

    elif operation == INTERSECT:
        for body in targets:
            container = D.component_of(body) or D.active_component(doc)
            tool = D.new_body(doc, container, label="%s tool" % label)
            D.tag(tool, role=D.ROLE_TOOL, group=gid)
            res.add(tool)
            tfeat = make_add(tool, binder_for(tool))
            res.add(tfeat)
            D.hide_object(tool)
            with guard(body):
                boolean = body.newObject("PartDesign::Boolean", "Intersect")
                boolean.Type = "Common"
                try:
                    boolean.setObjects([tool])
                except Exception:
                    boolean.addObject(tool)
            res.features.append(res.add(boolean))
            D.hide_object(tool)
    else:
        raise ValueError("Unknown operation %r" % operation)

    for i, f in enumerate(res.features):
        f.Label = label if i == 0 else "%s (%s)" % (label, (D.body_of(f).Label if D.body_of(f) else i))
        if "Refine" in f.PropertiesList:
            f.Refine = True
    for o in res.objects:
        D.tag(o, group=gid)
    res.primary = res.features[0] if res.features else None
    return res


def group_state(doc, gid):
    """(primary, features, bodies) of an existing feature group."""
    members = D.group_members(doc, gid)
    feats = [o for o in members if D.is_pd_feature(o) and D.role(o) != D.ROLE_BINDER
             and D.role(D.body_of(o)) != D.ROLE_TOOL]
    feats.sort(key=lambda o: o.ID)
    primary = feats[0] if feats else None
    return primary, feats, members


def insertion_points(doc, gid):
    """body name -> feature preceding this group's feature in that body."""
    points = {}
    for o in D.group_members(doc, gid):
        if not D.is_pd_feature(o) or D.role(o) == D.ROLE_BINDER:
            continue
        body = D.body_of(o)
        if body is None or D.role(body) == D.ROLE_TOOL:
            continue
        base = getattr(o, "BaseFeature", None)
        if o != body.Tip:
            points[body.Name] = base
    return points


def remove_group(doc, gid, keep=()):
    members = [o for o in D.group_members(doc, gid) if o not in keep]
    # remove features before bodies/components
    members.sort(key=lambda o: (D.is_component(o) or D.is_body(o), -o.ID))
    D.remove_objects(members)


def fix_direction(feature, center, direction, sign=1.0):
    """Flip feature.Reversed if its added/removed material points the wrong way.

    The profile normal of a SubShapeBinder is computed by fitting a plane, which can
    point either way. We compare where the material actually went with the intended
    direction and correct it.
    """
    try:
        shape = feature.AddSubShape
    except Exception:
        return False
    if shape is None or shape.isNull():
        return False
    v = shape.BoundBox.Center - center
    if v.Length < 1e-9:
        return False
    if v.dot(direction) * sign < 0:
        feature.Reversed = not feature.Reversed
        feature.Document.recompute()
        return True
    return False


def default_targets(doc, refs, operation, tool_shape):
    """Fusion's automatic target choice for an operation."""
    owner = P.owning_body(refs)
    if operation == JOIN:
        if owner is not None:
            return [owner]
        hits = D.bodies_intersecting(doc, tool_shape)
        return hits[:1]
    if operation in (CUT, INTERSECT):
        hits = D.bodies_intersecting(doc, tool_shape)
        if not hits and owner is not None:
            hits = [owner]
        return hits
    return []


def auto_operation(doc, refs, tool_shape, distance_sign=1.0):
    """Guess the operation Fusion would pre-select."""
    owner = P.owning_body(refs)
    if owner is not None:
        return CUT if distance_sign < 0 else JOIN
    if D.bodies_intersecting(doc, tool_shape):
        return JOIN
    return NEW_BODY
