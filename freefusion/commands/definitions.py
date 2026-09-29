# SPDX-License-Identifier: LGPL-2.1-or-later
"""Every FreeFusion command (FF_*), with Fusion 360 names, icons and shortcuts."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from .. import design as D
from . import base
from .base import doc_open, in_sketch, not_editing, register, wrap

# ---------------------------------------------------------------------------
# helpers


def _doc():
    doc = App.ActiveDocument
    if doc is None:
        new_design()
        doc = App.ActiveDocument
    return doc


def new_design():
    doc = App.newDocument("Untitled")
    doc.Label = "Untitled"
    D.root_component(doc, create=True)
    doc.recompute()
    try:
        Gui.SendMsgToActiveView("ViewFit")
        Gui.activeDocument().activeView().viewIsometric()
    except Exception:
        pass
    return doc


def _show(factory):
    def run():
        from ..ui import widgets as W
        _doc()
        W.show(factory())
    return run


def _sel_refs():
    from ..ui.widgets import selection_refs
    return selection_refs()


def _sel_items():
    return [(o, s) for o, subs in _sel_refs() for s in (subs or [""])]


def _sel_bodies():
    out = []
    for o, _ in _sel_refs():
        b = D.body_of(o)
        if b is None and D.role(o) == D.ROLE_BODY:
            b = o
        if b is not None and b not in out:
            out.append(b)
    return out


def activate_body_from_selection():
    """PartDesign commands work on the active body: activate the selected one."""
    bodies = _sel_bodies()
    view = Gui.ActiveDocument.ActiveView if Gui.ActiveDocument else None
    if view is None:
        return None
    if bodies:
        view.setActiveObject("pdbody", bodies[0])
        return bodies[0]
    cur = view.getActiveObject("pdbody")
    if cur is None:
        all_bodies = D.design_bodies(App.ActiveDocument)
        if len(all_bodies) == 1:
            view.setActiveObject("pdbody", all_bodies[0])
            return all_bodies[0]
    return cur


def when_dialog_closed(callback, interval=300):
    """Call callback once the current task dialog has been closed."""
    timer = QtCore.QTimer()
    timer.setInterval(interval)

    def tick():
        if not Gui.Control.activeDialog() and not base.editing_vp():
            timer.stop()
            timer.deleteLater()
            callback()
    timer.timeout.connect(tick)
    timer.start()
    _timers.append(timer)
    if len(_timers) > 20:
        del _timers[:-20]


_timers = []


def _primitive(kind):
    """Box/Cylinder/...: Fusion creates a new body for a primitive by default."""
    def run():
        doc = _doc()
        doc.openTransaction(kind)
        body = D.new_body(doc)
        doc.commitTransaction()
        Gui.ActiveDocument.ActiveView.setActiveObject("pdbody", body)
        Gui.Selection.clearSelection()
        base.run_target("PartDesign_Additive" + kind)

        def cleanup():
            try:
                if body in doc.Objects and not [f for f in body.Group if D.is_pd_feature(f)]:
                    doc.removeObject(body.Name)
            except Exception:
                pass
        when_dialog_closed(cleanup)
    return run


def _pd(target):
    """Wrap a PartDesign command so it acts on the body of the selection."""
    return lambda: (activate_body_from_selection(), base.run_target(target))


def _pattern(target):
    def run():
        refs = _sel_refs()
        whole = [o for o, subs in refs if (D.is_body(o) or D.role(o) == D.ROLE_BODY) and not subs]
        if whole and D.is_body(whole[0]):
            body = whole[0]
            doc = body.Document
            kind = target.split("_")[1]
            doc.openTransaction(kind)
            f = body.newObject("PartDesign::" + kind, kind)
            f.TransformMode = "Whole shape"
            origin = body.Origin
            axis = [a for a in origin.OriginFeatures if a.Role == ("Z_Axis" if kind == "PolarPattern" else "X_Axis")][0]
            if kind == "Mirrored":
                f.MirrorPlane = ([a for a in origin.OriginFeatures if a.Role == "YZ_Plane"][0], [""])
            elif kind == "PolarPattern":
                f.Axis = (axis, [""])
                f.Occurrences = 6
            else:
                f.Direction = (axis, [""])
                f.Occurrences = 3
                f.Length = 50
            doc.commitTransaction()
            doc.recompute()
            Gui.ActiveDocument.setEdit(f.Name)
            return
        activate_body_from_selection()
        base.run_target(target)
    return run


def _assembly(target):
    """Run an Assembly command with the design's root assembly activated."""
    def run():
        doc = _doc()
        root = D.root_component(doc, create=True)
        if not D.is_assembly(root):
            from ..ui import notify
            notify.error("This design's root component is not an assembly; "
                         "joints need designs created with FreeFusion 'New Design'.")
            return
        gd = Gui.ActiveDocument
        was_editing = base.editing_object() == root
        if not was_editing:
            if gd.getInEdit() is not None:
                gd.resetEdit()
            gd.setEdit(root.Name)
        mods = ("CommandCreateAssembly", "CommandCreateJoint", "CommandInsertLink", "CommandCreateView",
                "CommandCreateBom", "CommandCreateSimulation", "CommandSolveAssembly")
        base.ensure_command(target, mods, "AssemblyWorkbench")
        if target.startswith("Assembly_CreateJoint"):
            parts = [o for o in root.Group if (D.is_component(o) or D.is_body(o) or D.role(o) == D.ROLE_BODY)
                     and D.role(o) not in (D.ROLE_TOOL, D.ROLE_CONSUMED)]
            if len(parts) < 2:
                from ..ui import notify
                notify.error("Joints connect two components or bodies of the design.")
                if not was_editing:
                    gd.resetEdit()
                return
            _ground_first_part(parts)
        base.run_target(target, mods, "AssemblyWorkbench")
        if not was_editing:
            def leave():
                if base.editing_object() == root:
                    gd.resetEdit()
            timer = QtCore.QTimer()
            timer.setInterval(400)

            def tick():
                if not Gui.Control.activeDialog():
                    timer.stop()
                    leave()
            timer.timeout.connect(tick)
            QtCore.QTimer.singleShot(600, timer.start)
            _timers.append(timer)
    return run


