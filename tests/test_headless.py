# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI independent tests. Run through tests/run_headless.sh (uses freecadcmd)."""

import math
import traceback

import FreeCAD as App
import Part
import Sketcher

from freefusion import design as D
from freefusion import timeline as T
from freefusion.features import common as C
from freefusion.features import extrude as X

V = App.Vector
RESULTS = []


def check(name, cond, info=""):
    RESULTS.append((name, bool(cond)))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, info))


def rect(sk, x0, y0, x1, y1):
    pts = [V(x0, y0, 0), V(x1, y0, 0), V(x1, y1, 0), V(x0, y1, 0)]
    for i in range(4):
        sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))


def new_doc(name):
    doc = App.newDocument(name)
    D.root_component(doc, create=True)
    return doc


def xy_sketch(doc, comp=None):
    comp = comp or D.active_component(doc)
    return D.new_sketch(doc, comp, support=[(D.origin_feature(comp, "XY_Plane"), "")])


def top_face(obj, z):
    for i, f in enumerate(obj.Shape.Faces):
        if abs(f.CenterOfMass.z - z) < 1e-6 and abs(abs(f.normalAt(0, 0).z) - 1) < 1e-6:
            return "Face%d" % (i + 1)
    return None


def test_extrude_new_body_and_cut():
    doc = new_doc("ext1")
    sk = xy_sketch(doc)
    rect(sk, 0, 0, 20, 10)
    doc.recompute()
    res = X.create(doc, [(sk, [])], {"distance": 5})
    body = res.new_bodies[0] if res.new_bodies else None
    check("extrude.newbody.created", body is not None and body.Label == "Body1")
    check("extrude.newbody.volume", body is not None and abs(body.Shape.Volume - 1000) < 1e-6,
          body.Shape.Volume if body else None)
    check("extrude.newbody.up", body is not None and abs(body.Shape.BoundBox.ZMax - 5) < 1e-6,
          body.Shape.BoundBox if body else None)
    check("extrude.label", res.primary.Label == "Extrude1", res.primary.Label)

    # sketch on the top face, cut with negative distance -> auto Cut
    tip = body.Tip
    face = top_face(tip, 5)
    sk2 = D.new_sketch(doc, D.active_component(doc), support=[(tip, face)])
    sk2.addGeometry(Part.Circle(V(5, 5, 0), V(0, 0, 1), 2))
    doc.recompute()
    check("sketch.onface.placement", abs(sk2.Placement.Base.z - 5) < 1e-6, sk2.Placement)
    op = C.auto_operation(doc, [(sk2, [])], X.tool_shape([(sk2, [])], {"distance": -3}), -1)
    check("auto.cut", op == C.CUT, op)
    res2 = X.create(doc, [(sk2, [])], {"distance": -3})
    exp = 1000 - math.pi * 4 * 3
    check("extrude.cut.volume", abs(body.Shape.Volume - exp) < 1e-3, (body.Shape.Volume, exp))
    check("extrude.cut.op", D.data(res2.primary).get("operation") == C.CUT)

    # join upward
    res3 = X.create(doc, [(sk2, [])], {"distance": 4})
    check("auto.join", D.data(res3.primary).get("operation") == C.JOIN)
    exp2 = exp + math.pi * 4 * 4
    check("extrude.join.volume", abs(body.Shape.Volume - exp2) < 1e-3, (body.Shape.Volume, exp2))
    check("extrude.join.zmax", abs(body.Shape.BoundBox.ZMax - 9) < 1e-6, body.Shape.BoundBox.ZMax)

    # edit in place: taller boss
    refs, params, op3, targets = X.load(doc, D.group_id(res3.primary))
    params["distance"] = 6
    X.update(doc, D.group_id(res3.primary), refs, params, op3, targets)
    check("extrude.update.inplace", abs(body.Shape.BoundBox.ZMax - 11) < 1e-6, body.Shape.BoundBox.ZMax)
    return doc, body


