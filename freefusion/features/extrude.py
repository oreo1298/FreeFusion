# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion style Extrude built from PartDesign Pad / Pocket / Boolean."""

import FreeCAD as App

from .. import design as D
from . import common as C
from . import profiles as P

ONE_SIDE = "One side"
TWO_SIDES = "Two sides"
SYMMETRIC = "Symmetric"
DIRECTIONS = (ONE_SIDE, TWO_SIDES, SYMMETRIC)

EXTENT_DISTANCE = "Distance"
EXTENT_ALL = "All"
EXTENT_TO = "To Object"
EXTENTS = (EXTENT_DISTANCE, EXTENT_ALL, EXTENT_TO)


def default_params():
    return {
        "direction": ONE_SIDE,
        "extent": EXTENT_DISTANCE,
        "distance": 10.0,
        "distance2": 10.0,
        "taper": 0.0,
        "taper2": 0.0,
        "expr": "",        # expression for distance (user parameters)
        "expr2": "",
        "to": None,        # [objname, sub] for EXTENT_TO
    }


def tool_shape(refs, params):
    """Approximate solid swept by the extrude, used for target detection/preview."""
    faces = P.profile_faces(refs)
    if not faces:
        return None
    n = P.profile_normal(refs)
    d = params.get("distance", 10.0)
    direction = params.get("direction", ONE_SIDE)
    if params.get("extent") == EXTENT_ALL:
        d = 1e4 if d >= 0 else -1e4
    solids = []
    for f in faces:
        try:
            if direction == SYMMETRIC:
                s = f.copy()
                s.translate(n * (-abs(d) / 2.0))
                solids.append(s.extrude(n * abs(d)))
            elif direction == TWO_SIDES:
                solids.append(f.extrude(n * d))
                d2 = params.get("distance2", d)
                solids.append(f.extrude(n * (-abs(d2))))
            else:
                if abs(d) > 1e-9:
                    solids.append(f.extrude(n * d))
        except Exception:
            continue
    if not solids:
        return None
    shape = solids[0]
    for s in solids[1:]:
        try:
            shape = shape.fuse(s)
        except Exception:
            pass
    return shape


def _apply(feature, params, subtractive):
    doc = feature.Document
    direction = params.get("direction", ONE_SIDE)
    extent = params.get("extent", EXTENT_DISTANCE)
    d = float(params.get("distance", 10.0))
    has_side = "SideType" in feature.PropertiesList      # FreeCAD 1.1+
    if has_side:
        feature.SideType = direction
    else:                                               # FreeCAD 1.0
        feature.Midplane = direction == SYMMETRIC
    if not has_side and direction == TWO_SIDES and extent == EXTENT_DISTANCE:
        feature.Type = "TwoLengths"
    elif extent == EXTENT_ALL:
        feature.Type = "ThroughAll" if subtractive else "UpToLast"
    elif extent == EXTENT_TO and params.get("to"):
        name, sub = params["to"]
        target = doc.getObject(name)
        if target is not None:
            feature.Type = "UpToFace"
            feature.UpToFace = (target, [sub]) if sub else target
    else:
        feature.Type = "Length"
    feature.Length = max(abs(d), 1e-6)
    feature.TaperAngle = float(params.get("taper", 0.0))
    if direction == TWO_SIDES:
        feature.Length2 = max(abs(float(params.get("distance2", d))), 1e-6)
        feature.TaperAngle2 = float(params.get("taper2", 0.0))
    expr = params.get("expr") or ""
    try:
        feature.setExpression("Length", expr if expr else None)
    except Exception:
        pass
    expr2 = params.get("expr2") or ""
    if direction == TWO_SIDES:
        try:
            feature.setExpression("Length2", expr2 if expr2 else None)
        except Exception:
            pass
    # Pad grows along the profile normal; Pocket against it. A positive distance
    # always means "along the profile normal", like dragging Fusion's arrow.
    want_along = d >= 0
    feature.Reversed = want_along if subtractive else (not want_along)


def _make_pad(params):
    def make(body, binder):
        f = body.newObject("PartDesign::Pad", "Extrude")
        f.Profile = binder
        if "AllowMultiFace" in f.PropertiesList:
            f.AllowMultiFace = True
        _apply(f, params, subtractive=False)
        return f
    return make


def _make_pocket(params):
    def make(body, binder):
        f = body.newObject("PartDesign::Pocket", "Extrude")
        f.Profile = binder
        if "AllowMultiFace" in f.PropertiesList:
            f.AllowMultiFace = True
        _apply(f, params, subtractive=True)
        return f
    return make


