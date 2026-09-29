# SPDX-License-Identifier: LGPL-2.1-or-later
"""Body level operations: Combine, Split Body, Scale, Press Pull."""

import FreeCAD as App

from .. import design as D
from . import common as C
from . import extrude as X

def consume(feature, bodies):
    """Remove input bodies from the browser; delete_item() restores them."""
    info = D.data(feature)
    info["consumed"] = sorted(set(info.get("consumed", [])) | {b.Name for b in bodies})
    D.tag(feature, data=info)
    for b in bodies:
        D.tag(b, role=D.ROLE_CONSUMED)


BOOL_TYPES = {C.JOIN: "Fuse", C.CUT: "Cut", C.INTERSECT: "Common"}
PART_BOOL = {C.JOIN: "Part::MultiFuse", C.CUT: "Part::Cut", C.INTERSECT: "Part::MultiCommon"}


def combine(doc, target, tools, operation=C.JOIN, keep_tools=False, label=None):
    """Fusion Combine: merge/cut/intersect tool bodies into the target body."""
    tools = [t for t in tools if t is not None and t != target]
    if target is None or not tools:
        raise ValueError("Combine needs a target body and at least one tool body")
    label_, gid = D.new_group_id(doc, "Combine")
    label = label or label_
    if D.is_body(target):
        feat = target.newObject("PartDesign::Boolean", "Combine")
        feat.Type = BOOL_TYPES[operation]
        feat.setObjects(list(tools))
        feat.Label = label
        feat.Refine = True
        D.tag(feat, role=D.ROLE_FEATURE, group=gid, op="Combine",
              data={"type": "Combine", "operation": operation, "keep": keep_tools,
                    "tools": [t.Name for t in tools]})
        doc.recompute()
        for t in tools:
            if keep_tools:
                D.show_object(t)
            else:
                D.hide_object(t)
        if not keep_tools:
            consume(feat, tools)
        return feat
    # plain Part solids (e.g. split results): Part booleans
    container = D.component_of(target) or D.active_component(doc)
    if operation == C.CUT:
        feat = doc.addObject("Part::Cut", "Combine")
        base = target
        if len(tools) > 1:
            fuse = doc.addObject("Part::MultiFuse", "CombineTools")
            fuse.Shapes = tools
            D.add_to(container, fuse)
            D.tag(fuse, group=gid)
            D.hide_object(fuse)
            tool = fuse
        else:
            tool = tools[0]
        feat.Base = base
        feat.Tool = tool
    else:
        feat = doc.addObject(PART_BOOL[operation], "Combine")
        feat.Shapes = [target] + list(tools)
    feat.Label = label
    D.add_to(container, feat)
    D.tag(feat, role=D.ROLE_BODY, group=gid, op="Combine",
          data={"type": "Combine", "operation": operation})
    try:
        feat.Refine = True
    except Exception:
        pass
    doc.recompute()
    D.hide_object(target)
    for t in tools:
        if keep_tools:
            D.show_object(t)
        else:
            D.hide_object(t)
    # the combined result replaces the target in the browser
    consume(feat, [target] + ([] if keep_tools else list(tools)))
    return feat


def split_body(doc, body, tools):
    """Fusion Split Body: slice a body with planes/faces/bodies into new bodies."""
    import BOPTools.SplitFeatures as SF
    from CompoundTools.CompoundFilter import makeCompoundFilter

    label, gid = D.new_group_id(doc, "Split")
    container = D.component_of(body) or D.active_component(doc)
    sl = SF.makeSlice("Split")
    D.add_to(container, sl)
    sl.Base = body
    sl.Tools = list(tools)
    sl.Mode = "Split"
    sl.Label = label
    D.tag(sl, role=D.ROLE_FEATURE, group=gid, op="Split", data={"type": "Split"})
    doc.recompute()
    pieces = []
    n = len(sl.Shape.Solids) if sl.Shape and not sl.Shape.isNull() else 0
    for i in range(n):
        f = makeCompoundFilter("SplitBody")
        f.Base = sl
        f.FilterType = "specific items"
        f.items = str(i)
        f.Label = D.unique_label(doc, "Body")
        D.add_to(container, f)
        D.tag(f, role=D.ROLE_BODY, group=gid)
        pieces.append(f)
    D.hide_object(sl)
    D.hide_object(body)
    consume(sl, [body])
    for t in tools:
        D.hide_object(t)
    doc.recompute()
    return sl, pieces


def scale_body(doc, body, factor, uniform=True, factors=None, label=None):
    label_, gid = D.new_group_id(doc, "Scale")
    container = D.component_of(body) or D.active_component(doc)
    sc = doc.addObject("Part::Scale", "Scale")
    sc.Base = body
    if uniform or factors is None:
        sc.Uniform = True
        sc.UniformScale = factor
    else:
        sc.Uniform = False
        sc.XScale, sc.YScale, sc.ZScale = factors
    sc.Label = label or label_
    D.add_to(container, sc)
    D.tag(sc, role=D.ROLE_BODY, group=gid, op="Scale", data={"type": "Scale"})
    doc.recompute()
    D.hide_object(body)
    consume(sc, [body])
    return sc


def press_pull(doc, feature, faces, distance, expr=""):
    """Press Pull on planar faces: extrude them outward (join) or inward (cut)."""
    refs = [(feature, list(faces))]
    op = C.JOIN if distance >= 0 else C.CUT
    body = D.body_of(feature)
    targets = [body] if body is not None else None
    label, gid = D.new_group_id(doc, "PressPull")
    params = {"distance": distance, "expr": expr}
    res = X.create(doc, refs, params, operation=op, targets=targets, label=label, gid=gid)
    D.tag(res.primary, op="PressPull")
    return res
