# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeFusion: a Fusion 360 style workspace for FreeCAD."""

import os

__version__ = "0.1.0"

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
RESOURCE_DIR = os.path.join(PACKAGE_DIR, "resources")
ICON_DIR = os.path.join(RESOURCE_DIR, "icons")
STYLE_DIR = os.path.join(RESOURCE_DIR, "styles")


def icon_path(name):
    """Return the absolute path of a FreeFusion icon, or a FreeCAD resource path.

    Names starting with ':' are Qt resource paths provided by FreeCAD itself and are
    returned unchanged, so commands can fall back to stock FreeCAD icons.
    """
    if not name:
        return ""
    if name.startswith(":") or os.path.isabs(name):
        return name
    if not name.endswith(".svg"):
        name += ".svg"
    path = os.path.join(ICON_DIR, name)
    if os.path.exists(path):
        return path
    return os.path.join(ICON_DIR, "Generic.svg")