def orient(feats, refs, params):
    """Make every feature's material go in the requested direction."""
    if params.get("direction", ONE_SIDE) == SYMMETRIC:
        return
    if params.get("extent") == EXTENT_TO:
        return
    center = P.profile_center(refs)
    normal = P.profile_normal(refs)
    sign = 1.0 if float(params.get("distance", 10.0)) >= 0 else -1.0
    changed = False
    for f in feats:
        if f.isDerivedFrom("PartDesign::Boolean"):
            # the tool body's pad carries the geometry
            for tool in getattr(f, "Group", []):
                tip = getattr(tool, "Tip", None)
                if tip is not None and tip.isDerivedFrom("PartDesign::FeatureExtrude"):
                    changed |= C.fix_direction(tip, center, normal, sign)
            continue
        if params.get("direction") == TWO_SIDES:
            d1 = abs(float(params.get("distance", 10.0)))
            d2 = abs(float(params.get("distance2", d1)))
            if abs(d1 - d2) < 1e-9:
                continue
            s = sign if d1 > d2 else -sign
        else:
            s = sign
        changed |= C.fix_direction(f, center, normal, s)
    if changed:
        feats[0].Document.recompute()


def create(doc, refs, params=None, operation=None, targets=None, label=None, gid=None,
           insert_after=None, hide=True):
    """Create an Extrude. Returns the common.Built result."""
    params = dict(default_params(), **(params or {}))
    refs = P.normalize_refs(refs)
    if not refs:
        raise ValueError("Extrude needs a profile")
    if gid is None or label is None:
        label, gid = D.new_group_id(doc, "Extrude")
    shape = tool_shape(refs, params)
    if operation is None:
        operation = C.auto_operation(doc, refs, shape, 1.0 if params["distance"] >= 0 else -1.0)
    if targets is None:
        targets = C.default_targets(doc, refs, operation, shape)
    if operation in (C.CUT, C.INTERSECT) and not targets:
        raise ValueError("Nothing to %s: the extrude does not intersect any body"
                         % operation.lower())
    res = C.build_operation(doc, refs, operation, targets, gid, label,
                            _make_pad(params), _make_pocket(params), insert_after)
    prim = res.primary
    D.tag(prim, role=D.ROLE_FEATURE, op="Extrude", data={
        "type": "Extrude",
        "profiles": P.refs_to_json(refs),
        "params": params,
        "operation": operation,
        "targets": [b.Name for b in targets],
    })
    doc.recompute()
    orient(res.features, refs, params)
    if hide:
        hide_profiles(refs)
    return res


def hide_profiles(refs):
    """Fusion hides a sketch once a feature consumed it."""
    for o, _ in refs:
        if D.is_sketch(o):
            D.hide_object(o)


def load(doc, gid):
    """Return (refs, params, operation, targets) stored for an extrude group."""
    primary, feats, _ = C.group_state(doc, gid)
    if primary is None:
        return None
    info = D.data(primary)
    refs = P.refs_from_json(doc, info.get("profiles"))
    params = dict(default_params(), **info.get("params", {}))
    targets = [doc.getObject(n) for n in info.get("targets", [])]
    targets = [t for t in targets if t is not None]
    return refs, params, info.get("operation", C.JOIN), targets


def update(doc, gid, refs, params, operation, targets, hide=True):
    """Modify an existing extrude in place when possible, else rebuild it."""
    primary, feats, members = C.group_state(doc, gid)
    old = load(doc, gid)
    refs = P.normalize_refs(refs)
    if old is not None:
        o_refs, o_params, o_op, o_targets = old
        same_structure = (o_op == operation and [t.Name for t in o_targets] == [t.Name for t in targets]
                          and P.refs_to_json(o_refs) == P.refs_to_json(refs))
    else:
        same_structure = False
    if same_structure and feats:
        for f in feats:
            if f.isDerivedFrom("PartDesign::Boolean"):
                for tool in getattr(f, "Group", []):
                    tip = getattr(tool, "Tip", None)
                    if tip is not None:
                        _apply(tip, params, subtractive=False)
            else:
                _apply(f, params, subtractive=f.isDerivedFrom("PartDesign::Pocket"))
        info = D.data(primary)
        info["params"] = params
        D.tag(primary, data=info)
        doc.recompute()
        orient(feats, refs, params)
        return primary
    label = primary.Label if primary is not None else gid
    points = C.insertion_points(doc, gid)
    C.remove_group(doc, gid)
    doc.recompute()
    res = create(doc, refs, params, operation, targets, label=label, gid=gid,
                 insert_after={k: v for k, v in points.items() if v is not None}, hide=hide)
    return res.primary
