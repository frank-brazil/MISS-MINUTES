"""System agent for system information and controlled system tasks.

This agent provides a safe, deterministic foundation for system-level work.
It does NOT control the computer, launch processes, access the filesystem, or
execute shell commands.  It reports system-level information only, and is
designed so that a future injection of approved system tools can extend its
capabilities safely.

Terminology:

- **system tool**: a future injected callable ``fn(task) -> AgentResult``
  that performs a controlled, approved system action.  This chunk does NOT
  supply one.
- **system information**: read-only platform metadata such as the Python
  version and platform name.
"""

import logging
import platform
import sys
from typing import ClassVar

from app.agents.base import Agent, AgentResult
from app.core.task import Task


class SystemAgent(Agent):
    """Agent specialised in system information and controlled system tasks.

    In this foundation phase the agent provides read-only system information.
    It never controls the computer, launches processes, or accesses the
    filesystem.  A future ``system_fn`` callable will extend it.
    """

    name: ClassVar[str] = "system"
    description: ClassVar[str] = "Provides system information and controlled system-level tasks."
    capabilities: ClassVar[frozenset[str]] = frozenset(
        {"system_information", "application_control", "system_tasks"}
    )

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    async def execute(self, task: Task) -> AgentResult:
        self._logger.info(
            "SystemAgent executing task %s: %s",
            task.task_id,
            task.description[:80],
        )

        info = {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
        }
        return AgentResult.ok(
            output=(
                f"System info for task '{task.description[:120]}': "
                f"Python {info['python']}, {info['platform']}, "
                f"machine={info['machine']}. "
                "In this foundation phase the agent provides read-only "
                "information only — no computer control is performed."
            )
        )
