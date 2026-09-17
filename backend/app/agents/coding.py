"""Coding agent for program analysis and code-related tasks.

This agent handles deterministic code analysis and reporting.  It does not
execute arbitrary shell commands, does not write to the filesystem, and does
not make network calls.  All behaviour is local and deterministic.

Terminology:

- **code analysis**: a structured review of the supplied task description,
  reported as an ``AgentResult``.
- **code_analysis capability**: the agent can analyse code-related tasks but
  currently operates in a safe, read-only, deterministic mode.
"""

import logging
from typing import ClassVar

from app.agents.base import Agent, AgentResult
from app.core.task import Task


class CodingAgent(Agent):
    """Agent specialised in coding and programming tasks.

    In this foundation phase the agent provides safe, deterministic behaviour:
    it analyses the task description and returns a structured result without
    executing any code or accessing the filesystem.
    """

    name: ClassVar[str] = "coding"
    description: ClassVar[str] = (
        "Handles coding, programming, and code analysis tasks in safe deterministic mode."
    )
    capabilities: ClassVar[frozenset[str]] = frozenset({"coding", "programming", "code_analysis"})

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    async def execute(self, task: Task) -> AgentResult:
        self._logger.info(
            "CodingAgent executing task %s: %s",
            task.task_id,
            task.description[:80],
        )

        description = task.description.strip()

        has_code_keywords = any(
            keyword in description.lower()
            for keyword in ("code", "function", "class", "import", "def ", "error", "bug")
        )

        if has_code_keywords:
            output = (
                f"Coding analysis completed for task '{description[:120]}'. "
                "The task appears to involve code. In this foundation phase "
                "the agent provides analysis only — no code is executed and "
                "the filesystem is not modified."
            )
        else:
            output = (
                f"Coding analysis completed for task '{description[:120]}'. "
                "No code-related keywords detected. In this foundation phase "
                "the agent provides analysis only — no code is executed and "
                "the filesystem is not modified."
            )

        return AgentResult.ok(output=output)
