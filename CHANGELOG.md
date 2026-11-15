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
