# SPDX-License-Identifier: LGPL-2.1-or-later
# Documents back after a crash, a hang or a restart: from SafetyNet's
# auto-saves and checkpoints and from FreeCAD's own recovery files, opened
# beside the person's file as "<label> (recovered HH:MM)" and saved over it
# only with their typed say-so. Also what a hidden FreeCAD holds (hidden.json,
# for whoever restarts it after a crash), the documents to reopen from copies
# after a restart (reopen.json), and FreeCAD's own AutoSave kept on.
#
# Plain FreeCAD, imported where it is used.

import json
import os
import re
import shutil
import tempfile
import time

from . import autosave, checkpoints, settings
from .files import _load, _save, path, safe, stamp
from .refusal import Refused

RECOVERED_FOR = "AgentLinkRecoveredFor"
# Past this a reopen list is stale (a restart that never came back).
REOPEN_LIMIT = 600.0


def recovery_sources(doc, freecad_recovery=()):
    """What a document could come back from, newest first: our auto-saves,
    checkpoints, and FreeCAD's own recovery files ([(path, t)] passed in).
    Each { source, path, t }."""
    out = []
    d = autosave.autosave_dir(doc)
    try:
        for f in os.listdir(d):
            if f.endswith(".FCStd"):
                p = os.path.join(d, f)
                out.append({"source": "autosave", "path": p, "t": os.path.getmtime(p)})
    except OSError:
        pass
    for e in checkpoints.cp_index(doc):
        if os.path.isfile(e.get("file", "")):
            out.append({"source": "checkpoint", "path": e["file"], "t": os.path.getmtime(e["file"]), "checkpoint": e.get("id")})
    for p, t in freecad_recovery:
        out.append({"source": "freecad", "path": p, "t": t})
    return sorted(out, key=lambda x: -x["t"])


def freecad_recovery_files(cache_dirs, doc_label=None):
    """FreeCAD's own recovery copies under its cache folders: each holds
    fc_recovery_file.fcstd and an .xml naming the document. [(path, t, label)]"""
    found = []
    for root in cache_dirs:
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for n in names:
            d = os.path.join(root, n)
            f = os.path.join(d, "fc_recovery_file.fcstd")
            if not os.path.isfile(f):
                continue
            label = None
            try:
                with open(os.path.join(d, "fc_recovery_file.xml"), encoding="utf-8", errors="replace") as fh:
                    m = re.search(r"<Label>([^<]*)</Label>", fh.read())
                    label = m.group(1) if m else None
            except OSError:
                pass
            if doc_label is None or label in (None, doc_label):
                found.append((f, os.path.getmtime(f), label))
    return sorted(found, key=lambda x: -x[1])


# ---- with FreeCAD ------------------------------------------------------------------------

def _hm(t):
    return time.strftime("%H:%M", time.localtime(t))


def cache_dirs():
    import FreeCAD

    out = []
    for fn in ("getUserCachePath", "getUserCacheDir"):
        try:
            p = getattr(FreeCAD, fn)()
            if p and p not in out:
                out.append(p)
        except Exception:
            pass
    return out


def open_copy(src, name, label, t):
    """A saved copy opened beside the person's file, never over it: its own
    name and the label "<label> (recovered HH:MM)"."""
    import FreeCAD

    tmpd = tempfile.mkdtemp(prefix="agentlink-recovered-")
    tmp = os.path.join(tmpd, f"{safe(name)}_recovered.FCStd")
    shutil.copy2(src, tmp)
    nd = FreeCAD.openDocument(tmp)
    try:
        nd.recompute()
    except Exception:
        pass
    nd.Label = f"{label} (recovered {_hm(t)})"
    return nd


def recover_docs(documents, since=None):
    rec, failed = [], []
    for d in documents or []:
        name, label, fname = d.get("name"), d.get("label") or d.get("name"), d.get("file") or ""
        if not name:
            continue
        fc = [(p, t) for p, t, _ in freecad_recovery_files(cache_dirs(), label)]
        srcs = recovery_sources(name, fc)
        if not srcs:
            failed.append({"label": label, "why": "no saved copy (no checkpoint, auto-save or FreeCAD recovery file)"})
            continue
        errors = []
        for src in srcs:
            try:
                nd = open_copy(src["path"], name, label, src["t"])
            except Exception as e:
                errors.append(f"{src['source']} {_hm(src['t'])}: {e}")
                continue
            m = dict(nd.Meta or {})
            m[RECOVERED_FOR] = json.dumps({"file": fname, "label": label, "source": src["source"], "t": src["t"]})
            nd.Meta = m
            lost = None
            if since:
                mins = max(0, int(round((float(since) - src["t"]) / 60.0)))
                lost = "nothing after it lost" if mins == 0 else f"about {mins} min of changes lost"
            rec.append({"label": label, "document": nd.Name, "as": nd.Label, "source": src["source"], "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(src["t"])),
                        **({"lost": lost} if lost else {}), **({"skipped": errors} if errors else {}), "file": fname or None})
            break
        else:
            failed.append({"label": label, "why": "; ".join(errors)[:400]})
    return rec, failed


