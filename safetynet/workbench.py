# SPDX-License-Identifier: LGPL-2.1-or-later
# SafetyNet as the FreeCAD window opens: its commands and icons, the
# SafetyNet workbench, a Tools ▸ SafetyNet submenu in every workbench (so
# recovery is reachable from whatever bench the person is in), FreeCAD's own
# AutoSave kept on (once, the change logged), and the documents a restart
# could not save reopened from their copies beside their files, as
# "<label> (recovered HH:MM)". Never imports Agent Link. InitGui.py calls
# add().
#
# It is built here, in a real module, because FreeCAD runs InitGui.py with
# exec() and a separate locals dict: a class body or a method body there sees
# only FreeCAD's own globals, never the names InitGui.py defines.
import os

ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")


def _warn(text):
    try:
        import FreeCAD

        FreeCAD.Console.PrintWarning(text)
    except Exception:  # noqa: BLE001
        pass


def _log(text):
    try:
        import FreeCAD

        FreeCAD.Console.PrintLog(text)
    except Exception:  # noqa: BLE001
        pass


def _start():
    try:
        from . import recovery

        recovery.autosave_on()
        recovery.reopen_now()
    except Exception as e:  # noqa: BLE001 — never stop FreeCAD opening
        _warn(f"SafetyNet: start-up skipped: {e}\n")


def make_class(Gui):
    """SafetyNetWorkbench on this FreeCADGui's Workbench base."""

    class SafetyNetWorkbench(Gui.Workbench):
        MenuText = "SafetyNet"
        ToolTip = "Checkpoints, recovered copies, settings history and macros."
        Icon = os.path.join(ICONS, "SafetyNet_Workbench.svg")

        def Initialize(self):
            from . import commands

            commands.register()
            self.appendToolbar("SafetyNet", commands.TOOLBAR)
            self.appendMenu("SafetyNet", commands.NAMES)

        def Activated(self):
            # Its panel with it: beside Model and Tasks (the panel layout
            # setting), in front the first time.
            try:
                from . import layout, panel

                # Opening the panel changes nothing: the window's "*" stays
                # as it was (layout.keep_marks).
                with layout.keep_marks():
                    panel.show()
            except Exception as e:  # noqa: BLE001 — never stop the bench (no window in tests)
                _log(f"SafetyNet: panel not shown ({e})\n")

        def Deactivated(self):
            pass

        def GetClassName(self):
            return "Gui::PythonWorkbench"

    return SafetyNetWorkbench


class SafetyNetManipulator:
    """Tools ▸ SafetyNet in every workbench's menu bar."""

    def modifyMenuBar(self):
        return [{"append": "Separator", "menuItem": "&Tools"},
                {"append": "SafetyNet_Menu", "menuItem": "&Tools"}]


def qt_tools_menu(Gui):
    """For a FreeCAD without workbench manipulators: a slot that puts the
    submenu into the Tools menu by Qt after each workbench switch (which
    rebuilds it)."""

    def slot(*_):
        try:
            from PySide import QtCore, QtGui

            QtWidgets = QtGui
            try:
                from PySide import QtWidgets  # noqa: F811
            except ImportError:
                pass

            def add():
                from . import commands

                mw = Gui.getMainWindow()
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
                    act.triggered.connect(lambda checked=False, n=name: Gui.runCommand(n))

            QtCore.QTimer.singleShot(0, add)
        except Exception as e:  # noqa: BLE001
            _warn(f"SafetyNet: no Tools ▸ SafetyNet menu ({e})\n")

    return slot


def _setup(Gui):
    Gui.addIconPath(ICONS)
    from . import commands

    commands.register()
    Gui.addWorkbench(make_class(Gui)())
    if hasattr(Gui, "addWorkbenchManipulator"):
        Gui.addWorkbenchManipulator(SafetyNetManipulator())
        return "manipulator"
    slot = qt_tools_menu(Gui)
    mw = Gui.getMainWindow()
    mw.workbenchActivated.connect(slot)
    slot()
    return "qt"


def add(Gui=None):
    """The icons, commands, workbench and Tools menu, then the start-up
    (AutoSave on, recovered copies reopened) once the window is up and the
    files it was opened with are loaded: what InitGui.py calls. Returns how
    the Tools menu was added ("manipulator" or "qt"), None if it was not."""
    if Gui is None:
        import FreeCADGui as Gui
    menu = None
    try:
        menu = _setup(Gui)
    except Exception as e:  # noqa: BLE001 — never stop FreeCAD opening
        _warn(f"SafetyNet: workbench not loaded: {e}\n")
    try:
        from PySide import QtCore

        QtCore.QTimer.singleShot(2500, _start)
    except Exception:  # noqa: BLE001
        _start()
    return menu