def _ground_first_part(parts):
    """Fusion grounds the first component automatically; FreeCAD 1.0 needs it for joints."""
    try:
        import UtilsAssembly
        grounded = UtilsAssembly.isAssemblyGrounded() if hasattr(UtilsAssembly, "isAssemblyGrounded") else True
    except Exception:
        return
    if grounded:
        return
    first = parts[0]
    try:
        import CommandCreateJoint
        doc = first.Document
        doc.openTransaction("Ground")
        CommandCreateJoint.createGroundedJoint(first)
        doc.commitTransaction()
        doc.recompute()
    except Exception as e:
        App.Console.PrintLog("FreeFusion: could not ground %s: %s\n" % (first.Label, e))


def _construct(key):
    def run():
        from ..ui import widgets as W
        from ..ui.panels.modify_panels import ConstructPanel
        _doc()
        pre = _sel_items()
        Gui.Selection.clearSelection()
        W.show(ConstructPanel(key, pre))
    return run


def _profile_panel(cls_name):
    def run():
        from ..ui import widgets as W
        from ..ui.panels import profile_panels as PP
        from ..ui import sketching
        doc = _doc()
        refs = _sel_refs()
        profiles = [(o, s) for o, s in refs if D.is_sketch(o) or any(x.startswith("Face") for x in s)]
        if not profiles:
            last = sketching.last_finished_sketch()
            if last is not None and last.Document == doc and last.Visibility:
                profiles = [(last, [])]
        Gui.Selection.clearSelection()
        W.show(getattr(PP, cls_name)(profiles))
    return run


def edit_feature(obj):
    """Open the right dialog to edit a timeline item (Fusion 'Edit Feature')."""
    from ..ui import widgets as W
    from ..ui.panels import profile_panels as PP
    from ..ui import sketching
    if obj is None:
        return
    if D.is_sketch(obj):
        sketching.edit_sketch(obj)
        return
    info = D.data(obj)
    kind = info.get("type")
    gid = D.group_id(obj)
    if kind == "Extrude":
        W.show(PP.ExtrudePanel(gid=gid))
    elif kind == "Revolve":
        W.show(PP.RevolvePanel(gid=gid))
    elif D.is_component(obj):
        D.set_active_component(obj.Document, obj)
    else:
        try:
            Gui.ActiveDocument.setEdit(obj.Name)
        except Exception:
            pass


def _selected_primary():
    for o, _ in _sel_refs():
        return o
    return None


def toggle_visibility():
    bodies = _sel_bodies()
    objs = bodies or [o for o, _ in _sel_refs()]
    for o in objs:
        try:
            o.ViewObject.Visibility = not o.ViewObject.Visibility
        except Exception:
            pass
    Gui.Selection.clearSelection()


def isolate():
    keep = set(b.Name for b in _sel_bodies())
    if not keep:
        return
    doc = App.ActiveDocument
    for b in D.design_bodies(doc):
        b.ViewObject.Visibility = b.Name in keep
    for o in doc.Objects:
        if D.is_sketch(o) or D.is_datum(o):
            o.ViewObject.Visibility = False
    Gui.Selection.clearSelection()


def show_all():
    doc = App.ActiveDocument
    for b in D.design_bodies(doc):
        b.ViewObject.Visibility = True


_priority = {"gate": None}


def select_priority(kind):
    def run():
        target = {"Body": None, "Face": "Part_FaceSelection", "Edge": "Part_EdgeSelection",
                  "Vertex": "Part_VertexSelection", "None": None}[kind]
        try:
            Gui.Selection.removeSelectionGate()
        except Exception:
            pass
        if kind == "Body":
            class _BodyGate(object):
                def allow(self, doc, obj, sub):
                    return D.body_of(obj) is not None or D.role(obj) == D.ROLE_BODY or D.is_component(obj)
            Gui.Selection.addSelectionGate(_BodyGate())
        elif target:
            base.run_target(target)
        from ..ui import notify
        notify.status("Selection priority: %s" % kind)
    return run


