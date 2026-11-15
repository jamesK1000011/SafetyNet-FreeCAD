# SPDX-License-Identifier: LGPL-2.1-or-later
# SafetyNet's GUI layer with FreeCAD absent: every tool has its handler and
# the family binds exactly those; the local runner answers in Agent Link's
# shape; InitGui registers the workbench, its commands and the Tools menu
# manipulator under stub FreeCAD modules; the theme reads its accents from
# a parameter fixture; the Session widget alone never asks for the rows that
# need Agent Link; the plain modules import nothing of Agent Link.
import ast
import contextlib
import os
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from safetynet import handlers, local, theme  # noqa: E402

FAMS = ("fam_history", "fam_safety")
# Agent Link's source, where it is checked out beside this one (or named).
AGENTLINK = os.environ.get("AGENTLINK_SRC") or os.path.join(os.path.dirname(ROOT), "freecad-agentlink")


def bound_names(fam):
    """(tool name, handler key) for each Tool(...) a family module declares."""
    tree = ast.parse(open(os.path.join(ROOT, "safetynet", fam + ".py"), encoding="utf-8").read())
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "Tool":
            name = n.args[0].value
            fn = n.args[3]
            key = fn.args[0].slice.value if isinstance(fn, ast.Call) and isinstance(fn.args[0], ast.Subscript) else None
            out.append((name, key))
    return out


class FakeDoc:
    def __init__(self, name="Doc"):
        self.Name = self.Label = name
        self.FileName = ""
        self.UndoCount = 0
        self.Objects = []
        self.log = []

    def openTransaction(self, n):
        self.log.append(("open", n))

    def commitTransaction(self):
        self.log.append(("commit",))

    def abortTransaction(self):
        self.log.append(("abort",))


def fake_freecad(doc=None, macro_dir=None):
    fc = types.ModuleType("FreeCAD")
    fc.ActiveDocument = doc
    fc.GuiUp = True
    fc.listDocuments = lambda: {doc.Name: doc} if doc else {}
    fc.getUserMacroDir = lambda *_: macro_dir or tempfile.mkdtemp()
    fc.getUserAppDataDir = lambda: tempfile.mkdtemp()
    fc.getUserCachePath = lambda: tempfile.mkdtemp()

    class Grp:
        def __getattr__(self, n):
            return lambda *a: (a[1] if len(a) > 1 else None)

    fc.ParamGet = lambda *_: Grp()
    fc.Console = types.SimpleNamespace(PrintMessage=lambda *_: None, PrintWarning=lambda *_: None, PrintError=lambda *_: None)
    return fc


class Parity(unittest.TestCase):
    def test_every_tool_has_its_handler(self):
        names = [n for fam in FAMS for n, _ in bound_names(fam)]
        self.assertEqual(sorted(names), sorted(handlers.HANDLERS))
        for fam in FAMS:
            for name, key in bound_names(fam):
                self.assertEqual(name, key, f"{fam}: {name} is bound to {key}")

    def test_with_agent_link_the_family_binds_the_handlers(self):
        sys.path.append(AGENTLINK)
        try:
            from agentlink.protocol import ToolError

            from safetynet import fam_history, fam_safety
        except ImportError:
            self.skipTest("Agent Link is not beside it")
        finally:
            sys.path.remove(AGENTLINK)
        s = types.SimpleNamespace()
        tools = {t.name: t for fam in (fam_history, fam_safety) for t in fam.tools(s)}
        self.assertEqual(sorted(tools), sorted(handlers.HANDLERS))
        # The same refusal either way: Agent Link's ToolError from the tool,
        # the local runner's error from the handler.
        for name, args in (("macro_show", {"name": "../x"}), ("macro_approve", {"name": "a/b", "confirm": ""})):
            with self.assertRaises(ToolError) as e:
                tools[name].fn(args)
            ok, r = local.run(name, args)
            self.assertFalse(ok)
            self.assertEqual((e.exception.code, e.exception.message), (r["error"]["code"], r["error"]["message"]))
        for fam in (fam_history, fam_safety):
            self.assertTrue(set(fam.AREAS) <= {"history_", "app_recover", "pref_", "macro_"})
            self.assertFalse(getattr(fam, "WORKBENCHES", None), "a safety call never switches the bench")


