# SPDX-License-Identifier: LGPL-2.1-or-later
# The Session panel: what keeps the work safe while nobody watches — the
# document the agent works in, heavy jobs held for the person's go,
# recovered copies, settings changes and macros. One widget, two hosts,
# written against a runner(tool, args) -> (ok, result):
# - under Agent Link, a tab in its panel (register_tab) running Agent Link's
#   panel._call, so what the person does here is shown and logged like the
#   agent's work;
# - alone, SafetyNet's own dock running local.run over the same handlers
#   (one undo step each). The rows that need Agent Link (the document the
#   agent works in, jobs held for a go) hide there.
import json
import os

from .files import _load, path


def _qt():
    from PySide import QtCore, QtGui

    QtWidgets = QtGui
    try:
        from PySide import QtWidgets  # noqa: F811  (Qt 6 builds)
    except ImportError:
        pass
    return QtCore, QtWidgets


NAME = "SafetyNetSession"
TITLE = "SafetyNet"


# ---- what a person reads: one date format, settings in words ---------------------------

_STAMPS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y%m%d-%H%M%S")


def when(text, now=None):
    """A time as SafetyNet's tools give it (2026-11-15 12:41 or
    20261115-124100) in one readable local form: 15 Nov 12:41, with the
    year when it is not this one. Text it cannot read comes back as is."""
    import datetime

    t = str(text or "").strip()
    for f in _STAMPS:
        try:
            d = datetime.datetime.strptime(t, f)
        except ValueError:
            continue
        year = (now or datetime.datetime.now()).year
        return f"{d.day} {d:%b}" + (f" {d.year}" if d.year != year else "") + f" {d:%H:%M}"
    return t


def words(name):
    """A parameter's name in words: AutoSaveEnabled -> Auto save enabled."""
    n = str(name or "")
    if " " not in n:
        out = ""
        for i, c in enumerate(n):
            if c.isupper() and i and (n[i - 1].islower() or (i + 1 < len(n) and n[i + 1].islower())):
                out += " "
            out += c
        n = out.replace("_", " ")
        n = " ".join(w if w.isupper() and len(w) > 1 else w.lower() for w in n.split())
    return n[:1].upper() + n[1:]


def value_text(v):
    if v is None:
        return "not set"
    if isinstance(v, bool):
        return "on" if v else "off"
    t = str(v)
    return t if len(t) <= 40 else t[:39] + "…"


def change_text(c):
    """One settings-log entry as a person reads it: the setting's group and
    name in words with its real before and after; a rollback or a snapshot
    with nothing changed said as such, never "None → None"."""
    to, frm, name = c.get("to"), c.get("from"), c.get("name")
    if c.get("tool") == "pref_rollback":
        ref = str(to or "")
        text = f"Settings rolled back to before change {ref}" if ref.isdigit() else f"Settings rolled back to {when(ref)}"
    elif frm is None and to is None:
        text = "Settings snapshot" + (f" {name}" if name and " " in str(name) else f": {words(name)}" if name else "")
    else:
        group = str(c.get("path") or "").rstrip("/").split("/")[-1]
        label = words(name) if name else "Settings"
        if group and group not in ("Preferences", "BaseApp"):
            label = f"{words(group)} › {label}"
        text = f"{label}: {value_text(to)}" if frm is None else f"{label}: {value_text(frm)} → {value_text(to)}"
    return text + (" (restart)" if c.get("restart") else "")


def recovered_rows(documents, per_doc=5):
    """The Recovered Copies rows, newest first: (when, what, data)."""
    rows = []
    for d in documents or []:
        for c in (d.get("copies") or [])[:per_doc]:
            rows.append((str(c.get("time", "")), (when(c.get("time", "")), f"{d.get('label')}: {c.get('source', '')}",
                                                  {"document": d.get("document"), "label": d.get("label")})))
    return [r for _, r in sorted(rows, key=lambda x: x[0], reverse=True)]


def message(QtWidgets, parent, text, kind="information", title=TITLE):
    """A message box with SafetyNet's title. macOS shows no window title on
    a message box, so there the title is the bold first line and the text
    goes under it."""
    import sys

    icons = {"information": "Information", "warning": "Warning", "question": "Question"}
    box = QtWidgets.QMessageBox(parent)
    box.setIcon(getattr(QtWidgets.QMessageBox, icons.get(kind, "Information")))
    box.setWindowTitle(title)
    if sys.platform == "darwin":
        box.setText(title)
        box.setInformativeText(text)
    else:
        box.setText(text)
    if kind == "question":
        box.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        box.setDefaultButton(QtWidgets.QMessageBox.No)
    run = getattr(box, "exec", None) or box.exec_
    return run()


def qss(r):
    """SafetyNet's rules, scoped to its own widget by object name."""
    return (f"#{NAME} QLabel#SafetyNetPinned {{ color: {r['accent']}; font-weight: bold; }}\n"
            f"#{NAME} QLabel#SafetyNetHeld {{ color: {r['muted']}; }}\n"
            f"#{NAME} QPushButton#SafetyNetGo:enabled {{ color: {r['accent']}; font-weight: bold; }}\n"
            f"#{NAME} QTreeWidget {{ selection-background-color: {r['accent']}; }}\n")


