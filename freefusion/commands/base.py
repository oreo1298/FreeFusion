# SPDX-License-Identifier: LGPL-2.1-or-later
"""Command registry shared by the ribbon, marking menu, shortcut box and key map."""

import FreeCAD as App
import FreeCADGui as Gui

from .. import icon_path

REGISTRY = {}          # command name -> Spec
_last = {"name": None}


class Spec(object):
    def __init__(self, name, menu, tooltip, icon, run=None, active=None, target=None,
                 modules=(), workbench=None, keywords="", shortcut="", pre=None,
                 checkable=False):
        self.name = name
        self.menu = menu
        self.tooltip = tooltip or menu
        self.icon = icon
        self.run = run
        self.active = active
        self.target = target
        self.modules = modules
        self.workbench = workbench
        self.keywords = keywords
        self.shortcut = shortcut
        self.pre = pre
        self.checkable = checkable


def doc_open():
    return App.ActiveDocument is not None


def always():
    return True


def in_sketch():
    obj = editing_object()
    return obj is not None and obj.isDerivedFrom("Sketcher::SketchObject")


def editing_object():
    """The document object being edited (sketch, feature, assembly...) or None."""
    vp = editing_vp()
    if vp is None:
        return None
    obj = getattr(vp, "Object", None)
    if obj is not None:
        return obj
    # FreeCAD 1.0: some C++ view providers (e.g. assemblies) have no .Object
    doc = App.ActiveDocument
    for o in (doc.Objects if doc else []):
        try:
            if o.ViewObject is vp or o.ViewObject == vp:
                return o
        except Exception:
            continue
    return None


def editing_vp():
    try:
        gd = Gui.ActiveDocument
        return gd.getInEdit() if gd else None
    except Exception:
        return None


def not_editing():
    return doc_open() and editing_vp() is None and not Gui.Control.activeDialog()


def command_exists(name):
    try:
        return Gui.Command.get(name) is not None
    except Exception:
        return name in Gui.listCommands()


def ensure_command(target, modules=(), workbench=None):
    """Make sure a FreeCAD command is registered (import its module if needed)."""
    if command_exists(target):
        return True
    for m in modules:
        try:
            __import__(m)
        except Exception:
            pass
        if command_exists(target):
            return True
    if workbench:
        try:
            wb = Gui.getWorkbench(workbench)
        except Exception:
            wb = None
        if wb is not None:
            cur = Gui.activeWorkbench().name() if Gui.activeWorkbench() else None
            try:
                Gui.activateWorkbench(workbench)
            finally:
                if cur:
                    Gui.activateWorkbench(cur)
    return command_exists(target)


def run_target(target, modules=(), workbench=None):
    if not ensure_command(target, modules, workbench):
        App.Console.PrintWarning("FreeFusion: command %s is not available "
                                 "(missing workbench or add-on)\n" % target)
        return False
    Gui.runCommand(target, 0)
    return True


class _Command(object):
    def __init__(self, spec):
        self.spec = spec

    def GetResources(self):
        s = self.spec
        res = {"MenuText": s.menu, "ToolTip": s.tooltip}
        if s.icon:
            res["Pixmap"] = icon_path(s.icon)
        return res

    def IsActive(self):
        s = self.spec
        try:
            if s.active is not None:
                return bool(s.active())
            return doc_open()
        except Exception:
            return False

    def Activated(self, *args):
        s = self.spec
        if s.name != "FF_Repeat":
            _last["name"] = s.name
        if s.name != "FF_SkLine":
            try:
                from ..ui import sketch_tools
                sketch_tools.stop()
            except Exception:
                pass
        try:
            if s.pre is not None:
                s.pre()
            if s.run is not None:
                s.run()
            elif s.target:
                run_target(s.target, s.modules, s.workbench)
        except Exception as e:
            import traceback
            App.Console.PrintError("FreeFusion %s: %s\n%s" % (s.name, e, traceback.format_exc()))
            try:
                from ..ui import notify
                notify.error(str(e))
            except Exception:
                pass


def register(name, menu, tooltip="", icon="", run=None, active=None, target=None,
             modules=(), workbench=None, keywords="", shortcut="", pre=None):
    spec = Spec(name, menu, tooltip, icon, run, active, target, modules, workbench, keywords,
                shortcut, pre)
    REGISTRY[name] = spec
    if name not in Gui.listCommands():
        Gui.addCommand(name, _Command(spec))
    return spec


def wrap(name, target, menu, tooltip="", icon="", modules=(), workbench=None, active=None,
         keywords="", shortcut="", pre=None):
    """A FreeFusion command that runs an existing FreeCAD command."""
    return register(name, menu, tooltip, icon or "", None, active, target, modules, workbench,
                    keywords, shortcut, pre)


def last_command():
    return _last["name"]


def run(name):
    """Run a registered command by name (FreeFusion or FreeCAD)."""
    if name in REGISTRY or command_exists(name):
        Gui.runCommand(name, 0)
        return True
    return False


def spec(name):
    return REGISTRY.get(name)


def qaction(name):
    """The QAction FreeCAD created for a command (None if unavailable)."""
    try:
        cmd = Gui.Command.get(name)
        if cmd is None:
            return None
        acts = cmd.getAction()
        return acts[0] if acts else None
    except Exception:
        return None
