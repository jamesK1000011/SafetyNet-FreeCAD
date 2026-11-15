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
            self.pinned.setToolTip("The document the agent works in, whatever is in front")
            lay.addWidget(self.pinned)
            held = QtWidgets.QHBoxLayout()
            self.held = QtWidgets.QLabel("")
            self.held.setObjectName("SafetyNetHeld")
            self.held.setWordWrap(True)
            held.addWidget(self.held, 1)
            self.go = QtWidgets.QPushButton("Go")
            self.go.setObjectName("SafetyNetGo")
            self.go.setToolTip("Run the heavy jobs held while you worked")
            self.go.clicked.connect(lambda: self.do("queue_go", {}))
            held.addWidget(self.go)
            lay.addLayout(held)
            self.agent_rows = (self.pinned, self.held, self.go)
            for w in self.agent_rows:
                w.setVisible(hosted)
            self.tree = QtWidgets.QTreeWidget()
            self.tree.setHeaderLabels(["", "When", "What"])
            self.tree.setRootIsDecorated(True)
            lay.addWidget(self.tree, 1)
            row = QtWidgets.QHBoxLayout()
            self.buttons = {}
            for label, tip, fn in (("Use copy", "Save the recovered copy picked above over its file (you type to confirm)", self.accept),
                                   ("Roll back", "Put FreeCAD's settings back as they were before the change picked above", self.rollback),
                                   ("Approve", "Let Agent Link run the macro picked above (you type to confirm)", self.approve),
                                   ("Run", "Run the approved macro picked above", self.run)):
                b = QtWidgets.QPushButton(label)
                b.setToolTip(tip)
                b.clicked.connect(fn)
                row.addWidget(b)
                self.buttons[label] = b
            if not hosted:
                # A saved macro runs its calls through Agent Link.
                self.buttons["Run"].setEnabled(False)
                self.buttons["Run"].setToolTip("Running a macro of the agent's calls needs Agent Link for FreeCAD")
            lay.addLayout(row)
            self.roles = theme.roles(self)
            theme.follow(self, self._styled)

        def _styled(self, r):
            self.roles = r
            return qss(r)

        def say(self, text):
            QtWidgets.QMessageBox.information(self, "SafetyNet", text)

        def do(self, tool, args):
            ok, r = runner(tool, args)
            if not ok:
                self.say((r.get("error") or {}).get("message", str(r)))
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
                    it.setData(0, QtCore.Qt.UserRole, json.dumps({"kind": kind, **r[2]}))
                    it.setForeground(1, QtGui.QBrush(QtGui.QColor(self.roles[STATE.get(r[0], "muted") if kind == "macro" else "muted"])))
                    top.addChild(it)
                self.tree.addTopLevelItem(top)
                top.setExpanded(bool(rows))

            ok, rec = runner("app_recover", {"action": "list"})
            rows = []
            for docrow in (rec.get("documents") or []) if ok else []:
                for c in (docrow.get("copies") or [])[:5]:
                    rows.append((c.get("time", ""), f"{docrow.get('label')}: {c.get('source', '')}",
                                 {"document": docrow.get("document"), "label": docrow.get("label")}))
            section("Recovered copies", rows, "recover")
            ok, ph = runner("pref_history", {"limit": 10})
            section("Settings changes", [(c.get("time", ""), f"{c.get('path', '')}/{c.get('name', '')}: {c.get('from')} → {c.get('to')}", {"to": c.get("change")})
                                         for c in (ph.get("changes") or [])] if ok else [], "pref")
            ok, ml = runner("macro_list", {})
            section("Macros", [(m.get("state", ""), m.get("name"), {"name": m.get("name")})
                               for m in (ml.get("macros") or [])] if ok else [], "macro")

        def pick(self, kind):
            it = self.tree.currentItem()
            raw = it.data(0, QtCore.Qt.UserRole) if it else None
            d = json.loads(raw) if raw else None
            if not d or d.get("kind") != kind:
                self.say(f"Pick a line under {dict(recover='Recovered copies', pref='Settings changes', macro='Macros')[kind]} first.")
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
                    typed = self.typed("Use the recovered copy", f"save over {os.path.basename(rec['file'])}")
                    if typed:
                        self.do("app_recover", {"action": "accept", "document": rec["document"], "confirm": typed})

        def rollback(self):
            d = self.pick("pref")
            if d and d.get("to") is not None:
                self.do("pref_rollback", {"to": d["to"]})

        def approve(self):
            d = self.pick("macro")
            if d:
                typed = self.typed("Approve the macro", f"approve {d['name']}")
                if typed:
                    self.do("macro_approve", {"name": d["name"], "confirm": typed})

        def run(self):
            d = self.pick("macro")
            if d:
                self.do("macro_run", {"name": d["name"]})

    return SessionTab()


# ---- SafetyNet's own dock (Agent Link not loaded) ------------------------------------------

DOCK = "SafetyNetDock"


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
    SafetyNet and its panel is open, else SafetyNet's own dock, tabbed with
    the Combo View beside the model tree."""
    import safetynet

    QtCore, QtWidgets = _qt()
    mw = _main()
    if getattr(safetynet, "_hosted", False) and _raise_hosted_tab(mw):
        return "hosted"
    dock = mw.findChild(QtWidgets.QDockWidget, DOCK)
    if dock is None:
        from . import local

        dock = QtWidgets.QDockWidget("SafetyNet", mw)
        dock.setObjectName(DOCK)
        dock.setWidget(widget(local.run, hosted=False))
        mw.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)
        combo = mw.findChild(QtWidgets.QDockWidget, "Combo View")
        if combo is not None:
            mw.tabifyDockWidget(combo, dock)
    dock.show()
    dock.raise_()
    dock.widget().fill()
    return "dock"
