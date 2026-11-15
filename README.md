<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# SafetyNet for FreeCAD

> Not affiliated with or endorsed by the FreeCAD project or the FPA; FreeCAD is the FPA's trademark. Get FreeCAD itself from [freecad.org](https://freecad.org).

The work kept safe with no one at the computer:

- **Checkpoints** as saved copies of a document, to come back to past FreeCAD's undo stack and across restarts (`safetynet.checkpoints`).
- **Auto-save** copies every 5 minutes or 10 changes, the newest 5 kept (`safetynet.autosave`); FreeCAD's own AutoSave kept on.
- **Recovery** after a crash, a hang or a restart: the newest copy that opens, beside the person's file, saved over it only with their typed say-so (`safetynet.recovery`).
- **Settings**: a snapshot of FreeCAD's settings file before each change, a change log, and rollback (`safetynet.settings`).
- **Macros** of an agent's steps, run only once the person approved them; changed code needs approving again (`safetynet.macros`).

Everything is kept under `~/AgentLink` (or `$AGENTLINK_HOME`): `checkpoints/`, `autosave/`, `settings/`, `settings-log.jsonl`, `macros-approved.json`, `hidden.json`, `reopen.json`.

## In the FreeCAD window

The **SafetyNet** workbench, and a **Tools ▸ SafetyNet** submenu in every workbench, so recovery is reachable from whatever bench you are in:

- **Checkpoint now**, **Restore checkpoint…**
- **Recovered copies…**: the newest good copy opened beside its file; saved over it only once you type the confirm.
- **Settings history…**, **Roll back setting…**: on its own, SafetyNet reads the snapshot into the running FreeCAD (a setting read only at start applies when FreeCAD next opens); with Agent Link, FreeCAD restarts around the file.
- **Macros…**: show, approve (you type the confirm), take the approval back.
- **Panel**: the Session panel. With Agent Link it is the Session tab in Agent Link's panel; without it, SafetyNet's own dock beside the model tree.

Each command runs the same code an agent's tool does (`safetynet/handlers.py`), as one undo step, with no agent needed. Panels take their accent colours from FreeCAD's theme (`safetynet/theme.py`) and style only SafetyNet's own widgets.

## With Agent Link for FreeCAD

When [Agent Link for FreeCAD](https://github.com/jamesK1000011/AgentLink-FreeCAD) is installed, it finds `safetynet/agentlink_families.py` and offers an agent these tools:

| Tool | Group | What it does |
|---|---|---|
| `history_checkpoint` | core | Save a copy of the document now; list them. |
| `history_restore` | core | Back to a checkpoint, by undo or from its copy. |
| `app_recover` | safety | Documents back after a crash or a hang. |
| `pref_history` / `pref_rollback` | safety | FreeCAD's settings changes, and putting them back. |
| `macro_save` / `macro_list` / `macro_show` / `macro_approve` / `macro_unapprove` / `macro_run` | safety | Macros of the agent's steps, run once the person approved them. |

It also adds the Session tab to Agent Link's panel, auto-saves after the agent's changes, gives `history_diff { since: "cp3" }` its checkpoints, and reopens unsaved documents from copies after `app_restart`. Without SafetyNet, Agent Link has FreeCAD's undo only.

SafetyNet's own modules never import Agent Link; only `agentlink_families.py` and the `fam_*` modules it loads do.

## Licence

LGPL-2.1-or-later (`LICENSE`). Split out of Agent Link for FreeCAD, under the same licence.

## Icons

Icons adapted from Tabler Icons (MIT, tabler.io) and Pictogrammers Material Design Icons (Apache-2.0, pictogrammers.com). FreeCAD's own icons are used by name from FreeCAD. See `safetynet/icons/CREDITS.md`.
