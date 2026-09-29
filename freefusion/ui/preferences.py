# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeFusion preferences dialog, theme switching and the quick start help."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from .. import __version__, params, profile
from ..commands import base
from . import keys, notify, theme


def toggle_theme():
    new = "dark" if theme.current_theme() == "light" else "light"
    params.set_string("Theme", new)
    if params.get_bool("FusionLookApplied", False) or params.get_bool("ManagedProfile", False):
        profile.apply(new, backup=False)
    from . import workbench
    workbench.restyle()


def apply_look():
    profile.apply(theme.current_theme())
    notify.info("Fusion navigation, colors and ViewCube applied. Use 'Restore FreeCAD Settings' to undo.")


def restore_look():
    if profile.restore():
        notify.info("Previous FreeCAD settings restored.")
    else:
        notify.info("Nothing to restore.")


class KeyTable(QtWidgets.QTableWidget):
    def __init__(self, ctx, parent=None):
        super(KeyTable, self).__init__(parent)
        self.ctx = ctx
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(["Key", "Command"])
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)
        self.load(keys.keymap(ctx))

    def load(self, mapping):
        self.setRowCount(0)
        for k, v in sorted(mapping.items()):
            self._row(k, v)

    def _row(self, k, v):
        r = self.rowCount()
        self.insertRow(r)
        self.setItem(r, 0, QtWidgets.QTableWidgetItem(k))
        combo = QtWidgets.QComboBox()
        combo.setEditable(True)
        names = sorted(base.REGISTRY)
        for n in names:
            combo.addItem(base.REGISTRY[n].menu + "  (" + n + ")", n)
        prefix = ""
        name = v
        if ":" in v:
            prefix, name = v.split(":", 1)
        i = combo.findData(name)
        if i >= 0:
            combo.setCurrentIndex(i)
        combo.setProperty("prefix", prefix)
        self.setCellWidget(r, 1, combo)

    def add(self):
        self._row("", "FF_Toolbox")

    def mapping(self):
        out = {}
        for r in range(self.rowCount()):
            it = self.item(r, 0)
            k = it.text().strip() if it else ""
            combo = self.cellWidget(r, 1)
            name = combo.currentData() or combo.currentText().split("(")[-1].rstrip(")")
            prefix = combo.property("prefix") or ""
            if k and name:
                out[k if len(k) > 1 else k.upper()] = (prefix + ":" + name) if prefix else name
        return out


class PreferencesDialog(QtWidgets.QDialog):
    def __init__(self, page=None, parent=None):
        super(PreferencesDialog, self).__init__(parent or Gui.getMainWindow())
        self.setWindowTitle("FreeFusion Preferences")
        self.setWindowIcon(theme.icon("FreeFusion"))
        self.resize(640, 520)
        v = QtWidgets.QVBoxLayout(self)
        self.tabs = QtWidgets.QTabWidget()
        v.addWidget(self.tabs, 1)

        general = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(general)
        self.theme = QtWidgets.QComboBox()
        self.theme.addItem("Light", "light")
        self.theme.addItem("Dark", "dark")
        self.theme.setCurrentIndex(0 if theme.current_theme() == "light" else 1)
        form.addRow("Theme", self.theme)
        self.style_all = QtWidgets.QCheckBox("Restyle the whole FreeCAD window")
        self.style_all.setChecked(params.get_bool("StyleWindow", True))
        form.addRow("", self.style_all)
        self.marking = QtWidgets.QCheckBox("Right-click opens the marking menu")
        self.marking.setChecked(params.get_bool("MarkingMenu", True))
        form.addRow("Marking menu", self.marking)
        self.grid = QtWidgets.QCheckBox("Show the layout grid on the ground plane")
        self.grid.setChecked(params.get_bool("ShowGrid", True))
        form.addRow("Grid", self.grid)
        self.menubar = QtWidgets.QCheckBox("Hide FreeCAD's menu bar (menus stay in File > FreeCAD Menus)")
        self.menubar.setChecked(params.get_bool("HideMenuBar", True))
        form.addRow("Menu bar", self.menubar)
        self.newdesign = QtWidgets.QCheckBox("Start with an empty design")
        self.newdesign.setChecked(params.get_bool("NewDesignOnStart", True))
        form.addRow("Startup", self.newdesign)
        self.keys_on = QtWidgets.QCheckBox("Single-key Fusion shortcuts (E, Q, F, L, R, C, D ...)")
        self.keys_on.setChecked(params.get_bool("SingleKeyShortcuts", True))
        form.addRow("Shortcuts", self.keys_on)
        look = QtWidgets.QHBoxLayout()
        b1 = QtWidgets.QPushButton("Apply Fusion navigation & colors")
        b1.clicked.connect(apply_look)
        b2 = QtWidgets.QPushButton("Restore FreeCAD settings")
        b2.clicked.connect(restore_look)
        look.addWidget(b1)
        look.addWidget(b2)
        form.addRow("3D view", look)
        info = QtWidgets.QLabel("FreeFusion %s" % __version__)
        info.setObjectName("FFHint")
        form.addRow("", info)
        self.tabs.addTab(general, "General")

        keyspage = QtWidgets.QWidget()
        kv = QtWidgets.QVBoxLayout(keyspage)
        kv.addWidget(QtWidgets.QLabel("Model shortcuts (a 'sketch:' target first asks for a sketch plane)"))
        self.model_keys = KeyTable("model")
        kv.addWidget(self.model_keys, 1)
        kv.addWidget(QtWidgets.QLabel("Sketch shortcuts (while editing a sketch)"))
        self.sketch_keys = KeyTable("sketch")
        kv.addWidget(self.sketch_keys, 1)
        row = QtWidgets.QHBoxLayout()
        add_m = QtWidgets.QPushButton("Add model key")
        add_m.clicked.connect(self.model_keys.add)
        add_s = QtWidgets.QPushButton("Add sketch key")
        add_s.clicked.connect(self.sketch_keys.add)
        reset = QtWidgets.QPushButton("Reset to Fusion defaults")
        reset.clicked.connect(self._reset_keys)
        row.addWidget(add_m)
        row.addWidget(add_s)
        row.addStretch(1)
        row.addWidget(reset)
        kv.addLayout(row)
        self.tabs.addTab(keyspage, "Keyboard")
        if page == "keys":
            self.tabs.setCurrentIndex(1)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def _reset_keys(self):
        keys.reset_keymaps()
        self.model_keys.load(keys.keymap("model"))
        self.sketch_keys.load(keys.keymap("sketch"))

    def _save(self):
        old_theme = theme.current_theme()
        params.set_string("Theme", self.theme.currentData())
        params.set_bool("StyleWindow", self.style_all.isChecked())
        params.set_bool("MarkingMenu", self.marking.isChecked())
        params.set_bool("NewDesignOnStart", self.newdesign.isChecked())
        params.set_bool("SingleKeyShortcuts", self.keys_on.isChecked())
        keys.save_keymap("model", self.model_keys.mapping())
        keys.save_keymap("sketch", self.sketch_keys.mapping())
        from . import docks, viewport, workbench
        viewport.set_grid_visible(self.grid.isChecked())
        docks.set_menubar(not self.menubar.isChecked())
        keys.set_enabled(self.keys_on.isChecked())
        if self.theme.currentData() != old_theme:
            if params.get_bool("FusionLookApplied", False) or params.get_bool("ManagedProfile", False):
                profile.apply(self.theme.currentData(), backup=False)
        workbench.restyle()
        self.accept()


