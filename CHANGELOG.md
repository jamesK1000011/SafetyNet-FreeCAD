# Changelog

All notable changes to SafetyNet for FreeCAD. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

The first release, 0.1.0, is being prepared.

### Added

- SafetyNet split out of Agent Link for FreeCAD as its own add-on. It keeps
  checkpoints, auto-save copies, recovery after a crash or a hang, a log of
  FreeCAD's settings with rollback, and macros that run only once approved.
- Agent Link finds SafetyNet's tools when both are installed: the checkpoint
  tools in its core group, and the recovery, settings and macro tools in a
  safety group.
- Icons for the workbench and for Checkpoint, Restore and Recover, drawn in
  FreeCAD's style, with their credits and licence texts.
- The SafetyNet workbench, a Tools ▸ SafetyNet submenu in every workbench, and
  the Session panel as its own dock when Agent Link is not installed.
- Release preparation: a beginner's README with a generated tool list,
  complete Addon Manager metadata, licence headers checked for every file,
  how to uninstall, a privacy statement, and this changelog.
- The SafetyNet panel lists Recovered Copies once per original document,
  copies of copies included, says where each copy came from (FreeCAD
  autosave, SafetyNet autosave, My checkpoint or Agent checkpoint, by who
  took it), and folds closed documents over
  two hours old under Older. Its buttons work only on the kind of row picked,
  and SafetyNet's messages have a short bold first line. Opening a recovered
  copy rebuilds the shapes FreeCAD's autosave left empty and says why the
  Report view showed errors.
- Recovered Copies shows only open documents and a Last crash group; the
  rest is under a folded Older row. Old copies are cleaned up at start and
  at most once a day (the newest 3 a document, none past 7 days, never-saved
  documents' past 1 day), to the Trash, keeping open documents, the last
  crash, copies used this week and named checkpoints. Tools ▸ SafetyNet ▸
  Clean Up Copies… shows what would go and asks first.
- Macros build on FreeCAD's own: the list is FreeCAD's macro folder (.FCMacro
  and .py, as Macro ▸ Macros… shows it), and an approved macro runs as
  FreeCAD runs one, alone as well as with Agent Link. The approval list and
  the checkpoint before each run stay. The panel and the Macros command open
  FreeCAD's Macro dialog.
