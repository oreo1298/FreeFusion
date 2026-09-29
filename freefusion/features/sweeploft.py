# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion style Sweep and Loft on PartDesign AdditivePipe / AdditiveLoft."""

import FreeCAD as App

from .. import design as D
from . import common as C
from . import profiles as P


def _profile_sub(binder):
    """Pipe/Loft need an explicit element when the profile is not a sketch."""
    shp = binder.Shape
    if shp is not None and not shp.isNull():
        if shp.Faces:
            return "Face1"
        if shp.Wires:
            return "Wire1"
    return "Face1"


def _tool_from(res_shape_fn):
    try:
        return res_shape_fn()
    except Exception:
        return None


def sweep(doc, profile_refs, path_refs, operation=None, targets=None, orientation="Standard"):
    profile_refs = P.normalize_refs(profile_refs)
    path_refs = P.normalize_refs(path_refs)
    if not profile_refs or not path_refs:
        raise ValueError("Sweep needs a profile and a path")
    label, gid = D.new_group_id(doc, "Sweep")

    def tool():
        import Part
        faces = P.profile_faces(profile_refs)
        edges = []
        for o, subs in path_refs:
            shp = o.Shape if not subs else Part.Compound([o.getSubObject(s) for s in subs])
            edges.extend(shp.Edges)
        wire = Part.Wire(Part.__sortEdges__(edges))
        return wire.makePipeShell([faces[0].OuterWire], True, True)

    shape = _tool_from(tool)
    if operation is None:
        operation = C.auto_operation(doc, profile_refs, shape)
    if targets is None:
        targets = C.default_targets(doc, profile_refs, operation, shape)

    def spine(body):
        b = D.make_binder(body, path_refs, gid)
        n = len(b.Shape.Edges) if b.Shape and not b.Shape.isNull() else 1
        return (b, ["Edge%d" % (i + 1) for i in range(max(n, 1))])

    def make(kind):
        def fn(body, binder):
            f = body.newObject("PartDesign::%sPipe" % kind, "Sweep")
            doc.recompute()
            f.Profile = (binder, [_profile_sub(binder)])
            f.Spine = spine(body)
            f.Mode = orientation
            return f
        return fn

    res = C.build_operation(doc, profile_refs, operation, targets, gid, label, make("Additive"),
                            make("Subtractive"))
    D.tag(res.primary, role=D.ROLE_FEATURE, op="Sweep", data={
        "type": "Sweep", "profiles": P.refs_to_json(profile_refs), "path": P.refs_to_json(path_refs),
        "operation": operation, "targets": [b.Name for b in targets]})
    doc.recompute()
    for o, _ in profile_refs + path_refs:
        if D.is_sketch(o):
            D.hide_object(o)
    return res


def loft(doc, sections, operation=None, targets=None, ruled=False, closed=False):
    """sections: list of profile refs lists, e.g. [[(sk1, [])], [(sk2, [])]]."""
    sections = [P.normalize_refs(s) for s in sections if s]
    if len(sections) < 2:
        raise ValueError("Loft needs at least two profiles")
    label, gid = D.new_group_id(doc, "Loft")

    def tool():
        import Part
        wires = [P.profile_faces(s)[0].OuterWire for s in sections]
        return Part.makeLoft(wires, True, ruled, closed)

    shape = _tool_from(tool)
    first = sections[0]
    if operation is None:
        operation = C.auto_operation(doc, first, shape)
    if targets is None:
        targets = C.default_targets(doc, first, operation, shape)

    def make(kind):
        def fn(body, binder):
            f = body.newObject("PartDesign::%sLoft" % kind, "Loft")
            secs = [D.make_binder(body, s, gid) for s in sections[1:]]
            doc.recompute()
            f.Profile = (binder, [_profile_sub(binder)])
            f.Sections = [(b, [_profile_sub(b)]) for b in secs]
            f.Ruled = ruled
            f.Closed = closed
            return f
        return fn

    res = C.build_operation(doc, first, operation, targets, gid, label, make("Additive"),
                            make("Subtractive"))
    D.tag(res.primary, role=D.ROLE_FEATURE, op="Loft", data={
        "type": "Loft", "sections": [P.refs_to_json(s) for s in sections],
        "operation": operation, "targets": [b.Name for b in targets]})
    doc.recompute()
    for s in sections:
        for o, _ in s:
            if D.is_sketch(o):
                D.hide_object(o)
    return res