def listing():
    """Each document with saved copies (open ones and those with folders here)."""
    import FreeCAD

    names = {}
    for d in FreeCAD.listDocuments().values():
        names[d.Name] = {"label": d.Label, "file": d.FileName or ""}
    for sub in ("autosave", "checkpoints"):
        try:
            for n in os.listdir(path(sub)):
                names.setdefault(n, {"label": n, "file": ""})
        except OSError:
            pass
    out = []
    for n, info in sorted(names.items()):
        fc = [(p, t) for p, t, _ in freecad_recovery_files(cache_dirs(), info["label"])]
        srcs = recovery_sources(n, fc)[:6]
        if srcs:
            out.append({"document": n, "label": info["label"], "copies": [{"source": x["source"], "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(x["t"])), "path": x["path"]} for x in srcs]})
    return out


def accept(ref, confirm):
    """A recovered copy saved over the person's file, with their typed
    confirm; what was there kept under ~/AgentLink/replaced. The document."""
    import FreeCAD

    nd = next((d for d in FreeCAD.listDocuments().values() if ref in (d.Name, d.Label)), None)
    if nd is None:
        raise Refused("not_found", f"document {ref!r}: not open — app_recover (action list) shows the copies.")
    raw = (nd.Meta or {}).get(RECOVERED_FOR)
    if not raw:
        raise Refused("invalid_state", f"{nd.Label} is not a recovered copy.")
    info = json.loads(raw)
    target = info.get("file")
    if not target:
        raise Refused("invalid_state", f"{nd.Label} was never saved to a file: doc_save {{ path }} saves it where the person says.")
    want = f"save over {os.path.basename(target)}"
    if (confirm or "").strip() != want:
        raise Refused("not_allowed", f"confirm: \"{want}\", word for word, typed by the person — this replaces their file with the recovered copy. Nothing was changed.")
    other = next((d for d in FreeCAD.listDocuments().values() if d is not nd and d.FileName and os.path.abspath(d.FileName) == os.path.abspath(target)), None)
    if other is not None:
        raise Refused("invalid_state", f"{target} is open as {other.Label}: close it first (doc_close — its unsaved changes are the person's call), then accept again.")
    if os.path.isfile(target):
        backup = path("replaced", f"{stamp()}-{os.path.basename(target)}")
        os.makedirs(os.path.dirname(backup), exist_ok=True)
        shutil.copy2(target, backup)
    else:
        backup = None
    m = dict(nd.Meta or {})
    m.pop(RECOVERED_FOR, None)
    nd.Meta = m
    nd.saveAs(target)
    nd.Label = info.get("label") or nd.Label
    return nd, {"saved": target, "document": nd.Name, **({"previousFile": backup} if backup else {}),
                "note": "The recovered copy is now the file; what was there before is kept at previousFile."}


# ---- what a hidden FreeCAD holds, for after a crash ----------------------------------------

def write_hidden():
    """~/AgentLink/hidden.json: the documents this hidden FreeCAD holds, for
    the one that starts it again after a crash to recover (app_recover)."""
    import FreeCAD

    _save(path("hidden.json"), {"pid": os.getpid(), "t": time.time(),
                                "docs": [{"name": d.Name, "label": d.Label, "file": d.FileName or ""} for d in FreeCAD.listDocuments().values()]})


# ---- documents reopened from copies after a restart ----------------------------------------

def reopen_file():
    return path("reopen.json")


def keep_for_reopen(docs):
    """Before FreeCAD quits to start again: each document that is not being
    saved copied to its auto-save folder, to reopen beside its file when
    FreeCAD is back. [{ name, label, file, copy, t }]"""
    out = []
    for d in docs:
        f = autosave.copy_now(d)
        out.append({"name": d.Name, "label": d.Label, "file": d.FileName or "", "copy": f, "t": time.time()})
    if out:
        _save(reopen_file(), {"t": time.time(), "docs": out})
    return out


def reopen_pending(now=None):
    """The copies to reopen, once: the list is taken away as it is read; a
    stale one is dropped."""
    m = _load(reopen_file(), None)
    try:
        os.remove(reopen_file())
    except OSError:
        pass
    if not isinstance(m, dict) or (now or time.time()) - float(m.get("t") or 0) > REOPEN_LIMIT:
        return []
    return [c for c in m.get("docs") or [] if isinstance(c, dict)]


def reopen_now():
    """Open each pending copy beside its file. The labels opened."""
    opened = []
    for c in reopen_pending():
        try:
            if os.path.isfile(c.get("copy", "")):
                nd = open_copy(c["copy"], c.get("name") or "doc", c.get("label") or c.get("name") or "doc", float(c.get("t") or time.time()))
                opened.append(nd.Label)
        except Exception as e:  # noqa: BLE001
            try:
                import FreeCAD

                FreeCAD.Console.PrintWarning(f"SafetyNet: could not reopen {c.get('label')} from its copy: {e}\n")
            except Exception:
                pass
    return opened


class Reopen:
    """What SafetyNet offers Agent Link as its "reopen" service."""

    keep = staticmethod(keep_for_reopen)
    pending = staticmethod(reopen_pending)
    now = staticmethod(reopen_now)


# ---- FreeCAD's own auto-recovery ------------------------------------------------------------

def autosave_on():
    """FreeCAD's own recovery copies stay on: turned on once if they are off,
    and the change logged."""
    try:
        import FreeCAD

        al = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/AgentLink")
        if al.GetBool("AutoRecoveryChecked", False):
            return False
        g = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Document")
        changed = False
        if not g.GetBool("AutoSaveEnabled", True):
            g.SetBool("AutoSaveEnabled", True)
            settings.settings_log({"tool": "safetynet", "path": "BaseApp/Preferences/Document", "name": "AutoSaveEnabled", "from": False, "to": True, "restart": False,
                                   "why": "FreeCAD's own recovery copies kept on for unattended use"})
            changed = True
        al.SetBool("AutoRecoveryChecked", True)
        return changed
    except Exception:
        return False
