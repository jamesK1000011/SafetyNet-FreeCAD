# SPDX-License-Identifier: LGPL-2.1-or-later
# SafetyNet as the FreeCAD window opens: FreeCAD's own AutoSave kept on (once,
# the change logged), and the documents a restart could not save reopened
# from their copies beside their files, as "<label> (recovered HH:MM)".


def _safetynet_start():
    try:
        from safetynet import recovery

        recovery.autosave_on()
        recovery.reopen_now()
    except Exception as e:  # noqa: BLE001 — never stop FreeCAD opening
        try:
            import FreeCAD

            FreeCAD.Console.PrintWarning(f"SafetyNet: start-up skipped: {e}\n")
        except Exception:
            pass


try:
    from PySide import QtCore

    # Once the window is up and the files it was opened with are loaded.
    QtCore.QTimer.singleShot(2500, _safetynet_start)
except Exception:  # noqa: BLE001
    _safetynet_start()