class LocalRunner(unittest.TestCase):
    def test_refusals_and_answers_in_agent_links_shape(self):
        doc = FakeDoc()
        mdir = tempfile.mkdtemp()
        with mock.patch.dict(sys.modules, {"FreeCAD": fake_freecad(doc, mdir)}):
            ok, r = local.run("macro_list", {})
            self.assertTrue(ok, r)
            self.assertEqual(r, {"folder": mdir, "macros": []})
            self.assertEqual(doc.log[-2:], [("open", "SafetyNet: macro_list"), ("commit",)])
            ok, r = local.run("macro_show", {"name": "nope"})
            self.assertFalse(ok)
            self.assertEqual(r["error"]["code"], "not_found")
            self.assertEqual(doc.log[-1], ("abort",))
            ok, r = local.run("queue_go", {})
            self.assertEqual((ok, r["error"]["code"]), (False, "not_found"))
            ok, r = local.run("macro_save", {"name": "m"})
            self.assertEqual((ok, r["error"]["code"]), (False, "invalid_state"))  # no agent calls to save alone

    def test_no_document(self):
        with mock.patch.dict(sys.modules, {"FreeCAD": fake_freecad(None)}):
            ok, r = local.run("history_checkpoint", {})
        self.assertEqual((ok, r["error"]["code"]), (False, "invalid_state"))

    def test_sessions_never_share_an_id(self):
        a, b = local.LocalSession(), local.LocalSession()
        self.assertNotEqual(id(a), id(b))
        self.assertTrue(a.in_place)
        self.assertIsNone(a.server)


class Theme(unittest.TestCase):
    def test_accents_from_a_parameter_file(self):
        a = theme.accents(os.path.join(HERE, "data", "theme.cfg"))
        self.assertEqual(a, ["#3f93d6", "#b477ff", None])

    def test_accents_from_a_parameter_group(self):
        grp = types.SimpleNamespace(GetUnsigned=lambda n, d=0: {"ThemeAccentColor1": 0x112233FF}.get(n, d))
        r = theme.roles(params=grp)
        self.assertEqual((r["accent"], r["accent2"], r["accent3"]), ("#112233",) * 3)
        for k in ("muted", "ok", "warn", "bad"):
            self.assertRegex(r[k], r"^#[0-9a-f]{6}$")

    def test_no_accent_falls_back(self):
        grp = types.SimpleNamespace(GetUnsigned=lambda n, d=0: 0)
        self.assertEqual(theme.accents(grp), [None, None, None])
        self.assertRegex(theme.roles(params=grp)["accent"], r"^#[0-9a-f]{6}$")
        self.assertIsNone(theme.hex_of("x"))
        self.assertIsNone(theme.hex_of(2 ** 33))


# ---- stub FreeCADGui and Qt ------------------------------------------------------------------

class Anything:
    """A stand-in for any Qt object: every attribute a recording callable."""

    def __init__(self, *a, **k):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return Member(self, name)

    def __bool__(self):
        return True


class Member:
    """owner.name, owner.name.sub, …: a call records ("name.sub", args) on owner."""

    def __init__(self, owner, name):
        self.owner, self.name = owner, name

    def __getattr__(self, sub):
        if sub.startswith("__"):
            raise AttributeError(sub)
        return Member(self.owner, f"{self.name}.{sub}")

    def __call__(self, *a, **k):
        self.owner.calls.append((self.name, a))
        return Anything()


def fake_qt():
    pyside = types.ModuleType("PySide")
    qtcore = types.ModuleType("PySide.QtCore")
    qtgui = types.ModuleType("PySide.QtGui")
    for mod in (qtcore, qtgui):
        mod.__getattr__ = lambda n: Anything
    qtcore.QObject = Anything
    qtcore.Qt = types.SimpleNamespace(UserRole=32, LeftDockWidgetArea=1)
    qtcore.QEvent = types.SimpleNamespace(PaletteChange=39)
    qtcore.QTimer = types.SimpleNamespace(singleShot=lambda ms, fn: None)
    qtgui.QWidget = Anything
    pyside.QtCore, pyside.QtGui = qtcore, qtgui
    return {"PySide": pyside, "PySide.QtCore": qtcore, "PySide.QtGui": qtgui}


def fake_gui(manipulators=True):
    g = types.ModuleType("FreeCADGui")
    g.registered = {"icons": [], "commands": {}, "benches": [], "manipulators": []}

    class Workbench:
        def appendToolbar(self, name, cmds):
            g.registered.setdefault("toolbars", []).append((name, list(cmds)))

        def appendMenu(self, name, cmds):
            g.registered.setdefault("menus", []).append((name, list(cmds)))

    g.Workbench = Workbench
    g.addIconPath = g.registered["icons"].append
    g.addCommand = lambda n, c: g.registered["commands"].__setitem__(n, c)
    g.addWorkbench = g.registered["benches"].append
    if manipulators:
        g.addWorkbenchManipulator = g.registered["manipulators"].append
    mw = Anything()
    g.getMainWindow = lambda: mw
    g.mw = mw
    return g


@contextlib.contextmanager
def gui_stubs(manipulators=True):
    mods = {"FreeCAD": fake_freecad(FakeDoc()), "FreeCADGui": fake_gui(manipulators), **fake_qt()}
    import safetynet

    # Fresh copies under the stubs: neither the module table nor the
    # package's attributes keep one made under another test's stubs.
    for k in ("commands", "panel"):
        sys.modules.pop("safetynet." + k, None)
        safetynet.__dict__.pop(k, None)
    with mock.patch.dict(sys.modules, mods):
        yield mods["FreeCADGui"]
    for k in ("commands", "panel"):
        sys.modules.pop("safetynet." + k, None)
        safetynet.__dict__.pop(k, None)


