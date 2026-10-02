# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion 360 like light / dark Qt themes for the whole FreeCAD window."""

import os
from string import Template

import FreeCAD as App
from PySide import QtCore, QtGui, QtWidgets

from .. import ICON_DIR, params

LIGHT = {
    "bg": "#f3f4f6",          # window / dock background
    "panel": "#ffffff",       # browser, dialogs, inputs
    "panel_alt": "#f7f8fa",
    "ribbon": "#fbfbfc",
    "appbar": "#e9ebee",
    "border": "#d4d8dd",
    "border_strong": "#b8bec6",
    "text": "#3c4146",
    "text_dim": "#7b838c",
    "text_invert": "#ffffff",
    "accent": "#0696d7",
    "accent_hover": "#0a85bf",
    "accent_soft": "#d9eef9",
    "hover": "#e8f4fb",
    "pressed": "#cfe8f6",
    "header": "#eef0f3",
    "tab_active": "#0696d7",
    "timeline": "#eceef1",
    "scroll": "#c3c9d0",
    "danger": "#e03131",
    "ok": "#2f9e44",
    "tooltip": "#34393f",
}

DARK = {
    "bg": "#2a2d31",
    "panel": "#33373c",
    "panel_alt": "#2f3337",
    "ribbon": "#30343a",
    "appbar": "#24272b",
    "border": "#454b52",
    "border_strong": "#5a6168",
    "text": "#e3e6e9",
    "text_dim": "#9aa3ac",
    "text_invert": "#ffffff",
    "accent": "#1fa3e0",
    "accent_hover": "#3cb3ea",
    "accent_soft": "#1f4459",
    "hover": "#3b4148",
    "pressed": "#1f4459",
    "header": "#2c3035",
    "tab_active": "#1fa3e0",
    "timeline": "#26292d",
    "scroll": "#5a6168",
    "danger": "#ff6b6b",
    "ok": "#51cf66",
    "tooltip": "#111315",
}

THEMES = {"light": LIGHT, "dark": DARK}

