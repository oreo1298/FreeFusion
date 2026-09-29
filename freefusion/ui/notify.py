# SPDX-License-Identifier: LGPL-2.1-or-later
"""Small, non-modal user feedback (status bar + Fusion style toast)."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets


def _mw():
    return Gui.getMainWindow()


def status(msg, timeout=4000):
    try:
        _mw().statusBar().showMessage(msg, timeout)
    except Exception:
        pass


class _Toast(QtWidgets.QLabel):
    def __init__(self, parent, text, error=False):
        super(_Toast, self).__init__(text, parent)
        self.setObjectName("FFToast")
        bg = "#c92a2a" if error else "#34393f"
        self.setStyleSheet("QLabel#FFToast { background: %s; color: white; padding: 8px 14px;"
                           " border-radius: 4px; font-size: 9pt; }" % bg)
        self.setWordWrap(True)
        self.setMaximumWidth(520)
        self.adjustSize()
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        QtCore.QTimer.singleShot(3500 if not error else 6000, self.deleteLater)


def toast(msg, error=False):
    mw = _mw()
    if mw is None:
        return
    try:
        area = mw.centralWidget()
        t = _Toast(area, msg, error)
        g = area.rect()
        t.move(max(8, (g.width() - t.width()) // 2), max(8, g.height() - t.height() - 90))
        t.show()
        t.raise_()
    except Exception:
        pass
    status(msg)


def info(msg):
    App.Console.PrintMessage("FreeFusion: %s\n" % msg)
    toast(msg)


def error(msg):
    App.Console.PrintWarning("FreeFusion: %s\n" % msg)
    toast(msg, error=True)