def run_initgui():
    ns = {"__name__": "__main__"}
    with open(os.path.join(ROOT, "InitGui.py"), encoding="utf-8") as f:
        exec(compile(f.read(), "InitGui.py", "exec"), ns)
    return ns


# FreeCAD's own icons the commands name (resolved by FreeCAD, never copied).
FREECAD_ICONS = {"preferences-system", "edit-undo", "Std_DlgMacroExecute"}


class InitGui(unittest.TestCase):
    def test_registers_bench_commands_and_manipulator(self):
        with gui_stubs() as g:
            ns = run_initgui()
            reg = g.registered
            self.assertEqual(ns["_SAFETYNET_MENU"], "manipulator")
            self.assertEqual(len(reg["benches"]), 1)
            wb = reg["benches"][0]
            self.assertEqual(wb.MenuText, "SafetyNet")
            self.assertEqual(type(wb).__name__, "SafetyNetWorkbench")
            self.assertTrue(os.path.isfile(wb.Icon), wb.Icon)
            self.assertEqual(reg["icons"], [os.path.join(ROOT, "safetynet", "icons")])
            from safetynet import commands

            self.assertEqual(sorted(reg["commands"]), sorted(commands.NAMES + [commands.MENU]))
            for name in commands.NAMES:
                pix = reg["commands"][name].GetResources()["Pixmap"]
                self.assertTrue(pix in FREECAD_ICONS or os.path.isfile(os.path.join(reg["icons"][0], pix + ".svg")), f"{name}: {pix}")
            self.assertEqual(list(reg["commands"][commands.MENU].GetCommands()), commands.NAMES)
            for want in ("SafetyNet_Checkpoint", "SafetyNet_Restore", "SafetyNet_Recover", "SafetyNet_SettingsHistory", "SafetyNet_Rollback", "SafetyNet_Macros"):
                self.assertIn(want, commands.NAMES)
            (m,) = reg["manipulators"]
            entries = m.modifyMenuBar()
            self.assertIn({"append": "SafetyNet_Menu", "menuItem": "&Tools"}, entries)
            wb.Initialize()
            self.assertEqual(reg["toolbars"], [("SafetyNet", commands.TOOLBAR)])
            self.assertEqual(reg["menus"], [("SafetyNet", commands.NAMES)])
            self.assertEqual(len(reg["commands"]), len(commands.NAMES) + 1, "registered once")

    def test_falls_back_to_qt_without_manipulators(self):
        with gui_stubs(manipulators=False) as g:
            ns = run_initgui()
            self.assertEqual(ns["_SAFETYNET_MENU"], "qt")
            self.assertEqual(len(g.registered["benches"]), 1)
            self.assertIn("workbenchActivated.connect", [c[0] for c in g.mw.calls])


class SessionWidget(unittest.TestCase):
    def build(self, hosted):
        asked = []

        def runner(tool, args):
            asked.append(tool)
            return True, {}

        with gui_stubs():
            from safetynet import panel

            w = panel.widget(runner, hosted=hosted)
            w.fill()
        return w, asked

    def test_alone_hides_agent_rows_and_never_asks_for_them(self):
        w, asked = self.build(False)
        for row in w.agent_rows:
            self.assertIn(("setVisible", (False,)), row.calls)
        self.assertNotIn("doc_switch", asked)
        self.assertEqual(asked, ["app_recover", "pref_history", "macro_list"])
        self.assertIn(("setEnabled", (False,)), w.buttons["Run"].calls)

    def test_hosted_shows_them(self):
        w, asked = self.build(True)
        for row in w.agent_rows:
            self.assertIn(("setVisible", (True,)), row.calls)
        self.assertEqual(asked[0], "doc_switch")


class NoAgentLink(unittest.TestCase):
    def test_plain_modules_import_nothing_of_agent_link(self):
        mods = "safetynet, safetynet.handlers, safetynet.local, safetynet.theme, safetynet.panel, safetynet.refusal"
        code = (f"import sys; sys.path[:0] = [{ROOT!r}, {AGENTLINK!r}]; import {mods}; "
                "print(sorted(m for m in sys.modules if m.startswith('agentlink')))")
        out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(out, "[]")

    def test_no_agentlink_import_statement_outside_the_family_layer(self):
        allowed = {"agentlink_families.py", "fam_history.py", "fam_safety.py"}
        for root in (os.path.join(ROOT, "safetynet"), ROOT):
            for f in os.listdir(root):
                if not f.endswith(".py") or f in allowed:
                    continue
                tree = ast.parse(open(os.path.join(root, f), encoding="utf-8").read())
                for n in ast.walk(tree):
                    names = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or ""] if isinstance(n, ast.ImportFrom) else []
                    self.assertFalse(any(x.split(".")[0] == "agentlink" for x in names), f"{f} imports Agent Link")


if __name__ == "__main__":
    unittest.main()
