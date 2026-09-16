"""Capability-based agent routing for plan step execution.

An ``AgentRouter`` maps required capabilities to registered agents.  It
enables deterministic, provider-independent agent selection without LLM
calls.

Terminology:

- **capability**: a string tag an agent declares it can handle.
- **required capabilities**: the set of capabilities a ``PlanStep`` needs.
- **selection**: the process of choosing a single agent whose capabilities
  cover the required set.
"""

import logging
from collections.abc import Iterable

from app.agents.base import Agent

logger = logging.getLogger(__name__)


class AgentRoutingError(Exception):
    """Base exception for agent routing failures."""


class UnknownCapabilityError(AgentRoutingError):
    """Raised when a required capability is not declared by any agent."""

    def __init__(self, capability: str) -> None:
        self.capability = capability
        super().__init__(
            f"No agent registered with capability '{capability}'"
        )


class NoMatchingAgentError(AgentRoutingError):
    """Raised when no single agent covers all required capabilities."""

    def __init__(self, required: frozenset[str]) -> None:
        self.required = required
        super().__init__(
            f"No agent matches capabilities {sorted(required)}"
        )


class AgentSelection:
    """Describes which agent was selected for a given plan step.

    ``step_id`` identifies the step; ``agent_name`` identifies the agent
    chosen through capability matching.
    """

    __slots__ = ("step_id", "required_capabilities", "agent_name")

    def __init__(
        self,
        step_id: object,
        required_capabilities: frozenset[str],
        agent_name: str,
    ) -> None:
        self.step_id = step_id
        self.required_capabilities = required_capabilities
        self.agent_name = agent_name

    def __repr__(self) -> str:
        return (
            f"AgentSelection(step_id={self.step_id!r}, "
            f"required_capabilities={self.required_capabilities!r}, "
            f"agent_name={self.agent_name!r})"
        )


class AgentRouter:
    """Deterministic, capability-based agent router.

    Agents are registered by name (unique).  Selection finds all agents
    whose declared capabilities are a superset of the required set and
    picks the first by deterministic (alphabetical) name order.

    Parameters
    ----------
    agents : iterable of Agent, optional
        Initial agents to register.
    """

    def __init__(self, agents: Iterable[Agent] | None = None) -> None:
        self._agents: dict[str, Agent] = {}
        for agent in agents or ():
            self.register(agent)

    def register(self, agent: Agent) -> None:
        if agent.name in self._agents:
            raise ValueError(
                f"Agent '{agent.name}' is already registered"
            )
        self._agents[agent.name] = agent
        logger.info("AgentRouter registered agent '%s'", agent.name)

    def agents(self) -> tuple[Agent, ...]:
        return tuple(self._agents.values())

    def agent_names(self) -> tuple[str, ...]:
        return tuple(self._agents)

    def all_capabilities(self) -> frozenset[str]:
        """Union of every capability declared by registered agents."""
        caps: set[str] = set()
        for agent in self._agents.values():
            caps |= agent.capabilities
        return frozenset(caps)

    def has_capability(self, capability: str) -> bool:
        """Return True when at least one agent declares ``capability``."""
        return any(
            capability in agent.capabilities
            for agent in self._agents.values()
        )

    def select(self, required_capabilities: frozenset[str]) -> Agent:
        """Select an agent whose capabilities cover the required set.

        When ``required_capabilities`` is empty any agent is acceptable; the
        first registered (alphabetical name order) is returned.

        Raises
        ------
        UnknownCapabilityError
            If a required capability is not declared by *any* agent.
        NoMatchingAgentError
            If no single agent covers all required capabilities.
        """
        if required_capabilities:
            for capability in required_capabilities:
                if not self.has_capability(capability):
                    raise UnknownCapabilityError(capability)

        candidates: list[Agent] = []
        for agent in self._agents.values():
            if required_capabilities <= agent.capabilities:
                candidates.append(agent)

        if not candidates:
            raise NoMatchingAgentError(required_capabilities)

        candidates.sort(key=lambda a: a.name)
        selected = candidates[0]
        logger.info(
            "AgentRouter selected agent '%s' for capabilities %s",
            selected.name,
            sorted(required_capabilities) if required_capabilities else "(any)",
        )
        return selected

    def select_for_step(
        self, step_id: object, required_capabilities: frozenset[str]
    ) -> AgentSelection:
        """Select an agent and return a typed ``AgentSelection``."""
        agent = self.select(required_capabilities)
        return AgentSelection(
            step_id=step_id,
            required_capabilities=required_capabilities,
            agent_name=agent.name,
        )
