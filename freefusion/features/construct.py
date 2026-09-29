# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion CONSTRUCT tools mapped to attached Part datum objects.

Every function takes references as (obj, sub) tuples (sub may be '' for whole
objects such as origin planes) and returns the new datum object, which is placed in
the active component and labelled Plane1 / Axis1 / Point1 like Fusion does.
"""

import math

import FreeCAD as App
import Part

from .. import design as D

V = App.Vector


def _datum(doc, typ, base, support, mode, offset=None, container=None, path_param=None,
           gid_base=None):
    container = container if container is not None else D.active_component(doc)
    obj = doc.addObject(typ, base)
    label, gid = D.new_group_id(doc, gid_base or base)
    obj.Label = label
    D.add_to(container, obj)
    if support:
        obj.AttachmentSupport = [(o, s) for o, s in support]
        obj.MapMode = mode
    if offset is not None:
        obj.AttachmentOffset = offset
    if path_param is not None:
        obj.MapPathParameter = path_param
    D.tag(obj, role=D.ROLE_FEATURE, group=gid, op="Construct",
          data={"type": gid_base or base, "mode": mode})
    doc.recompute()
    return obj


def _shape(ref):
    obj, sub = ref
    try:
        return obj.getSubObject(sub) if sub else obj.Shape
    except Exception:
        return None


def _sub_index(obj, shape, kind="Vertex"):
    """Find the name ('Vertex7') of a sub-shape of obj matching shape."""
    items = getattr(obj.Shape, kind + "es" if kind == "Vertex" else kind + "s")
    for i, it in enumerate(items):
        if it.isSame(shape) or (kind == "Vertex" and (it.Point - shape.Point).Length < 1e-7):
            return "%s%d" % (kind, i + 1)
    return None


def _plane_of(ref):
    """(point, normal) of a plane reference: origin/datum plane or planar face."""
    obj, sub = ref
    if not sub:
        pl = obj.getGlobalPlacement() if hasattr(obj, "getGlobalPlacement") else obj.Placement
        return pl.Base, pl.Rotation.multVec(V(0, 0, 1))
    s = _shape(ref)
    f = s.Faces[0] if s is not None and s.Faces else None
    if f is None:
        raise ValueError("Select planes or planar faces")
    return f.CenterOfMass, _normal(f)


def _normal(face):
    u0, u1, v0, v1 = face.ParameterRange
    return face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)


# -- planes -----------------------------------------------------------------

def offset_plane(doc, ref, distance, container=None):
    return _datum(doc, "Part::DatumPlane", "Plane", [ref], "FlatFace",
                  App.Placement(V(0, 0, distance), App.Rotation()), container)


def plane_at_angle(doc, edge_ref, angle, container=None):
    rot = App.Rotation(V(0, 0, 1), angle).multiply(App.Rotation(V(1, 0, 0), 90))
    return _datum(doc, "Part::DatumPlane", "Plane", [edge_ref], "NormalToEdge",
                  App.Placement(V(), rot), container)


def tangent_plane(doc, face_ref, point_ref=None, container=None):
    obj, sub = face_ref
    if point_ref is None:
        face = _shape(face_ref)
        vname = _sub_index(obj, face.Vertexes[0]) if face and face.Vertexes else None
        if vname is None:
            raise ValueError("Select a point on the face as well")
        point_ref = (obj, vname)
    return _datum(doc, "Part::DatumPlane", "Plane", [face_ref, point_ref], "TangentPlane",
                  None, container)


def midplane(doc, ref_a, ref_b, container=None):
    pa, n = _plane_of(ref_a)
    pb, _ = _plane_of(ref_b)
    d = (pb - pa).dot(n)
    obj = offset_plane(doc, ref_a, d / 2.0, container)
    return obj


def plane_two_edges(doc, edge_a, edge_b, container=None):
    e2 = _shape(edge_b)
    vname = _sub_index(edge_b[0], e2.Vertexes[0]) if e2 is not None and e2.Vertexes else None
    if vname is None:
        raise ValueError("The second edge needs an end point")
    return _datum(doc, "Part::DatumPlane", "Plane", [edge_a, (edge_b[0], vname)],
                  "ThreePointsPlane", None, container)


def plane_three_points(doc, p1, p2, p3, container=None):
    return _datum(doc, "Part::DatumPlane", "Plane", [p1, p2, p3], "ThreePointsPlane", None,
                  container)


def plane_along_path(doc, edge_ref, parameter=0.5, container=None):
    return _datum(doc, "Part::DatumPlane", "Plane", [edge_ref], "NormalToEdge", None,
                  container, path_param=parameter)


# -- axes -------------------------------------------------------------------

def axis_through_cylinder(doc, face_ref, container=None):
    obj, sub = face_ref
    face = _shape(face_ref)
    if face is None:
        raise ValueError("Select a cylindrical, conical or toroidal face")
    for e in face.Edges:
        if isinstance(getattr(e, "Curve", None), (Part.Circle,)):
            ename = _sub_index(obj, e, "Edge")
            if ename:
                return _datum(doc, "Part::DatumLine", "Axis", [(obj, ename)], "AxisOfCurvature",
                              None, container)
    return _datum(doc, "Part::DatumLine", "Axis", [face_ref], "AxisOfInertia1", None, container)


def axis_through_edge(doc, edge_ref, container=None):
    edge = _shape(edge_ref)
    if edge is not None and isinstance(getattr(edge, "Curve", None), Part.Circle):
        return _datum(doc, "Part::DatumLine", "Axis", [edge_ref], "AxisOfCurvature", None,
                      container)
    return _datum(doc, "Part::DatumLine", "Axis", [edge_ref], "TwoPointLine", None, container)


def axis_two_planes(doc, ref_a, ref_b, container=None):
    return _datum(doc, "Part::DatumLine", "Axis", [ref_a, ref_b], "IntersectionLine", None,
                  container)


def axis_two_points(doc, p1, p2, container=None):
    return _datum(doc, "Part::DatumLine", "Axis", [p1, p2], "TwoPointLine", None, container)


def axis_normal_at_point(doc, face_ref, point_ref, container=None):
    return _datum(doc, "Part::DatumLine", "Axis", [face_ref, point_ref], "FaceNormal", None,
                  container)


# -- points -----------------------------------------------------------------

def point_at_vertex(doc, vertex_ref, container=None):
    return _datum(doc, "Part::DatumPoint", "Point", [vertex_ref], "Vertex", None, container)


def point_center(doc, edge_ref, container=None):
    return _datum(doc, "Part::DatumPoint", "Point", [edge_ref], "CenterOfCurvature", None,
                  container)


def point_two_edges(doc, edge_a, edge_b, container=None):
    return _datum(doc, "Part::DatumPoint", "Point", [edge_a, edge_b], "ProximityPoint1", None,
                  container)


def point_edge_plane(doc, edge_ref, plane_ref, container=None):
    return _datum(doc, "Part::DatumPoint", "Point", [edge_ref, plane_ref], "ProximityPoint1",
                  None, container)


def point_along_path(doc, edge_ref, parameter=0.5, container=None):
    return _datum(doc, "Part::DatumPoint", "Point", [edge_ref], "OnEdge", None, container,
                  path_param=parameter)


def point_three_planes(doc, a, b, c, container=None):
    """Intersection of three planes (fixed position, recomputed on creation only)."""
    planes = [_plane_of(r) for r in (a, b, c)]
    (p1, n1), (p2, n2), (p3, n3) = planes
    det = n1.dot(n2.cross(n3))
    if abs(det) < 1e-9:
        raise ValueError("The planes do not intersect in a single point")
    p = (n2.cross(n3) * p1.dot(n1) + n3.cross(n1) * p2.dot(n2) + n1.cross(n2) * p3.dot(n3)) \
        * (1.0 / det)
    obj = _datum(doc, "Part::DatumPoint", "Point", None, "Deactivated", None, container)
    obj.Placement = App.Placement(p, App.Rotation())
    doc.recompute()
    return obj


def classify(ref):
    """'plane', 'face', 'cylface', 'edge', 'lineedge', 'circle', 'vertex' or ''."""
    obj, sub = ref
    if not sub:
        if obj.isDerivedFrom("App::Plane") or obj.isDerivedFrom("Part::DatumPlane") \
                or obj.isDerivedFrom("PartDesign::Plane"):
            return "plane"
        if obj.isDerivedFrom("App::Line") or obj.isDerivedFrom("Part::DatumLine") \
                or obj.isDerivedFrom("PartDesign::Line"):
            return "lineedge"
        if obj.isDerivedFrom("App::Point") or obj.isDerivedFrom("Part::DatumPoint") \
                or obj.isDerivedFrom("PartDesign::Point"):
            return "vertex"
        return ""
    s = _shape(ref)
    if s is None:
        return ""
    if sub.startswith("Face"):
        surf = getattr(s.Faces[0], "Surface", None) if s.Faces else None
        if isinstance(surf, Part.Plane):
            return "face"
        if isinstance(surf, (Part.Cylinder, Part.Cone, Part.Toroid)):
            return "cylface"
        return "surface"
    if sub.startswith("Edge"):
        c = getattr(s.Edges[0], "Curve", None) if s.Edges else None
        if isinstance(c, Part.Line) or type(c).__name__ in ("Line", "LineSegment"):
            return "lineedge"
        if isinstance(c, (Part.Circle, Part.ArcOfCircle)):
            return "circle"
        return "edge"
    if sub.startswith("Vertex"):
        return "vertex"
    return ""