QSS = Template(r"""
/* ===== FreeFusion ($name) ===== */
QMainWindow, QDialog, QDockWidget, QStatusBar { background: $bg; color: $text; }
QWidget { color: $text; font-size: 9pt; }
QMainWindow::separator { background: $border; width: 1px; height: 1px; }
QToolTip { background: $tooltip; color: #ffffff; border: none; padding: 4px 6px; border-radius: 3px; }

/* --- menus --- */
QMenuBar { background: $appbar; border-bottom: 1px solid $border; padding: 1px 4px; }
QMenuBar::item { background: transparent; padding: 4px 9px; border-radius: 3px; }
QMenuBar::item:selected { background: $hover; }
QMenu { background: $panel; border: 1px solid $border_strong; padding: 4px 0; }
QMenu::item { padding: 5px 28px 5px 26px; background: transparent; }
QMenu::item:selected { background: $accent; color: $text_invert; }
QMenu::item:disabled { color: $text_dim; }
QMenu::separator { height: 1px; background: $border; margin: 4px 8px; }
QMenu::icon { padding-left: 6px; }

/* --- toolbars --- */
QToolBar { background: $ribbon; border: none; spacing: 2px; padding: 1px; }
QToolBar::separator { background: $border; width: 1px; margin: 4px 3px; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 3px; padding: 2px; }
QToolButton:hover { background: $hover; border-color: $accent_soft; }
QToolButton:pressed, QToolButton:checked { background: $pressed; border-color: $accent; }
QToolButton:disabled { color: $text_dim; }

/* --- docks --- */
QDockWidget { titlebar-close-icon: none; }
QDockWidget::title { background: $header; padding: 5px 8px; border-bottom: 1px solid $border;
    font-weight: bold; }
QDockWidget > QWidget { background: $panel; border: 1px solid $border; }

/* --- tabs --- */
QTabWidget::pane { border: 1px solid $border; background: $panel; top: -1px; }
QTabBar::tab { background: $bg; color: $text_dim; border: 1px solid $border; border-bottom: none;
    padding: 5px 12px; margin-right: 1px; border-top-left-radius: 3px; border-top-right-radius: 3px; }
QTabBar::tab:selected { background: $panel; color: $text; border-top: 2px solid $accent; }
QTabBar::tab:hover:!selected { background: $hover; color: $text; }
QMdiArea QTabBar::tab { min-width: 110px; padding: 6px 14px; }
QMdiArea QTabBar::tab:selected { color: $text; font-weight: bold; }

/* --- inputs --- */
QLineEdit, QAbstractSpinBox, QComboBox, QPlainTextEdit, QTextEdit {
    background: $panel; border: 1px solid $border_strong; border-radius: 3px; padding: 3px 5px;
    selection-background-color: $accent; selection-color: $text_invert; }
QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border-color: $accent; }
QLineEdit:disabled, QAbstractSpinBox:disabled, QComboBox:disabled { color: $text_dim; background: $panel_alt; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: $panel; border: 1px solid $border_strong;
    selection-background-color: $accent; selection-color: $text_invert; outline: 0; }

QPushButton { background: $panel; border: 1px solid $border_strong; border-radius: 3px;
    padding: 5px 14px; min-height: 16px; }
QPushButton:hover { border-color: $accent; background: $hover; }
QPushButton:pressed { background: $pressed; }
QPushButton:default { background: $accent; color: $text_invert; border-color: $accent; }
QPushButton:default:hover { background: $accent_hover; }
QPushButton:disabled { color: $text_dim; background: $panel_alt; border-color: $border; }

QCheckBox, QRadioButton { spacing: 6px; background: transparent; }
QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid $border_strong; border-radius: 2px;
    background: $panel; }
QCheckBox::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: url($res/styles/check.svg); }
QCheckBox::indicator:disabled { background: $panel_alt; border-color: $border; }
QGroupBox { border: 1px solid $border; border-radius: 4px; margin-top: 14px; padding-top: 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: $text_dim;
    font-weight: bold; }

/* --- item views --- */
QTreeView, QListView, QTableView, QTreeWidget, QListWidget, QTableWidget {
    background: $panel; alternate-background-color: $panel_alt; border: none;
    selection-background-color: $accent_soft; selection-color: $text; outline: 0; }
QTreeView::item, QListView::item { padding: 2px 0; }
QTreeView::item:hover, QListView::item:hover { background: $hover; }
QTreeView::item:selected, QListView::item:selected { background: $accent_soft; color: $text; }
QHeaderView::section { background: $header; color: $text_dim; border: none;
    border-right: 1px solid $border; border-bottom: 1px solid $border; padding: 4px 6px; }

/* --- scrollbars --- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle { background: $scroll; border-radius: 4px; min-height: 24px; min-width: 24px; margin: 2px; }
QScrollBar::handle:hover { background: $text_dim; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QSplitter::handle { background: $border; }
QProgressBar { border: 1px solid $border; border-radius: 3px; text-align: center; background: $panel; }
QProgressBar::chunk { background: $accent; }
QSlider::groove:horizontal { height: 4px; background: $border; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; margin: -6px 0; border-radius: 7px; background: $accent; }

/* --- FreeCAD task panels (Fusion command dialogs) --- */
QSint--ActionGroup { background: $panel; border: 1px solid $border; border-radius: 4px; }
QSint--ActionGroup QFrame[class="header"] { background: $header; border: none;
    border-bottom: 1px solid $border; border-top-left-radius: 4px; border-top-right-radius: 4px; }
QSint--ActionGroup QFrame[class="header"] QLabel { color: $text; font-weight: bold; }
QSint--ActionGroup QFrame[class="content"] { background: $panel; border: none; }
QSint--ActionGroup QToolButton { border: none; background: transparent; }
Gui--TaskView--TaskView, Gui--TaskView--TaskView > QWidget { background: $bg; }

/* =================== FreeFusion widgets =================== */
#FFAppBar { background: $appbar; border-bottom: 1px solid $border; }
#FFAppBar QToolButton { padding: 3px; }
#FFAppBar QToolButton#FFFileButton { padding: 3px 6px; }
#FFAppBar QLabel#FFDocTitle { color: $text; font-weight: bold; padding: 0 10px; }

#FFRibbon { background: $ribbon; border-bottom: 1px solid $border; }
#FFRibbon QToolButton#FFWorkspaceButton { border: 1px solid $border_strong; border-radius: 3px;
    padding: 4px 8px; font-weight: bold; background: $panel; min-width: 96px; text-align: left; }
#FFRibbon QToolButton#FFWorkspaceButton:hover { border-color: $accent; }
#FFRibbon QToolButton#FFWorkspaceButton::menu-indicator { subcontrol-position: right center; right: 6px; }
#FFRibbonTabs QToolButton { border: none; border-bottom: 2px solid transparent; border-radius: 0;
    color: $text_dim; font-weight: bold; padding: 4px 10px 3px 10px; font-size: 8pt; }
#FFRibbonTabs QToolButton:hover { color: $text; background: transparent; }
#FFRibbonTabs QToolButton:checked { color: $tab_active; border-bottom-color: $tab_active; background: transparent; }
#FFRibbonTabs QToolButton[contextual="true"] { color: $ok; }
#FFRibbonTabs QToolButton[contextual="true"]:checked { color: $ok; border-bottom-color: $ok; }
QFrame#FFRibbonGroup { border: none; border-right: 1px solid $border; background: transparent; }
QToolButton#FFRibbonBig { border-radius: 3px; padding: 2px; }
QToolButton#FFRibbonBig:hover { background: $hover; border: 1px solid $accent_soft; }
QToolButton#FFGroupLabel { border: none; color: $text; font-size: 7.5pt; font-weight: bold;
    padding: 0 4px 1px 4px; }
QToolButton#FFGroupLabel:hover { color: $accent; background: transparent; }
QToolButton#FFGroupLabel::menu-indicator { image: none; width: 0; }
QToolButton#FFFinishSketch { font-weight: bold; color: $ok; font-size: 7.5pt; }

#FFBrowser, #FFBrowser QTreeWidget { background: $panel; }
#FFBrowserHeader { background: $header; border-bottom: 1px solid $border; }
#FFBrowserHeader QLabel { font-weight: bold; color: $text; letter-spacing: 1px; }
#FFBrowser QTreeWidget::item { padding: 3px 0; }

#FFTimelineDock { background: $timeline; }
#FFTimeline { background: $timeline; border-top: 1px solid $border; }
#FFTimeline QToolButton { padding: 1px; }
#FFNavBar { background: $panel; border: 1px solid $border; border-radius: 5px; }
#FFNavBar QToolButton { padding: 2px; }

#FFShortcutBox { background: $panel; border: 1px solid $border_strong; border-radius: 6px; }
#FFShortcutBox QLineEdit { border: none; border-bottom: 1px solid $border; border-radius: 0;
    padding: 8px; font-size: 11pt; }
#FFShortcutBox QListWidget::item { padding: 5px 4px; }
#FFShortcutBox QListWidget::item:selected { background: $accent; color: $text_invert; }

#FFPanel QLabel[role="caption"] { color: $text_dim; }
#FFPanel QLabel[role="title"] { font-weight: bold; }
#FFSketchPalette { background: $panel; }
QLabel#FFHint { color: $text_dim; padding: 4px; }
""")


