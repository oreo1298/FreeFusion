# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion style design history (timeline) on top of a FreeCAD document.

The timeline is a flat, ordered list of *items*. An item is a group of document
objects that the user thinks of as one operation (e.g. an Extrude that cut three
bodies is one item made of three PartDesign::Pocket features plus binders).

The order and the history marker are persisted in ``Document.Meta`` so they survive
save/load. Rolling the marker back suppresses PartDesign features after the marker
(and moves each body's Tip so new features are inserted at the marker, like Fusion),
and hides sketches / construction geometry after it.
"""

import json

import FreeCAD as App

from . import design as D

META_ORDER = "FreeFusion.Timeline"
META_MARKER = "FreeFusion.Marker"
META_ROLLED = "FreeFusion.Rolled"

# TypeId -> (kind, display name). Kind doubles as the icon name (Timeline_<kind>).
KINDS = {
    "Sketcher::SketchObject": "Sketch",
    "PartDesign::Pad": "Extrude",
    "PartDesign::Pocket": "ExtrudeCut",
    "PartDesign::Revolution": "Revolve",
    "PartDesign::Groove": "RevolveCut",
    "PartDesign::Fillet": "Fillet",
    "PartDesign::Chamfer": "Chamfer",
    "PartDesign::Thickness": "Shell",
    "PartDesign::Draft": "Draft",
    "PartDesign::Hole": "Hole",
    "PartDesign::LinearPattern": "RectPattern",
    "PartDesign::PolarPattern": "CircPattern",
    "PartDesign::Mirrored": "Mirror",
    "PartDesign::MultiTransform": "RectPattern",
    "PartDesign::AdditivePipe": "Sweep",
    "PartDesign::SubtractivePipe": "Sweep",
    "PartDesign::AdditiveLoft": "Loft",
    "PartDesign::SubtractiveLoft": "Loft",
    "PartDesign::AdditiveHelix": "Coil",
    "PartDesign::SubtractiveHelix": "Thread",
    "PartDesign::AdditiveBox": "Box",
    "PartDesign::AdditiveCylinder": "Cylinder",
    "PartDesign::AdditiveSphere": "Sphere",
    "PartDesign::AdditiveTorus": "Torus",
    "PartDesign::AdditiveCone": "Cylinder",
    "PartDesign::AdditivePrism": "Box",
    "PartDesign::AdditiveWedge": "Box",
    "PartDesign::AdditiveEllipsoid": "Sphere",
    "PartDesign::Boolean": "Combine",
    "Part::DatumPlane": "Plane",
    "PartDesign::Plane": "Plane",
    "Part::DatumLine": "Axis",
    "PartDesign::Line": "Axis",
    "Part::DatumPoint": "Point",
    "PartDesign::Point": "Point",
    "App::Part": "Component",
    "Part::Scale": "Scale",
    "Part::Cut": "Combine",
    "Part::Fuse": "Combine",
    "Part::Common": "Combine",
    "Part::MultiFuse": "Combine",
    "Part::MultiCommon": "Combine",
}

# FFOp overrides the icon kind (e.g. an extrude that created a new body).
OP_KINDS = {
    "PressPull": "PressPull",
    "Split": "Split",
    "Intersect": "Extrude",
    "Joint": "Joint",
}

SKIP_TYPES = (
    "PartDesign::Body", "PartDesign::ShapeBinder", "PartDesign::SubShapeBinder",
    "App::Origin", "App::OriginFeature", "App::LocalCoordinateSystem",
    "Spreadsheet::Sheet", "App::VarSet", "App::DocumentObjectGroup",
    "TechDraw::DrawPage", "TechDraw::DrawView", "TechDraw::DrawTemplate",
    "App::MaterialObject", "App::TextDocument", "Image::ImagePlane",
)


class Item(object):
    __slots__ = ("key", "objects", "kind", "label", "rolled", "suppressed")

    def __init__(self, key, objects):
        self.key = key
        self.objects = objects
        prim = self.primary
        self.label = getattr(prim, "Label", key) if prim is not None else key
        self.kind = _kind_of(prim)
        self.rolled = False
        self.suppressed = False

    @property
    def primary(self):
        for o in self.objects:
            if D.role(o) == D.ROLE_FEATURE:
                return o
        for o in self.objects:
            if D.role(o) not in (D.ROLE_BINDER, D.ROLE_TOOL) and not D.is_body(o) \
                    and not D.is_component(o):
                return o
        for o in self.objects:
            if D.role(o) != D.ROLE_BINDER:
                return o
        return self.objects[0] if self.objects else None

    def __repr__(self):
        return "<Item %s %s %d objs>" % (self.key, self.kind, len(self.objects))


def _kind_of(obj):
    if obj is None:
        return "Generic"
    o = D.op(obj)
    if o in OP_KINDS:
        return OP_KINDS[o]
    if D.is_component(obj):
        return "Component"
    if obj.TypeId in KINDS:
        return KINDS[obj.TypeId]
    if "Joint" in obj.Name or "Joint" in obj.TypeId:
        return "Joint"
    for t, k in KINDS.items():
        try:
            if obj.isDerivedFrom(t):
                return k
        except Exception:
            pass
    return "Generic"


def _is_joint(obj):
    proxy = getattr(obj, "Proxy", None)
    return proxy is not None and type(proxy).__name__ == "Joint"


def is_history_object(obj):
    """Should obj appear in the timeline?"""
    r = D.role(obj)
    if r in (D.ROLE_ROOT, D.ROLE_BINDER, D.ROLE_TOOL, D.ROLE_PARAMS):
        return False
    if _is_joint(obj):
        return True
    if any(obj.isDerivedFrom(t) for t in SKIP_TYPES):
        return False
    if D.is_body(obj):
        return False
    if obj.TypeId.startswith("Assembly::"):
        return False
    if D.is_origin_feature(obj):
        return False
    if D.is_sketch(obj) or D.is_datum(obj) or D.is_pd_feature(obj):
        return True
    if D.is_component(obj):
        return True
    if obj.isDerivedFrom("Part::Feature"):
        return True
    return False


# ---------------------------------------------------------------------------
# Meta persistence


def _meta_get(doc, key, default):
    try:
        raw = doc.Meta.get(key)
    except Exception:
        return default
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except ValueError:
        return default


def _meta_set(doc, key, value):
    meta = dict(doc.Meta)
    if value is None:
        meta.pop(key, None)
    else:
        meta[key] = json.dumps(value)
    if meta != dict(doc.Meta):
        doc.Meta = meta


def marker(doc):
    """Number of active items, or None when the marker is at the end."""
    return _meta_get(doc, META_MARKER, None)


# ---------------------------------------------------------------------------
# Items


def _groups(doc):
    groups = {}
    order = []
    for o in D.ordered_objects(doc):
        gid = getattr(o, "FFGroup", "")
        if gid:
            if gid not in groups:
                groups[gid] = []
                order.append(gid)
            groups[gid].append(o)
        elif is_history_object(o):
            groups[o.Name] = [o]
            order.append(o.Name)
    # a group is shown only if at least one member is a history object
    keep = []
    for gid in order:
        objs = groups[gid]
        if any(is_history_object(o) for o in objs):
            keep.append(gid)
    return keep, groups


def _persistent(doc):
    """Only FreeFusion designs get timeline data written into them."""
    try:
        if META_ORDER in doc.Meta:
            return True
    except Exception:
        return False
    return D.root_component(doc) is not None


def sync(doc):
    """Reconcile the stored order with the document; returns (keys, groups)."""
    natural, groups = _groups(doc)
    if not _persistent(doc):
        return natural, groups
    stored = _meta_get(doc, META_ORDER, [])
    mark = marker(doc)
    known = [k for k in stored if k in groups]
    new = [k for k in natural if k not in known]
    if new:
        if mark is not None:
            mark = max(0, min(mark, len(known)))
            known[mark:mark] = new
            mark += len(new)
        else:
            known.extend(new)
    if known != stored:
        _meta_set(doc, META_ORDER, known)
    if mark is not None:
        mark = max(0, min(mark, len(known)))
        if mark >= len(known):
            mark = None
        if mark != marker(doc):
            _meta_set(doc, META_MARKER, mark)
    return known, groups


def items(doc):
    if doc is None:
        return []
    keys, groups = sync(doc)
    mark = marker(doc)
    out = []
    for i, k in enumerate(keys):
        it = Item(k, groups[k])
        it.rolled = mark is not None and i >= mark
        it.suppressed = any(getattr(o, "Suppressed", False) for o in it.objects) and not it.rolled
        out.append(it)
    return out


def move_item(doc, key, new_index):
    """Reorder an item (only the stored order; geometry order is not changed)."""
    keys, _ = sync(doc)
    if key not in keys:
        return
    keys.remove(key)
    keys.insert(max(0, min(new_index, len(keys))), key)
    _meta_set(doc, META_ORDER, keys)


# ---------------------------------------------------------------------------
# Rollback


def _body_last_active(body, rolled_names):
    last = None
    for f in body.Group:
        if not D.is_pd_feature(f):
            continue
        if D.role(f) == D.ROLE_BINDER or f.isDerivedFrom("PartDesign::ShapeBinder") \
                or f.isDerivedFrom("PartDesign::SubShapeBinder"):
            continue
        if f.Name in rolled_names or getattr(f, "Suppressed", False):
            continue
        if hasattr(f, "BaseFeature"):  # solid features only (not datums)
            last = f
    return last


def roll_to(doc, position):
    """Move the history marker so that only the first ``position`` items are active.

    ``position=None`` (or >= number of items) rolls forward to the end.
    """
    keys, groups = sync(doc)
    n = len(keys)
    if position is not None and position >= n:
        position = None
    rolled = _meta_get(doc, META_ROLLED, {"suppressed": [], "hidden": []})
    suppressed = set(rolled.get("suppressed", []))
    hidden = set(rolled.get("hidden", []))

    active_keys = keys if position is None else keys[:position]
    inactive_keys = [] if position is None else keys[position:]

    # 1. restore everything that is active again
    for k in active_keys:
        for o in groups[k]:
            if o.Name in suppressed:
                try:
                    o.Suppressed = False
                except Exception:
                    pass
                suppressed.discard(o.Name)
            if o.Name in hidden:
                if D.role(o) != D.ROLE_BINDER:
                    D.show_object(o)
                hidden.discard(o.Name)

    # 2. deactivate items after the marker
    for k in inactive_keys:
        for o in groups[k]:
            if D.is_pd_feature(o) and "Suppressed" in o.PropertiesList \
                    and D.role(o) != D.ROLE_BINDER:
                if not o.Suppressed:
                    o.Suppressed = True
                    suppressed.add(o.Name)
            elif D.is_sketch(o) or D.is_datum(o) or D.is_component(o) \
                    or o.isDerivedFrom("Part::Feature"):
                if D.role(o) == D.ROLE_BINDER:
                    continue
                vis = o.ViewObject.Visibility if (App.GuiUp and o.ViewObject) else o.Visibility
                if vis:
                    D.hide_object(o)
                    hidden.add(o.Name)

    # 3. bodies: move Tip to the last active feature, hide bodies with nothing active
    for body in [o for o in doc.Objects if D.is_body(o)]:
        last = _body_last_active(body, suppressed)
        tip_target = last
        if position is None:
            # rolled forward: Tip goes to the last solid feature
            tip_target = _body_last_active(body, set())
        if tip_target is not None and body.Tip != tip_target:
            try:
                body.Tip = tip_target
            except Exception:
                pass
        if last is None and position is not None and any(
                D.is_pd_feature(f) and D.role(f) != D.ROLE_BINDER for f in body.Group):
            vis = body.ViewObject.Visibility if (App.GuiUp and body.ViewObject) else body.Visibility
            if vis:
                D.hide_object(body)
                hidden.add(body.Name)
        elif body.Name in hidden and (last is not None or position is None):
            D.show_object(body)
            hidden.discard(body.Name)
        if App.GuiUp and tip_target is not None:
            # keep only the tip visible, like PartDesign does
            try:
                for f in body.Group:
                    if D.is_pd_feature(f) and f.ViewObject is not None:
                        f.ViewObject.Visibility = (f == tip_target)
            except Exception:
                pass

    _meta_set(doc, META_ROLLED, {"suppressed": sorted(suppressed), "hidden": sorted(hidden)}
              if (suppressed or hidden) else None)
    _meta_set(doc, META_MARKER, position)
    doc.recompute()
    return position


def step(doc, delta):
    keys, _ = sync(doc)
    mark = marker(doc)
    cur = len(keys) if mark is None else mark
    return roll_to(doc, max(0, min(len(keys), cur + delta)))


def suppress_item(doc, key, state=True):
    _, groups = sync(doc)
    for o in groups.get(key, []):
        if "Suppressed" in o.PropertiesList and D.role(o) != D.ROLE_BINDER:
            o.Suppressed = state
    doc.recompute()


def delete_item(doc, key):
    _, groups = sync(doc)
    objs = list(groups.get(key, []))
    # binders belonging to the same group
    gid_objs = D.group_members(doc, key)
    for o in gid_objs:
        if o not in objs:
            objs.append(o)
    # bring back bodies this item consumed (Combine / Split / Scale)
    for o in objs:
        for name in D.data(o).get("consumed", []):
            b = doc.getObject(name)
            if b is not None and D.role(b) == D.ROLE_CONSUMED:
                D.tag(b, role=D.ROLE_BODY)
                D.show_object(b)
    # delete dependents first
    objs.sort(key=lambda o: -o.ID)
    D.remove_objects(objs)
    sync(doc)
    doc.recompute()
