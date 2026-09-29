# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Fusion 360 design model mapped onto FreeCAD objects.

Fusion                      FreeCAD
-------------------------   ------------------------------------------------------
Design (root component)     App::Part tagged FFRole='root'
Component                   App::Part tagged FFRole='component'
Body                        PartDesign::Body (or a solid Part feature tagged 'body')
Sketch                      Sketcher::SketchObject living in a *component*, not a body
Construction geometry       Part::DatumPlane / DatumLine / DatumPoint in a component
Feature (Extrude, ...)      One or more PartDesign features, sharing an FFGroup id

Sketches live at component level exactly like in Fusion, so one sketch can drive
features in several bodies. Features reach the sketch through hidden
PartDesign::SubShapeBinder objects created inside each body (FFRole='binder').

Everything in this module works without the GUI so it can be unit tested with
freecadcmd.
"""

import json
import re

import FreeCAD as App

PROP_GROUP = "FreeFusion"

ROLE_ROOT = "root"
ROLE_COMPONENT = "component"
ROLE_BODY = "body"
ROLE_BINDER = "binder"
ROLE_TOOL = "tool"          # hidden helper bodies (e.g. intersect tools)
ROLE_FEATURE = "feature"
ROLE_PARAMS = "params"
ROLE_CONSUMED = "consumed"  # body replaced by a Combine/Split/Scale result

SKETCH_TYPES = ("Sketcher::SketchObject",)
DATUM_TYPES = (
    "Part::DatumPlane", "Part::DatumLine", "Part::DatumPoint",
    "PartDesign::Plane", "PartDesign::Line", "PartDesign::Point",
)

# ---------------------------------------------------------------------------
# Tagging


def _ensure_prop(obj, name, ptype="App::PropertyString", doc=""):
    if name not in obj.PropertiesList:
        obj.addProperty(ptype, name, PROP_GROUP, doc)
        try:
            obj.setEditorMode(name, 2)  # hidden in the property editor
        except Exception:
            pass


def tag(obj, role=None, group=None, op=None, data=None):
    """Attach FreeFusion metadata to a document object."""
    if role is not None:
        _ensure_prop(obj, "FFRole", doc="FreeFusion role")
        obj.FFRole = role
    if group is not None:
        _ensure_prop(obj, "FFGroup", doc="FreeFusion timeline group")
        obj.FFGroup = group
    if op is not None:
        _ensure_prop(obj, "FFOp", doc="FreeFusion operation")
        obj.FFOp = op
    if data is not None:
        _ensure_prop(obj, "FFData", doc="FreeFusion feature parameters (JSON)")
        obj.FFData = json.dumps(data)
    return obj


def role(obj):
    return getattr(obj, "FFRole", "") if obj is not None else ""


def group_id(obj):
    return getattr(obj, "FFGroup", "") or obj.Name


def op(obj):
    return getattr(obj, "FFOp", "")


def data(obj):
    raw = getattr(obj, "FFData", "")
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


def group_members(doc, gid):
    return [o for o in doc.Objects if getattr(o, "FFGroup", "") == gid]


# ---------------------------------------------------------------------------
# Naming: Fusion style labels (Body1, Sketch2, Extrude3, ...)


def unique_label(doc, base):
    pat = re.compile(r"^%s(\d+)$" % re.escape(base))
    highest = 0
    for o in doc.Objects:
        m = pat.match(o.Label)
        if m:
            highest = max(highest, int(m.group(1)))
    return "%s%d" % (base, highest + 1)


def new_group_id(doc, base):
    """Return a new timeline group id (also used as the primary feature label)."""
    label = unique_label(doc, base)
    used = {getattr(o, "FFGroup", "") for o in doc.Objects}
    gid = label
    n = 1
    while gid in used:
        n += 1
        gid = "%s_%d" % (label, n)
    return label, gid


# ---------------------------------------------------------------------------
# Type helpers


def is_type(obj, *types):
    return obj is not None and any(obj.isDerivedFrom(t) for t in types)


def is_body(obj):
    return is_type(obj, "PartDesign::Body")


def is_component(obj):
    return is_type(obj, "App::Part") and not is_body(obj)


def is_sketch(obj):
    return is_type(obj, *SKETCH_TYPES)


def is_datum(obj):
    return is_type(obj, *DATUM_TYPES)


def is_pd_feature(obj):
    return is_type(obj, "PartDesign::Feature") and not is_body(obj)


def is_origin_feature(obj):
    return is_type(obj, "App::OriginFeature", "App::Origin", "App::LocalCoordinateSystem",
                   "App::DatumElement") and not is_datum(obj)


# ---------------------------------------------------------------------------
# Containers


def parent_group(obj):
    """Nearest GeoFeatureGroup (Body, Part, ...) owning obj, or None."""
    try:
        return obj.getParentGeoFeatureGroup()
    except Exception:
        return None


def body_of(obj):
    if obj is None:
        return None
    if is_body(obj):
        return obj
    b = getattr(obj, "_Body", None)
    if b is not None:
        return b
    p = parent_group(obj)
    while p is not None:
        if is_body(p):
            return p
        p = parent_group(p)
    return None


def component_of(obj):
    """Component (App::Part) that contains obj, or None when at document level."""
    p = parent_group(obj) if obj is not None else None
    while p is not None:
        if is_component(p):
            return p
        p = parent_group(p)
    return None


def root_component(doc, create=False):
    if doc is None:
        return None
    for o in doc.Objects:
        if role(o) == ROLE_ROOT and is_component(o):
            return o
    if not create:
        return None
    root = doc.addObject("App::Part", "Design")
    root.Label = doc.Label or "Design"
    tag(root, role=ROLE_ROOT)
    return root


_active_component = {}


def active_component(doc):
    """Component where new geometry goes (Fusion's 'activated' component)."""
    if doc is None:
        return None
    if App.GuiUp:
        try:
            import FreeCADGui as Gui
            gdoc = Gui.getDocument(doc.Name)
            view = gdoc.ActiveView if gdoc else None
            if view is not None and hasattr(view, "getActiveObject"):
                part = view.getActiveObject("part")
                if part is not None and is_component(part):
                    return part
        except Exception:
            pass
    comp = _active_component.get(doc.Name)
    if comp is not None:
        try:
            if comp.Document == doc and comp in doc.Objects:
                return comp
        except Exception:
            pass
    return root_component(doc, create=True)


def set_active_component(doc, comp):
    _active_component[doc.Name] = comp
    if App.GuiUp:
        try:
            import FreeCADGui as Gui
            view = Gui.getDocument(doc.Name).ActiveView
            if view is not None and hasattr(view, "setActiveObject"):
                if comp is None or role(comp) == ROLE_ROOT:
                    view.setActiveObject("part", None)
                else:
                    view.setActiveObject("part", comp)
        except Exception:
            pass


def add_to(container, obj):
    if container is not None and obj not in getattr(container, "Group", []):
        container.addObject(obj)
    return obj


def origin_of(container):
    return getattr(container, "Origin", None) if container is not None else None


def origin_feature(container, role_name):
    """role_name: XY_Plane, XZ_Plane, YZ_Plane, X_Axis, Y_Axis, Z_Axis, Origin."""
    origin = origin_of(container)
    if origin is None:
        return None
    for f in getattr(origin, "OriginFeatures", []):
        if getattr(f, "Role", "") == role_name:
            return f
    return None


# ---------------------------------------------------------------------------
# Creation helpers


def new_component(doc, parent=None, label=None):
    parent = parent if parent is not None else active_component(doc)
    comp = doc.addObject("App::Part", "Component")
    comp.Label = label or unique_label(doc, "Component")
    tag(comp, role=ROLE_COMPONENT)
    add_to(parent, comp)
    return comp


def new_body(doc, container=None, label=None):
    container = container if container is not None else active_component(doc)
    body = doc.addObject("PartDesign::Body", "Body")
    body.Label = label or unique_label(doc, "Body")
    tag(body, role=ROLE_BODY)
    add_to(container, body)
    return body


def new_sketch(doc, container=None, support=None, map_mode="FlatFace", placement=None,
               label=None):
    container = container if container is not None else active_component(doc)
    sk = doc.addObject("Sketcher::SketchObject", "Sketch")
    sk.Label = label or unique_label(doc, "Sketch")
    add_to(container, sk)
    if support:
        sk.AttachmentSupport = support
        sk.MapMode = map_mode
    elif placement is not None:
        sk.MapMode = "Deactivated"
        sk.Placement = placement
    if "MakeInternals" in sk.PropertiesList:
        sk.MakeInternals = True   # selectable profile regions, like Fusion
    return sk


def make_binder(body, refs, gid=None):
    """Create a hidden SubShapeBinder in body that copies refs=[(obj, [subs])]."""
    doc = body.Document
    binder = body.newObject("PartDesign::SubShapeBinder", "FF_Profile")
    binder.Support = [(o, tuple(s) if s else ("",)) for o, s in refs]
    for prop, val in (("BindMode", "Synchronized"), ("Fuse", False)):
        if prop in binder.PropertiesList:
            try:
                setattr(binder, prop, val)
            except Exception:
                pass
    tag(binder, role=ROLE_BINDER, group=gid)
    binder.Visibility = False
    if App.GuiUp:
        try:
            binder.ViewObject.Visibility = False
            if hasattr(binder.ViewObject, "ShowInTree"):
                binder.ViewObject.ShowInTree = False
        except Exception:
            pass
    return binder


# ---------------------------------------------------------------------------
# Queries


def design_bodies(doc, visible_only=False):
    """Bodies as the user sees them (excludes FreeFusion helper bodies)."""
    out = []
    for o in doc.Objects:
        if is_body(o):
            if role(o) in (ROLE_TOOL, ROLE_CONSUMED):
                continue
        elif role(o) != ROLE_BODY:
            continue
        if visible_only and not o.Visibility:
            continue
        out.append(o)
    return out


def body_solid(body):
    shape = getattr(body, "Shape", None)
    if shape is None or shape.isNull():
        return None
    return shape


def bodies_intersecting(doc, tool_shape, exclude=(), visible_only=True, tol=1e-6):
    hits = []
    if tool_shape is None or tool_shape.isNull():
        return hits
    tbb = tool_shape.BoundBox
    for b in design_bodies(doc, visible_only=visible_only):
        if b in exclude:
            continue
        s = body_solid(b)
        if s is None or not s.Solids:
            continue
        if not s.BoundBox.intersect(tbb):
            continue
        try:
            common = s.common(tool_shape)
            if common.Volume > tol:
                hits.append(b)
        except Exception:
            continue
    return hits


def ordered_objects(doc):
    return sorted(doc.Objects, key=lambda o: o.ID)


def hide_object(obj):
    try:
        if App.GuiUp and obj.ViewObject is not None:
            obj.ViewObject.Visibility = False
        else:
            obj.Visibility = False
    except Exception:
        pass


def show_object(obj):
    try:
        if App.GuiUp and obj.ViewObject is not None:
            obj.ViewObject.Visibility = True
        else:
            obj.Visibility = True
    except Exception:
        pass


def remove_objects(objs):
    """Delete objects, detaching PartDesign features from their bodies first."""
    for o in list(objs):
        try:
            doc = o.Document
        except Exception:
            continue
        if o not in doc.Objects:
            continue
        body = body_of(o) if not is_body(o) else None
        if body is not None:
            try:
                body.removeObject(o)
            except Exception:
                pass
        try:
            doc.removeObject(o.Name)
        except Exception:
            pass
