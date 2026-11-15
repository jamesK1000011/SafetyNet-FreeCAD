# SPDX-License-Identifier: LGPL-2.1-or-later
# Macros of agent calls: a session's steps saved as a .FCMacro in FreeCAD's
# own macro folder, its key sizes named at the top, replayed through
# agentlink.run(tool, args) — the same refusals and undo steps as live calls.
# A macro is Python with the run of the Mac, so one runs only once the person
# approved it (its SHA-256 recorded in ~/AgentLink/macros-approved.json;
# changed code needs approving again), and the agent never approves its own.
#
# Plain FreeCAD, imported where it is used: writing and reading a macro's
# text needs neither.

import ast
import hashlib
import os
import re
import time

from .files import _load, _save, path


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def approvals():
    return _load(path("macros-approved.json"), {})


def approve(name, p):
    a = approvals()
    a[name] = {"sha256": sha256_file(p), "path": p, "t": time.time()}
    _save(path("macros-approved.json"), a)
    return a[name]


def unapprove(name):
    a = approvals()
    gone = a.pop(name, None)
    _save(path("macros-approved.json"), a)
    return gone


def approval_state(name, p):
    """approved | changed (its code moved since the OK) | no."""
    e = approvals().get(name)
    if not e:
        return "no"
    try:
        return "approved" if sha256_file(p) == e["sha256"] else "changed"
    except OSError:
        return "no"


def macro_name_ok(name):
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,60}", str(name or "")))


def _ident(k):
    s = re.sub(r"\W+", "_", str(k)).strip("_").upper() or "P"
    return s if not s[0].isdigit() else "P_" + s


def macro_text(name, calls, params, header):
    """A .FCMacro replaying agent calls in order, with the listed sizes as
    named constants at the top: each place a listed value appears in the
    calls' arguments is replaced by its name."""
    consts = {_ident(k): v for k, v in (params or {}).items()}
    by_value = {}
    for k, v in consts.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            by_value.setdefault(float(v), k)
        elif isinstance(v, str):
            by_value.setdefault(v, k)

    def lit(x):
        if isinstance(x, bool) or x is None:
            return repr(x)
        if isinstance(x, (int, float)):
            k = by_value.get(float(x))
            return k if k else repr(x)
        if isinstance(x, str):
            k = by_value.get(x)
            return k if k else repr(x)
        if isinstance(x, list):
            return "[" + ", ".join(lit(y) for y in x) + "]"
        if isinstance(x, dict):
            return "{" + ", ".join(f"{k!r}: {lit(v)}" for k, v in x.items()) + "}"
        return repr(x)

    lines = ["# -*- coding: utf-8 -*-"] + [f"# {h}" for h in header] + ["", "# Key sizes: change them here."]
    for k, v in consts.items():
        lines.append(f"{k} = {v!r}")
    lines += ["", "import agentlink", ""]
    for c in calls:
        lines.append(f"agentlink.run({c['tool']!r}, {lit(c.get('args') or {})})")
    return "\n".join(lines) + "\n"


def macro_calls(text):
    """The calls and constants a macro written by macro_text holds, read
    without running it (it is Python: only literals are taken)."""
    tree = ast.parse(text)
    consts, calls = {}, []
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                consts[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f = node.value.func
            if isinstance(f, ast.Attribute) and f.attr == "run" and len(node.value.args) == 2:
                calls.append(node.value)
    return consts, calls


def macro_dir():
    import FreeCAD

    try:
        d = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Macro").GetString("MacroPath", "")
    except Exception:
        d = ""
    if not d:
        try:
            d = FreeCAD.getUserMacroDir(True)
        except Exception:
            d = os.path.join(FreeCAD.getUserAppDataDir(), "Macro")
    return d


def macro_path(name):
    return os.path.join(macro_dir(), f"{name}.FCMacro")


def with_params(text, params):
    """The macro's source with its named constants set to params (only
    top-level NAME = literal lines; the rest is the approved code as it is)."""
    tree = ast.parse(text)
    known = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            n = node.targets[0].id
            # Only a constant the person wrote as a plain value (a number, a
            # string, a list of them): never an expression, a call or a
            # path built in code, which the approval did not cover as data.
            try:
                ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, RecursionError):
                continue
            if n in params:
                v = params[n]
                try:
                    ast.literal_eval(repr(v))
                except (ValueError, SyntaxError):
                    continue
                node.value = ast.Constant(params[n]) if not isinstance(params[n], (list, dict)) else ast.parse(repr(params[n]), mode="eval").body
                known.add(n)
    missing = [k for k in params if k not in known]
    return ast.fix_missing_locations(tree), missing


def listing():
    """The macros in the folder, each approved, changed or not."""
    d = macro_dir()
    rows = []
    try:
        names = sorted(f for f in os.listdir(d) if f.lower().endswith(".fcmacro"))
    except OSError:
        names = []
    for f in names:
        name = f[: -len(".FCMacro")]
        p = os.path.join(d, f)
        first = ""
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if line.startswith("# ") and "coding" not in line:
                        first = line[2:].strip()
                        break
        except OSError:
            pass
        rows.append({"name": name, "state": approval_state(name, p), **({"about": first[:160]} if first else {})})
    return d, rows
