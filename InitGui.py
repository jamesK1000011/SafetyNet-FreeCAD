# SPDX-License-Identifier: LGPL-2.1-or-later
# SafetyNet as the FreeCAD window opens: its commands and icons, the
# SafetyNet workbench, a Tools ▸ SafetyNet submenu in every workbench (so
# recovery is reachable from whatever bench the person is in), FreeCAD's own
# AutoSave kept on (once, the change logged), and the documents a restart
# could not save reopened from their copies beside their files, as
# "<label> (recovered HH:MM)". Never imports Agent Link.
import os

import FreeCAD
import FreeCADGui


def _safetynet_start():
    try:
        from safetynet import recovery

        recovery.autosave_on()
        recovery.reopen_now()
    except Exception as e:  # noqa: BLE001 — never stop FreeCAD opening
        try:
            FreeCAD.Console.PrintWarning(f"SafetyNet: start-up skipped: {e}\n")
        except Exception:
            pass


def _icons():
    import safetynet

    return os.path.join(os.path.dirname(os.path.abspath(safetynet.__file__)), "icons")


class SafetyNetWorkbench(FreeCADGui.Workbench):
    MenuText = "SafetyNet"
    ToolTip = "Checkpoints, recovered copies after a crash, FreeCAD's settings history and rollback, and approved macros"
    Icon = os.path.join(_icons(), "SafetyNet_Workbench.svg")

    def Initialize(self):
        from safetynet import commands

        commands.register()
        self.appendToolbar("SafetyNet", commands.TOOLBAR)
        self.appendMenu("SafetyNet", commands.NAMES)

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


class SafetyNetManipulator:
    """Tools ▸ SafetyNet in every workbench's menu bar."""

    def modifyMenuBar(self):
        return [{"append": "Separator", "menuItem": "&Tools"},
                {"append": "SafetyNet_Menu", "menuItem": "&Tools"}]


def _qt_tools_menu(*_):
    """For a FreeCAD without workbench manipulators: the submenu put into
    the Tools menu by Qt after each workbench switch (which rebuilds it)."""
    try:
        from PySide import QtCore, QtGui

        QtWidgets = QtGui
        try:
            from PySide import QtWidgets  # noqa: F811
        except ImportError:
            pass

        def add():
            from safetynet import commands

            mw = FreeCADGui.getMainWindow()
            tools = next((a.menu() for a in mw.menuBar().actions() if a.menu() is not None and a.menu().objectName() == "&Tools"), None)
            if tools is None or tools.findChild(QtWidgets.QMenu, "SafetyNetToolsMenu") is not None:
                return
            tools.addSeparator()
            sub = tools.addMenu("SafetyNet")
            sub.setObjectName("SafetyNetToolsMenu")
            for name in commands.NAMES:
                res = commands.COMMANDS[name]().GetResources()
                act = sub.addAction(res["MenuText"])
                act.setToolTip(res["ToolTip"])
                act.triggered.connect(lambda checked=False, n=name: FreeCADGui.runCommand(n))

        QtCore.QTimer.singleShot(0, add)
    except Exception as e:  # noqa: BLE001
        FreeCAD.Console.PrintWarning(f"SafetyNet: no Tools ▸ SafetyNet menu ({e})\n")


def _setup():
    FreeCADGui.addIconPath(_icons())
    from safetynet import commands

    commands.register()
    FreeCADGui.addWorkbench(SafetyNetWorkbench())
    if hasattr(FreeCADGui, "addWorkbenchManipulator"):
        FreeCADGui.addWorkbenchManipulator(SafetyNetManipulator())
        return "manipulator"
    mw = FreeCADGui.getMainWindow()
    mw.workbenchActivated.connect(_qt_tools_menu)
    _qt_tools_menu()
    return "qt"


try:
    _SAFETYNET_MENU = _setup()
except Exception as e:  # noqa: BLE001 — never stop FreeCAD opening
    FreeCAD.Console.PrintWarning(f"SafetyNet: workbench not loaded: {e}\n")

try:
    from PySide import QtCore

    # Once the window is up and the files it was opened with are loaded.
    QtCore.QTimer.singleShot(2500, _safetynet_start)
except Exception:  # noqa: BLE001
    _safetynet_start()
