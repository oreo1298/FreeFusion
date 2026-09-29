# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD preferences that make the 3D view feel like Fusion 360.

``apply()`` writes them (backing up the previous values once) and ``restore()``
puts the user's original values back. The FreeFusion launcher uses a separate
user.cfg, so there these become simply the defaults of that profile.
"""

import FreeCAD as App

from . import params
from .params import rgba

P = "User parameter:BaseApp/Preferences/"
BACKUP = params.ROOT + "/Backup"
PROFILE_VERSION = 4


def _settings(theme="light"):
    dark = theme == "dark"
    s = [
        # --- navigation: Fusion = middle-drag pan, Shift+middle orbit, wheel zoom
        ("View", "ASCII", "NavigationStyle", "Gui::RevitNavigationStyle"),
        ("View", "Int", "OrbitStyle", 0),            # turntable, like Fusion's constrained orbit
        ("View", "Int", "RotationMode", 1),          # orbit around the point under the cursor
        ("View", "Bool", "ZoomAtCursor", True),
        ("View", "Bool", "InvertZoom", True),        # wheel forward = zoom in
        ("View", "Float", "ZoomStep", 0.2),
        ("View", "Bool", "UseNavigationAnimations", True),
        ("View", "Bool", "Orthographic", True),
        ("View", "Bool", "ShowAxisCross", False),
        ("View", "Bool", "CornerCoordSystem", True),
        ("View", "Int", "CornerCoordSystemSize", 10),
        ("View", "Bool", "ShowFPS", False),
        ("View", "Bool", "EnablePreselection", True),
        ("View", "Bool", "EnableSelection", True),
        ("View", "Float", "PickRadius", 5.0),
        # --- canvas
        ("View", "Bool", "Simple", False),
        ("View", "Bool", "Gradient", True),
        ("View", "Bool", "RadialGradient", False),
        ("View", "Bool", "UseBackgroundColorMid", False),
        ("View", "Unsigned", "BackgroundColor2", rgba("#3c4046" if dark else "#d5dce4")),
        ("View", "Unsigned", "BackgroundColor3", rgba("#5a6068" if dark else "#fbfcfd")),
        ("View", "Unsigned", "BackgroundColor", rgba("#50555c" if dark else "#f2f4f6")),
        ("View", "Unsigned", "SelectionColor", rgba("#0696d7")),
        ("View", "Unsigned", "HighlightColor", rgba("#7cc8ee")),
        ("View", "Unsigned", "DefaultShapeColor", rgba("#c5ccd4")),
        ("View", "Unsigned", "DefaultShapeLineColor", rgba("#202428")),
        ("View", "Unsigned", "DefaultShapeVertexColor", rgba("#202428")),
        ("View", "Int", "DefaultShapeLineWidth", 1),
        ("View", "Int", "DefaultShapePointSize", 3),
        ("View", "Int", "DefaultShapeShininess", 50),
        # --- sketch colours (Fusion: blue = under-constrained, black = fixed)
        ("View", "Unsigned", "EditedEdgeColor", rgba("#6cb4ff" if dark else "#1c6fd6")),
        ("View", "Unsigned", "EditedVertexColor", rgba("#6cb4ff" if dark else "#1c6fd6")),
        ("View", "Unsigned", "FullyConstraintElementColor", rgba("#f1f3f5" if dark else "#141618")),
        ("View", "Unsigned", "FullyConstraintConstructionElementColor", rgba("#ffa94d" if dark else "#d9480f")),
        ("View", "Unsigned", "FullyConstraintInternalAlignmentColor", rgba("#adb5bd" if dark else "#495057")),
        ("View", "Unsigned", "FullyConstrainedColor", rgba("#f1f3f5" if dark else "#141618")),
        ("View", "Unsigned", "ConstructionColor", rgba("#ffa94d" if dark else "#f08c00")),
        ("View", "Unsigned", "InternalAlignedGeoColor", rgba("#adb5bd" if dark else "#868e96")),
        ("View", "Unsigned", "ExternalColor", rgba("#da77f2" if dark else "#9c36b5")),
        ("View", "Unsigned", "ExternalDefiningColor", rgba("#e599f7" if dark else "#7b2cbf")),
        ("View", "Unsigned", "ConstrainedDimColor", rgba("#f1f3f5" if dark else "#212529")),
        ("View", "Unsigned", "ConstrainedIcoColor", rgba("#ff8787" if dark else "#c92a2a")),
        ("View", "Unsigned", "NonDrivingConstrDimColor", rgba("#adb5bd" if dark else "#868e96")),
        ("View", "Unsigned", "ExprBasedConstrDimColor", rgba("#ffa94d" if dark else "#e8590c")),
        ("View", "Unsigned", "CursorTextColor", rgba("#6cb4ff" if dark else "#1c6fd6")),
        ("View", "Unsigned", "SketchEdgeColor", rgba("#6cb4ff" if dark else "#2b5f9e")),
        ("View", "Unsigned", "SketchVertexColor", rgba("#6cb4ff" if dark else "#2b5f9e")),
        ("View", "Unsigned", "SketchFaceColor", rgba("#ffc078")),
        ("View", "Unsigned", "InvalidSketchColor", rgba("#e03131")),
        ("Mod/Sketcher/General", "Unsigned", "GridLineColor", rgba("#6b7178" if dark else "#dfe3e8")),
        ("Mod/Sketcher/General", "Unsigned", "GridDivLineColor", rgba("#7d848c" if dark else "#c7cdd4")),
        ("Mod/Sketcher/General", "Bool", "ShowGrid", True),
        ("Mod/Sketcher/General", "Bool", "LeaveSketchWithEscape", False),
        ("Mod/Sketcher/General", "Bool", "AutoRecompute", True),
        ("Mod/Sketcher/General", "Bool", "ShowDimensionalName", False),
        # --- ViewCube (NaviCube) in Fusion's position and colours
        ("NaviCube", "Int", "CornerNaviCube", 1),
        ("NaviCube", "Int", "CubeSize", 110),
        ("NaviCube", "Unsigned", "BaseColor", rgba("#4a5058" if dark else "#f4f6f8", 230)),
        ("NaviCube", "Unsigned", "EmphaseColor", rgba("#e9ecef" if dark else "#3c4146")),
        ("NaviCube", "Unsigned", "HiliteColor", rgba("#7cc8ee")),
        ("NaviCube", "Int", "InactiveOpacity", 70),
        ("NaviCube", "Bool", "NaviRotateToNearest", True),
        ("NaviCube", "ASCII", "TextFront", "FRONT"),
        ("NaviCube", "ASCII", "TextRear", "BACK"),
        ("NaviCube", "ASCII", "TextTop", "TOP"),
        ("NaviCube", "ASCII", "TextBottom", "BOTTOM"),
        ("NaviCube", "ASCII", "TextLeft", "LEFT"),
        ("NaviCube", "ASCII", "TextRight", "RIGHT"),
        # --- startup: no start page, straight into an untitled design
        ("Mod/Start", "Bool", "ShowOnStartup", False),
        ("Mod/Start", "Bool", "FirstStart2024", False),
        ("Mod/Start", "Bool", "closeStart", True),
        ("General", "ASCII", "AutoloadModule", "FreeFusionWorkbench"),
        # --- PartDesign: merge coplanar faces like Fusion does
        ("Mod/PartDesign", "Bool", "RefineModel", True),
        ("Mod/PartDesign", "Bool", "SwitchToWB", False),
        ("Mod/Assembly", "Bool", "SwitchToWB", False),
        # --- keep the report view closed like Fusion; errors show in the timeline
        ("OutputWindow", "Bool", "checkShowReportViewOnError", False),
        ("OutputWindow", "Bool", "checkShowReportViewOnWarning", False),
        # --- document
        ("Document", "Bool", "CreateBackupFiles", True),
        ("Document", "Int", "CountBackupFiles", 1),
        ("Document", "Bool", "SaveThumbnail", True),
        ("Document", "Bool", "AutoSaveEnabled", True),
        ("Document", "Int", "AutoSaveTimeout", 10),
    ]
    return s


def _group(path):
    return App.ParamGet(P + path)


def _get(grp, typ, key):
    """(exists, value) of a preference; GetContents tells us whether it was ever set."""
    contents = {k: v for (t, k, v) in _contents(_group(grp))}
    return (key in contents, contents.get(key))


def _contents(g):
    try:
        return g.GetContents() or []
    except Exception:
        return []


def _set(grp, typ, key, val):
    g = _group(grp)
    if typ == "ASCII":
        g.SetString(key, val)
    elif typ == "Bool":
        g.SetBool(key, bool(val))
    elif typ == "Int":
        g.SetInt(key, int(val))
    elif typ == "Unsigned":
        g.SetUnsigned(key, int(val))
    elif typ == "Float":
        g.SetFloat(key, float(val))


def _remove(grp, typ, key):
    g = _group(grp)
    fn = {"ASCII": "RemString", "Bool": "RemBool", "Int": "RemInt", "Unsigned": "RemUnsigned",
          "Float": "RemFloat"}[typ]
    try:
        getattr(g, fn)(key)
    except Exception:
        pass


def _backup_key(grp, key):
    return (grp + "/" + key).replace("/", "__")


def apply(theme=None, backup=True):
    """Write the Fusion preferences. The first call backs up the previous values."""
    theme = theme or params.get_string("Theme", "light")
    bk = App.ParamGet(BACKUP)
    have_backup = bk.GetBool("__has_backup__", False)
    for grp, typ, key, val in _settings(theme):
        if backup and not have_backup:
            exists, old = _get(grp, typ, key)
            bkey = _backup_key(grp, key)
            if exists:
                bk.SetString(bkey, "%s|%r" % (typ, old))
            else:
                bk.SetString(bkey, "%s|<unset>" % typ)
        _set(grp, typ, key, val)
    if backup and not have_backup:
        bk.SetBool("__has_backup__", True)
    params.set_int("ProfileVersion", PROFILE_VERSION)
    params.set_bool("FusionLookApplied", True)


def restore():
    """Restore the preferences that apply() overwrote."""
    import ast
    bk = App.ParamGet(BACKUP)
    if not bk.GetBool("__has_backup__", False):
        return False
    for grp, typ, key, _ in _settings():
        raw = bk.GetString(_backup_key(grp, key), "")
        if not raw:
            continue
        _typ, _, val = raw.partition("|")
        if val == "<unset>":
            _remove(grp, typ, key)
        else:
            try:
                _set(grp, typ, key, ast.literal_eval(val))
            except Exception:
                pass
    App.ParamGet(params.ROOT).RemGroup("Backup")
    params.set_bool("FusionLookApplied", False)
    return True


def needs_apply():
    """True in the FreeFusion launcher profile when the defaults are outdated."""
    return params.get_bool("ManagedProfile", False) and \
        params.get_int("ProfileVersion", 0) < PROFILE_VERSION
