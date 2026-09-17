"""Research agent for information gathering and evidence collection.

This agent accepts a task and uses an injected ``ResearchProvider`` to gather
evidence.  It never makes live web requests on its own: all network behaviour
comes from the provider supplied at construction time.

Terminology:

- **evidence**: structured information gathered from an external source,
  surfaced via ``ResearchResponse``.  The agent does not fabricate evidence.
- **query**: the search text derived from the task description.
"""

import logging
from typing import ClassVar

from app.agents.base import Agent, AgentResult
from app.core.task import Task
from app.research.base import (
    ResearchProvider,
    ResearchResponse,
    SearchRequest,
)


class ResearchAgent(Agent):
    """Agent specialised in research and evidence gathering.

    The agent requires a ``ResearchProvider`` at construction time.  When no
    provider is given it falls back to deterministic behaviour that reports the
    absence of a provider rather than making network calls.
    """

    name: ClassVar[str] = "research"
    description: ClassVar[str] = (
        "Gathers evidence and structured research results for a given task."
    )
    capabilities: ClassVar[frozenset[str]] = frozenset({"research", "web_search", "evidence"})

    def __init__(self, provider: ResearchProvider | None = None) -> None:
        self._provider = provider
        self._logger = logging.getLogger(__name__)

    @property
    def provider(self) -> ResearchProvider | None:
        return self._provider

    async def execute(self, task: Task) -> AgentResult:
        self._logger.info(
            "ResearchAgent executing task %s: %s",
            task.task_id,
            task.description[:80],
        )

        if self._provider is None:
            return AgentResult.ok(
                output=(
                    f"No research provider configured for task "
                    f"'{task.description[:120]}'. "
                    "Inject a ResearchProvider to enable evidence gathering."
                )
            )

        query = task.description.strip()
        request = SearchRequest(query=query)

        try:
            response: ResearchResponse = await self._provider.research(request)
        except Exception as exc:
            error_msg = f"Research provider raised: {type(exc).__name__}: {exc}"
            self._logger.error(error_msg)
            return AgentResult.fail(error=error_msg)

        if not response.success:
            return AgentResult.fail(error=response.error or "Research returned no success")

        source_count = response.result_count
        if source_count == 0:
            return AgentResult.ok(
                output=(
                    f"Research completed for task '{task.description[:120]}' with 0 sources found."
                )
            )

        titles = [r.source.title for r in response.results]
        return AgentResult.ok(
            output=(
                f"Research completed for task '{task.description[:120]}' "
                f"with {source_count} source(s): "
                f"{', '.join(titles[:5])}"
            )
        )