def tokens(name=None):
    name = name or current_theme()
    return THEMES.get(name, LIGHT)


def current_theme():
    t = params.get_string("Theme", "light")
    return t if t in THEMES else "light"


def stylesheet(name=None):
    name = name or current_theme()
    d = dict(tokens(name))
    d["name"] = name
    import os
    d["res"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "resources").replace(os.sep, "/")
    return QSS.substitute(d)


def palette(name=None):
    t = tokens(name)
    pal = QtGui.QPalette()
    c = QtGui.QColor
    roles = QtGui.QPalette.ColorRole if hasattr(QtGui.QPalette, "ColorRole") else QtGui.QPalette
    pal.setColor(roles.Window, c(t["bg"]))
    pal.setColor(roles.WindowText, c(t["text"]))
    pal.setColor(roles.Base, c(t["panel"]))
    pal.setColor(roles.AlternateBase, c(t["panel_alt"]))
    pal.setColor(roles.Text, c(t["text"]))
    pal.setColor(roles.Button, c(t["panel"]))
    pal.setColor(roles.ButtonText, c(t["text"]))
    pal.setColor(roles.Highlight, c(t["accent"]))
    pal.setColor(roles.HighlightedText, c(t["text_invert"]))
    pal.setColor(roles.ToolTipBase, c(t["tooltip"]))
    pal.setColor(roles.ToolTipText, c("#ffffff"))
    pal.setColor(roles.Link, c(t["accent"]))
    pal.setColor(roles.PlaceholderText if hasattr(roles, "PlaceholderText") else roles.Mid,
                 c(t["text_dim"]))
    groups = QtGui.QPalette.ColorGroup if hasattr(QtGui.QPalette, "ColorGroup") else QtGui.QPalette
    pal.setColor(groups.Disabled, roles.Text, c(t["text_dim"]))
    pal.setColor(groups.Disabled, roles.ButtonText, c(t["text_dim"]))
    pal.setColor(groups.Disabled, roles.WindowText, c(t["text_dim"]))
    return pal


