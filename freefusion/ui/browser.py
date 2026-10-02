# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Fusion 360 BROWSER: components, bodies, sketches and construction geometry."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from .. import design as D
from . import theme

ROLE_OBJ = QtCore.Qt.UserRole
ROLE_KIND = QtCore.Qt.UserRole + 1
ROLE_PATH = QtCore.Qt.UserRole + 2

COL_NAME, COL_EYE, COL_ACTIVE = 0, 1, 2

UNIT_SCHEMAS = [(0, "mm (Standard)"), (1, "m (MKS)"), (3, "in (Imperial decimal)"), (7, "mm (Building Euro)"),
                (6, "mm (Metric small parts / CNC)"), (5, "ft-in (Building US)")]


def _vis(obj):
    try:
        return obj.ViewObject.Visibility
    except Exception:
        return getattr(obj, "Visibility", True)


def _children(comp, doc):
    """Classify objects owned by comp (None = document level)."""
    out = {"bodies": [], "sketches": [], "construction": [], "components": [], "meshes": [], "joints": []}
    objs = comp.Group if comp is not None else [o for o in doc.Objects
                                                   if D.parent_group(o) is None and not o.InList]
    for o in objs:
        r = D.role(o)
        if r in (D.ROLE_BINDER, D.ROLE_TOOL, D.ROLE_CONSUMED, D.ROLE_PARAMS):
            continue
        if D.is_body(o) or r == D.ROLE_BODY:
            out["bodies"].append(o)
        elif D.is_component(o):
            out["components"].append(o)
        elif D.is_sketch(o):
            out["sketches"].append(o)
        elif D.is_datum(o):
            out["construction"].append(o)
        elif o.TypeId == "Assembly::JointGroup":
            out["joints"].extend(o.Group)
        elif o.isDerivedFrom("Mesh::Feature"):
            out["meshes"].append(o)
        elif o.isDerivedFrom("Part::Feature") and not D.is_origin_feature(o):
            # imported / Part-workbench solids; skip ones that only feed another feature
            consumers = [p for p in o.InList if not D.is_component(p)
                         and not p.isDerivedFrom("App::DocumentObjectGroup")]
            if not consumers:
                out["bodies"].append(o)
    return out


class BrowserTree(QtWidgets.QTreeWidget):
    def __init__(self, parent=None):
        super(BrowserTree, self).__init__(parent)
        self.setColumnCount(3)
        self.setHeaderHidden(True)
        self.setIndentation(14)
        self.setIconSize(QtCore.QSize(16, 16))
        self.setUniformRowHeights(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditKeyPressed)
        hdr = self.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(COL_NAME, QtWidgets.QHeaderView.Stretch)
        hdr.setSectionResizeMode(COL_EYE, QtWidgets.QHeaderView.Fixed)
        hdr.setSectionResizeMode(COL_ACTIVE, QtWidgets.QHeaderView.Fixed)
        self.setColumnWidth(COL_EYE, 22)
        self.setColumnWidth(COL_ACTIVE, 22)
        self.setFocusPolicy(QtCore.Qt.ClickFocus)


