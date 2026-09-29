# SPDX-License-Identifier: LGPL-2.1-or-later
"""Profiles: the closed regions / planar faces a feature like Extrude consumes.

A profile reference is ``(obj, [sub, ...])``:
  * ``(sketch, [])``                   the whole sketch (all closed loops)
  * ``(sketch, ["InternalFace2"])``    one region of a sketch (Fusion 'profile')
  * ``(feature, ["Face6"])``           a planar face of a solid
"""

import FreeCAD as App
import Part

from .. import design as D

Z = App.Vector(0, 0, 1)


def normalize_refs(refs):
    """Merge refs of the same object and resolve bodies to their Tip feature."""
    merged = {}
    order = []
    for obj, subs in refs:
        if obj is None:
            continue
        if D.is_body(obj):
            tip = obj.Tip
            if tip is None:
                continue
            subs = [s.split(".")[-1] for s in subs]
            obj = tip
        subs = [s for s in (subs or []) if s]
        # whole-sketch selection wins over sub regions
        if obj.Name not in merged:
            merged[obj.Name] = (obj, [])
            order.append(obj.Name)
        cur = merged[obj.Name][1]
        if not subs:
            merged[obj.Name] = (obj, [])
            merged[obj.Name + "#whole"] = True
        elif not merged.get(obj.Name + "#whole"):
            for s in subs:
                if s not in cur:
                    cur.append(s)
    return [merged[n] for n in order]


def refs_from_selection(sel_ex):
    """Turn Gui.Selection.getSelectionEx() into profile refs."""
    refs = []
    for s in sel_ex:
        obj = s.Object
        subs = [n for n in s.SubElementNames if n]
        if D.is_sketch(obj):
            regions = [n for n in subs if n.startswith("InternalFace") or n.startswith("Face")]
            if regions:
                refs.append((obj, regions))
            else:
                refs.append((obj, []))   # edges/vertices/whole -> whole sketch
        else:
            faces = [n for n in subs if n.startswith("Face")]
            if faces:
                refs.append((obj, faces))
    return normalize_refs(refs)


def sketch_faces(sk):
    """Faces of a sketch in global coordinates."""
    shape = sk.Shape
    if shape.isNull() or not shape.Wires:
        return []
    closed = [w for w in shape.Wires if w.isClosed()]
    if not closed:
        return []
    try:
        f = Part.makeFace(closed, "Part::FaceMakerBullseye")
        return list(f.Faces)
    except Exception:
        faces = []
        for w in closed:
            try:
                faces.append(Part.Face(w))
            except Exception:
                pass
        return faces


def ref_faces(obj, subs):
    if D.is_sketch(obj) and not subs:
        return sketch_faces(obj)
    faces = []
    for s in subs:
        try:
            shp = obj.getSubObject(s)
        except Exception:
            shp = None
        if shp is None:
            continue
        if isinstance(shp, Part.Shape) and not shp.isNull():
            faces.extend(shp.Faces)
    return faces


def ref_normal(obj, subs):
    """Extrusion direction of a profile in global coordinates."""
    if D.is_sketch(obj):
        return obj.getGlobalPlacement().Rotation.multVec(Z) if hasattr(obj, "getGlobalPlacement") \
            else obj.Placement.Rotation.multVec(Z)
    for f in ref_faces(obj, subs):
        try:
            u0, u1, v0, v1 = f.ParameterRange
            n = f.normalAt((u0 + u1) / 2.0, (v0 + v1) / 2.0)
            return n
        except Exception:
            continue
    return App.Vector(Z)


def profile_faces(refs):
    faces = []
    for obj, subs in refs:
        faces.extend(ref_faces(obj, subs))
    return faces


def profile_normal(refs):
    for obj, subs in refs:
        return ref_normal(obj, subs)
    return App.Vector(Z)


def profile_center(refs):
    faces = profile_faces(refs)
    if not faces:
        return App.Vector()
    total = 0.0
    c = App.Vector()
    for f in faces:
        a = f.Area
        c = c + f.CenterOfMass * a
        total += a
    return c * (1.0 / total) if total > 0 else faces[0].CenterOfMass


def owning_body(refs):
    """The body a profile lies on (sketch attached to a body face, or a body face)."""
    for obj, subs in refs:
        if D.is_sketch(obj):
            for sup, _ in (obj.AttachmentSupport or []):
                b = D.body_of(sup)
                if b is not None and D.role(b) != D.ROLE_TOOL:
                    return b
        else:
            b = D.body_of(obj)
            if b is not None:
                return b
            if D.role(obj) == D.ROLE_BODY:
                return obj
    return None


def refs_to_json(refs):
    return [[o.Name, list(s)] for o, s in refs]


def refs_from_json(doc, data):
    out = []
    for name, subs in data or []:
        o = doc.getObject(name)
        if o is not None:
            out.append((o, list(subs)))
    return out


def sketch_of_refs(refs):
    for o, _ in refs:
        if D.is_sketch(o):
            return o
    return None