def test_timeline(doc, body):
    items = T.items(doc)
    kinds = [i.kind for i in items]
    check("timeline.items", kinds[:5] == ["Sketch", "Extrude", "Sketch", "ExtrudeCut", "Extrude"], kinds)
    v_full = body.Shape.Volume
    T.roll_to(doc, 2)  # sketch1 + extrude1 only
    check("timeline.rollback.volume", abs(body.Shape.Volume - 1000) < 1e-6, body.Shape.Volume)
    check("timeline.rollback.marker", T.marker(doc) == 2)
    rolled = [i.rolled for i in T.items(doc)]
    check("timeline.rolled.flags", rolled[:5] == [False, False, True, True, True], rolled)
    # a feature created while rolled back is inserted at the marker
    sk = xy_sketch(doc)
    rect(sk, 30, 0, 40, 10)
    doc.recompute()
    res = X.create(doc, [(sk, [])], {"distance": 2})
    keys = [i.key for i in T.items(doc)]
    check("timeline.insert.at.marker", keys.index(D.group_id(res.primary)) == 3, keys)
    T.roll_to(doc, None)
    check("timeline.rollforward.volume", abs(body.Shape.Volume - v_full) < 1e-6, (body.Shape.Volume, v_full))
    check("timeline.marker.end", T.marker(doc) is None)
    # suppression and delete
    gid = D.group_id(res.primary)
    T.delete_item(doc, gid)
    check("timeline.delete", gid not in [i.key for i in T.items(doc)])


def test_intersect_and_component():
    doc = new_doc("ext2")
    sk = xy_sketch(doc)
    rect(sk, 0, 0, 10, 10)
    doc.recompute()
    b1 = X.create(doc, [(sk, [])], {"distance": 10}).new_bodies[0]
    sk2 = xy_sketch(doc)
    rect(sk2, 5, 5, 15, 15)
    doc.recompute()
    res = X.create(doc, [(sk2, [])], {"distance": 10}, operation=C.INTERSECT)
    check("intersect.volume", abs(b1.Shape.Volume - 250) < 1e-6, b1.Shape.Volume)
    items = T.items(doc)
    check("intersect.single.item", len(items) == 4, [i.key for i in items])
    check("intersect.toolbody.hidden", all(b.Label != "Extrude2 tool" for b in D.design_bodies(doc)))

    sk3 = xy_sketch(doc)
    rect(sk3, 50, 0, 60, 10)
    doc.recompute()
    res = X.create(doc, [(sk3, [])], {"distance": 3}, operation=C.NEW_COMPONENT)
    comp = res.new_components[0]
    check("newcomponent", D.is_component(comp) and comp.Label == "Component1", comp.Label)
    check("newcomponent.volume", abs(res.new_bodies[0].Shape.Volume - 300) < 1e-6)
    check("newcomponent.parent", D.component_of(comp) == D.root_component(doc))


def test_cut_multiple_bodies():
    doc = new_doc("ext3")
    sk = xy_sketch(doc)
    rect(sk, 0, 0, 10, 10)
    rect(sk, 20, 0, 30, 10)
    doc.recompute()
    # sketch regions: extrude each as its own body
    faces = ["InternalFace%d" % (i + 1) for i in range(len(sk.InternalShape.Faces))]
    check("regions.count", len(faces) == 2, faces)
    b1 = X.create(doc, [(sk, [faces[0]])], {"distance": 10}).new_bodies[0]
    b2 = X.create(doc, [(sk, [faces[1]])], {"distance": 10}, operation=C.NEW_BODY).new_bodies[0]
    check("regions.two.bodies", b1 != b2 and abs(b1.Shape.Volume - 1000) < 1e-6 and abs(b2.Shape.Volume - 1000) < 1e-6)
    sk2 = xy_sketch(doc)
    rect(sk2, 5, 2, 25, 8)
    doc.recompute()
    res = X.create(doc, [(sk2, [])], {"distance": 10}, operation=C.CUT)
    check("cut.two.targets", len(res.features) == 2, len(res.features))
    check("cut.b1", abs(b1.Shape.Volume - (1000 - 5 * 6 * 10)) < 1e-6, b1.Shape.Volume)
    check("cut.b2", abs(b2.Shape.Volume - (1000 - 5 * 6 * 10)) < 1e-6, b2.Shape.Volume)
    # symmetric & two sides on a new body
    sk3 = xy_sketch(doc)
    rect(sk3, 40, 0, 50, 10)
    doc.recompute()
    b3 = X.create(doc, [(sk3, [])], {"distance": 10, "direction": X.SYMMETRIC}).new_bodies[0]
    bb = b3.Shape.BoundBox
    check("symmetric", abs(bb.ZMin + 5) < 1e-6 and abs(bb.ZMax - 5) < 1e-6, bb)
    sk4 = xy_sketch(doc)
    rect(sk4, 60, 0, 70, 10)
    doc.recompute()
    b4 = X.create(doc, [(sk4, [])], {"distance": 10, "distance2": 4,
                                    "direction": X.TWO_SIDES}).new_bodies[0]
    bb = b4.Shape.BoundBox
    check("twosides", abs(bb.ZMin + 4) < 1e-6 and abs(bb.ZMax - 10) < 1e-6, bb)
    sk5 = xy_sketch(doc)
    rect(sk5, 80, 0, 90, 10)
    doc.recompute()
    b5 = X.create(doc, [(sk5, [])], {"distance": -7}).new_bodies[0]
    bb = b5.Shape.BoundBox
    check("negative.newbody", abs(bb.ZMin + 7) < 1e-6 and abs(bb.ZMax) < 1e-6, bb)


