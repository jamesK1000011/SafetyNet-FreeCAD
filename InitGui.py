# SPDX-License-Identifier: LGPL-2.1-or-later
# SafetyNet as the FreeCAD window opens: its commands and icons, the
# SafetyNet workbench, a Tools ▸ SafetyNet submenu in every workbench (so
# recovery is reachable from whatever bench the person is in), FreeCAD's own
# AutoSave kept on (once, the change logged), and the documents a restart
# could not save reopened from their copies beside their files, as
# "<label> (recovered HH:MM)". Never imports Agent Link.
# The workbench and the rest are built in safetynet/workbench.py; FreeCAD runs
# this file at start.
import FreeCADGui

from safetynet import workbench as _safetynet_workbench

_SAFETYNET_MENU = _safetynet_workbench.add(FreeCADGui)
