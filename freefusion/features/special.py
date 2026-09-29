# SPDX-License-Identifier: LGPL-2.1-or-later
"""Coil, modeled Thread and Pipe."""

import math

import FreeCAD as App
import Part

from .. import design as D
from . import profiles as P
from . import sweeploft as SL

V = App.Vector

# ISO 261 coarse pitches (nominal diameter mm -> pitch mm)
ISO_COARSE = [(1, .25), (1.2, .25), (1.6, .35), (2, .4), (2.5, .45), (3, .5), (4, .7), (5, .8), (6, 1.0),
              (8, 1.25), (10, 1.5), (12, 1.75), (14, 2.0), (16, 2.0), (18, 2.5), (20, 2.5), (22, 2.5),
              (24, 3.0), (27, 3.0), (30, 3.5), (33, 3.5), (36, 4.0), (42, 4.5), (48, 5.0), (56, 5.5),
              (64, 6.0)]


def iso_pitch(diameter):
    best = min(ISO_COARSE, key=lambda x: abs(x[0] - diameter))
    return best[1]


def coil(doc, diameter=20.0, pitch=5.0, revolutions=5.0, section=2.0, container=None):
    """Spring: circular section swept along a helix, as a new body."""
    container = container if container is not None else D.active_component(doc)
    label, gid = D.new_group_id(doc, "Coil")
    body = D.new_body(doc, container)
    D.tag(body, group=gid)
    xz = [f for f in body.Origin.OriginFeatures if f.Role == "XZ_Plane"][0]
    sk = body.newObject("Sketcher::SketchObject", "CoilSection")
    sk.AttachmentSupport = [(xz, "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(V(diameter / 2.0, 0, 0), V(0, 0, 1), section / 2.0), False)
    sk.Label = label + " Section"
    D.tag(sk, group=gid)
    helix = body.newObject("PartDesign::AdditiveHelix", "Coil")
    helix.Profile = sk
    helix.ReferenceAxis = (sk, ["V_Axis"])
    helix.Mode = "pitch-turns-angle"
    helix.Pitch = pitch
    helix.Turns = revolutions
    helix.Label = label
    D.tag(helix, role=D.ROLE_FEATURE, group=gid, op="Coil", data={"type": "Coil"})
    doc.recompute()
    D.hide_object(sk)
    return helix


def _cyl_info(face):
    surf = face.Surface
    if not isinstance(surf, Part.Cylinder):
        raise ValueError("Select a cylindrical face")
    axis = V(surf.Axis)
    axis.normalize()
    center = V(surf.Center)
    # axial extent of the face
    ts = [(v.Point - center).dot(axis) for v in face.Vertexes] or [0.0]
    if not face.Vertexes:
        bb = face.BoundBox
        ts = [(V(bb.XMin, bb.YMin, bb.ZMin) - center).dot(axis), (V(bb.XMax, bb.YMax, bb.ZMax) - center).dot(axis)]
    t0, t1 = min(ts), max(ts)
    # is the material outside (hole) or inside (shaft)?
    u0, u1, v0, v1 = face.ParameterRange
    p = face.valueAt((u0 + u1) / 2, (v0 + v1) / 2)
    n = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
    radial = p - (center + axis * (p - center).dot(axis))
    internal = radial.dot(n) < 0
    return center + axis * t0, axis, surf.Radius, t1 - t0, internal


def thread(doc, feature, face_name, pitch=None, length=None, modeled=True):
    """Modeled ISO-like 60 degree thread on a cylindrical face of a PartDesign body."""
    body = D.body_of(feature)
    if body is None:
        raise ValueError("Threads need a face of a body")
    face = feature.getSubObject(face_name)
    start, axis, radius, height, internal = _cyl_info(face)
    pitch = pitch or iso_pitch(2 * radius)
    length = length or height
    label, gid = D.new_group_id(doc, "Thread")
    # sketch plane containing the axis: local X radial, local Y along the axis
    ref = V(1, 0, 0) if abs(axis.x) < 0.9 else V(0, 1, 0)
    xdir = ref - axis * ref.dot(axis)
    xdir.normalize()
    zdir = xdir.cross(axis)
    rot = App.Rotation(xdir, axis, zdir, "ZXY")
    glob = App.Placement(start, rot)
    local = body.getGlobalPlacement().inverse().multiply(glob) if hasattr(body, "getGlobalPlacement") \
        else body.Placement.inverse().multiply(glob)
    sk = body.newObject("Sketcher::SketchObject", "ThreadProfile")
    sk.MapMode = "Deactivated"
    sk.Placement = local
    depth = 0.5413 * pitch            # 5/8 H for ISO threads
    half = depth * math.tan(math.radians(30))
    ext = 0.25 * pitch
    if internal:
        tip, outer = radius + depth, radius - ext
    else:
        tip, outer = radius - depth, radius + ext
    half_out = half + ext * math.tan(math.radians(30))
    y0 = pitch / 2.0
    pts = [V(outer, y0 - half_out, 0), V(tip, y0, 0), V(outer, y0 + half_out, 0)]
    for i in range(3):
        sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 3]), False)
    sk.Label = label + " Profile"
    D.tag(sk, group=gid)
    f = body.newObject("PartDesign::SubtractiveHelix", "Thread")
    f.Profile = sk
    f.ReferenceAxis = (sk, ["V_Axis"])
    f.Mode = "pitch-height-angle"
    f.Pitch = pitch
    f.Height = max(pitch, length - pitch)
    f.Label = label
    try:
        f.Refine = True
    except Exception:
        pass
    D.tag(f, role=D.ROLE_FEATURE, group=gid, op="Thread",
          data={"type": "Thread", "pitch": pitch, "internal": internal})
    doc.recompute()
    D.hide_object(sk)
    return f


def pipe(doc, path_refs, diameter=5.0, operation=None):
    """Fusion Pipe: sweep a circle of the given diameter along a path."""
    path_refs = P.normalize_refs(path_refs)
    if not path_refs:
        raise ValueError("Select a path")
    obj, subs = path_refs[0]
    edge_name = subs[0] if subs else "Edge1"
    container = D.active_component(doc)
    sk = D.new_sketch(doc, container, support=[(obj, edge_name)], map_mode="NormalToEdge")
    sk.MapPathParameter = 0.0
    sk.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), diameter / 2.0), False)
    doc.recompute()
    res = SL.sweep(doc, [(sk, [])], path_refs, operation)
    D.tag(res.primary, op="Pipe")
    D.tag(sk, group=D.group_id(res.primary))
    return res
