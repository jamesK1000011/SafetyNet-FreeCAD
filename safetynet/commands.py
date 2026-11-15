# SPDX-License-Identifier: LGPL-2.1-or-later
# SafetyNet's FreeCAD commands: checkpoints, recovered copies, the settings
# log and its rollback, and macros, by hand. Each runs the same handler the
# agent's tool does (local.run: one undo step, the same refusals), with no
# agent and no Agent Link needed. Small dialogs: a pick list or a typed
# confirm where a task panel would be overkill.
import os

import FreeCAD
import FreeCADGui

from . import local

ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")


def _qt():
    from PySide import QtGui

    QtWidgets = QtGui
    try:
        from PySide import QtWidgets  # noqa: F811  (Qt 6 builds)
    except ImportError:
        pass
    return QtWidgets


def _mw():
    try:
        return FreeCADGui.getMainWindow()
    except Exception:
        return None


def say(text, error=False):
    (FreeCAD.Console.PrintError if error else FreeCAD.Console.PrintMessage)(f"SafetyNet: {text}\n")
    try:
        QtWidgets = _qt()
        (QtWidgets.QMessageBox.warning if error else QtWidgets.QMessageBox.information)(_mw(), "SafetyNet", text)
    except Exception:
        pass


def call(tool, args=None, quiet=False):
    """The handler through the local runner; a refusal shown. The answer or None."""
    ok, r = local.run(tool, args or {})
    if not ok:
        if not quiet:
            say((r.get("error") or {}).get("message", str(r)), error=True)
        return None
    return r


def pick(title, label, items):
    """One of items (text, value) picked from a list, or None."""
    if not items:
        return None
    QtWidgets = _qt()
    texts = [t for t, _ in items]
    text, ok = QtWidgets.QInputDialog.getItem(_mw(), title, label, texts, 0, False)
    if not ok:
        return None
    return items[texts.index(text)][1]


def typed(title, want, why=""):
    """The person's typed confirm, when it is word for word; else None."""
    QtWidgets = _qt()
    text, ok = QtWidgets.QInputDialog.getText(_mw(), title, f"{why}\nType  {want}  to confirm:".strip())
    return text if ok and text.strip() == want else None


def has_doc():
    return FreeCAD.ActiveDocument is not None


def show_text(title, text):
    QtWidgets = _qt()
    dlg = QtWidgets.QDialog(_mw())
    dlg.setWindowTitle(title)
    lay = QtWidgets.QVBoxLayout(dlg)
    view = QtWidgets.QPlainTextEdit()
    view.setReadOnly(True)
    view.setPlainText(text)
    lay.addWidget(view)
    close = QtWidgets.QPushButton("Close")
    close.clicked.connect(dlg.accept)
    lay.addWidget(close)
    dlg.resize(560, 420)
    dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()


class _Cmd:
    menu, tip, pixmap = "", "", ""

    def GetResources(self):
        return {"MenuText": self.menu, "ToolTip": self.tip, "Pixmap": self.pixmap}

    def IsActive(self):
        return True


class Checkpoint(_Cmd):
    menu, pixmap = "Checkpoint now", "SafetyNet_Checkpoint"
    tip = "Save a copy of the document now, to come back to past the undo stack and across restarts. Your file is not touched."

    def IsActive(self):
        return has_doc()

    def Activated(self):
        r = call("history_checkpoint", {})
        if r:
            FreeCAD.Console.PrintMessage(f"SafetyNet: checkpoint {r['checkpoint']} of {FreeCAD.ActiveDocument.Label} ({r.get('bytes', 0) // 1024} KB).\n")
            try:
                FreeCADGui.getMainWindow().statusBar().showMessage(f"SafetyNet: checkpoint {r['checkpoint']} saved", 4000)
            except Exception:
                pass


class Restore(_Cmd):
    menu, pixmap = "Restore checkpoint…", "SafetyNet_Restore"
    tip = "Go back to one of this document's checkpoints (the state before is checkpointed first, so a restore can be undone the same way)."

    def IsActive(self):
        return has_doc()

    def Activated(self):
        r = call("history_checkpoint", {"list": True})
        if r is None:
            return
        rows = [(f"{c['checkpoint']}{' · ' + c['name'] if c.get('name') else ''} · {c.get('time', '')}{' · auto' if c.get('auto') else ''}", c["checkpoint"])
                for c in reversed(r.get("checkpoints") or [])]
        if not rows:
            say(f"{r.get('document')} has no checkpoints yet: Checkpoint now takes one.")
            return
        cp = pick("Restore checkpoint", f"Back to which checkpoint of {r.get('document')}?", rows)
        if cp:
            out = call("history_restore", {"checkpoint": cp})
            if out:
                say(f"Back at {cp}." + (f" The state before is {out['before']}." if out.get("before") else ""))


