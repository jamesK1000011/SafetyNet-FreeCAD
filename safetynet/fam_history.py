# SPDX-License-Identifier: LGPL-2.1-or-later
# SafetyNet's history tools for Agent Link: checkpoints as saved copies, to
# come back to past FreeCAD's undo stack and across restarts. They join
# Agent Link's core group beside history_undo, history_redo and
# history_diff. A thin layer over safetynet.checkpoints.
from agentlink.protocol import Tool, ToolError

from . import checkpoints
from .files import stamp
from .refusal import Refused

GROUP = "core"
INFO = "The session, groups, guides, batches, undo, soundness, export. Always listed."


def obj(props, required=()):
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


def plain(fn):
    """SafetyNet's refusal as Agent Link's."""
    def run(a):
        try:
            return fn(a)
        except Refused as e:
            raise ToolError(e.code, e.message) from None
    return run


def tools(session):
    s = session

    def history_checkpoint(a):
        d = s.doc
        if a.get("list"):
            return {"document": d.Label, "checkpoints": [
                {"checkpoint": e["id"], **({"name": e["name"]} if e.get("name") else {}), "time": stamp(e.get("t")), "bytes": e.get("bytes"),
                 **({"auto": True} if e.get("auto") else {})} for e in checkpoints.cp_index(d.Name)]}
        name = a.get("name")
        if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 60):
            raise ToolError("invalid_input", "name: a short name for the checkpoint (60 characters at most).")
        e, dropped = checkpoints.take(s, name)
        out = {"checkpoint": e["id"], **({"name": name} if name else {}), "step": e["step"], "file": e["file"], "bytes": e["bytes"],
               "note": "A saved copy: history_restore comes back to it even past the undo stack, or after FreeCAD restarts."}
        if dropped:
            out["dropped"] = [x["id"] for x in dropped]
        return out

    def history_restore(a):
        return checkpoints.restore(s, a.get("checkpoint"))

    return [
        Tool("history_checkpoint", "Save a copy of the document now (name: optional; named ones are kept), to come back to with history_restore or measure from with history_diff { since } — past FreeCAD's 20-step undo and across restarts. list: true lists this document's checkpoints. The person's file is never touched.",
             obj({"name": {"type": "string"}, "list": {"type": "boolean"}}), plain(history_checkpoint)),
        Tool("history_restore", "Go back to a checkpoint (its id, cp3, or its name): by undo while the stack reaches it, else by reopening its saved copy (the state before is checkpointed first, so a restore can be undone the same way).",
             obj({"checkpoint": {"type": "string"}}, ["checkpoint"]), plain(history_restore)),
    ]