def show(page=None):
    d = PreferencesDialog(page)
    d.exec_() if hasattr(d, "exec_") else d.exec()


HELP = """
<h2>FreeFusion quick start</h2>
<p>FreeFusion arranges FreeCAD like Fusion 360: the <b>ribbon</b> on top, the <b>Browser</b> on the
left, command dialogs on the right and the <b>timeline</b> at the bottom.</p>
<h3>Mouse</h3>
<table cellspacing=4>
<tr><td><b>Middle drag</b></td><td>Pan</td></tr>
<tr><td><b>Shift + middle drag</b></td><td>Orbit</td></tr>
<tr><td><b>Wheel</b></td><td>Zoom at cursor</td></tr>
<tr><td><b>Double middle click</b></td><td>Fit</td></tr>
<tr><td><b>Right click</b></td><td>Marking menu (drag in a direction to flick a command)</td></tr>
</table>
<h3>Keys</h3>
<table cellspacing=4>
<tr><td><b>S</b></td><td>Design shortcuts / command search</td><td><b>E</b></td><td>Extrude</td></tr>
<tr><td><b>Q</b></td><td>Press Pull</td><td><b>F</b></td><td>Fillet</td></tr>
<tr><td><b>H</b></td><td>Hole</td><td><b>M</b></td><td>Move/Copy</td></tr>
<tr><td><b>J</b></td><td>Joint</td><td><b>I</b></td><td>Measure</td></tr>
<tr><td><b>L</b></td><td>Line</td><td><b>R</b></td><td>2-Point Rectangle</td></tr>
<tr><td><b>C</b></td><td>Center Diameter Circle</td><td><b>D</b></td><td>Sketch Dimension</td></tr>
<tr><td><b>T</b></td><td>Trim</td><td><b>O</b></td><td>Offset</td></tr>
<tr><td><b>X</b></td><td>Construction</td><td><b>P</b></td><td>Project</td></tr>
<tr><td><b>V</b></td><td>Show/Hide</td><td><b>A</b></td><td>Appearance</td></tr>
</table>
<h3>Modeling like Fusion</h3>
<ul>
<li>Sketches belong to a <b>component</b>, not to a body. One sketch can drive several bodies.</li>
<li><b>Extrude</b> lets you choose <i>Join, Cut, Intersect, New Body</i> or <i>New Component</i>.
Click inside closed regions of a sketch to pick individual profiles.</li>
<li>Type values with units (<code>1 in</code>) or expressions using your parameters
(<code>width / 2</code>) - see <b>Modify &gt; Change Parameters</b>.</li>
<li>Drag the marker on the <b>timeline</b> to roll back the history; new features are inserted at
the marker. Double-click a timeline item to edit it.</li>
<li>Activate a component with the radio button in the Browser; new sketches and bodies go there.</li>
</ul>
"""


def show_help():
    box = QtWidgets.QMessageBox(Gui.getMainWindow())
    box.setWindowTitle("FreeFusion")
    box.setIconPixmap(theme.icon("FreeFusion").pixmap(48, 48))
    box.setText(HELP)
    box.exec_() if hasattr(box, "exec_") else box.exec()
