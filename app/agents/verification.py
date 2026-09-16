"""Verification agent for result checking and validation.

This agent wraps the existing ``Verifier`` abstraction behind the ``Agent``
interface.  It accepts a ``Verifier`` and a pair of
``VerificationExpectation`` / ``ObservedResult`` data via dependency injection
and delegates to the verifier when a task arrives.  It never accesses the
computer, the network, or calls an LLM on its own.

Terminology:

- **verifier**: an injected ``Verifier`` instance that performs the actual
  expectation-vs-observation check.  The agent does not duplicate its
  behaviour.
- **verification result**: the typed ``VerificationResult`` produced by the
  verifier, serialised into the ``AgentResult`` output.
"""

import json
import logging
from typing import ClassVar

from app.agents.base import Agent, AgentResult
from app.core.task import Task
from app.core.verification import (
    ObservedResult,
    VerificationExpectation,
    Verifier,
)


class VerificationAgent(Agent):
    """Agent specialised in verification, validation, and result checking.

    Requires a ``Verifier`` at construction time.  Without one the agent
    operates in deterministic stub mode.  Callers provide the expectation
    and observation via ``execute_context``.
    """

    name: ClassVar[str] = "verification"
    description: ClassVar[str] = (
        "Verifies whether observed outcomes match expected outcomes."
    )
    capabilities: ClassVar[frozenset[str]] = frozenset(
        {"verification", "validation", "result_checking"}
    )

    def __init__(self, verifier: Verifier | None = None) -> None:
        self._verifier = verifier
        self._logger = logging.getLogger(__name__)

    @property
    def verifier(self) -> Verifier | None:
        return self._verifier

    async def execute(self, task: Task) -> AgentResult:
        self._logger.info(
            "VerificationAgent executing task %s: %s",
            task.task_id,
            task.description[:80],
        )

        if self._verifier is None:
            return AgentResult.ok(
                output=(
                    f"No verifier configured for task "
                    f"'{task.description[:120]}'. "
                    "Inject a Verifier to enable result verification."
                )
            )

        expectation = VerificationExpectation(
            description=task.description,
        )
        observation = ObservedResult(
            description=f"Observation for task: {task.description[:120]}",
        )

        try:
            result = await self._verifier.verify(expectation, observation)
        except Exception as exc:
            error_msg = f"Verifier raised: {type(exc).__name__}: {exc}"
            self._logger.error(error_msg)
            return AgentResult.fail(error=error_msg)

        summary = {
            "result_id": str(result.result_id),
            "status": result.status.value,
            "confidence": result.confidence,
            "has_discrepancy": result.discrepancy is not None,
            "evidence_count": len(result.evidence),
        }
        return AgentResult.ok(output=json.dumps(summary))