class Browser(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(Browser, self).__init__(parent)
        self.setObjectName("FFBrowser")
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head = QtWidgets.QWidget()
        head.setObjectName("FFBrowserHeader")
        head.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        hl = QtWidgets.QHBoxLayout(head)
        hl.setContentsMargins(8, 4, 4, 4)
        lab = QtWidgets.QLabel("BROWSER")
        hl.addWidget(lab)
        hl.addStretch(1)
        collapse = QtWidgets.QToolButton()
        collapse.setText("−")
        collapse.setToolTip("Collapse all")
        collapse.setAutoRaise(True)
        collapse.clicked.connect(lambda: (self.tree.collapseAll(), self._expand_roots()))
        hl.addWidget(collapse)
        v.addWidget(head)
        self.tree = BrowserTree()
        v.addWidget(self.tree, 1)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.itemChanged.connect(self._renamed)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemSelectionChanged.connect(self._tree_selection)
        self.tree.itemExpanded.connect(lambda it: self._remember(it, True))
        self.tree.itemCollapsed.connect(lambda it: self._remember(it, False))
        self._expanded = {}
        self._items = {}
        self._syncing = False
        self._building = False
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self.rebuild)
        self._eye = theme.icon("Eye")
        self._eye_off = theme.icon("EyeOff")
        self._radio = theme.icon("Radio")
        self._radio_on = theme.icon("RadioOn")

    # -------------------------------------------------------------------------
    def schedule(self):
        self._timer.start()

    def _remember(self, item, state):
        if not self._building:
            key = item.data(0, ROLE_PATH)
            if key:
                self._expanded[key] = state

    def _expand_roots(self):
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setExpanded(True)

    def _item(self, parent, text, icon, kind, obj=None, path=""):
        it = QtWidgets.QTreeWidgetItem(parent, [text, "", ""])
        it.setIcon(COL_NAME, theme.icon(icon) if isinstance(icon, str) else icon)
        it.setData(0, ROLE_KIND, kind)
        it.setData(0, ROLE_OBJ, obj.Name if obj is not None else "")
        it.setData(0, ROLE_PATH, path)
        flags = it.flags()
        if obj is not None and kind in ("body", "sketch", "construction", "component", "mesh", "joint"):
            it.setFlags(flags | QtCore.Qt.ItemIsEditable)
        if obj is not None:
            self._items.setdefault(obj.Name, []).append(it)
        if path in self._expanded:
            it.setExpanded(self._expanded[path])
        return it

    def _eye_for(self, it, visible):
        it.setIcon(COL_EYE, self._eye if visible else self._eye_off)
        it.setToolTip(COL_EYE, "Show/Hide")

    def rebuild(self):
        doc = App.ActiveDocument
        self._building = True
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            self._items = {}
            if doc is None:
                return
            root = D.root_component(doc)
            active = D.active_component(doc, create=False)
            top = self._item(self.tree, root.Label if root else doc.Label, "Component", "root",
                             root, "root")
            if root is not None:
                top.setIcon(COL_ACTIVE, self._radio_on if active == root else self._radio)
                top.setToolTip(COL_ACTIVE, "Activate component")
            f = QtGui.QFont(top.font(0))
            f.setBold(True)
            top.setFont(0, f)
            # document settings / named views
            ds = self._item(top, "Document Settings", "DocSettings", "folder", None, "root/ds")
            schema = App.ParamGet("User parameter:BaseApp/Preferences/Units").GetInt("UserSchema", 0)
            unit = dict(UNIT_SCHEMAS).get(schema, "mm")
            self._item(ds, "Units: %s" % unit.split(" ")[0], "Measure", "units", None, "root/ds/u")
            nv = self._item(top, "Named Views", "NamedViews", "folder", None, "root/nv")
            for name in ("Top", "Front", "Right", "Home"):
                self._item(nv, name.upper(), "NamedViews", "view:" + name, None, "root/nv/" + name)
            self._fill(top, root, doc, "root")
            if "root" not in self._expanded:
                top.setExpanded(True)
        finally:
            self.tree.blockSignals(False)
            self._building = False
        self._sync_from_selection()

    def _fill(self, parent, comp, doc, path):
        kids = _children(comp, doc)
        origin = D.origin_of(comp)
        if origin is not None:
            it = self._item(parent, "Origin", "Origin", "origin", origin, path + "/origin")
            self._eye_for(it, _vis(origin))
        if kids["joints"]:
            jf = self._item(parent, "Joints", "Joint", "folder", None, path + "/joints")
            for j in kids["joints"]:
                self._item(jf, j.Label, "Joint", "joint", j, path + "/joints/" + j.Name)
        sections = (("Bodies", "bodies", "Body", "body"), ("Meshes", "meshes", "InsertMesh", "mesh"),
                    ("Sketches", "sketches", "CreateSketch", "sketch"),
                    ("Construction", "construction", "OffsetPlane", "construction"))
        for title, key, icon, kind in sections:
            objs = kids[key]
            if not objs:
                continue
            folder = self._item(parent, title, "Folder", "folder:" + key, None, path + "/" + key)
            any_vis = False
            for o in objs:
                ic = icon
                if kind == "construction":
                    ic = "Point" if "Point" in o.TypeId else "AxisTwoPoints" if "Line" in o.TypeId \
                        else "OffsetPlane"
                it = self._item(folder, o.Label, ic, kind, o, path + "/" + key + "/" + o.Name)
                vis = _vis(o)
                any_vis = any_vis or vis
                self._eye_for(it, vis)
            self._eye_for(folder, any_vis)
            if path + "/" + key not in self._expanded:
                folder.setExpanded(key in ("bodies",))
        active = D.active_component(doc, create=False)
        for c in kids["components"]:
            it = self._item(parent, "%s:1" % c.Label, "Component", "component", c, path + "/" + c.Name)
            self._eye_for(it, _vis(c))
            it.setIcon(COL_ACTIVE, self._radio_on if active == c else self._radio)
            it.setToolTip(COL_ACTIVE, "Activate component")
            self._fill(it, c, doc, path + "/" + c.Name)

    # -------------------------------------------------------------------------
    def _obj(self, item):
        name = item.data(0, ROLE_OBJ) if item else ""
        doc = App.ActiveDocument
        return doc.getObject(name) if (doc and name) else None

    def _folder_objects(self, item):
        out = []
        for i in range(item.childCount()):
            o = self._obj(item.child(i))
            if o is not None:
                out.append(o)
        return out

    def _clicked(self, item, col):
        kind = item.data(0, ROLE_KIND) or ""
        obj = self._obj(item)
        if col == COL_EYE:
            targets = [obj] if obj is not None else self._folder_objects(item)
            if not targets:
                return
            new = not _vis(targets[0]) if obj is not None else not any(_vis(o) for o in targets)
            for o in targets:
                try:
                    o.ViewObject.Visibility = new
                except Exception:
                    pass
            self.schedule()
            return
        if col == COL_ACTIVE and kind in ("component", "root"):
            D.set_active_component(App.ActiveDocument, obj)
            self.schedule()
            return
        if kind.startswith("view:"):
            view = kind.split(":")[1]
            if view == "Home":
                from . import viewport
                viewport.home()
            else:
                Gui.runCommand({"Top": "Std_ViewTop", "Front": "Std_ViewFront",
                                "Right": "Std_ViewRight"}[view], 0)
        elif kind == "units":
            self._units_menu(QtGui.QCursor.pos())

    def _tree_selection(self):
        if self._syncing or self._building:
            return
        self._syncing = True
        try:
            Gui.Selection.clearSelection()
            for it in self.tree.selectedItems():
                o = self._obj(it)
                if o is not None and it.data(0, ROLE_KIND) not in ("origin",):
                    try:
                        Gui.Selection.addSelection(o)
                    except Exception:
                        pass
        finally:
            self._syncing = False

    def _sync_from_selection(self):
        if self._syncing:
            return
        self._syncing = True
        try:
            self.tree.blockSignals(True)
            self.tree.clearSelection()
            for s in Gui.Selection.getSelectionEx("", 0):
                from .widgets import resolve
                for sub in (s.SubElementNames or [""]):
                    leaf, _ = resolve(s.DocumentName, s.ObjectName, sub)
                    b = D.body_of(leaf) if leaf is not None else None
                    for o in (leaf, b):
                        if o is not None:
                            for it in self._items.get(o.Name, []):
                                it.setSelected(True)
        except Exception:
            pass
        finally:
            self.tree.blockSignals(False)
            self._syncing = False

    def _double_clicked(self, item, col):
        kind = item.data(0, ROLE_KIND) or ""
        obj = self._obj(item)
        if obj is None:
            return
        if kind == "sketch":
            from . import sketching
            sketching.edit_sketch(obj)
        elif kind in ("component", "root"):
            D.set_active_component(App.ActiveDocument, obj)
            self.schedule()
        elif kind == "construction":
            try:
                Gui.ActiveDocument.setEdit(obj.Name)
            except Exception:
                pass
        elif kind == "joint":
            try:
                Gui.ActiveDocument.setEdit(obj.Name)
            except Exception:
                pass

    def _renamed(self, item, col):
        if self._building or col != COL_NAME:
            return
        obj = self._obj(item)
        if obj is None:
            return
        text = item.text(0)
        if text.endswith(":1") and item.data(0, ROLE_KIND) == "component":
            text = text[:-2]
        if text and text != obj.Label:
            obj.Document.openTransaction("Rename")
            obj.Label = text
            obj.Document.commitTransaction()

    def _units_menu(self, pos):
        m = QtWidgets.QMenu(self)
        cur = App.ParamGet("User parameter:BaseApp/Preferences/Units").GetInt("UserSchema", 0)
        for idx, label in UNIT_SCHEMAS:
            a = m.addAction(label)
            a.setCheckable(True)
            a.setChecked(idx == cur)
            a.triggered.connect(lambda *_, i=idx: (
                App.ParamGet("User parameter:BaseApp/Preferences/Units").SetInt("UserSchema", i),
                App.Units.setSchema(i) if hasattr(App.Units, "setSchema") else None,
                self.schedule()))
        m.exec_(pos) if hasattr(m, "exec_") else m.exec(pos)

    def _context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if item is None:
            return
        kind = item.data(0, ROLE_KIND) or ""
        obj = self._obj(item)
        m = QtWidgets.QMenu(self)
        from ..commands import base

        def act(text, fn, icon=None):
            a = m.addAction(theme.icon(icon) if icon else QtGui.QIcon(), text)
            a.triggered.connect(lambda *_: fn())
            return a

        def select_then(cmd):
            def run():
                Gui.Selection.clearSelection()
                Gui.Selection.addSelection(obj)
                base.run(cmd)
            return run

        if kind in ("component", "root") and obj is not None:
            act("Activate", lambda: (D.set_active_component(App.ActiveDocument, obj), self.schedule()), "RadioOn")
            act("New Component", lambda: (D.set_active_component(App.ActiveDocument, obj),
                                          base.run("FF_NewComponent")), "NewComponent")
            act("Create Sketch", lambda: (D.set_active_component(App.ActiveDocument, obj),
                                          base.run("FF_CreateSketch")), "CreateSketch")
            if kind == "component":
                m.addSeparator()
                act("Ground", select_then("FF_Ground"), "Ground")
                act("Move/Copy", select_then("FF_Move"), "Move")
        elif kind == "sketch":
            act("Edit Sketch", lambda: __import__("freefusion.ui.sketching", fromlist=["x"]).edit_sketch(obj),
                "CreateSketch")
            act("Redefine Sketch Plane", lambda: (Gui.Selection.clearSelection(),
                                                  Gui.Selection.addSelection(obj),
                                                  base.run_target("Sketcher_MapSketch")), "LookAt")
        elif kind == "body":
            act("Move/Copy", select_then("FF_Move"), "Move")
            act("Appearance", select_then("FF_Appearance"), "Appearance")
            act("Physical Material", select_then("FF_Material"), "Material")
            act("Properties", select_then("FF_Properties"), "Properties")
            act("Isolate", select_then("FF_Isolate"), "Eye")
            act("Export...", select_then("FF_Export"), "Export")
            act("Save as Mesh (3D Print)", select_then("FF_Print3D"), "Print3D")
        elif kind == "construction":
            act("Edit", lambda: Gui.ActiveDocument.setEdit(obj.Name), "OffsetPlane")
        elif kind == "units":
            self._units_menu(self.tree.viewport().mapToGlobal(pos))
            return
        if obj is not None and kind not in ("root", "origin"):
            m.addSeparator()
            act("Show/Hide", lambda: setattr(obj.ViewObject, "Visibility", not obj.ViewObject.Visibility), "Eye")
            act("Rename", lambda: self.tree.editItem(item, COL_NAME))
            act("Delete", select_then("FF_Delete"), "Delete")
        if kind.startswith("folder:"):
            act("Show All", lambda: [setattr(o.ViewObject, "Visibility", True) for o in self._folder_objects(item)],
                "Eye")
            act("Hide All", lambda: [setattr(o.ViewObject, "Visibility", False)
                                     for o in self._folder_objects(item)], "EyeOff")
        if m.actions():
            m.exec_(self.tree.viewport().mapToGlobal(pos)) if hasattr(m, "exec_") \
                else m.exec(self.tree.viewport().mapToGlobal(pos))

    def reveal(self, obj):
        for it in self._items.get(obj.Name, []):
            p = it.parent()
            while p is not None:
                p.setExpanded(True)
                p = p.parent()
            self.tree.scrollToItem(it)
            it.setSelected(True)


_instance = {"w": None}


def instance():
    return _instance["w"]


def create(parent=None):
    if _instance["w"] is None:
        _instance["w"] = Browser(parent)
    return _instance["w"]


def find_selection():
    b = instance()
    if b is None:
        return
    from .widgets import selection_refs
    for o, _ in selection_refs():
        b.reveal(D.body_of(o) or o)