def test_revolve_presspull_combine():
    from freefusion.features import revolve as R, bodies as B
    doc = new_doc("rev")
    root = D.root_component(doc)
    sk = D.new_sketch(doc, root, support=[(D.origin_feature(root, "XZ_Plane"), "")])
    rect(sk, 5, 0, 10, 4)
    doc.recompute()
    zax = D.origin_feature(root, "Z_Axis")
    res = R.create(doc, [(sk, [])], {"axis": [zax.Name, ""]})
    body = res.new_bodies[0]
    exp = math.pi * (100 - 25) * 4
    check("revolve.full", abs(body.Shape.Volume - exp) < 1e-3, (body.Shape.Volume, exp))
    R.update(doc, D.group_id(res.primary), [(sk, [])],
             dict(R.default_params(), axis=[zax.Name, ""], extent=R.ANGLE, angle=90), C.NEW_BODY, [])
    body = [b for b in D.design_bodies(doc)][0]
    check("revolve.update.angle", abs(body.Shape.Volume - exp / 4) < 1e-3, body.Shape.Volume)

    # press pull the top face of a box up by 5 and then down by 2
    sk2 = xy_sketch(doc)
    rect(sk2, 30, 0, 40, 10)
    doc.recompute()
    b = X.create(doc, [(sk2, [])], {"distance": 10}).new_bodies[0]
    tip = b.Tip
    r = B.press_pull(doc, tip, [top_face(tip, 10)], 5)
    check("presspull.out", abs(b.Shape.BoundBox.ZMax - 15) < 1e-6 and abs(b.Shape.Volume - 1500) < 1e-6,
          (b.Shape.BoundBox.ZMax, b.Shape.Volume))
    tip = b.Tip
    B.press_pull(doc, tip, [top_face(tip, 15)], -2)
    check("presspull.in", abs(b.Shape.BoundBox.ZMax - 13) < 1e-6, b.Shape.BoundBox.ZMax)
    check("presspull.kind", T.items(doc)[-1].kind == "PressPull", T.items(doc)[-1].kind)

    # combine: cut body2 from body1
    sk3 = xy_sketch(doc)
    rect(sk3, 35, 5, 45, 15)
    doc.recompute()
    b2 = X.create(doc, [(sk3, [])], {"distance": 20}, operation=C.NEW_BODY).new_bodies[0]
    feat = B.combine(doc, b, [b2], C.CUT)
    check("combine.cut", abs(b.Shape.Volume - (1300 - 5 * 5 * 13)) < 1e-6, b.Shape.Volume)
    check("combine.consumed", b2 not in D.design_bodies(doc))
    T.delete_item(doc, D.group_id(feat))
    check("combine.delete.restores", b2 in D.design_bodies(doc) and abs(b.Shape.Volume - 1300) < 1e-6)

    # split body with an offset plane, scale a body
    from freefusion.features import construct as K
    pl = K.offset_plane(doc, (D.origin_feature(root, "YZ_Plane"), ""), 33)
    check("construct.offset", abs(pl.Placement.Base.x - 33) < 1e-6, pl.Placement)
    sl, pieces = B.split_body(doc, b, [pl])
    check("split.pieces", len(pieces) == 2 and abs(sum(p.Shape.Volume for p in pieces) - 1300) < 1e-6,
          [p.Shape.Volume for p in pieces])
    check("split.browser", b not in D.design_bodies(doc) and all(p in D.design_bodies(doc) for p in pieces))
    sc = B.scale_body(doc, b2, 2.0)
    check("scale", abs(sc.Shape.Volume - 8 * 2000) < 1e-3, sc.Shape.Volume)


