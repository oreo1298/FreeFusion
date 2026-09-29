# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion style Revolve built from PartDesign Revolution / Groove / Boolean."""

import FreeCAD as App

from .. import design as D
from . import common as C
from . import profiles as P

ONE_SIDE = "One side"
TWO_SIDES = "Two sides"
SYMMETRIC = "Symmetric"
DIRECTIONS = (ONE_SIDE, TWO_SIDES, SYMMETRIC)
FULL = "Full"
ANGLE = "Angle"
EXTENTS = (ANGLE, FULL)


def default_params():
    return {"direction": ONE_SIDE, "extent": FULL, "angle": 360.0, "angle2": 90.0,
            "expr": "", "axis": None}


def axis_line(doc, axis):
    """(point, direction) of an axis reference [objname, sub] in global coordinates."""
    if not axis:
        return None
    obj = doc.getObject(axis[0])
    if obj is None:
        return None
    sub = axis[1] if len(axis) > 1 else ""
    try:
        shp = obj.getSubObject(sub) if sub else obj.Shape
    except Exception:
        shp = None
    if shp is None or shp.isNull() or not shp.Edges:
        return None
    e = shp.Edges[0]
    try:
        p0 = e.Vertexes[0].Point
        p1 = e.Vertexes[-1].Point
        d = p1 - p0
        if d.Length < 1e-9:
            raise ValueError
        d.normalize()
        return p0, d
    except Exception:
        try:
            # circular edge -> its axis
            c = e.Curve
            return c.Center, c.Axis
        except Exception:
            return None


def tool_shape(doc, refs, params):
    faces = P.profile_faces(refs)
    line = axis_line(doc, params.get("axis"))
    if not faces or line is None:
        return None
    p, d = line
    ang = 360.0 if params.get("extent") == FULL else float(params.get("angle", 360.0))
    shapes = []
    for f in faces:
        try:
            s = f.revolve(p, d, ang)
            shapes.append(s)
        except Exception:
            pass
    if not shapes:
        return None
    out = shapes[0]
    for s in shapes[1:]:
        try:
            out = out.fuse(s)
        except Exception:
            pass
    return out


def _apply(feature, params, axis_binder):
    feature.ReferenceAxis = (axis_binder, ["Edge1"])
    direction = params.get("direction", ONE_SIDE)
    full = params.get("extent", FULL) == FULL
    angle = 360.0 if full else max(0.001, min(360.0, abs(float(params.get("angle", 360.0)))))
    if direction == TWO_SIDES and not full:
        feature.Type = "TwoAngles"
        feature.Angle2 = max(0.001, min(360.0, abs(float(params.get("angle2", 90.0)))))
    else:
        feature.Type = "Angle"
    feature.Angle = angle
    feature.Midplane = direction == SYMMETRIC and not full
    feature.Reversed = float(params.get("angle", 360.0)) < 0
    expr = params.get("expr") or ""
    try:
        feature.setExpression("Angle", expr if (expr and not full) else None)
    except Exception:
        pass


def create(doc, refs, params=None, operation=None, targets=None, label=None, gid=None,
           insert_after=None):
    params = dict(default_params(), **(params or {}))
    refs = P.normalize_refs(refs)
    if not refs:
        raise ValueError("Revolve needs a profile")
    if not params.get("axis"):
        raise ValueError("Revolve needs an axis")
    axis_obj = doc.getObject(params["axis"][0])
    axis_sub = params["axis"][1] if len(params["axis"]) > 1 else ""
    if label is None or gid is None:
        label, gid = D.new_group_id(doc, "Revolve")
    shape = tool_shape(doc, refs, params)
    if operation is None:
        operation = C.auto_operation(doc, refs, shape)
    if targets is None:
        targets = C.default_targets(doc, refs, operation, shape)
    if operation in (C.CUT, C.INTERSECT) and not targets:
        raise ValueError("Nothing to %s: the revolve does not intersect any body" % operation.lower())

    def axis_binder(body):
        b = D.make_binder(body, [(axis_obj, [axis_sub] if axis_sub else [])], gid)
        return b

    def make_add(body, binder):
        f = body.newObject("PartDesign::Revolution", "Revolve")
        f.Profile = binder
        _apply(f, params, axis_binder(body))
        return f

    def make_sub(body, binder):
        f = body.newObject("PartDesign::Groove", "Revolve")
        f.Profile = binder
        _apply(f, params, axis_binder(body))
        return f

    res = C.build_operation(doc, refs, operation, targets, gid, label, make_add, make_sub,
                            insert_after)
    D.tag(res.primary, role=D.ROLE_FEATURE, op="Revolve", data={
        "type": "Revolve", "profiles": P.refs_to_json(refs), "params": params,
        "operation": operation, "targets": [b.Name for b in targets]})
    doc.recompute()
    for o, _ in refs:
        if D.is_sketch(o):
            D.hide_object(o)
    return res


def load(doc, gid):
    primary, feats, _ = C.group_state(doc, gid)
    if primary is None:
        return None
    info = D.data(primary)
    refs = P.refs_from_json(doc, info.get("profiles"))
    params = dict(default_params(), **info.get("params", {}))
    targets = [t for t in (doc.getObject(n) for n in info.get("targets", [])) if t is not None]
    return refs, params, info.get("operation", C.JOIN), targets


def update(doc, gid, refs, params, operation, targets):
    primary, _, _ = C.group_state(doc, gid)
    label = primary.Label if primary is not None else gid
    points = C.insertion_points(doc, gid)
    C.remove_group(doc, gid)
    doc.recompute()
    return create(doc, refs, params, operation, targets, label=label, gid=gid,
                  insert_after={k: v for k, v in points.items() if v is not None}).primary
