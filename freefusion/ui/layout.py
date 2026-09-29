# SPDX-License-Identifier: LGPL-2.1-or-later
"""What goes where in the ribbon: Fusion 360's Design workspace layout.

A group is (TITLE, [quick buttons], [menu entries]); a menu entry is a command
name, "-" (separator) or ("Submenu", [entries]).
"""

PATTERN = ("Pattern", ["FF_RectPattern", "FF_CircPattern"])

SOLID = [
    ("CREATE",
     ["FF_NewComponent", "FF_CreateSketch", "FF_Extrude", "FF_Revolve", "FF_Hole", "FF_RectPattern"],
     ["FF_NewComponent", "FF_CreateSketch", "-",
      "FF_Extrude", "FF_Revolve", "FF_Sweep", "FF_Loft", "-",
      "FF_Hole", "FF_Thread", "-",
      "FF_Box", "FF_Cylinder", "FF_Sphere", "FF_Torus", "FF_Coil", "FF_Pipe", "-",
      PATTERN, "FF_Mirror", "FF_Thicken"]),
    ("MODIFY",
     ["FF_PressPull", "FF_Fillet", "FF_Chamfer", "FF_Shell", "FF_Combine", "FF_Parameters"],
     ["FF_PressPull", "FF_Fillet", "FF_Chamfer", "FF_Shell", "FF_Draft", "FF_Scale", "FF_Combine", "-",
      "FF_SplitBody", "FF_SplitFace", "-",
      "FF_Move", "FF_Align", "FF_Delete", "-",
      "FF_Material", "FF_Appearance", "-",
      "FF_Parameters", "FF_ComputeAll"]),
    ("ASSEMBLE",
     ["FF_NewComponent", "FF_Joint", "FF_Ground"],
     ["FF_NewComponent", "FF_Joint", "FF_AsBuiltJoint", "FF_RigidGroup", "FF_Ground", "-",
      "FF_InsertComponent", "FF_ExplodedView", "FF_BOM", "FF_Motion"]),
    ("CONSTRUCT",
     ["FF_OffsetPlane", "FF_AxisCylinder", "FF_PointVertex"],
     ["FF_OffsetPlane", "FF_PlaneAngle", "FF_TangentPlane", "FF_Midplane", "FF_PlaneTwoEdges",
      "FF_PlaneThreePoints", "FF_PlaneTangentAtPoint", "FF_PlaneAlongPath", "-",
      "FF_AxisCylinder", "FF_AxisNormal", "FF_AxisTwoPlanes", "FF_AxisTwoPoints", "FF_AxisEdge", "-",
      "FF_PointVertex", "FF_PointTwoEdges", "FF_PointThreePlanes", "FF_PointCenter",
      "FF_PointEdgePlane", "FF_PointAlongPath"]),
    ("INSPECT",
     ["FF_Measure", "FF_Interference", "FF_SectionAnalysis"],
     ["FF_Measure", "FF_Interference", "FF_SectionAnalysis", "FF_CenterOfMass", "FF_ComponentColors",
      "FF_Properties"]),
    ("INSERT",
     ["FF_InsertCAD", "FF_Canvas"],
     ["FF_InsertCAD", "FF_InsertMesh", "FF_InsertSVG", "FF_InsertDXF", "FF_Canvas"]),
    ("SELECT",
     ["FF_WindowSelect"],
     ["FF_WindowSelect", "FF_SelectAll", "-",
      ("Selection Priority", ["FF_SelectPriorityBody", "FF_SelectPriorityFace", "FF_SelectPriorityEdge",
                              "FF_SelectPriorityVertex", "FF_SelectPriorityNone"])]),
]

SURFACE = [
    ("CREATE",
     ["FF_SurfExtrude", "FF_SurfRevolve", "FF_SurfLoft", "FF_Patch"],
     ["FF_SurfExtrude", "FF_SurfRevolve", "FF_SurfSweep", "FF_SurfLoft", "FF_Patch", "FF_Ruled",
      "FF_SurfOffset", "FF_Boundary", "-", "FF_CreateSketch"]),
    ("MODIFY",
     ["FF_Stitch", "FF_Thicken", "FF_SurfExtend"],
     ["FF_Stitch", "FF_Unstitch", "FF_Thicken", "FF_SurfExtend", "FF_SurfSections", "-",
      "FF_Move", "FF_Delete"]),
    ("CONSTRUCT", ["FF_OffsetPlane"], ["FF_OffsetPlane", "FF_Midplane", "FF_AxisTwoPoints", "FF_PointVertex"]),
    ("INSPECT", ["FF_Measure", "FF_CheckGeometry"], ["FF_Measure", "FF_CheckGeometry", "FF_SectionAnalysis"]),
]

MESH = [
    ("CREATE", ["FF_InsertMesh", "FF_MeshFromBody"], ["FF_InsertMesh", "FF_MeshFromBody"]),
    ("PREPARE", ["FF_MeshRepair", "FF_MeshReduce"],
     ["FF_MeshRepair", "FF_MeshReduce", "FF_MeshSmooth", "FF_MeshRemesh"]),
    ("MODIFY", ["FF_MeshToBRep", "FF_MeshPlaneCut"],
     ["FF_MeshToBRep", "FF_MeshPlaneCut", "FF_MeshSection"]),
    ("EXPORT", ["FF_Print3D"], ["FF_Print3D", "FF_Export"]),
]

SHEETMETAL = [
    ("CREATE", ["FF_SMBase", "FF_SMFlange", "FF_SMBend"],
     ["FF_SMBase", "FF_SMFlange", "FF_SMBend", "FF_SMRelief", "FF_SMCorner", "FF_SMJunction"]),
    ("MODIFY", ["FF_SMUnfold"], ["FF_SMUnfold", "FF_SMSolidToSheet"]),
    ("ADD-ON", ["FF_AddonManager"], ["FF_AddonManager"]),
]