def test_construct_and_params():
    from freefusion.features import construct as K, parameters as PR
    doc = new_doc("con")
    root = D.root_component(doc)
    sk = xy_sketch(doc)
    rect(sk, 0, 0, 10, 10)
    doc.recompute()
    b = X.create(doc, [(sk, [])], {"distance": 10}).new_bodies[0]
    tip = b.Tip
    top = top_face(tip, 10)
    pl = K.offset_plane(doc, (tip, top), 5)
    check("construct.offset.face", abs(pl.Placement.Base.z - 15) < 1e-6, pl.Placement)
    check("construct.label", pl.Label == "Plane1", pl.Label)
    bot = top_face(tip, 0)
    mp = K.midplane(doc, (tip, top), (tip, bot))
    check("construct.midplane", abs(mp.Placement.Base.z - 5) < 1e-6, mp.Placement)
    ax = K.axis_two_planes(doc, (D.origin_feature(root, "XZ_Plane"), ""), (D.origin_feature(root, "YZ_Plane"), ""))
    check("construct.axis.planes", ax.isValid() and abs(abs(ax.Placement.Rotation.multVec(V(0, 0, 1)).z) - 1) < 1e-6)
    pt = K.point_three_planes(doc, (tip, top), (D.origin_feature(root, "XZ_Plane"), ""), (D.origin_feature(root, "YZ_Plane"), ""))
    check("construct.point3", (pt.Placement.Base - V(0, 0, 10)).Length < 1e-6, pt.Placement.Base)
    check("construct.classify", K.classify((tip, top)) == "face")

    PR.set_parameter(doc, "width", "20", "mm", "overall width")
    PR.set_parameter(doc, "height", "width / 4", "mm")
    params = {p["name"]: p for p in PR.user_parameters(doc)}
    check("params.list", set(params) == {"width", "height"}, list(params))
    val, expr = PR.parse_value(doc, "height * 2")
    check("params.parse.expr", expr == "FFParams.height * 2" and abs(val - 10) < 1e-9, (val, expr))
    val, expr = PR.parse_value(doc, "1 in")
    check("params.parse.literal", expr == "" and abs(val - 25.4) < 1e-9, (val, expr))
    refs, prm, op_, targets = X.load(doc, D.group_id(b.Tip))
    prm["distance"], prm["expr"] = val, PR.to_expression(doc, "height")
    X.update(doc, D.group_id(b.Tip), refs, prm, op_, targets)
    check("params.drive.feature", abs(b.Shape.BoundBox.ZMax - 5) < 1e-6, b.Shape.BoundBox.ZMax)
    PR.set_parameter(doc, "width", "40", "mm")
    check("params.propagate", abs(b.Shape.BoundBox.ZMax - 10) < 1e-6, b.Shape.BoundBox.ZMax)
    PR.remove_parameter(doc, "height")
    check("params.remove", PR.parameter_names(doc) == ["width"], PR.parameter_names(doc))
    sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 10))
    doc.recompute()
    PR.name_dimensions(sk)
    check("params.dimnames", sk.Constraints[-1].Name == "d1", sk.Constraints[-1].Name)
    mps = PR.model_parameters(doc)
    check("params.model", any(m[5] == "d1" for m in mps) and any(m[2] == "Length" for m in mps))


