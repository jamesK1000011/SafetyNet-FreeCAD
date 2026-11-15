# SPDX-License-Identifier: LGPL-2.1-or-later
# SafetyNet's tools for Agent Link: documents back after a crash or a hang
# (app_recover), FreeCAD's settings history and rollback, and macros the
# person approved. A thin layer over safetynet's own modules.
#
# The person's calls stay the person's: saving over their file and approving
# a macro each need their own words in chat (a typed confirm), never the
# agent's.
import os
import shutil
import time

from agentlink.protocol import Tool, ToolError

from . import checkpoints, macros, recovery, settings
from .fam_history import obj, plain
from .files import _load, path

GROUP = "safety"
INFO = "SafetyNet: documents back after a crash or a hang (app_recover), FreeCAD's settings history and rollback, and macros the person approved (save, list, show, approve, run)."


def bad(msg):
    return ToolError("invalid_input", msg)


def tools(s):
    def app_recover(a):
        import FreeCAD

        action = a.get("action", "list")
        if action == "list":
            return {"documents": recovery.listing(), "note": "action auto { documents } opens the newest good copy of each beside its file; accept { document, confirm } saves one over its file."}
        if action == "auto":
            docs = a.get("documents")
            if not isinstance(docs, list) or not docs:
                raise bad("documents: [{ name, label, file }] — the documents to bring back (app_recover lists what has copies).")
            rec, failed = recovery.recover_docs(docs, a.get("since"))
            if rec:
                s.switch(FreeCAD.getDocument(rec[0]["document"]))
            return {"recovered": rec, **({"failed": failed} if failed else {}),
                    "note": "Opened beside the person's files as \"(recovered …)\"; their files are untouched. accept { document, confirm: \"save over <file name>\" } typed by them saves one over its file."}
        if action == "accept":
            nd, out = recovery.accept(a.get("document"), a.get("confirm"))
            s.switch(nd)
            return out
        raise bad("action: list | auto { documents, since } | accept { document, confirm }.")

    # ---- settings -------------------------------------------------------------------------

    def pref_history(a):
        return {"changes": settings.history_rows(int(a.get("limit", 20) or 20)),
                "note": "Newest first. pref_rollback { to: change } puts the settings back as they were before that change (a snapshot of the whole settings file)."}

    def pref_rollback(a):
        import FreeCAD

        to = a.get("to")
        if to in (None, ""):
            raise bad("to: a change's number (pref_history) or a time, YYYYMMDD-HHMMSS.")
        snap = settings.settings_snapshot_for(to)
        if not snap:
            raise ToolError("not_found", f"to {to!r}: no settings snapshot for it — pref_history lists the changes with theirs.")
        gui = getattr(FreeCAD, "GuiUp", False)
        if not gui:
            hb = _load(path("heartbeat.json"), {}) or {}
            if time.time() - float(hb.get("t") or 0) < 10:
                raise ToolError("invalid_state", "The FreeCAD window is open with its link off: it would write its own settings over the rollback as it quits. Turn its link on (the rollback then restarts it) or close it, then pref_rollback again. Nothing was changed.")
        if not gui and not os.environ.get("AGENTLINK_SUPERVISED"):
            raise ToolError("unavailable", "Rolling settings back needs FreeCAD to start again around the file: through the window's link, or the supervised server the launcher runs. Nothing was changed.")
        restart = (getattr(getattr(s, "server", None), "tools", None) or {}).get("app_restart")
        if gui and restart is None:
            raise ToolError("unavailable", "No app_restart here to start FreeCAD again around the file. Nothing was changed.")
        current = settings.snapshot_now()
        settings.settings_log({"tool": "pref_rollback", "to": str(to), "restoredFrom": snap, "snapshot": current, "restart": True})
        if gui:
            out = restart.fn({"_cfg_from": snap, "save": a.get("save", "agent")})
            out.update({"rolledBackTo": os.path.basename(snap), "note": "FreeCAD quits, its settings file is put back, and it opens again in the background with its documents. pref_rollback again with the newest change undoes this."})
            return out
        shutil.copy2(snap, settings.user_cfg())
        s.exit_after_reply = "nosave"
        return {"rolledBackTo": os.path.basename(snap), "restarting": "the hidden FreeCAD, at once (the window is closed: it reads these settings when it next opens)"}

    # ---- macros ---------------------------------------------------------------------------

    def _macro(name):
        if not macros.macro_name_ok(name):
            raise bad("name: letters, digits, spaces, - and _ (60 at most), no folders.")
        return macros.macro_path(name)

    def macro_save(a):
        try:
            from agentlink.server import VERSION
        except Exception:
            VERSION = "?"
        name = a.get("name")
        p = _macro(name)
        if os.path.exists(p) and not a.get("overwrite"):
            raise ToolError("invalid_state", f"A macro named {name} is there already ({p}): another name, or overwrite: true (it then needs approving again).")
        calls = list(s.calls)
        lo, hi = a.get("from"), a.get("to")

        def tx_of(ref):
            """A from / to bound as an undo-step count: a step number (the
            calls up to that step) or a checkpoint of this session."""
            if ref is None:
                return None
            if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
                n = int(ref)
                return max([c["tx"] for c in calls if c["step"] <= n] or [0])
            cp = checkpoints.find(s, ref)
            if not cp:
                raise ToolError("not_found", f"{ref!r}: no such checkpoint or step.")
            if cp.get("session") != id(s):
                raise ToolError("invalid_state", f"{cp['id']} is from an earlier session: its steps are not here to save — from: a step of this one.")
            return int(cp.get("tx", 0))

        t0, t1 = tx_of(lo), tx_of(hi)
        picked = [c for c in calls if (t0 is None or c["tx"] > t0) and (t1 is None or c["tx"] <= t1)]
        # A step undone and not redone is not part of the work.
        picked = [c for c in picked if c["tx"] <= s.tx]
        if not picked:
            raise ToolError("invalid_state", "No changing calls in that range to save: make the part first, or widen from / to.")
        params = a.get("params") or {}
        if not isinstance(params, dict) or any(not isinstance(v, (int, float, str)) or isinstance(v, bool) for v in params.values()):
            raise bad("params: { name: number or text } — the key sizes, e.g. { \"wall\": 2.0, \"length\": 60 }; each place a value appears in the calls takes its name.")
        made = [o.Label for o in s.bodies()]
        header = [
            f"{name}: made by Agent Link {VERSION} from {len(picked)} calls of a session on {time.strftime('%Y-%m-%d %H:%M')}",
            f"Makes: {', '.join(made) or 'the changes below'} in {s.doc.Label if s.doc else 'the document'}",
            "Runs through agentlink.run(tool, arguments): the same refusals and undo steps as live calls.",
            "Run by Agent Link only once approved (macro_approve, the person's typed OK); a change to this file needs approving again.",
        ]
        text = macros.macro_text(name, picked, params, header)
        compile(text, p, "exec")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        state = macros.approval_state(name, p)
        consts, _ = macros.macro_calls(text)
        return {"macro": name, "path": p, "calls": len(picked), "constants": consts, "approved": state == "approved",
                "note": "Saved in FreeCAD's macro folder (Macro › Macros… runs it by hand too). Agent Link runs it only after the person approves it: macro_approve { name, confirm: \"approve " + name + "\" } typed by them."}

    def macro_list(a):
        d, rows = macros.listing()
        return {"folder": d, "macros": rows}

    def macro_show(a):
        p = _macro(a.get("name"))
        if not os.path.isfile(p):
            raise ToolError("not_found", f"No macro {a.get('name')} in {os.path.dirname(p)}: macro_list lists them.")
        with open(p, encoding="utf-8", errors="replace") as f:
            text = f.read()
        try:
            consts, calls = macros.macro_calls(text)
        except SyntaxError as e:
            consts, calls = {}, []
            text = f"(does not parse: {e})\n" + text
        return {"name": a.get("name"), "state": macros.approval_state(a.get("name"), p), "constants": consts, "calls": len(calls),
                "text": text if len(text) <= 6000 else text[:6000] + f"\n… ({len(text)} characters in all)"}

    def macro_approve(a):
        name = a.get("name")
        p = _macro(name)
        if not os.path.isfile(p):
            raise ToolError("not_found", f"No macro {name}: macro_list lists them.")
        want = f"approve {name}"
        if (a.get("confirm") or "").strip() != want:
            raise ToolError("not_allowed", f"confirm: \"{want}\", word for word, typed by the person — a macro is Python that runs with the Mac's full reach, so approving it is theirs. Show them macro_show first. Nothing was changed.")
        e = macros.approve(name, p)
        return {"approved": name, "sha256": e["sha256"], "note": "macro_run runs it from now on; a change to its file needs approving again."}

    def macro_unapprove(a):
        name = a.get("name")
        _macro(name)
        gone = macros.unapprove(name)
        return {"unapproved": name, "was": bool(gone)}

    def macro_run(a):
        import agentlink

        name = a.get("name")
        p = _macro(name)
        if not os.path.isfile(p):
            raise ToolError("not_found", f"No macro {name}: macro_list lists them.")
        state = macros.approval_state(name, p)
        if state != "approved":
            why = "its file changed since it was approved" if state == "changed" else "it has not been approved"
            raise ToolError("not_allowed", f"{name} is not run: {why}. The person approves it: macro_approve {{ name: \"{name}\", confirm: \"approve {name}\" }} typed by them (macro_show shows it first).")
        with open(p, encoding="utf-8") as f:
            text = f.read()
        params = a.get("params") or {}
        if not isinstance(params, dict):
            raise bad("params: { CONSTANT: value } — the macro's named sizes (macro_show lists them).")
        tree, missing = macros.with_params(text, params)
        if missing:
            consts, _ = macros.macro_calls(text)
            raise bad(f"params: {', '.join(missing)} — not among the macro's named sizes ({', '.join(consts) or 'none'}).")
        server = getattr(s, "server", None)
        if server is None:
            raise ToolError("invalid_state", "No server to run the macro through.")
        cp, _ = checkpoints.take(s, f"before macro {name}", auto=True)
        n0 = len(s.calls)
        try:
            with agentlink.serving(server):
                exec(compile(tree, p, "exec"), {"__name__": "__agentlink_macro__", "__file__": p})
        except Exception as e:
            ran = len(s.calls) - n0
            try:
                back = checkpoints.restore(s, cp["id"])
                how = back.get("how")
            except Exception as e2:
                how = f"not rolled back ({e2})"
            raise ToolError("failed", f"{name} stopped after {ran} call{'s' if ran != 1 else ''}: {e}. Rolled back whole ({how}) to how it was before.")
        return {"ran": name, "calls": len(s.calls) - n0, "checkpoint": cp["id"], **({"params": params} if params else {}),
                "bodies": [o.Label for o in s.bodies()], "note": f"history_restore {{ checkpoint: {cp['id']} }} goes back to before it."}

    st = {"type": "string"}
    return [
        Tool("macro_save", "Save this session's changing calls as a FreeCAD macro (.FCMacro in the person's macro folder): name, from / to (a checkpoint or step; the whole session by default), params { wall: 2.0, length: 60 } — the key sizes, named at the top of the macro and put in place of each value in the calls. It runs (macro_run) only once the person approves it.",
             obj({"name": st, "from": {"type": ["string", "integer"]}, "to": {"type": ["string", "integer"]}, "params": {"type": "object"}, "overwrite": {"type": "boolean"}}, ["name"]), plain(macro_save)),
        Tool("macro_list", "The macros in FreeCAD's macro folder, each approved, changed (its code moved since the OK) or not approved. Changes nothing.", obj({}), plain(macro_list)),
        Tool("macro_show", "One macro's text, its named sizes and how many calls it makes, and whether it is approved. Changes nothing.", obj({"name": st}, ["name"]), plain(macro_show)),
        Tool("macro_approve", "The person approves a macro to be run by Agent Link: confirm: \"approve <name>\" typed by them, never by the agent — a macro is Python with the Mac's full reach. Approval holds until its file changes.",
             obj({"name": st, "confirm": st}, ["name", "confirm"]), plain(macro_approve)),
        Tool("macro_unapprove", "Take a macro off the approved list.", obj({"name": st}, ["name"]), plain(macro_unapprove)),
        Tool("macro_run", "Run an approved macro: params { CONSTANT: value } changes its named sizes for this run. One checkpoint before; a call refused part way rolls the whole run back. An unapproved or changed macro is refused.",
             obj({"name": st, "params": {"type": "object"}}, ["name"]), plain(macro_run)),
        Tool("app_recover", "Documents back after a crash or a hang: action list (each document's saved copies: auto-saves, checkpoints, FreeCAD's recovery files, newest first) | auto { documents [{ name, label, file }], since } (the newest copy that opens, beside the file as \"<label> (recovered HH:MM)\") | accept { document, confirm: \"save over <file name>\" typed by the person } (the recovered copy saved over their file, the old one kept).",
             obj({"action": {"type": "string", "enum": ["list", "auto", "accept"]}, "documents": {"type": "array", "items": {"type": "object"}}, "since": {"type": "number"}, "document": st, "confirm": st}), plain(app_recover)),
        Tool("pref_history", "The settings changes Agent Link made, newest first: change number, time, tool, path, name, from, to, and whether a restart is needed (limit, 20 by default). Changes nothing.",
             obj({"limit": {"type": "integer"}}), plain(pref_history)),
        Tool("pref_rollback", "Put FreeCAD's settings back as they were before a change (to: its number from pref_history, or a time YYYYMMDD-HHMMSS): the whole settings file from its snapshot, written while FreeCAD is down — the window restarts around it in the background (save as app_restart's); the state before is snapshotted too.",
             obj({"to": {"type": ["integer", "string"]}, "save": {"type": "string", "enum": ["agent", "none"]}}, ["to"]), plain(pref_rollback)),
    ]