class Recover(_Cmd):
    menu, pixmap = "Recovered copies…", "SafetyNet_Recover"
    tip = "Documents back after a crash or a hang: open a saved copy beside its file, then, if you choose, save it over the file."

    def Activated(self):
        r = call("app_recover", {"action": "list"})
        if r is None:
            return
        docs = r.get("documents") or []
        rows = []
        for d in docs:
            newest = (d.get("copies") or [{}])[0]
            rows.append((f"{d.get('label')} · {len(d.get('copies') or [])} copies · newest {newest.get('source', '')} {newest.get('time', '')}", d))
        if not rows:
            say("No saved copies of any document here.")
            return
        d = pick("Recovered copies", "Open the newest good copy of which document (beside its file)?", rows)
        if not d:
            return
        out = call("app_recover", {"action": "auto", "documents": [{"name": d["document"], "label": d.get("label")}]})
        rec = (out or {}).get("recovered") or []
        if not rec:
            if out and out.get("failed"):
                say(f"No copy of {d.get('label')} opened: {out['failed']}", error=True)
            return
        rec = rec[0]
        if not rec.get("file"):
            say(f"{rec.get('as')} is open; it was never saved to a file — save it where you like.")
            return
        want = f"save over {os.path.basename(rec['file'])}"
        t = typed("Use the recovered copy", want, f"{rec.get('as')} is open beside your file. To make it the file (the old one is kept):")
        if t:
            done = call("app_recover", {"action": "accept", "document": rec["document"], "confirm": t})
            if done:
                say(f"Saved over {done['saved']}." + (f" The old file is kept at {done['previousFile']}." if done.get("previousFile") else ""))


def _changes(limit=20):
    r = call("pref_history", {"limit": limit})
    return (r or {}).get("changes") or []


def _change_text(c):
    return f"#{c['change']} · {c.get('time', '')} · {c.get('path', '')}/{c.get('name', '')}: {c.get('from')} → {c.get('to')}{' (restart)' if c.get('restart') else ''}"


class SettingsHistory(_Cmd):
    menu, pixmap = "Settings history…", "preferences-system"
    tip = "The settings changes logged (made through Agent Link, and rollbacks), newest first."

    def Activated(self):
        rows = _changes(50)
        show_text("Settings history", "\n".join(_change_text(c) for c in rows) if rows else "No settings changes logged.")


class Rollback(_Cmd):
    menu, pixmap = "Roll back setting…", "edit-undo"
    tip = "Put FreeCAD's settings back as they were before a logged change (the state before is snapshotted too)."

    def Activated(self):
        rows = _changes(20)
        if not rows:
            say("No settings changes logged to roll back.")
            return
        ch = pick("Roll back setting", "Put the settings back as they were before which change?", [(_change_text(c), c["change"]) for c in rows])
        if ch is None:
            return
        QtWidgets = _qt()
        sure = QtWidgets.QMessageBox.question(_mw(), "Roll back setting", f"Put all of FreeCAD's settings back as they were before change #{ch}? The settings now are snapshotted first.")
        if sure != QtWidgets.QMessageBox.Yes:
            return
        out = call("pref_rollback", {"to": ch})
        if out:
            say(out.get("note") or f"Rolled back to {out.get('rolledBackTo')}.")


class Macros(_Cmd):
    menu, pixmap = "Macros…", "Std_DlgMacroExecute"
    tip = "The macros in FreeCAD's macro folder: show one, approve it for Agent Link to run (you type to confirm), or take the approval back."

    def Activated(self):
        r = call("macro_list", {})
        if r is None:
            return
        rows = [(f"{m['name']} · {m.get('state', '')}{' · ' + m['about'] if m.get('about') else ''}", m["name"]) for m in r.get("macros") or []]
        if not rows:
            say(f"No macros in {r.get('folder')}.")
            return
        name = pick("Macros", f"Macros in {r.get('folder')}:", rows)
        if not name:
            return
        what = pick(name, "Do what with it?", [("Show", "show"), ("Approve…", "approve"), ("Take approval back", "unapprove")])
        if what == "show":
            m = call("macro_show", {"name": name})
            if m:
                show_text(f"{name} · {m.get('state')}", m.get("text", ""))
        elif what == "approve":
            m = call("macro_show", {"name": name})
            if m:
                show_text(f"{name} · read before approving", m.get("text", ""))
                t = typed("Approve the macro", f"approve {name}", "A macro is Python that runs with the computer's full reach.")
                if t:
                    if call("macro_approve", {"name": name, "confirm": t}):
                        say(f"{name} approved: it runs until its file changes.")
        elif what == "unapprove":
            if call("macro_unapprove", {"name": name}) is not None:
                say(f"{name} is off the approved list.")


class Panel(_Cmd):
    menu, pixmap = "Panel", "SafetyNet_Workbench"
    tip = "The Session panel: recovered copies, settings changes and macros (in Agent Link's panel when it is loaded, else SafetyNet's own)."

    def Activated(self):
        from . import panel

        panel.show()


class Menu:
    """Tools ▸ SafetyNet in every workbench: the commands as one submenu."""

    def GetCommands(self):
        return tuple(NAMES)

    def GetResources(self):
        return {"MenuText": "SafetyNet", "ToolTip": "SafetyNet: checkpoints, recovered copies, settings and macros", "Pixmap": "SafetyNet_Workbench",
                "DropDownMenu": True, "Exclusive": False}

    def IsActive(self):
        return True


COMMANDS = {
    "SafetyNet_Checkpoint": Checkpoint,
    "SafetyNet_Restore": Restore,
    "SafetyNet_Recover": Recover,
    "SafetyNet_SettingsHistory": SettingsHistory,
    "SafetyNet_Rollback": Rollback,
    "SafetyNet_Macros": Macros,
    "SafetyNet_Panel": Panel,
}
NAMES = list(COMMANDS)
TOOLBAR = NAMES
MENU = "SafetyNet_Menu"

_done = []


def register():
    """Each command added once (InitGui runs this at start)."""
    if _done:
        return
    for name, cls in COMMANDS.items():
        FreeCADGui.addCommand(name, cls())
    FreeCADGui.addCommand(MENU, Menu())
    _done.append(True)
