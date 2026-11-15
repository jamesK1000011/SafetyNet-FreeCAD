# SPDX-License-Identifier: LGPL-2.1-or-later
# The Session tab in Agent Link's panel: what keeps the agent's work safe
# while nobody watches — the document the agent works in, heavy jobs held
# for the person's go, recovered copies, settings changes and macros. Each
# button runs the same tool the agent would (panel._call), so what the
# person does here is shown and logged like the agent's work. Built only
# when Agent Link's panel asks for it (its register_tab hook).
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


def make(panel):
    """factory(panel) for Agent Link's register_tab: the tab's widget, whose
    fill() Agent Link calls each time the tab comes up."""
    QtCore, QtWidgets = _qt()

    class SessionTab(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            lay = QtWidgets.QVBoxLayout(self)
            self.pinned = QtWidgets.QLabel("")
            self.pinned.setWordWrap(True)
            self.pinned.setToolTip("The document the agent works in, whatever is in front")
            lay.addWidget(self.pinned)
            held = QtWidgets.QHBoxLayout()
            self.held = QtWidgets.QLabel("")
            self.held.setWordWrap(True)
            held.addWidget(self.held, 1)
            self.go = QtWidgets.QPushButton("Go")
            self.go.setToolTip("Run the heavy jobs held while you worked")
            self.go.clicked.connect(lambda: self.do("queue_go", {}))
            held.addWidget(self.go)
            lay.addLayout(held)
            self.tree = QtWidgets.QTreeWidget()
            self.tree.setHeaderLabels(["", "When", "What"])
            self.tree.setRootIsDecorated(True)
            lay.addWidget(self.tree, 1)
            row = QtWidgets.QHBoxLayout()
            for label, tip, fn in (("Use copy", "Save the recovered copy picked above over its file (you type to confirm)", self.accept),
                                   ("Roll back", "Put FreeCAD's settings back as they were before the change picked above", self.rollback),
                                   ("Approve", "Let Agent Link run the macro picked above (you type to confirm)", self.approve),
                                   ("Run", "Run the approved macro picked above", self.run)):
                b = QtWidgets.QPushButton(label)
                b.setToolTip(tip)
                b.clicked.connect(fn)
                row.addWidget(b)
            lay.addLayout(row)

        def say(self, text):
            QtWidgets.QMessageBox.information(self, "SafetyNet", text)

        def do(self, tool, args):
            ok, r = panel._call(tool, args)
            if not ok:
                self.say((r.get("error") or {}).get("message", str(r)))
            self.fill()
            return ok, r

        def fill(self):
            ok, d = panel._call("doc_switch", {})
            name = (d.get("label") or d.get("document")) if ok else None
            self.pinned.setText(f"Agent works in: {name}" if name else "Agent works in: the document in front")
            q = _load(path("queue.json"), {}) or {}
            held = q.get("held") or []
            self.held.setText(f"Held for your go: {q.get('notice') or len(held)}" if held else "Nothing held.")
            self.go.setEnabled(bool(held))
            self.tree.clear()

            def section(title, rows, kind):
                top = QtWidgets.QTreeWidgetItem([title, "", ""])
                for r in rows:
                    it = QtWidgets.QTreeWidgetItem(["", str(r[0]), str(r[1])])
                    it.setData(0, QtCore.Qt.UserRole, json.dumps({"kind": kind, **r[2]}))
                    top.addChild(it)
                self.tree.addTopLevelItem(top)
                top.setExpanded(bool(rows))

            ok, rec = panel._call("app_recover", {"action": "list"})
            rows = []
            for docrow in (rec.get("documents") or []) if ok else []:
                for c in (docrow.get("copies") or [])[:5]:
                    rows.append((c.get("time", ""), f"{docrow.get('label')}: {c.get('source', '')}",
                                 {"document": docrow.get("document"), "label": docrow.get("label")}))
            section("Recovered copies", rows, "recover")
            ok, ph = panel._call("pref_history", {"limit": 10})
            section("Settings changes", [(c.get("time", ""), f"{c.get('path', '')}/{c.get('name', '')}: {c.get('from')} → {c.get('to')}", {"to": c.get("change")})
                                         for c in (ph.get("changes") or [])] if ok else [], "pref")
            ok, ml = panel._call("macro_list", {})
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