def make(panel):
    """factory(panel) for Agent Link's register_tab: the tab's widget, whose
    fill() Agent Link calls each time the tab comes up."""
    return widget(panel._call, hosted=True)


def widget(runner, hosted=False):
    """The Session widget over a runner; hosted: Agent Link runs the calls."""
    QtCore, QtWidgets = _qt()
    from PySide import QtGui

    from . import theme

    STATE = {"approved": "ok", "changed": "warn"}

    class SessionTab(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.setObjectName(NAME)
            self.hosted = hosted
            lay = QtWidgets.QVBoxLayout(self)
            self.pinned = QtWidgets.QLabel("")
            self.pinned.setObjectName("SafetyNetPinned")
            self.pinned.setWordWrap(True)
            self.pinned.setToolTip("The document the agent works in.")
            lay.addWidget(self.pinned)
            held = QtWidgets.QHBoxLayout()
            self.held = QtWidgets.QLabel("")
            self.held.setObjectName("SafetyNetHeld")
            self.held.setWordWrap(True)
            held.addWidget(self.held, 1)
            self.go = QtWidgets.QPushButton("Go")
            self.go.setObjectName("SafetyNetGo")
            self.go.setToolTip("Run the heavy jobs held for you.")
            self.go.clicked.connect(lambda: self.do("queue_go", {}))
            held.addWidget(self.go)
            lay.addLayout(held)
            self.agent_rows = (self.pinned, self.held, self.go)
            for w in self.agent_rows:
                w.setVisible(hosted)
            self.tree = QtWidgets.QTreeWidget()
            self.tree.setHeaderLabels(["", "When", "What"])
            self.tree.setRootIsDecorated(True)
            # Long names cut in the middle, the full name in the tooltip.
            self.tree.setWordWrap(False)
            self.tree.setTextElideMode(QtCore.Qt.ElideMiddle)
            try:
                # Group titles span the row; When fits its dates; What takes
                # the rest. No fixed widths to clip them.
                head = self.tree.header()
                fit = QtWidgets.QHeaderView.ResizeToContents
                head.setSectionResizeMode(0, fit)
                head.setSectionResizeMode(1, fit)
                head.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
                head.setStretchLastSection(True)
            except Exception:
                pass
            lay.addWidget(self.tree, 1)
            row = QtWidgets.QHBoxLayout()
            self.buttons = {}
            for label, tip, fn in (("Use Copy", "Save the picked copy over its file.", self.accept),
                                   ("Roll Back", "Undo the picked settings change.", self.rollback),
                                   ("Approve", "Let Agent Link run the picked macro.", self.approve),
                                   ("Run", "Run the picked macro.", self.run)):
                b = QtWidgets.QPushButton(label)
                b.setToolTip(tip)
                b.clicked.connect(fn)
                row.addWidget(b)
                self.buttons[label] = b
            if not hosted:
                # A saved macro runs its calls through Agent Link.
                self.buttons["Run"].setEnabled(False)
                self.buttons["Run"].setToolTip("Needs Agent Link for FreeCAD.")
            lay.addLayout(row)
            self.roles = theme.roles(self)
            theme.follow(self, self._styled)

        def _styled(self, r):
            self.roles = r
            return qss(r)

        def say(self, text, kind="information"):
            message(QtWidgets, self, text, kind)

        def do(self, tool, args):
            ok, r = runner(tool, args)
            if not ok:
                self.say((r.get("error") or {}).get("message", str(r)), "warning")
            self.fill()
            return ok, r

        def fill(self):
            if self.hosted:
                ok, d = runner("doc_switch", {})
                name = (d.get("label") or d.get("document")) if ok else None
                self.pinned.setText(f"Agent works in: {name}" if name else "Agent works in: the document in front")
                q = _load(path("queue.json"), {}) or {}
                held = q.get("held") or []
                self.held.setText(f"Held for your go: {q.get('notice') or len(held)}" if held else "Nothing held.")
                self.go.setEnabled(bool(held))
            self.tree.clear()

            def section(title, rows, kind):
                top = QtWidgets.QTreeWidgetItem([title, "", ""])
                top.setForeground(0, QtGui.QBrush(QtGui.QColor(self.roles["accent"])))
                for r in rows:
                    it = QtWidgets.QTreeWidgetItem(["", str(r[0]), str(r[1])])
                    it.setToolTip(2, str(r[1]))
                    it.setData(0, QtCore.Qt.UserRole, json.dumps({"kind": kind, **r[2]}))
                    it.setForeground(1, QtGui.QBrush(QtGui.QColor(self.roles[STATE.get(r[0], "muted") if kind == "macro" else "muted"])))
                    top.addChild(it)
                self.tree.addTopLevelItem(top)
                top.setFirstColumnSpanned(True)
                top.setExpanded(bool(rows))

            ok, rec = runner("app_recover", {"action": "list"})
            section("Recovered Copies", recovered_rows(rec.get("documents") if ok else []), "recover")
            ok, ph = runner("pref_history", {"limit": 10})
            section("Settings Changes", [(when(c.get("time", "")), change_text(c), {"to": c.get("change")})
                                         for c in (ph.get("changes") or [])] if ok else [], "pref")
            ok, ml = runner("macro_list", {})
            section("Macros", [(m.get("state", ""), m.get("name"), {"name": m.get("name")})
                               for m in (ml.get("macros") or [])] if ok else [], "macro")

        def pick(self, kind):
            it = self.tree.currentItem()
            raw = it.data(0, QtCore.Qt.UserRole) if it else None
            d = json.loads(raw) if raw else None
            if not d or d.get("kind") != kind:
                self.say(f"Pick a line under {dict(recover='Recovered Copies', pref='Settings Changes', macro='Macros')[kind]} first.")
                return None
            return d

        def typed(self, title, want):
            text, ok = QtWidgets.QInputDialog.getText(self, title, f"Type  {want}  to confirm:")
            return text if ok and text.strip() == want else None

        def accept(self):
            d = self.pick("recover")
            if d:
                ok, r = self.do("app_recover", {"action": "auto", "documents": [{"name": d["document"], "label": d.get("label")}]})
                rec = (r.get("recovered") or [None])[0] if ok else None
                if rec:
                    if not rec.get("file"):
                        self.say(f"{rec['as']} is open; it was never saved to a file — save it where you like.")
                        return
                    typed = self.typed("Use Recovered Copy", f"save over {os.path.basename(rec['file'])}")
                    if typed:
                        self.do("app_recover", {"action": "accept", "document": rec["document"], "confirm": typed})

        def rollback(self):
            d = self.pick("pref")
            if d and d.get("to") is not None:
                self.do("pref_rollback", {"to": d["to"]})

        def approve(self):
            d = self.pick("macro")
            if d:
                typed = self.typed("Approve Macro", f"approve {d['name']}")
                if typed:
                    self.do("macro_approve", {"name": d["name"], "confirm": typed})

        def run(self):
            d = self.pick("macro")
            if d:
                self.do("macro_run", {"name": d["name"]})

    return SessionTab()


# ---- SafetyNet's own dock (Agent Link not loaded) ------------------------------------------

DOCK = "SafetyNetDock"
WORKBENCH = "SafetyNetWorkbench"


def _main():
    import FreeCADGui

    return FreeCADGui.getMainWindow()


def _raise_hosted_tab(mw):
    """Agent Link's panel tab holding the Session widget, brought to front;
    False when its panel is not open."""
    _, QtWidgets = _qt()
    for tabs in mw.findChildren(QtWidgets.QTabWidget):
        for i in range(tabs.count()):
            if tabs.widget(i) is not None and tabs.widget(i).objectName() == NAME:
                tabs.setCurrentIndex(i)
                w = tabs.parentWidget()
                while w is not None and not isinstance(w, QtWidgets.QDockWidget):
                    w = w.parentWidget()
                if w is not None:
                    w.show()
                    w.raise_()
                fill = getattr(tabs.widget(i), "fill", None)
                if fill:
                    fill()
                return True
    return False


def show():
    """The Panel command: Agent Link's Session tab when Agent Link hosts
    SafetyNet (put in its bar for now outside SafetyNet's workbench), else
    SafetyNet's own dock, placed by the panel layout setting (layout.py)
    for the workbench it was opened in (Tools ▸ SafetyNet reaches it from
    any)."""
    import importlib

    import safetynet

    from . import layout

    _, QtWidgets = _qt()
    mw = _main()
    if getattr(safetynet, "_hosted", False) and layout.in_agentlink_panel("Session"):
        try:
            importlib.import_module("agentlink.panel").show(tab="Session")
            return "hosted"
        except Exception:  # noqa: BLE001 — an Agent Link before tabs per workbench
            if _raise_hosted_tab(mw):
                return "hosted"
    dock = mw.findChild(QtWidgets.QDockWidget, DOCK)
    if dock is None:
        from . import local

        dock = QtWidgets.QDockWidget("SafetyNet", mw)
        dock.setObjectName(DOCK)
        # Under Agent Link its clicks run through it (shown and logged as
        # the agent's are) and the rows that need it show; alone, local.
        c = layout.caller() if getattr(safetynet, "_hosted", False) else None
        dock.setWidget(widget(c._call, hosted=True) if c is not None else widget(local.run, hosted=False))
    content = getattr(dock, "_content", None) or dock.widget()
    dock._content = content  # kept: in the Combo View or the slide-out it is not the dock's
    p = layout.placer()
    p.show(DOCK, dock, layout.active_workbench() or WORKBENCH, "SafetyNet")
    p.reveal(DOCK)
    fill = getattr(content, "fill", None)
    if fill:
        fill()
    return "dock"