_applied = {"on": False, "prev_sheet": None, "prev_style": None, "prev_palette": None}


def apply(name=None):
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    if not _applied["on"]:
        _applied["prev_sheet"] = app.styleSheet()
        _applied["prev_style"] = app.style().objectName() if app.style() else None
        _applied["prev_palette"] = QtGui.QPalette(app.palette())
    try:
        app.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
    except Exception:
        pass
    app.setPalette(palette(name))
    app.setStyleSheet(stylesheet(name))
    _applied["on"] = True


def restore():
    app = QtWidgets.QApplication.instance()
    if app is None or not _applied["on"]:
        return
    if _applied["prev_style"]:
        try:
            app.setStyle(QtWidgets.QStyleFactory.create(_applied["prev_style"]))
        except Exception:
            pass
    if _applied["prev_palette"] is not None:
        app.setPalette(_applied["prev_palette"])
    app.setStyleSheet(_applied["prev_sheet"] or "")
    _applied["on"] = False


def is_applied():
    return _applied["on"]


# colours swapped in the dark theme so line-art icons stay readable
DARK_SWAPS = [("#343a40", "#e9ecef"), ("#868e96", "#adb5bd"), ("#1864ab", "#74c0fc")]


def _dark_icon_path(path):
    """Recoloured copy of an SVG icon for the dark theme (cached on disk)."""
    try:
        cache = App.getUserCachePath() if hasattr(App, "getUserCachePath") else App.getUserAppDataDir()
    except Exception:
        return path
    folder = os.path.join(cache, "FreeFusion", "icons-dark")
    out = os.path.join(folder, os.path.basename(path))
    try:
        if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(path):
            os.makedirs(folder, exist_ok=True)
            with open(path) as f:
                svg = f.read()
            for a, b in DARK_SWAPS:
                svg = svg.replace(a, b)
            with open(out, "w") as f:
                f.write(svg)
        return out
    except Exception:
        return path


def icon(name):
    """QIcon for a FreeFusion icon name, falling back to FreeCAD resources."""
    if not name:
        return QtGui.QIcon()
    if name.startswith(":"):
        return QtGui.QIcon(name)
    path = os.path.join(ICON_DIR, name if name.endswith(".svg") else name + ".svg")
    if os.path.exists(path):
        if current_theme() == "dark":
            path = _dark_icon_path(path)
        return QtGui.QIcon(path)
    try:
        import FreeCADGui as Gui
        ic = Gui.getIcon(name) if hasattr(Gui, "getIcon") else None
        if ic is not None and not ic.isNull():
            return ic
    except Exception:
        pass
    return QtGui.QIcon(":/icons/" + name + ".svg")