def look_at():
    if in_sketch():
        base.run_target("Sketcher_ViewSketch")
    elif Gui.Selection.getSelection():
        base.run_target("Std_AlignToSelection")
    else:
        base.run_target("Std_ViewHome")


def repeat():
    last = base.last_command()
    if last:
        Gui.runCommand(last, 0)


def component_colors():
    """Toggle random per-component colours (Fusion 'Display Component Colors')."""
    import random
    doc = App.ActiveDocument
    state = D.data(D.root_component(doc) or doc.Objects[0]).get("colors", False) if doc.Objects else False
    comps = [o for o in doc.Objects if D.is_component(o)]
    rnd = random.Random(7)
    for comp in comps:
        col = (rnd.uniform(.3, 1), rnd.uniform(.3, 1), rnd.uniform(.3, 1))
        for o in comp.Group:
            if D.is_body(o) or D.role(o) == D.ROLE_BODY:
                try:
                    if not state:
                        o.ViewObject.ShapeColor = col
                    else:
                        c = App.ParamGet("User parameter:BaseApp/Preferences/View").GetUnsigned(
                            "DefaultShapeColor", 0xCCCCCCFF)
                        o.ViewObject.ShapeColor = ((c >> 24 & 255) / 255.0, (c >> 16 & 255) / 255.0,
                                                   (c >> 8 & 255) / 255.0)
                except Exception:
                    pass
    root = D.root_component(doc)
    if root is not None:
        info = D.data(root)
        info["colors"] = not state
        D.tag(root, data=info)


def toggle_panel(name):
    def run():
        from ..ui import docks
        docks.toggle(name)
    return run


# ---------------------------------------------------------------------------


