# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeFusion: a Fusion 360 style workspace for FreeCAD."""

import FreeCAD as App
import FreeCADGui as Gui


class FreeFusionWorkbench(Gui.Workbench):
    import freefusion as _ff

    MenuText = "FreeFusion"
    ToolTip = "Fusion 360 style design workspace: ribbon, browser, timeline and marking menu"
    Icon = _ff.icon_path("FreeFusion")

    def Initialize(self):
        from freefusion.commands import definitions
        from freefusion.ui import layout

        definitions.register_all()

        def names(groups):
            out = []
            for title, quick, entries in groups:
                for e in entries:
                    if isinstance(e, tuple):
                        out.extend(e[1])
                    elif e != "-" and e not in out:
                        out.append(e)
            return out

        # classic menus (visible when the FreeCAD menu bar is shown)
        self.appendMenu("&Solid", names(layout.SOLID))
        self.appendMenu("S&ketch", names(layout.SKETCH) + ["FF_FinishSketch"])
        self.appendMenu("S&urface", names(layout.SURFACE))
        self.appendMenu("&Mesh", names(layout.MESH))
        self.appendMenu("&Utilities", names(layout.UTILITIES) + ["FF_Toolbox"])

    def Activated(self):
        from freefusion.ui import workbench
        workbench.activated()

    def Deactivated(self):
        from freefusion.ui import workbench
        workbench.deactivated()

    def ContextMenu(self, recipient):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(FreeFusionWorkbench())


def _freefusion_startup():
    """Runs once the main window exists."""
    try:
        from freefusion import params, profile
        if profile.needs_apply():
            profile.apply(params.get_string("Theme", "light"), backup=False)
        if params.get_bool("ManagedProfile", False) and params.get_bool("StyleWindow", True):
            from freefusion.ui import theme
            theme.apply()
        from freefusion.ui import workbench
        workbench.setup_global()
    except Exception as e:  # never break FreeCAD's start-up
        App.Console.PrintWarning("FreeFusion start-up: %s\n" % e)


try:
    from PySide import QtCore
    QtCore.QTimer.singleShot(0, _freefusion_startup)
except Exception:
    pass
