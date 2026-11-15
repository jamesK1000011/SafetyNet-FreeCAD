# SPDX-License-Identifier: LGPL-2.1-or-later
"""SafetyNet for FreeCAD: the work kept safe with no one at the computer.

Checkpoints as saved copies of a document, auto-save copies, documents back
after a crash, FreeCAD's settings logged and rolled back, and macros run
only once the person approved them. Plain FreeCAD: nothing here imports
Agent Link; its agentlink_families module (and the fam_* modules it loads)
offer these to an agent when Agent Link for FreeCAD is installed.

Everything is kept under ~/AgentLink (or $AGENTLINK_HOME), the same files
and formats Agent Link kept before SafetyNet was split out of it.
"""

VERSION = "0.1.0"

# Set by agentlink_families._register(), which only Agent Link ever imports:
# True when Agent Link hosts SafetyNet's Session panel (and runs its calls).
_hosted = False