def register_all():
    # ---- application
    register("FF_NewDesign", "New Design", "Create a new design (Ctrl+N)", "NewDesign", new_design,
             active=base.always, keywords="new document file")
    wrap("FF_Open", "Std_Open", "Open...", "Open a design", "Open", active=base.always)
    wrap("FF_Save", "Std_Save", "Save", "Save the active design", "Save")
    wrap("FF_SaveAs", "Std_SaveAs", "Save As...", "Save the design under a new name", "Save")
    wrap("FF_Export", "Std_Export", "Export...", "Export to STEP, IGES, STL, 3MF, OBJ, DXF...", "Export")
    wrap("FF_Undo", "Std_Undo", "Undo", "Undo (Ctrl+Z)", "Undo", active=doc_open)
    wrap("FF_Redo", "Std_Redo", "Redo", "Redo (Ctrl+Y)", "Redo", active=doc_open)
    wrap("FF_Delete", "Std_Delete", "Delete", "Delete the selection (Del)", "Delete", keywords="remove")
    register("FF_Repeat", "Repeat Last Command", "Repeat the last command", "ComputeAll", repeat,
             active=lambda: base.last_command() is not None)
    register("FF_Toolbox", "Design Shortcuts", "Search and run any command (S)", "Toolbox",
             lambda: __import__("freefusion.ui.shortcut_box", fromlist=["x"]).show(),
             active=base.always, shortcut="S", keywords="search find command")

    # ---- CREATE
    register("FF_NewComponent", "New Component", "Create a new empty component", "NewComponent",
             lambda: (_doc().openTransaction("New Component"),
                      D.set_active_component(App.ActiveDocument, D.new_component(App.ActiveDocument)),
                      App.ActiveDocument.commitTransaction(), App.ActiveDocument.recompute()),
             active=not_editing, keywords="part assembly")
    register("FF_CreateSketch", "Create Sketch", "Create a sketch on a plane or planar face", "CreateSketch",
             lambda: __import__("freefusion.ui.sketching", fromlist=["x"]).create_sketch(),
             active=lambda: not in_sketch(), keywords="sketch 2d draw")
    register("FF_Extrude", "Extrude", "Add depth to a sketch profile or planar face (E)", "Extrude",
             _profile_panel("ExtrudePanel"), active=not_editing, shortcut="E", keywords="pad pocket extrusion")
    register("FF_Revolve", "Revolve", "Revolve a sketch profile around an axis", "Revolve",
             _profile_panel("RevolvePanel"), active=not_editing, keywords="revolution groove lathe")
    register("FF_Sweep", "Sweep", "Sweep a profile along a path", "Sweep",
             _show(lambda: __import__("freefusion.ui.panels.modify_panels", fromlist=["x"]).SweepPanel()),
             active=not_editing, keywords="pipe")
    register("FF_Loft", "Loft", "Blend between two or more profiles", "Loft",
             _show(lambda: __import__("freefusion.ui.panels.modify_panels", fromlist=["x"]).LoftPanel()),
             active=not_editing)
    register("FF_Hole", "Hole", "Place a hole on a planar face (H)", "Hole",
             lambda: __import__("freefusion.ui.sketching", fromlist=["x"]).hole(), active=not_editing,
             shortcut="H", keywords="drill counterbore countersink tapped")
    register("FF_Thread", "Thread", "Add a modeled thread to a cylindrical face", "Thread",
             lambda: __import__("freefusion.ui.tools", fromlist=["x"]).thread(), active=not_editing,
             keywords="screw metric")
    register("FF_Box", "Box", "Create a box as a new body", "Box", _primitive("Box"), active=not_editing)
    register("FF_Cylinder", "Cylinder", "Create a cylinder as a new body", "Cylinder", _primitive("Cylinder"),
             active=not_editing)
    register("FF_Sphere", "Sphere", "Create a sphere as a new body", "Sphere", _primitive("Sphere"),
             active=not_editing)
    register("FF_Torus", "Torus", "Create a torus as a new body", "Torus", _primitive("Torus"),
             active=not_editing)
    register("FF_Coil", "Coil", "Create a coil / spring", "Coil",
             lambda: __import__("freefusion.ui.tools", fromlist=["x"]).coil(), active=not_editing,
             keywords="spring helix")
    register("FF_Pipe", "Pipe", "Sweep a round section along a path", "Pipe",
             lambda: __import__("freefusion.ui.tools", fromlist=["x"]).pipe(), active=not_editing)
    register("FF_RectPattern", "Rectangular Pattern", "Pattern features or bodies in rows and columns",
             "RectPattern", _pattern("PartDesign_LinearPattern"), active=not_editing, keywords="array linear")
    register("FF_CircPattern", "Circular Pattern", "Pattern features or bodies around an axis",
             "CircPattern", _pattern("PartDesign_PolarPattern"), active=not_editing, keywords="array polar")
    register("FF_Mirror", "Mirror", "Mirror features or bodies about a plane", "Mirror",
             _pattern("PartDesign_Mirrored"), active=not_editing, keywords="symmetry")
    wrap("FF_Thicken", "Part_Thickness", "Thicken", "Add thickness to faces (Part thickness)", "Thicken")

    # ---- MODIFY
    register("FF_PressPull", "Press Pull", "Offset faces or fillet edges (Q)", "PressPull",
             lambda: __import__("freefusion.ui.tools", fromlist=["x"]).press_pull(), active=not_editing,
             shortcut="Q", keywords="offset face push pull")
    register("FF_Fillet", "Fillet", "Round edges (F)", "Fillet", _pd("PartDesign_Fillet"), active=not_editing,
             shortcut="F", keywords="round radius")
    register("FF_Chamfer", "Chamfer", "Bevel edges", "Chamfer", _pd("PartDesign_Chamfer"), active=not_editing,
             keywords="bevel")
    register("FF_Shell", "Shell", "Hollow a body, removing selected faces", "Shell",
             _pd("PartDesign_Thickness"), active=not_editing, keywords="thickness hollow")
    register("FF_Draft", "Draft", "Apply a draft angle to faces", "Draft", _pd("PartDesign_Draft"),
             active=not_editing, keywords="taper mold")
    register("FF_Scale", "Scale", "Scale a body", "Scale",
             _show(lambda: __import__("freefusion.ui.panels.modify_panels", fromlist=["x"]).ScalePanel()),
             active=not_editing)
    register("FF_Combine", "Combine", "Join, cut or intersect bodies", "Combine",
             _show(lambda: __import__("freefusion.ui.panels.modify_panels", fromlist=["x"]).CombinePanel()),
             active=not_editing, keywords="boolean union subtract")
    register("FF_SplitBody", "Split Body", "Split a body with a plane, face or body", "SplitBody",
             _show(lambda: __import__("freefusion.ui.panels.modify_panels", fromlist=["x"]).SplitBodyPanel()),
             active=not_editing, keywords="slice cut")
    wrap("FF_SplitFace", "Part_BooleanFragments", "Split Face", "Split faces with a tool (Boolean fragments)",
         "SplitFace", modules=("BOPTools.SplitFeatures", "PartGui"))
    register("FF_Move", "Move/Copy", "Move bodies or components (M)", "Move",
             lambda: __import__("freefusion.ui.tools", fromlist=["x"]).move(), active=not_editing, shortcut="M",
             keywords="translate rotate transform")
    wrap("FF_Align", "Std_Placement", "Align", "Position the selection precisely", "Align")
    register("FF_Material", "Physical Material", "Assign a physical material", "Material",
             lambda: (activate_body_from_selection(), base.run_target("Std_SetMaterial")),
             keywords="density steel aluminum")
    register("FF_Appearance", "Appearance", "Change the look of bodies or faces (A)", "Appearance",
             lambda: base.run_target("Std_SetAppearance"), shortcut="A", keywords="color colour")
    register("FF_Parameters", "Change Parameters", "User and model parameters", "Parameters",
             lambda: __import__("freefusion.ui.dialogs", fromlist=["x"]).show_parameters(),
             keywords="variables dimensions spreadsheet")
    register("FF_ComputeAll", "Compute All", "Recompute the whole design (Ctrl+B)", "ComputeAll",
             lambda: (App.ActiveDocument.recompute(None, True, True)), keywords="recompute update")

    # ---- ASSEMBLE
    register("FF_Joint", "Joint", "Position and constrain components (J)", "Joint",
             _assembly("Assembly_CreateJointRevolute"), active=not_editing, shortcut="J",
             keywords="assembly constraint revolute slider")
    register("FF_AsBuiltJoint", "As-built Joint", "Joint components in their current position",
             "AsBuiltJoint", _assembly("Assembly_CreateJointFixed"), active=not_editing)
    register("FF_RigidGroup", "Rigid Group", "Lock components together", "RigidGroup",
             _assembly("Assembly_CreateJointFixed"), active=not_editing)
    register("FF_Ground", "Ground", "Fix a component in place", "Ground",
             _assembly("Assembly_ToggleGrounded"), active=not_editing, keywords="fix")
    register("FF_InsertComponent", "Insert into Current Design", "Insert another design as a component",
             "InsertComponent", _assembly("Assembly_InsertLink"), active=not_editing, keywords="link")
    register("FF_ExplodedView", "Exploded View", "Create an exploded view", "ExplodedView",
             _assembly("Assembly_CreateView"), active=not_editing, keywords="animation explode")
    register("FF_BOM", "Bill of Materials", "Create a bill of materials", "BOM",
             _assembly("Assembly_CreateBom"), active=not_editing, keywords="parts list")
    register("FF_Motion", "Motion Study", "Drive joints and animate", "Motion",
             _assembly("Assembly_CreateSimulation"), active=not_editing, keywords="simulate animation")

    # ---- CONSTRUCT
    from ..ui.panels.modify_panels import CONSTRUCT
    for key, spec in CONSTRUCT.items():
        register("FF_" + key, spec[0].title().replace("/", " / "), spec[0].title(), spec[1], _construct(key),
                 active=not_editing, keywords="construction datum plane axis point")

    # ---- INSPECT
    wrap("FF_Measure", "Std_Measure", "Measure", "Measure distances, angles and sizes (I)", "Measure",
         shortcut="I", keywords="distance dimension")
    register("FF_Interference", "Interference", "Find overlaps between bodies", "Interference",
             lambda: __import__("freefusion.ui.dialogs", fromlist=["x"]).interference(), keywords="collision clash")
    wrap("FF_SectionAnalysis", "Part_SectionCut", "Section Analysis", "Cut the view to look inside",
         "SectionAnalysis", keywords="clip cross section")
    register("FF_CenterOfMass", "Center of Mass", "Show the center of mass", "CenterOfMass",
             lambda: __import__("freefusion.ui.dialogs", fromlist=["x"]).center_of_mass())
    register("FF_ComponentColors", "Display Component Colors", "Color each component differently",
             "ComponentColors", component_colors)
    register("FF_Properties", "Properties", "Mass, volume, area and center of mass", "Properties",
             lambda: __import__("freefusion.ui.dialogs", fromlist=["x"]).show_properties(),
             keywords="mass volume weight")
    wrap("FF_CheckGeometry", "Part_CheckGeometry", "Check Geometry", "Validate the selected shapes", "Properties")

    # ---- INSERT
    wrap("FF_InsertCAD", "Std_Import", "Insert CAD File", "Import STEP, IGES, BREP, STL... into the design",
         "InsertCAD", keywords="step iges import")
    register("FF_InsertMesh", "Insert Mesh", "Insert an STL / OBJ / 3MF mesh", "InsertMesh",
             lambda: __import__("freefusion.ui.tools", fromlist=["x"]).insert_file("Mesh (*.stl *.obj *.3mf *.ply *.off)"))
    register("FF_InsertSVG", "Insert SVG", "Insert an SVG drawing", "InsertSVG",
             lambda: __import__("freefusion.ui.tools", fromlist=["x"]).insert_file("SVG (*.svg)"))
    register("FF_InsertDXF", "Insert DXF", "Insert a DXF drawing", "InsertDXF",
             lambda: __import__("freefusion.ui.tools", fromlist=["x"]).insert_file("DXF (*.dxf)"))
    wrap("FF_Canvas", "Image_CreateImagePlane", "Canvas", "Place a reference image on a plane", "Canvas",
         modules=("ImageGui",), keywords="image picture reference")

    # ---- SELECT
    wrap("FF_WindowSelect", "Std_BoxElementSelection", "Window Selection", "Select by dragging a window",
         "WindowSelect")
    wrap("FF_SelectAll", "Std_SelectAll", "Select All", "Select everything", "SelectAll")
    for kind in ("Body", "Face", "Edge", "Vertex", "None"):
        register("FF_SelectPriority" + kind, "%s Priority" % kind if kind != "None" else "No Priority",
                 "Only select %ss" % kind.lower() if kind != "None" else "Select anything",
                 "Select" + (kind if kind != "None" else "All"), select_priority(kind))

    # ---- view / misc
    register("FF_LookAt", "Look At", "Look straight at the selection or sketch", "LookAt", look_at)
    wrap("FF_Home", "Std_ViewHome", "Home", "Home view", "Home")
    wrap("FF_Fit", "Std_ViewFitAll", "Fit", "Fit the design in the window (F6)", "Fit")
    register("FF_ToggleVisibility", "Show/Hide", "Toggle visibility of the selection (V)", "Eye",
             toggle_visibility, shortcut="V", keywords="hide show")
    register("FF_Isolate", "Isolate", "Show only the selected bodies", "Eye", isolate)
    register("FF_ShowAll", "Show All Bodies", "Show every body", "Eye", show_all)
    register("FF_FindInBrowser", "Find in Browser", "Reveal the selection in the browser", "Folder",
             lambda: __import__("freefusion.ui.browser", fromlist=["x"]).find_selection())

    # ---- SKETCH
    sk = [
        ("FF_SkLine", "Sketcher_CreatePolyline", "Line", "Draw lines and arcs (L)", "Line", "L"),
        ("FF_SkRect2Point", "Sketcher_CreateRectangle", "2-Point Rectangle", "Rectangle by two corners (R)",
         "Rect2Point", "R"),
        ("FF_SkRectCenter", "Sketcher_CreateRectangle_Center", "Center Rectangle", "Rectangle from its center",
         "RectCenter", ""),
        ("FF_SkRect3Point", "Sketcher_CreateRectangle", "3-Point Rectangle",
         "Rectangle tool (press M to cycle to the 3-point mode)", "Rect3Point", ""),
        ("FF_SkCircle", "Sketcher_CreateCircle", "Center Diameter Circle", "Circle by center and diameter (C)",
         "Circle", "C"),
        ("FF_SkCircle3Point", "Sketcher_Create3PointCircle", "3-Point Circle", "Circle through three points",
         "Circle3Point", ""),
        ("FF_SkArc3Point", "Sketcher_Create3PointArc", "3-Point Arc", "Arc through three points", "Arc3Point", ""),
        ("FF_SkArcCenter", "Sketcher_CreateArc", "Center Point Arc", "Arc from center, start and end",
         "ArcCenter", ""),
        ("FF_SkPolygon", "Sketcher_CreateRegularPolygon", "Polygon", "Regular polygon", "Polygon", ""),
        ("FF_SkHexagon", "Sketcher_CreateHexagon", "Hexagon", "Regular hexagon", "Polygon", ""),
        ("FF_SkEllipse", "Sketcher_CreateEllipseByCenter", "Ellipse", "Ellipse by center", "Ellipse", ""),
        ("FF_SkSlot", "Sketcher_CreateSlot", "Center to Center Slot", "Straight slot", "Slot", ""),
        ("FF_SkArcSlot", "Sketcher_CreateArcSlot", "Arc Slot", "Curved slot", "Slot", ""),
        ("FF_SkSpline", "Sketcher_CreateBSplineByInterpolation", "Fit Point Spline", "Spline through points",
         "Spline", ""),
        ("FF_SkSplineCP", "Sketcher_CreateBSpline", "Control Point Spline", "Spline by control points",
         "SplineCP", ""),
        ("FF_SkPoint", "Sketcher_CreatePoint", "Point", "Sketch point", "SketchPoint", ""),
        ("FF_SkMirror", "Sketcher_Symmetry", "Mirror", "Mirror sketch geometry about a line", "SketchMirror", ""),
        ("FF_SkCircPattern", "Sketcher_Rotate", "Circular Pattern", "Pattern sketch geometry around a point",
         "SketchCircPattern", ""),
        ("FF_SkRectPattern", "Sketcher_RectangularArray", "Rectangular Pattern", "Pattern sketch geometry in rows",
         "SketchRectPattern", ""),
        ("FF_SkProject", "Sketcher_Projection", "Project", "Project model geometry onto the sketch (P)",
         "Project", "P"),
        ("FF_SkIntersect", "Sketcher_Intersection", "Intersect", "Intersect model geometry with the sketch plane",
         "Project", ""),
        ("FF_SkDimension", "Sketcher_Dimension", "Sketch Dimension", "Add a driving dimension (D)",
         "SketchDimension", "D"),
        ("FF_SkFillet", "Sketcher_CreateFillet", "Fillet", "Round a sketch corner", "SketchFillet", ""),
        ("FF_SkChamfer", "Sketcher_CreateChamfer", "Chamfer", "Bevel a sketch corner", "SketchChamfer", ""),
        ("FF_SkTrim", "Sketcher_Trimming", "Trim", "Trim curves at intersections (T)", "Trim", "T"),
        ("FF_SkExtend", "Sketcher_Extend", "Extend", "Extend a curve to the next one", "Extend", ""),
        ("FF_SkBreak", "Sketcher_Split", "Break", "Break a curve at a point", "Break", ""),
        ("FF_SkScale", "Sketcher_Scale", "Sketch Scale", "Scale sketch geometry", "SketchScale", ""),
        ("FF_SkOffset", "Sketcher_Offset", "Offset", "Offset sketch curves (O)", "SketchOffset", "O"),
        ("FF_SkMove", "Sketcher_Translate", "Move/Copy", "Move or copy sketch geometry", "SketchMove", ""),
        ("FF_SkConstruction", "Sketcher_ToggleConstruction", "Normal/Construction",
         "Toggle construction geometry (X)", "Construction", "X"),
        ("FF_SkToggleDriving", "Sketcher_ToggleDrivingConstraint", "Driven Dimension",
         "Toggle a dimension between driving and driven", "SketchDimension", ""),
        ("FF_SkValidate", "Sketcher_ValidateSketch", "Validate Sketch", "Find and fix sketch problems",
         "Properties", ""),
        ("FF_CHorVert", "Sketcher_ConstrainHorVer", "Horizontal/Vertical", "Horizontal or vertical constraint",
         "HorizontalVertical", ""),
        ("FF_CCoincident", "Sketcher_ConstrainCoincidentUnified", "Coincident", "Coincident constraint",
         "Coincident", ""),
        ("FF_CTangent", "Sketcher_ConstrainTangent", "Tangent", "Tangent constraint", "Tangent", ""),
        ("FF_CEqual", "Sketcher_ConstrainEqual", "Equal", "Equal constraint", "Equal", ""),
        ("FF_CParallel", "Sketcher_ConstrainParallel", "Parallel", "Parallel constraint", "Parallel", ""),
        ("FF_CPerpendicular", "Sketcher_ConstrainPerpendicular", "Perpendicular", "Perpendicular constraint",
         "Perpendicular", ""),
        ("FF_CFix", "Sketcher_ConstrainBlock", "Fix/Unfix", "Fix geometry in place", "Fix", ""),
        ("FF_CMidpoint", "Sketcher_ConstrainSymmetric", "Midpoint",
         "Midpoint: select a point and a line (symmetric about its end points)", "Midpoint", ""),
        ("FF_CConcentric", "Sketcher_ConstrainCoincidentUnified", "Concentric",
         "Concentric: select two circles or arcs", "Concentric", ""),
        ("FF_CCollinear", "Sketcher_ConstrainTangent", "Collinear", "Collinear: tangent between two lines",
         "Collinear", ""),
        ("FF_CSymmetry", "Sketcher_ConstrainSymmetric", "Symmetry", "Symmetry constraint", "Symmetry", ""),
    ]
    for name, target, menu, tip, icon, key in sk:
        wrap(name, target, menu, tip, icon, active=in_sketch, shortcut=key, keywords="sketch")
    register("FF_FinishSketch", "Finish Sketch", "Leave the sketch", "FinishSketch",
             lambda: __import__("freefusion.ui.sketching", fromlist=["x"]).finish_sketch(), active=in_sketch)

    # ---- SURFACE
    surf = [
        ("FF_SurfExtrude", "Part_Extrude", "Extrude", "Extrude a curve into a surface", "Surface", ("PartGui",)),
        ("FF_SurfRevolve", "Part_Revolve", "Revolve", "Revolve a curve into a surface", "Revolve", ("PartGui",)),
        ("FF_SurfSweep", "Part_Sweep", "Sweep", "Sweep a curve along a path", "Sweep", ("PartGui",)),
        ("FF_SurfLoft", "Part_Loft", "Loft", "Loft through curves", "Loft", ("PartGui",)),
        ("FF_Patch", "Surface_Filling", "Patch", "Fill a closed boundary with a surface", "Patch", ("SurfaceGui",)),
        ("FF_Ruled", "Part_RuledSurface", "Ruled", "Ruled surface between two curves", "Surface", ("PartGui",)),
        ("FF_SurfOffset", "Part_Offset", "Offset", "Offset a surface or solid", "Surface", ("PartGui",)),
        ("FF_Boundary", "Surface_GeomFillSurface", "Boundary Fill", "Surface from boundary curves", "Patch",
         ("SurfaceGui",)),
        ("FF_Stitch", "Part_MakeSolid", "Stitch", "Stitch closed surfaces into a solid", "Stitch", ("PartGui",)),
        ("FF_Unstitch", "Part_Explode", "Unstitch", "Split a body into its faces",
         "Stitch", ("CompoundTools.Explode", "PartGui")),
        ("FF_SurfExtend", "Surface_Extend", "Extend", "Extend a surface", "Surface", ("SurfaceGui",)),
        ("FF_SurfSections", "Surface_Sections", "Section Blend", "Surface through sections", "Surface",
         ("SurfaceGui",)),
    ]
    for name, target, menu, tip, icon, mods in surf:
        wrap(name, target, menu, tip, icon, modules=mods, workbench="SurfaceWorkbench", keywords="surface")

    # ---- MESH
    mesh = [
        ("FF_MeshFromBody", "MeshPart_Mesher", "Mesh from Body", "Tessellate a body into a mesh", "Mesh"),
        ("FF_MeshRepair", "Mesh_Evaluation", "Repair", "Analyse and repair a mesh", "Repair"),
        ("FF_MeshReduce", "Mesh_Decimating", "Reduce", "Reduce the number of triangles", "Reduce"),
        ("FF_MeshSmooth", "Mesh_Smoothing", "Smooth", "Smooth a mesh", "Mesh"),
        ("FF_MeshRemesh", "Mesh_RemeshGmsh", "Remesh", "Remesh with Gmsh", "Mesh"),
        ("FF_MeshToBRep", "Part_ShapeFromMesh", "Convert Mesh", "Convert a mesh into a body", "MeshToBRep"),
        ("FF_MeshPlaneCut", "Mesh_TrimByPlane", "Plane Cut", "Cut a mesh with a plane", "SectionAnalysis"),
        ("FF_MeshSection", "MeshPart_CrossSections", "Section", "Mesh cross sections", "SectionAnalysis"),
    ]
    for name, target, menu, tip, icon in mesh:
        wrap(name, target, menu, tip, icon, modules=("MeshGui", "MeshPartGui", "PartGui"),
             workbench="MeshWorkbench", keywords="mesh stl")
    register("FF_Print3D", "3D Print", "Export bodies for 3D printing", "Print3D",
             lambda: __import__("freefusion.ui.dialogs", fromlist=["x"]).print3d(), keywords="stl 3mf slicer")

    # ---- SHEET METAL (SheetMetal add-on)
    sm = [
        ("FF_SMBase", "SheetMetal_AddBase", "Flange (Base)", "Create a sheet metal base from a sketch", "Sheetmetal"),
        ("FF_SMFlange", "SheetMetal_AddWall", "Flange", "Add a flange to an edge", "Flange"),
        ("FF_SMBend", "SheetMetal_AddFoldWall", "Bend", "Bend along a sketch line", "Flange"),
        ("FF_SMRelief", "SheetMetal_AddRelief", "Relief", "Add a relief", "Sheetmetal"),
        ("FF_SMCorner", "SheetMetal_AddCornerRelief", "Corner Relief", "Add a corner relief", "Sheetmetal"),
        ("FF_SMJunction", "SheetMetal_AddJunction", "Junction", "Split a corner into a junction", "Sheetmetal"),
        ("FF_SMUnfold", "SheetMetal_Unfold", "Create Flat Pattern", "Unfold the sheet metal part", "Unfold"),
        ("FF_SMSolidToSheet", "SheetMetal_AddBaseShape", "Base Shape", "Sheet metal base shape", "Sheetmetal"),
    ]
    for name, target, menu, tip, icon in sm:
        wrap(name, target, menu, tip, icon, workbench="SMWorkbench", keywords="sheet metal")

    # ---- UTILITIES
    wrap("FF_Scripts", "Std_DlgMacroExecute", "Scripts and Add-Ins", "Run Python macros", "Scripts",
         active=base.always, keywords="macro python")
    wrap("FF_RecordMacro", "Std_DlgMacroRecord", "Record Macro", "Record a macro", "Scripts", active=base.always)
    wrap("FF_AddonManager", "Std_AddonMgr", "Add-on Manager", "Install workbenches and add-ons", "AddIns",
         active=base.always, keywords="plugin install")
    register("FF_TextCommands", "Text Commands", "Show the Python console and report view", "TextCommands",
             toggle_panel("console"), active=base.always, keywords="python console log")
    register("FF_ModelTree", "Model Tree", "Show FreeCAD's model tree", "Folder", toggle_panel("tree"),
             active=base.always)
    register("FF_PropertyEditor", "Property Editor", "Show FreeCAD's property editor", "Properties",
             toggle_panel("properties"), active=base.always)
    register("FF_Preferences", "FreeFusion Preferences", "Theme, shortcuts and behaviour", "Preferences",
             lambda: __import__("freefusion.ui.preferences", fromlist=["x"]).show(), active=base.always)
    wrap("FF_FreeCADPreferences", "Std_DlgPreferences", "FreeCAD Preferences", "All FreeCAD preferences",
         "Settings", active=base.always)
    register("FF_ToggleTheme", "Toggle Dark Theme", "Switch between the light and dark theme", "DisplayMode",
             lambda: __import__("freefusion.ui.preferences", fromlist=["x"]).toggle_theme(), active=base.always)
    register("FF_Shortcuts", "Keyboard Shortcuts", "Show and change FreeFusion shortcuts", "Shortcuts",
             lambda: __import__("freefusion.ui.preferences", fromlist=["x"]).show(page="keys"), active=base.always)
    register("FF_ApplyLook", "Apply Fusion Navigation & Colors", "Write Fusion-like navigation, colors and "
             "ViewCube settings into the FreeCAD preferences", "Orbit",
             lambda: __import__("freefusion.ui.preferences", fromlist=["x"]).apply_look(), active=base.always)
    register("FF_RestoreLook", "Restore FreeCAD Settings", "Undo 'Apply Fusion Navigation & Colors'", "Undo",
             lambda: __import__("freefusion.ui.preferences", fromlist=["x"]).restore_look(), active=base.always)
