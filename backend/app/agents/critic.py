"""Critic agent for solution review and quality assessment.

This agent wraps the existing ``Critic`` abstraction behind the ``Agent``
interface.  It accepts a ``Critic`` via dependency injection and delegates
to it when a task arrives.  It never calls an LLM or makes network requests
on its own.

Terminology:

- **critic**: an injected ``Critic`` instance that performs the actual
  solution review.  The agent does not duplicate its behaviour.
- **critique**: the typed ``Critique`` produced by the critic, serialised
  into the ``AgentResult`` output.
"""

import json
import logging
from typing import ClassVar

from app.agents.base import Agent, AgentResult
from app.core.critic import Critic, CritiqueRequest
from app.core.task import Task


class CriticAgent(Agent):
    """Agent specialised in critique, risk review, and quality assessment.

    Requires a ``Critic`` at construction time.  Without one the agent
    operates in deterministic stub mode.
    """

    name: ClassVar[str] = "critic"
    description: ClassVar[str] = (
        "Reviews proposed solutions for weaknesses, risks, and quality issues."
    )
    capabilities: ClassVar[frozenset[str]] = frozenset(
        {"critique", "risk_review", "quality_review"}
    )

    def __init__(self, critic: Critic | None = None) -> None:
        self._critic = critic
        self._logger = logging.getLogger(__name__)

    @property
    def critic(self) -> Critic | None:
        return self._critic

    async def execute(self, task: Task) -> AgentResult:
        self._logger.info(
            "CriticAgent executing task %s: %s",
            task.task_id,
            task.description[:80],
        )

        if self._critic is None:
            return AgentResult.ok(
                output=(
                    f"No critic configured for task "
                    f"'{task.description[:120]}'. "
                    "Inject a Critic to enable solution review."
                )
            )

        request = CritiqueRequest(target=task.description)

        try:
            critique = await self._critic.critique(request)
        except Exception as exc:
            error_msg = f"Critic raised: {type(exc).__name__}: {exc}"
            self._logger.error(error_msg)
            return AgentResult.fail(error=error_msg)

        summary = {
            "critique_id": str(critique.critique_id),
            "points_count": len(critique.points),
            "overall_severity": critique.overall_severity.value,
            "confidence": critique.confidence,
            "has_weaknesses": len(critique.weaknesses) > 0,
            "has_risks": len(critique.risks) > 0,
        }
        return AgentResult.ok(output=json.dumps(summary))
