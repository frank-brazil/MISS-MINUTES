"""Minimal permission boundary for computer-interaction tools.

This module establishes the *seam* only.  Full security/permission management
(allow/deny rules, approval flows, policy evaluation) is intentionally left
for a later chunk.  Tools declare the permission category they require so
future authorization work does not require rewriting every tool.
"""

from enum import StrEnum


class ToolPermission(StrEnum):
    """Permission category a computer-interaction tool requires.

    - ``READ``: reads information from the local machine (files, system).
    - ``WRITE``: modifies local state (creates/edits files, saves artifacts).
    - ``SYSTEM``: accesses system-level facilities (processes, terminals,
      low-level system information).
    """

    READ = "read"
    WRITE = "write"
    SYSTEM = "system"