UTILITIES = [
    ("MAKE", ["FF_Print3D"], ["FF_Print3D", "FF_Export"]),
    ("ADD-INS", ["FF_Scripts", "FF_AddonManager"], ["FF_Scripts", "FF_RecordMacro", "FF_AddonManager"]),
    ("UTILITY", ["FF_Parameters", "FF_TextCommands", "FF_Preferences"],
     ["FF_Parameters", "FF_TextCommands", "FF_ModelTree", "FF_PropertyEditor", "-",
      "FF_Preferences", "FF_FreeCADPreferences", "FF_ToggleTheme", "FF_Shortcuts", "-",
      "FF_ApplyLook", "FF_RestoreLook"]),
]

SKETCH = [
    ("CREATE",
     ["FF_SkLine", "FF_SkRect2Point", "FF_SkCircle", "FF_SkArc3Point", "FF_SkPolygon", "FF_SkSlot",
      "FF_SkSpline", "FF_SkPoint", "FF_SkMirror", "FF_SkProject", "FF_SkDimension"],
     ["FF_SkLine",
      ("Rectangle", ["FF_SkRect2Point", "FF_SkRectCenter", "FF_SkRect3Point"]),
      ("Circle", ["FF_SkCircle", "FF_SkCircle3Point"]),
      ("Arc", ["FF_SkArc3Point", "FF_SkArcCenter"]),
      ("Polygon", ["FF_SkPolygon", "FF_SkHexagon"]),
      "FF_SkEllipse", ("Slot", ["FF_SkSlot", "FF_SkArcSlot"]),
      ("Spline", ["FF_SkSpline", "FF_SkSplineCP"]),
      "FF_SkPoint", "-",
      "FF_SkMirror", "FF_SkCircPattern", "FF_SkRectPattern", "-",
      ("Project / Include", ["FF_SkProject", "FF_SkIntersect"]), "FF_SkDimension"]),
    ("MODIFY",
     ["FF_SkFillet", "FF_SkTrim", "FF_SkOffset"],
     ["FF_SkFillet", "FF_SkChamfer", "FF_SkTrim", "FF_SkExtend", "FF_SkBreak", "FF_SkScale", "FF_SkOffset",
      "FF_SkMove", "-", "FF_SkConstruction", "FF_Parameters"]),
    ("CONSTRAINTS",
     ["FF_CHorVert", "FF_CCoincident", "FF_CTangent", "FF_CEqual", "FF_CParallel", "FF_CPerpendicular",
      "FF_CFix", "FF_CMidpoint", "FF_CConcentric", "FF_CCollinear", "FF_CSymmetry"],
     ["FF_CHorVert", "FF_CCoincident", "FF_CTangent", "FF_CEqual", "FF_CParallel", "FF_CPerpendicular",
      "FF_CFix", "FF_CMidpoint", "FF_CConcentric", "FF_CCollinear", "FF_CSymmetry", "-",
      "FF_SkToggleDriving"]),
    ("INSPECT", ["FF_Measure"], ["FF_Measure", "FF_SkValidate"]),
    ("PALETTE", ["FF_SkLookAt", "FF_SkGrid", "FF_SkSlice"],
     ["FF_SkLookAt", "FF_SkGrid", "FF_SkSnap", "FF_SkSlice", "FF_SkShowProfile"]),
    ("SELECT", ["FF_WindowSelect"], ["FF_WindowSelect", "FF_SelectAll"]),
]

TABS = [
    ("SOLID", SOLID),
    ("SURFACE", SURFACE),
    ("MESH", MESH),
    ("SHEET METAL", SHEETMETAL),
    ("UTILITIES", UTILITIES),
]

SKETCH_TAB = ("SKETCH", SKETCH)

# Fusion workspaces -> FreeCAD workbenches
WORKSPACES = [
    ("DESIGN", "FreeFusionWorkbench", "WSDesign"),
    ("RENDER", "RenderWorkbench", "WSRender"),
    ("ANIMATION", "AssemblyWorkbench", "WSAnimation"),
    ("SIMULATION", "FemWorkbench", "WSSimulation"),
    ("MANUFACTURE", "CAMWorkbench", "WSManufacture"),
    ("DRAWING", "TechDrawWorkbench", "WSDrawing"),
]

# marking menu (right click): 8 directions N, NE, E, SE, S, SW, W, NW
MARKING_MODEL = ["FF_Repeat", "FF_Delete", "FF_PressPull", "FF_Undo", "FF_Move", "FF_Hole", "FF_Redo",
                 "FF_CreateSketch"]
MARKING_SKETCH = ["FF_Repeat", "FF_Delete", "FF_SkDimension", "FF_Undo", "FF_FinishSketch", "FF_SkTrim",
                  "FF_SkLine", "FF_SkCircle"]
MARKING_MODEL_LIST = ["FF_Extrude", "FF_Fillet", "FF_Combine", "FF_OffsetPlane", "-", "FF_ToggleVisibility",
                      "FF_Isolate", "FF_ShowAll", "-", "FF_Appearance", "FF_Material", "FF_Properties", "-",
                      "FF_FindInBrowser", "FF_Toolbox"]
MARKING_SKETCH_LIST = ["FF_SkRect2Point", "FF_SkArc3Point", "FF_SkProject", "FF_SkOffset", "FF_SkMirror",
                       "-", "FF_SkConstruction", "FF_LookAt", "FF_Toolbox"]
