# SPDX-License-Identifier: LGPL-2.1-or-later
"""FILLET and CHAMFER on edges of bodies (PartDesign dress-up features).

Like Fusion, one command can round edges of several bodies (one feature per body)
and extends the selection along tangent-continuous edges ("Tangent Chain").
"""

import FreeCAD as App

from .. import design as D

FILLET = "Fillet"
CHAMFER = "Chamfer"
EQUAL = "Equal distance"
TWO_DISTANCES = "Two distances"
DISTANCE_ANGLE = "Distance and Angle"


def _base_feature(obj):
    """The feature whose shape the edge names refer to."""
    if D.is_body(obj):
        return obj.Tip
    return obj


def _key(p):
    return (round(p.x, 5), round(p.y, 5), round(p.z, 5))


def _tangent_at(edge, point):
    try:
        u = edge.Curve.parameter(point)
        return edge.tangentAt(u)
    except Exception:
        return None


def tangent_chain(shape, names):
    """Extend edge names with every edge joined to them with tangent continuity."""
    edges = shape.Edges
    by_vertex = {}
    for i, e in enumerate(edges):
        for v in e.Vertexes:
            by_vertex.setdefault(_key(v.Point), []).append(i)
    todo = []
    out = []
    for n in names:
        if n.startswith("Edge"):
            try:
                todo.append(int(n[4:]) - 1)
            except ValueError:
                pass
        if n not in out:
            out.append(n)
    seen = set(todo)
    while todo:
        i = todo.pop()
        e = edges[i]
        for v in e.Vertexes:
            t1 = _tangent_at(e, v.Point)
            if t1 is None:
                continue
            for j in by_vertex.get(_key(v.Point), []):
                if j in seen:
                    continue
                t2 = _tangent_at(edges[j], v.Point)
                if t2 is None or t1.Length < 1e-9 or t2.Length < 1e-9:
                    continue
                c = abs(t1.normalize().dot(t2.normalize()))
                if c > 0.9999:
                    seen.add(j)
                    todo.append(j)
                    out.append("Edge%d" % (j + 1))
    return out


def group_refs(refs):
    """[(obj, [subs])] -> {body: (base_feature, [subs])}, keeping order."""
    out = []
    for obj, subs in refs:
        base = _base_feature(obj)
        body = D.body_of(base)
        if body is None:
            raise ValueError("Fillet and chamfer work on edges of bodies")
        for b, (f, s) in out:
            if b == body and f == base:
                s.extend(x for x in subs if x not in s)
                break
        else:
            out.append((body, (base, list(subs))))
    return out


def _apply(feat, kind, params):
    if kind == FILLET:
        feat.Radius = params.get("radius", 1.0)
        if params.get("expr"):
            feat.setExpression("Radius", params["expr"])
    else:
        ctype = params.get("type", EQUAL)
        try:
            feat.ChamferType = ctype
        except Exception:
            pass
        feat.Size = params.get("distance", 1.0)
        if params.get("expr"):
            feat.setExpression("Size", params["expr"])
        if ctype == TWO_DISTANCES:
            feat.Size2 = params.get("distance2", params.get("distance", 1.0))
        elif ctype == DISTANCE_ANGLE:
            feat.Angle = params.get("angle", 45.0)
    try:
        feat.Refine = True
    except Exception:
        pass


def _subs(shape, subs, chain):
    return tangent_chain(shape, subs) if chain else list(subs)


def create(doc, kind, refs, params, label=None, gid=None):
    """Create one dress-up feature per body. Returns the created features."""
    if label is None:
        label, gid = D.new_group_id(doc, kind)
    chain = params.get("tangent_chain", True)
    feats = []
    for body, (base, subs) in group_refs(refs):
        if not subs:
            continue
        feat = body.newObject("PartDesign::" + kind, kind)
        feat.Base = (base, _subs(base.Shape, subs, chain))
        _apply(feat, kind, params)
        feat.Label = label if not feats else D.unique_label(doc, label)
        D.tag(feat, role=D.ROLE_FEATURE, group=gid, op=kind,
              data={"type": kind, "params": {k: v for k, v in params.items()},
                    "selected": [base.Name, list(subs)]})
        feats.append(feat)
    doc.recompute()
    return feats


def load(doc, gid):
    """(refs, params) of an existing Fillet/Chamfer group."""
    refs, prm = [], {}
    for f in D.group_members(doc, gid):
        info = D.data(f)
        prm = dict(info.get("params", {}))
        sel = info.get("selected")
        base = doc.getObject(sel[0]) if sel else None
        if base is not None:
            refs.append((base, list(sel[1])))
        elif f.Base:
            refs.append((f.Base[0], list(f.Base[1])))
    return refs, prm


def update(doc, gid, kind, refs, params):
    """Change edges and values of the group's features in place (keeps history)."""
    feats = [f for f in D.group_members(doc, gid) if D.is_pd_feature(f)]
    grouped = dict((b.Name, v) for b, v in group_refs(refs))
    chain = params.get("tangent_chain", True)
    for f in feats:
        body = D.body_of(f)
        base, subs = grouped.pop(body.Name, (None, None))
        if base is None:
            continue
        f.Base = (base, _subs(base.Shape, subs, chain))
        _apply(f, kind, params)
        info = D.data(f)
        info["params"] = dict(params)
        info["selected"] = [base.Name, list(subs)]
        D.tag(f, data=info)
    doc.recompute()
    return feats


def edge_frame(obj, sub):
    """(point, inward direction) at the middle of an edge of a solid, for the drag arrow."""
    shape = _base_feature(obj).Shape
    edge = obj.getSubObject(sub) if not D.is_body(obj) else _base_feature(obj).getSubObject(sub)
    edge = edge.Edges[0]
    u0, u1 = edge.ParameterRange
    mid = edge.valueAt((u0 + u1) / 2.0)
    normals = []
    try:
        faces = shape.ancestorsOfType(edge, __import__("Part").Face)
    except Exception:
        faces = [f for f in shape.Faces if any(e.isSame(edge) for e in f.Edges)]
    for f in faces[:2]:
        try:
            u, v = f.Surface.parameter(mid)
            normals.append(f.normalAt(u, v))
        except Exception:
            pass
    s = App.Vector()
    for n in normals:
        s = s + n
    if s.Length < 1e-9:
        return mid, None
    return mid, s.normalize() * -1


def map_element(feature, name, base):
    """Name of the edge/face in `base` with the same geometry as `name` in `feature`."""
    try:
        el = feature.getSubObject(name)
    except Exception:
        return None
    if el is None:
        return None
    kind = "Edge" if name.startswith("Edge") else "Face"
    items = base.Shape.Edges if kind == "Edge" else base.Shape.Faces
    c = el.CenterOfMass if kind == "Face" else el.valueAt(sum(el.ParameterRange) / 2.0)
    size = el.Area if kind == "Face" else el.Length
    for i, it in enumerate(items):
        try:
            ci = it.CenterOfMass if kind == "Face" else it.valueAt(sum(it.ParameterRange) / 2.0)
            si = it.Area if kind == "Face" else it.Length
        except Exception:
            continue
        if (ci - c).Length < 1e-6 and abs(si - size) < 1e-6:
            return "%s%d" % (kind, i + 1)
    return None
