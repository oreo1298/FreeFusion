# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fusion 'Change Parameters': user parameters, model parameters and value input.

User parameters live in a spreadsheet (object name ``FFParams``) with one row per
parameter: A=name, B=expression (the aliased cell), C=unit, D=comment. Anywhere a
value is typed, bare parameter names are accepted (``width / 2``) and rewritten to
FreeCAD expression syntax (``FFParams.width / 2``).
"""

import re

import FreeCAD as App

from .. import design as D

SHEET_NAME = "FFParams"
IDENT = re.compile(r"(?<![\w.<>])([A-Za-z_][A-Za-z_0-9]*)(?![\w(])")
DIM_TYPES = ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle")


def sheet(doc, create=False):
    s = doc.getObject(SHEET_NAME)
    if s is None and create:
        s = doc.addObject("Spreadsheet::Sheet", SHEET_NAME)
        s.Label = "Parameters"
        D.tag(s, role=D.ROLE_PARAMS)
        s.set("A1", "Name")
        s.set("B1", "Expression")
        s.set("C1", "Unit")
        s.set("D1", "Comment")
        doc.recompute()
    return s


def _text(s, cell):
    """Cell contents without the leading apostrophe FreeCAD adds to text cells."""
    t = s.getContents(cell) or ""
    return t[1:] if t.startswith("'") else t


def _rows(s):
    row = 2
    while True:
        name = _text(s, "A%d" % row)
        if not name:
            break
        yield row, name
        row += 1


def user_parameters(doc):
    """List of dicts: name, expression, unit, comment, value (string)."""
    s = sheet(doc)
    if s is None:
        return []
    out = []
    for row, name in _rows(s):
        expr = s.getContents("B%d" % row)
        if expr.startswith("="):
            expr = expr[1:]
        try:
            val = s.get("B%d" % row)
            val = val.UserString if hasattr(val, "UserString") else str(val)
        except Exception:
            val = ""
        out.append({"name": name, "expression": expr, "unit": _text(s, "C%d" % row),
                    "comment": _text(s, "D%d" % row), "value": val, "row": row})
    return out


def parameter_names(doc):
    return [p["name"] for p in user_parameters(doc)]


def _valid_name(name):
    return bool(re.match(r"^[A-Za-z_][A-Za-z_0-9]*$", name or ""))


def set_parameter(doc, name, expression, unit="mm", comment=""):
    if not _valid_name(name):
        raise ValueError("Invalid parameter name %r" % name)
    s = sheet(doc, create=True)
    row = None
    last = 1
    for r, n in _rows(s):
        last = r
        if n == name:
            row = r
    if row is None:
        row = last + 1
    s.set("A%d" % row, name)
    expr = to_expression(doc, expression, allow_self=name)
    if unit and re.match(r"^-?[\d.]+(e-?\d+)?$", expr.strip()):
        expr = "%s %s" % (expr.strip(), unit)
    s.set("B%d" % row, "=" + expr)
    s.set("C%d" % row, unit or "")
    s.set("D%d" % row, comment or "")
    try:
        if s.getAlias("B%d" % row) != name:
            s.setAlias("B%d" % row, name)
    except Exception:
        s.setAlias("B%d" % row, name)
    doc.recompute()
    return row


def remove_parameter(doc, name):
    s = sheet(doc)
    if s is None:
        return
    rows = list(_rows(s))
    data = [(n, s.getContents("B%d" % r), _text(s, "C%d" % r), _text(s, "D%d" % r))
            for r, n in rows if n != name]
    for r, _ in rows:
        try:
            s.setAlias("B%d" % r, "")
        except Exception:
            pass
        for col in "ABCD":
            s.clear("%s%d" % (col, r))
    doc.recompute()
    for i, (n, e, u, c) in enumerate(data):
        r = i + 2
        s.set("A%d" % r, n)
        s.set("B%d" % r, e)
        s.set("C%d" % r, u)
        s.set("D%d" % r, c)
        s.setAlias("B%d" % r, n)
    doc.recompute()


def to_expression(doc, text, allow_self=None):
    """Rewrite bare parameter names to FreeCAD expression syntax."""
    text = (text or "").strip()
    if text.startswith("="):
        text = text[1:].strip()
    names = set(parameter_names(doc))
    if allow_self:
        names.discard(allow_self)
    if not names:
        return text

    def sub(m):
        word = m.group(1)
        if word in names:
            return "%s.%s" % (SHEET_NAME, word)
        return word
    return IDENT.sub(sub, text)


def parse_value(doc, text, unit="mm"):
    """Parse user input. Returns (value, expression) where expression is '' for literals.

    value is a float in the internal unit (mm / degrees) or None if it cannot be
    evaluated.
    """
    text = (text or "").strip()
    if not text:
        return None, ""
    literal = text[1:] if text.startswith("=") else text
    try:
        q = App.Units.Quantity(literal)
        if q.Unit == App.Units.Unit() and unit:
            q = App.Units.Quantity("%s %s" % (literal, unit))
        if not text.startswith("="):
            return float(q.Value), ""
    except Exception:
        pass
    expr = to_expression(doc, text)
    value = evaluate(doc, expr, unit)
    return value, expr


def evaluate(doc, expr, unit="mm"):
    holder = sheet(doc) or next((o for o in doc.Objects), None)
    if holder is None:
        return None
    try:
        v = holder.evalExpression(expr)
    except Exception:
        return None
    try:
        return float(v.Value) if hasattr(v, "Value") else float(v)
    except Exception:
        return None


def format_value(value, unit="mm"):
    if value is None:
        return ""
    q = App.Units.Quantity("%s %s" % (value, unit)) if unit else App.Units.Quantity(value)
    return q.UserString


# ---------------------------------------------------------------------------
# Model parameters (the "Model Parameters" section of Fusion's dialog)

FEATURE_PROPS = {
    "PartDesign::Pad": ("Length", "Length2", "TaperAngle"),
    "PartDesign::Pocket": ("Length", "Length2", "TaperAngle"),
    "PartDesign::Revolution": ("Angle", "Angle2"),
    "PartDesign::Groove": ("Angle", "Angle2"),
    "PartDesign::Fillet": ("Radius",),
    "PartDesign::Chamfer": ("Size", "Size2", "Angle"),
    "PartDesign::Thickness": ("Value",),
    "PartDesign::Draft": ("Angle",),
    "PartDesign::Hole": ("Diameter", "Depth"),
    "PartDesign::LinearPattern": ("Length", "Occurrences", "Length2", "Occurrences2"),
    "PartDesign::PolarPattern": ("Angle", "Occurrences"),
    "Part::DatumPlane": (),
}


def name_dimensions(sketch):
    """Give unnamed driving dimensions Fusion style names (d1, d2, ...)."""
    doc = sketch.Document
    used = set()
    for o in doc.Objects:
        if D.is_sketch(o):
            for c in o.Constraints:
                if c.Name:
                    used.add(c.Name)
    n = 1
    changed = False
    for i, c in enumerate(sketch.Constraints):
        if c.Type in DIM_TYPES and not c.Name and c.Driving:
            while "d%d" % n in used:
                n += 1
            sketch.renameConstraint(i, "d%d" % n)
            used.add("d%d" % n)
            changed = True
    return changed


def model_parameters(doc):
    """[(feature_label, obj, property_path, display_value, expression, name)]"""
    out = []
    for obj in D.ordered_objects(doc):
        if D.is_sketch(obj):
            for i, c in enumerate(obj.Constraints):
                if c.Type in DIM_TYPES and c.Driving:
                    path = ".Constraints.%s" % c.Name if c.Name else ".Constraints[%d]" % i
                    unit = "deg" if c.Type == "Angle" else "mm"
                    val = c.Value if c.Type != "Angle" else c.Value * 180.0 / 3.141592653589793
                    out.append((obj.Label, obj, path, format_value(val, unit),
                                _expr_of(obj, path), c.Name or "#%d" % (i + 1)))
            continue
        props = None
        for t, ps in FEATURE_PROPS.items():
            if obj.isDerivedFrom(t):
                props = ps
                break
        if not props or D.role(obj) == D.ROLE_BINDER:
            continue
        for p in props:
            if p not in obj.PropertiesList:
                continue
            v = getattr(obj, p)
            disp = v.UserString if hasattr(v, "UserString") else str(v)
            out.append((obj.Label, obj, p, disp, _expr_of(obj, p), p))
    return out


def _expr_of(obj, path):
    for p, e in obj.ExpressionEngine:
        if p == path or p == path.lstrip("."):
            return e
    return ""


def set_model_parameter(doc, obj, path, text):
    value, expr = parse_value(doc, text, "deg" if "Angle" in path else "mm")
    if expr:
        obj.setExpression(path, expr)
    else:
        obj.setExpression(path, None)
        if path.startswith(".Constraints"):
            m = re.match(r"\.Constraints(?:\.(\w+)|\[(\d+)\])", path)
            idx = None
            if m and m.group(1):
                idx = [c.Name for c in obj.Constraints].index(m.group(1))
            elif m:
                idx = int(m.group(2))
            if idx is not None:
                q = App.Units.Quantity(text if not re.match(r"^-?[\d.]+$", text.strip())
                                       else "%s %s" % (text, "deg" if obj.Constraints[idx].Type == "Angle" else "mm"))
                obj.setDatum(idx, q)
        else:
            setattr(obj, path, value if not isinstance(getattr(obj, path), int) else int(value))
    doc.recompute()
