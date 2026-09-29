# SPDX-License-Identifier: LGPL-2.1-or-later
"""Small helpers around FreeCAD's parameter manager."""

import FreeCAD as App

ROOT = "User parameter:BaseApp/Preferences/Mod/FreeFusion"


def group(path=ROOT):
    return App.ParamGet(path)


def get_bool(name, default=False, path=ROOT):
    return group(path).GetBool(name, default)


def set_bool(name, value, path=ROOT):
    group(path).SetBool(name, bool(value))


def get_int(name, default=0, path=ROOT):
    return group(path).GetInt(name, default)


def set_int(name, value, path=ROOT):
    group(path).SetInt(name, int(value))


def get_string(name, default="", path=ROOT):
    return group(path).GetString(name, default)


def set_string(name, value, path=ROOT):
    group(path).SetString(name, str(value))


def get_float(name, default=0.0, path=ROOT):
    return group(path).GetFloat(name, default)


def set_float(name, value, path=ROOT):
    group(path).SetFloat(name, float(value))


def rgba(hex_color, alpha=255):
    """Convert '#rrggbb' into the packed unsigned int FreeCAD stores colors as."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return (r << 24) | (g << 16) | (b << 8) | alpha


def rgb_float(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
