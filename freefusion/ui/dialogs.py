# SPDX-License-Identifier: LGPL-2.1-or-later
"""CHANGE PARAMETERS, PROPERTIES, INTERFERENCE and 3D PRINT dialogs."""

import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from .. import design as D
from ..features import parameters as PR
from . import notify, theme


def _mw():
    return Gui.getMainWindow()


class ParametersDialog(QtWidgets.QDialog):
    """Fusion 'Change Parameters': user parameters + model parameters."""

    def __init__(self, parent=None):
        super(ParametersDialog, self).__init__(parent or _mw())
        self.setWindowTitle("Parameters")
        self.setWindowIcon(theme.icon("Parameters"))
        self.resize(760, 520)
        self.doc = App.ActiveDocument
        lay = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QHBoxLayout()
        add = QtWidgets.QPushButton(theme.icon("NewDesign"), "  User Parameter")
        add.clicked.connect(self._add)
        top.addWidget(QtWidgets.QLabel("<b>PARAMETERS</b>"))
        top.addStretch(1)
        self.filter = QtWidgets.QLineEdit()
        self.filter.setPlaceholderText("Filter")
        self.filter.textChanged.connect(self._filter)
        top.addWidget(self.filter)
        top.addWidget(add)
        lay.addLayout(top)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(["Parameter", "Name", "Unit", "Expression", "Value", "Comment"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.header().setStretchLastSection(True)
        self.tree.itemChanged.connect(self._changed)
        lay.addWidget(self.tree, 1)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        self.delete_button = btns.addButton("Delete", QtWidgets.QDialogButtonBox.ActionRole)
        self.delete_button.clicked.connect(self._delete)
        btns.rejected.connect(self.accept)
        btns.accepted.connect(self.accept)
        lay.addWidget(btns)
        self._loading = False
        self.reload()

    def reload(self):
        self._loading = True
        self.tree.clear()
        self.user = QtWidgets.QTreeWidgetItem(self.tree, ["User Parameters"])
        self.user.setFirstColumnSpanned(True)
        for p in PR.user_parameters(self.doc):
            it = QtWidgets.QTreeWidgetItem(self.user, ["", p["name"], p["unit"],
                                                       p["expression"].replace(PR.SHEET_NAME + ".", ""),
                                                       p["value"], p["comment"]])
            it.setFlags(it.flags() | QtCore.Qt.ItemIsEditable)
            it.setData(0, QtCore.Qt.UserRole, ("user", p["name"]))
        self.model = QtWidgets.QTreeWidgetItem(self.tree, ["Model Parameters"])
        self.model.setFirstColumnSpanned(True)
        groups = {}
        for label, obj, path, disp, expr, name in PR.model_parameters(self.doc):
            g = groups.get(obj.Name)
            if g is None:
                g = groups[obj.Name] = QtWidgets.QTreeWidgetItem(self.model, [label])
                g.setFirstColumnSpanned(True)
            it = QtWidgets.QTreeWidgetItem(g, ["", name, "", expr.replace(PR.SHEET_NAME + ".", "") or disp,
                                                disp, ""])
            it.setFlags(it.flags() | QtCore.Qt.ItemIsEditable)
            it.setData(0, QtCore.Qt.UserRole, ("model", obj.Name, path))
        self.tree.expandAll()
        for c in range(6):
            self.tree.resizeColumnToContents(c)
        self._loading = False

    def _filter(self, text):
        text = text.lower()
        it = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            if item.childCount() == 0:
                item.setHidden(bool(text) and text not in " ".join(
                    item.text(c).lower() for c in range(6)))
            it += 1

    def _add(self):
        names = PR.parameter_names(self.doc)
        n = 1
        while "param%d" % n in names:
            n += 1
        self.doc.openTransaction("Add Parameter")
        PR.set_parameter(self.doc, "param%d" % n, "10", "mm")
        self.doc.commitTransaction()
        self.reload()

    def _delete(self):
        item = self.tree.currentItem()
        data = item.data(0, QtCore.Qt.UserRole) if item else None
        if not data or data[0] != "user":
            return
        self.doc.openTransaction("Delete Parameter")
        PR.remove_parameter(self.doc, data[1])
        self.doc.commitTransaction()
        self.reload()

    def _changed(self, item, column):
        if self._loading:
            return
        data = item.data(0, QtCore.Qt.UserRole)
        if not data:
            return
        try:
            self.doc.openTransaction("Change Parameter")
            if data[0] == "user":
                old = data[1]
                name, unit, expr, comment = item.text(1), item.text(2), item.text(3), item.text(5)
                if name != old:
                    PR.remove_parameter(self.doc, old)
                PR.set_parameter(self.doc, name, expr, unit, comment)
            else:
                obj = self.doc.getObject(data[1])
                PR.set_model_parameter(self.doc, obj, data[2], item.text(3))
            self.doc.commitTransaction()
        except Exception as e:
            self.doc.abortTransaction()
            notify.error(str(e))
        QtCore.QTimer.singleShot(0, self.reload)


def show_parameters():
    if App.ActiveDocument is None:
        return
    ParametersDialog().exec_() if hasattr(QtWidgets.QDialog, "exec_") else ParametersDialog().exec()


# ---------------------------------------------------------------------------

def _shape_of(obj):
    s = getattr(obj, "Shape", None)
    return s if s is not None and not s.isNull() else None


def _selected_bodies():
    from .widgets import selection_refs
    out = []
    for o, _ in selection_refs():
        b = D.body_of(o) or o
        if b not in out and _shape_of(b) is not None:
            out.append(b)
    return out


def _density(obj):
    """kg/m^3 from the object's FreeCAD material, default steel."""
    try:
        mat = getattr(obj, "ShapeMaterial", None)
        if mat is not None:
            d = mat.getPhysicalValue("Density")
            return float(App.Units.Quantity(d).getValueAs("kg/m^3"))
    except Exception:
        pass
    return 7850.0


def show_properties():
    bodies = _selected_bodies() or [b for b in D.design_bodies(App.ActiveDocument, True)
                                    if _shape_of(b) is not None] if App.ActiveDocument else []
    if not bodies:
        notify.error("Nothing to measure")
        return
    rows = []
    tot_v = tot_m = tot_a = 0.0
    com = App.Vector()
    for b in bodies:
        s = _shape_of(b)
        v = s.Volume
        a = s.Area
        rho = _density(b)
        m = rho * v * 1e-9
        c = s.CenterOfGravity if hasattr(s, "CenterOfGravity") and s.Solids else s.BoundBox.Center
        rows.append((b.Label, v, a, m, rho, c))
        tot_v += v
        tot_a += a
        tot_m += m
        com = com + c * m
    if tot_m > 0:
        com = com * (1.0 / tot_m)
    bb = App.BoundBox()
    for b in bodies:
        bb.add(_shape_of(b).BoundBox)
    q = lambda v, u: App.Units.Quantity("%r %s" % (v, u)).UserString
    html = ["<h3>PROPERTIES</h3><table cellspacing=6>"]
    html.append("<tr><td><b>Mass</b></td><td>%.4g kg</td></tr>" % tot_m)
    html.append("<tr><td><b>Volume</b></td><td>%s</td></tr>" % q(tot_v, "mm^3"))
    html.append("<tr><td><b>Area</b></td><td>%s</td></tr>" % q(tot_a, "mm^2"))
    if len(rows) == 1:
        html.append("<tr><td><b>Density</b></td><td>%.4g kg/m³</td></tr>" % rows[0][4])
    html.append("<tr><td><b>Bounding box</b></td><td>%.2f × %.2f × %.2f mm</td></tr>"
                % (bb.XLength, bb.YLength, bb.ZLength))
    html.append("<tr><td><b>Center of mass</b></td><td>%.3f, %.3f, %.3f mm</td></tr>" % (com.x, com.y, com.z))
    html.append("</table>")
    if len(rows) > 1:
        html.append("<h4>Bodies</h4><table cellspacing=6><tr><th>Body</th><th>Mass</th><th>Volume</th></tr>")
        for label, v, a, m, rho, c in rows:
            html.append("<tr><td>%s</td><td>%.4g kg</td><td>%s</td></tr>" % (label, m, q(v, "mm^3")))
        html.append("</table>")
    box = QtWidgets.QMessageBox(_mw())
    box.setWindowTitle("Properties")
    box.setIconPixmap(theme.icon("Properties").pixmap(48, 48))
    box.setText("".join(html))
    box.exec_() if hasattr(box, "exec_") else box.exec()


def center_of_mass():
    doc = App.ActiveDocument
    bodies = _selected_bodies() or [b for b in D.design_bodies(doc, True) if _shape_of(b) is not None]
    if not bodies:
        notify.error("Select bodies")
        return
    tot = 0.0
    com = App.Vector()
    for b in bodies:
        s = _shape_of(b)
        m = s.Volume * _density(b)
        c = s.CenterOfGravity if s.Solids else s.BoundBox.Center
        com = com + c * m
        tot += m
    if tot <= 0:
        return
    com = com * (1.0 / tot)
    doc.openTransaction("Center of Mass")
    pt = doc.addObject("Part::DatumPoint", "CenterOfMass")
    pt.Label = D.unique_label(doc, "Center of Mass ")
    pt.MapMode = "Deactivated"
    pt.Placement = App.Placement(com, App.Rotation())
    D.add_to(D.active_component(doc), pt)
    doc.commitTransaction()
    doc.recompute()
    notify.info("Center of mass: %.3f, %.3f, %.3f mm" % (com.x, com.y, com.z))


def interference():
    """Report and show pairwise overlaps between the selected (or all) bodies."""
    doc = App.ActiveDocument
    bodies = _selected_bodies()
    if len(bodies) < 2:
        bodies = [b for b in D.design_bodies(doc, True) if _shape_of(b) is not None]
    results = []
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            a, b = _shape_of(bodies[i]), _shape_of(bodies[j])
            if not a.BoundBox.intersect(b.BoundBox):
                continue
            try:
                c = a.common(b)
            except Exception:
                continue
            if c.Volume > 1e-6:
                results.append((bodies[i], bodies[j], c))
    old = doc.getObject("FF_Interference")
    doc.openTransaction("Interference")
    if old is not None:
        for o in list(old.Group):
            doc.removeObject(o.Name)
        doc.removeObject(old.Name)
    if results:
        grp = doc.addObject("App::DocumentObjectGroup", "FF_Interference")
        grp.Label = "Interference"
        for a, b, c in results:
            f = doc.addObject("Part::Feature", "Interference")
            f.Shape = c
            f.Label = "%s ∩ %s" % (a.Label, b.Label)
            grp.addObject(f)
            try:
                f.ViewObject.ShapeColor = (0.9, 0.1, 0.1)
            except Exception:
                pass
    doc.commitTransaction()
    doc.recompute()
    if results:
        text = "\n".join("%s  ∩  %s :  %.3f mm³" % (a.Label, b.Label, c.Volume) for a, b, c in results)
        QtWidgets.QMessageBox.information(_mw(), "Interference",
                                          "%d interference(s) found:\n\n%s" % (len(results), text))
    else:
        notify.info("No interference between %d bodies" % len(bodies))


def print3d():
    """Utilities > Make > 3D Print: export selected bodies as STL/3MF/OBJ."""
    doc = App.ActiveDocument
    bodies = _selected_bodies() or [b for b in D.design_bodies(doc, True) if _shape_of(b) is not None]
    if not bodies:
        notify.error("Nothing to print")
        return
    default = os.path.join(os.path.dirname(doc.FileName) if doc.FileName else os.path.expanduser("~"),
                           (bodies[0].Label if len(bodies) == 1 else doc.Label) + ".stl")
    fn, _ = QtWidgets.QFileDialog.getSaveFileName(
        _mw(), "3D Print", default, "STL (*.stl);;3MF (*.3mf);;OBJ (*.obj)")
    if not fn:
        return
    import Mesh
    import MeshPart
    meshes = []
    for b in bodies:
        s = _shape_of(b)
        meshes.append(MeshPart.meshFromShape(Shape=s, LinearDeflection=0.02, AngularDeflection=0.2,
                                             Relative=False))
    m = meshes[0]
    for other in meshes[1:]:
        m.addMesh(other)
    m.write(fn)
    notify.info("Exported %s" % fn)