def test_sweep_loft():
    from freefusion.features import sweeploft as SL
    doc = new_doc("swl")
    root = D.root_component(doc)
    prof = D.new_sketch(doc, root, support=[(D.origin_feature(root, "XY_Plane"), "")])
    prof.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), 2))
    path = D.new_sketch(doc, root, support=[(D.origin_feature(root, "XZ_Plane"), "")])
    path.addGeometry(Part.LineSegment(V(0, 0, 0), V(0, 30, 0)))
    doc.recompute()
    res = SL.sweep(doc, [(prof, [])], [(path, [])])
    b = res.new_bodies[0]
    check("sweep.volume", abs(b.Shape.Volume - math.pi * 4 * 30) < 1e-3, b.Shape.Volume)
    top = D.new_sketch(doc, root, support=[(D.origin_feature(root, "XY_Plane"), "")])
    top.AttachmentOffset = App.Placement(V(50, 0, 20), App.Rotation())
    rect(top, -5, -5, 5, 5)
    bot = D.new_sketch(doc, root, support=[(D.origin_feature(root, "XY_Plane"), "")])
    bot.AttachmentOffset = App.Placement(V(50, 0, 0), App.Rotation())
    rect(bot, -10, -10, 10, 10)
    doc.recompute()
    res = SL.loft(doc, [[(bot, [])], [(top, [])]], ruled=True)
    b = res.new_bodies[0]
    exp = 20.0 / 3 * (400 + 100 + math.sqrt(400 * 100))
    check("loft.volume", abs(b.Shape.Volume - exp) < 1e-3, (b.Shape.Volume, exp))


def test_special():
    from freefusion.features import special as SP
    doc = new_doc("spc")
    root = D.root_component(doc)
    h = SP.coil(doc, 20, 5, 3, 2)
    b = D.body_of(h)
    exp = math.pi * 1 * (math.pi * 20) * 3
    check("coil.volume", abs(b.Shape.Volume - exp) / exp < 0.02, (b.Shape.Volume, exp))
    sk = xy_sketch(doc)
    sk.addGeometry(Part.Circle(V(50, 0, 0), V(0, 0, 1), 5))
    doc.recompute()
    shaft = X.create(doc, [(sk, [])], {"distance": 20}).new_bodies[0]
    tip = shaft.Tip
    face = [("Face%d" % (i + 1)) for i, f in enumerate(tip.Shape.Faces) if isinstance(f.Surface, Part.Cylinder)][0]
    v0 = shaft.Shape.Volume
    t = SP.thread(doc, tip, face)
    check("thread.valid", t.isValid() and shaft.Shape.isValid(), t.getStatusString())
    check("thread.removes", 0 < v0 - shaft.Shape.Volume < 0.2 * v0, (v0, shaft.Shape.Volume))
    check("thread.pitch", abs(t.Pitch.Value - 1.5) < 1e-9, t.Pitch)
    path = D.new_sketch(doc, root, support=[(D.origin_feature(root, "XZ_Plane"), "")])
    path.addGeometry(Part.LineSegment(V(100, 0, 0), V(100, 40, 0)))
    doc.recompute()
    res = SP.pipe(doc, [(path, [])], 6)
    check("pipe.volume", abs(res.new_bodies[0].Shape.Volume - math.pi * 9 * 40) < 1e-2,
          res.new_bodies[0].Shape.Volume)


TESTS = [
    ("extrude", lambda: test_timeline(*test_extrude_new_body_and_cut())),
    ("intersect", test_intersect_and_component),
    ("multi", test_cut_multiple_bodies),
    ("revolve", test_revolve_presspull_combine),
    ("construct", test_construct_and_params),
    ("sweeploft", test_sweep_loft),
    ("special", test_special),
]

for name, fn in TESTS:
    try:
        fn()
    except Exception:
        RESULTS.append((name, False))
        print("ERROR %s\n%s" % (name, traceback.format_exc().replace("\n", "\nERROR ")))

try:
    import test_headless_more  # noqa: F401  (optional extra suites)
except ImportError:
    pass

failed = [n for n, ok in RESULTS if not ok]
print("SUMMARY %s %d/%d" % ("ok" if not failed else "failed", len(RESULTS) - len(failed), len(RESULTS)))
