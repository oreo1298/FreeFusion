# SPDX-License-Identifier: LGPL-2.1-or-later
"""Turns the FreeCAD window into the Fusion 360 layout while FreeFusion is active."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from .. import design as D
from .. import params
from ..commands import base
from . import browser, docks, keys, theme, timeline_ui, viewport
from .ribbon import RibbonBar, WorkspaceBar

WB_NAME = "FreeFusionWorkbench"

_state = {
    "active": False, "ribbon": None, "wsbar": None, "hidden": [], "doc_obs": None, "sel_obs": None,
    "watch": None, "in_sketch": False, "editing": None, "global": False,
}

FUSION_NAMES = [
    ("PartDesign::Pad", "Extrude"), ("PartDesign::Pocket", "Extrude"), ("PartDesign::Revolution", "Revolve"),
    ("PartDesign::Groove", "Revolve"), ("PartDesign::Fillet", "Fillet"), ("PartDesign::Chamfer", "Chamfer"),
    ("PartDesign::Thickness", "Shell"), ("PartDesign::Draft", "Draft"), ("PartDesign::Hole", "Hole"),
    ("PartDesign::LinearPattern", "Rectangular Pattern"), ("PartDesign::PolarPattern", "Circular Pattern"),
    ("PartDesign::Mirrored", "Mirror"), ("PartDesign::MultiTransform", "Pattern"),
    ("PartDesign::AdditivePipe", "Sweep"), ("PartDesign::SubtractivePipe", "Sweep"),
    ("PartDesign::AdditiveLoft", "Loft"), ("PartDesign::SubtractiveLoft", "Loft"),
    ("PartDesign::AdditiveHelix", "Coil"), ("PartDesign::SubtractiveHelix", "Coil"),
    ("PartDesign::AdditiveBox", "Box"), ("PartDesign::AdditiveCylinder", "Cylinder"),
    ("PartDesign::AdditiveSphere", "Sphere"), ("PartDesign::AdditiveTorus", "Torus"),
    ("PartDesign::AdditiveCone", "Cone"), ("PartDesign::Boolean", "Combine"),
    ("Sketcher::SketchObject", "Sketch"), ("PartDesign::Body", "Body"),
    ("Part::DatumPlane", "Plane"), ("PartDesign::Plane", "Plane"), ("Part::DatumLine", "Axis"),
    ("PartDesign::Line", "Axis"), ("Part::DatumPoint", "Point"), ("PartDesign::Point", "Point"),
]


def _mw():
    return Gui.getMainWindow()


# ---------------------------------------------------------------------------
# observers


class DocObserver(object):
    PROPS = {"Label", "Visibility", "Group", "Suppressed", "FFRole", "Tip", "Meta"}

    def slotCreatedObject(self, obj):
        doc = obj.Document
        loading = any(getattr(doc, flag, False) for flag in ("Restoring", "Transacting", "Importing"))
        if _state["active"] and not loading:
            QtCore.QTimer.singleShot(0, lambda o=obj: _fusion_name(o))
            if D.is_sketch(obj):
                QtCore.QTimer.singleShot(0, lambda o=obj: D.keep_sketch_in_workbench(o))
        refresh()

    def slotFinishRestoreDocument(self, doc):
        _prepare_document(doc)
        refresh()

    def slotDeletedObject(self, obj):
        refresh()

    def slotChangedObject(self, obj, prop):
        if prop == "Geometry":
            from . import sketch_tools
            sketch_tools.geometry_changed(obj)
        elif prop == "Constraints":
            from . import sketch_dims
            sketch_dims.constraints_changed(obj)
        if prop in self.PROPS:
            refresh()

    def slotRecomputedDocument(self, doc):
        refresh()

    def slotActivateDocument(self, doc):
        refresh()

    def slotCreatedDocument(self, doc):
        name = doc.Name
        QtCore.QTimer.singleShot(400, lambda: _init_new_document(name))
        refresh()

    def slotDeletedDocument(self, doc):
        refresh()

    def slotRelabelDocument(self, doc):
        _sync_root_label(doc)
        refresh()

    def slotStartSaveDocument(self, doc, filename=None):
        # Fusion style version numbers (v1, v2, ...) stored in the file itself
        try:
            meta = dict(doc.Meta)
            meta["FreeFusion.Version"] = str(int(meta.get("FreeFusion.Version", "0")) + 1)
            doc.Meta = meta
        except Exception:
            pass

    def slotFinishSaveDocument(self, doc, filename=None):
        _sync_root_label(doc)
        refresh()

    def slotCommitTransaction(self, doc):
        from . import sketch_dims
        sketch_dims.committed(doc)

    def slotAbortTransaction(self, doc):
        from . import sketch_dims
        sketch_dims.aborted(doc)

    def slotUndoDocument(self, doc):
        refresh()

    def slotRedoDocument(self, doc):
        refresh()


class SelObserver(object):
    def _sync(self):
        b = browser.instance()
        if b is not None and _state["active"]:
            QtCore.QTimer.singleShot(0, b._sync_from_selection)

    def addSelection(self, *a):
        self._sync()

    def removeSelection(self, *a):
        self._sync()

    def setSelection(self, *a):
        self._sync()

    def clearSelection(self, *a):
        self._sync()


def _fusion_name(obj):
    try:
        if obj.Document is None or obj not in obj.Document.Objects:
            return
    except Exception:
        return
    if obj.Label != obj.Name or getattr(obj, "FFGroup", ""):
        return
    for t, base_name in FUSION_NAMES:
        try:
            if obj.isDerivedFrom(t):
                obj.Label = D.unique_label(obj.Document, base_name)
                return
        except Exception:
            return
    if D.is_component(obj) and not D.role(obj):
        obj.Label = D.unique_label(obj.Document, "Component")


def _sync_root_label(doc):
    """Fusion names the root component after the design."""
    try:
        root = D.root_component(doc)
        if root is not None and root.Label != doc.Label and \
                (root.Label.startswith("Untitled") or root.Label.startswith("Design")
                 or root.Label == D.data(root).get("doc_label")):
            root.Label = doc.Label
            info = D.data(root)
            info["doc_label"] = doc.Label
            D.tag(root, data=info)
    except Exception:
        pass


def _prepare_document(doc):
    if not _state["active"]:
        return
    for o in doc.Objects:
        if D.is_sketch(o):
            D.keep_sketch_in_workbench(o)


def _init_new_document(name):
    """New empty documents get a Fusion style root component."""
    if not _state["active"]:
        return
    try:
        doc = App.getDocument(name)
    except Exception:
        return
    if doc.FileName or doc.Objects:
        return
    D.root_component(doc, create=True)
    doc.recompute()
    try:
        viewport.default_view(Gui.getDocument(name).ActiveView)
    except Exception:
        pass
    viewport.install_filters(True)
    viewport.refresh_grids(True)


_refresh_timer = {"t": None}


def refresh():
    if not _state["active"]:
        return
    t = _refresh_timer["t"]
    if t is None:
        t = QtCore.QTimer()
        t.setSingleShot(True)
        t.setInterval(120)
        t.timeout.connect(_do_refresh)
        _refresh_timer["t"] = t
    t.start()


def _do_refresh():
    if not _state["active"]:
        return
    b = browser.instance()
    if b is not None:
        b.rebuild()
    tl = timeline_ui.instance()
    if tl is not None:
        tl.timeline.refresh()
    _update_title()


def _update_title():
    rb = _state["ribbon"]
    if rb is None:
        return
    doc = App.ActiveDocument
    if doc is None:
        rb.appbar.set_title("")
        return
    modified = False
    try:
        modified = Gui.getDocument(doc.Name).Modified
    except Exception:
        pass
    rb.appbar.set_title("%s%s" % (doc.Label, "  ●" if modified else ""))


# ---------------------------------------------------------------------------
# edit mode watcher (sketch contextual tab, deferred sketch tools)


def _enforce_layout():
    """FreeCAD re-shows some panels/toolbars on its own timers; keep the Fusion layout."""
    for tb in _std_toolbars():
        if tb.isVisible():
            tb.hide()
            tb.toggleViewAction().setVisible(False)
            if tb not in _state.get("changed", []):
                _state.setdefault("changed", []).append(tb)
    dialog = bool(Gui.Control.activeDialog())
    for d in docks._find(docks.FC_DOCKS["tasks"]):
        if docks.in_overlay(d):
            # FreeCAD 1.1 floats the task panel over the 3D view (like Fusion's
            # dialogs) but never hides it when it is empty; do that here.
            docks.show_overlay_for(d, dialog or params.get_bool("Show_tasks", False))
            continue
        want = dialog or params.get_bool("Show_tasks", False)
        if d.isVisible() != want:
            d.setVisible(want)
            if want:
                d.raise_()


def _install_palette(tries=8):
    from . import sketch_palette
    if not base.in_sketch():
        return
    try:
        if sketch_palette.install():
            return
    except Exception as e:
        App.Console.PrintLog("FreeFusion palette: %s\n" % e)
        return
    if tries > 0:
        QtCore.QTimer.singleShot(150, lambda: _install_palette(tries - 1))


def _watch():
    if not _state["active"]:
        return
    try:
        _enforce_layout()
    except Exception:
        pass
    sketch = base.in_sketch()
    if sketch != _state["in_sketch"]:
        _state["in_sketch"] = sketch
        if _state["ribbon"] is not None:
            _state["ribbon"].ribbon.set_sketch_mode(sketch)
        k = keys.instance()
        if sketch and k is not None:
            k.sketch_opened()
        # the sketch grid replaces the ground grid while sketching
        from . import grid, sketch_snap
        grid.refresh(force=True)
        if not sketch:
            sketch_snap.hide_marker()
        if sketch:
            obj = base.editing_object()
            _state["editing"] = (obj.Document.Name, obj.Name) if obj is not None else None
            from . import sketch_snap, sketch_dims
            sketch_snap.sketch_opened(obj)
            if obj is not None:
                sketch_dims.remember(obj)
            _install_palette()
        else:
            ed = _state["editing"]
            _state["editing"] = None
            if ed:
                try:
                    from ..features import parameters as PR
                    sk = App.getDocument(ed[0]).getObject(ed[1])
                    if sk is not None:
                        PR.name_dimensions(sk)
                        from . import sketching
                        sketching._last_sketch["name"] = ed
                except Exception:
                    pass
            refresh()
    _update_title()


# ---------------------------------------------------------------------------
# activation


def _std_toolbars():
    mw = _mw()
    out = []
    for tb in mw.findChildren(QtWidgets.QToolBar):
        if tb.objectName() in ("FreeFusionRibbon", "FreeFusionWorkspace"):
            continue
        if tb.parent() is not mw:
            continue
        out.append(tb)
    return out


def restyle():
    if params.get_bool("StyleWindow", True) and _state["active"]:
        theme.apply()
    else:
        theme.restore()
    viewport.refresh_grids(False)
    viewport.refresh_grids(_state["active"])
    # rebuild widgets so icons and painted colours follow the theme
    mw = _mw()
    if _state["ribbon"] is not None:
        old = _state["ribbon"]
        mw.removeToolBar(old)
        old.deleteLater()
        _state["ribbon"] = RibbonBar(mw)
        mw.addToolBar(QtCore.Qt.TopToolBarArea, _state["ribbon"])
        _state["ribbon"].setVisible(_state["active"])
        _state["ribbon"].ribbon.workspace.refresh("DESIGN")
        _state["ribbon"].ribbon.set_sketch_mode(base.in_sketch())
    if _state["wsbar"] is not None:
        _state["wsbar"].button.refresh()
    b = browser.instance()
    if b is not None:
        b._eye, b._eye_off = theme.icon("Eye"), theme.icon("EyeOff")
        b._radio, b._radio_on = theme.icon("Radio"), theme.icon("RadioOn")
        b.rebuild()
    timeline_ui.recreate()
    refresh()


def activated():
    mw = _mw()
    _state["active"] = True
    setup_global()
    if params.get_bool("StyleWindow", True):
        theme.apply()
    if _state["ribbon"] is None:
        _state["ribbon"] = RibbonBar(mw)
        mw.addToolBar(QtCore.Qt.TopToolBarArea, _state["ribbon"])
    rb = _state["ribbon"]
    rb.show()
    rb.ribbon.workspace.refresh("DESIGN")
    # hide FreeCAD's toolbars without recording that as the user's choice
    hidden, changed = [], []
    for tb in _std_toolbars():
        if tb.isVisible():
            hidden.append(tb)
        if tb.toggleViewAction().isVisible():
            changed.append(tb)
        tb.hide()
        tb.toggleViewAction().setVisible(False)
    _state["hidden"] = hidden
    _state["changed"] = changed
    if _state["wsbar"] is not None:
        _state["wsbar"].hide()
    docks.activate()
    if params.get_bool("ManagedProfile", False):
        # new designs are saved into the local projects folder by default
        gen = App.ParamGet("User parameter:BaseApp/Preferences/General")
        if not gen.GetString("FileOpenSavePath", ""):
            from . import datapanel
            import os
            try:
                os.makedirs(datapanel.projects_dir(), exist_ok=True)
                gen.SetString("FileOpenSavePath", datapanel.projects_dir())
            except OSError:
                pass
    for doc in App.listDocuments().values():
        _prepare_document(doc)
    k = keys.install()
    k.enabled = params.get_bool("SingleKeyShortcuts", True)
    from . import sketch_dims
    sketch_dims.set_enabled(params.get_bool("InlineDimensions", True))
    viewport.install_filters(True)
    viewport.refresh_grids(True)
    if _state["doc_obs"] is None:
        _state["doc_obs"] = DocObserver()
        App.addDocumentObserver(_state["doc_obs"])
    if _state["sel_obs"] is None:
        _state["sel_obs"] = SelObserver()
        Gui.Selection.addObserver(_state["sel_obs"])
    if _state["watch"] is None:
        t = QtCore.QTimer()
        t.setInterval(250)
        t.timeout.connect(_watch)
        _state["watch"] = t
    _state["watch"].start()
    mdi = mw.findChild(QtWidgets.QMdiArea)
    if mdi is not None and not getattr(mdi, "_ff_connected", False):
        mdi.subWindowActivated.connect(_view_activated)
        mdi._ff_connected = True
    if not App.listDocuments() and params.get_bool("NewDesignOnStart", True) and not _state.get("started"):
        from ..commands.definitions import new_design
        QtCore.QTimer.singleShot(200, new_design)
    _state["started"] = True
    refresh()


def _view_activated(*_):
    if not _state["active"]:
        return
    viewport.install_filters(True)
    viewport.refresh_grids(True)
    refresh()


def deactivated():
    _state["active"] = False
    if _state["watch"] is not None:
        _state["watch"].stop()
    if _state["ribbon"] is not None:
        _state["ribbon"].hide()
    # give FreeCAD's toolbars back; the next workbench's setup decides their visibility
    for tb in _state.get("changed", []):
        try:
            tb.toggleViewAction().setVisible(True)
        except Exception:
            pass
    for tb in _state["hidden"]:
        try:
            tb.show()
        except Exception:
            pass
    _state["hidden"] = []
    docks.deactivate()
    try:
        from . import datapanel
        datapanel.hide()
    except Exception:
        pass
    keys.set_enabled(False)
    viewport.set_enabled(False)
    from . import sketch_dims
    sketch_dims.set_enabled(False)
    viewport.refresh_grids(False)
    if not params.get_bool("KeepThemeEverywhere", True):
        theme.restore()
    QtCore.QTimer.singleShot(0, _show_workspace_bar)


def _show_workspace_bar():
    if _state["active"]:
        return
    mw = _mw()
    if _state["wsbar"] is None:
        _state["wsbar"] = WorkspaceBar(mw)
        mw.addToolBar(QtCore.Qt.TopToolBarArea, _state["wsbar"])
    _state["wsbar"].button.refresh()
    _state["wsbar"].show()


# FreeCAD switches workbench by itself when a PartDesign feature, a sketch or an
# assembly is edited (Gui.Command::assureWorkbench -> Gui.activateWorkbench). In
# the Fusion layout everything happens in one workspace, so those automatic
# switches are ignored while FreeFusion is active.
AUTO_SWITCH_BLOCKED = {"PartDesignWorkbench", "SketcherWorkbench", "AssemblyWorkbench"}
_orig_activate = {"fn": None}


def real_activate_workbench(name):
    fn = _orig_activate["fn"] or Gui.activateWorkbench
    return fn(name)


def _install_switch_guard():
    if _orig_activate["fn"] is not None:
        return
    original = Gui.activateWorkbench
    _orig_activate["fn"] = original

    def activateWorkbench(name, *args, **kwargs):
        if _state["active"] and name in AUTO_SWITCH_BLOCKED and params.get_bool("SingleWorkspace", True):
            return True
        return original(name, *args, **kwargs)
    activateWorkbench.__doc__ = original.__doc__
    try:
        Gui.activateWorkbench = activateWorkbench
    except Exception as e:
        App.Console.PrintLog("FreeFusion: cannot guard workbench switching: %s\n" % e)


def setup_global():
    """One-time hooks that also matter while other workbenches are active."""
    if _state["global"]:
        return
    _state["global"] = True
    _install_switch_guard()
    mw = _mw()
    try:
        mw.workbenchActivated.connect(_workbench_changed)
    except Exception:
        pass
    try:
        QtWidgets.QApplication.instance().aboutToQuit.connect(_restore_sketcher_settings)
    except Exception:
        pass


def _restore_sketcher_settings():
    """Quitting while FreeFusion is active: give a shared FreeCAD profile its sketcher
    settings back (grid line style, dimension dialog). The launcher profile keeps them."""
    if params.get_bool("ManagedProfile", False):
        return
    try:
        from . import grid, sketch_dims
        grid.hide_freecad_sketch_grid(False)
        sketch_dims.set_enabled(False)
    except Exception:
        pass


def _workbench_changed(name):
    if name != WB_NAME:
        QtCore.QTimer.singleShot(0, _show_workspace_bar)
    elif _state["wsbar"] is not None:
        _state["wsbar"].hide()
