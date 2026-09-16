import pytest

from app.agents.base import Agent, AgentResult
from app.core.routing import (
    AgentRouter,
    AgentRoutingError,
    AgentSelection,
    NoMatchingAgentError,
    UnknownCapabilityError,
)
from app.core.task import Task


class AlphaAgent(Agent):
    name = "alpha"
    description = "Alpha agent."
    capabilities = frozenset({"alpha-cap", "shared-cap"})

    async def execute(self, task: Task) -> AgentResult:
        return AgentResult.ok(output="alpha")


class BetaAgent(Agent):
    name = "beta"
    description = "Beta agent."
    capabilities = frozenset({"beta-cap", "shared-cap"})

    async def execute(self, task: Task) -> AgentResult:
        return AgentResult.ok(output="beta")


class GammaAgent(Agent):
    name = "gamma"
    description = "Gamma agent with broad capabilities."
    capabilities = frozenset({"alpha-cap", "beta-cap", "gamma-cap", "shared-cap"})

    async def execute(self, task: Task) -> AgentResult:
        return AgentResult.ok(output="gamma")


# --- AgentRouter creation ---


def test_empty_router() -> None:
    router = AgentRouter()
    assert router.agents() == ()
    assert router.agent_names() == ()
    assert router.all_capabilities() == frozenset()


def test_router_with_initial_agents() -> None:
    router = AgentRouter(agents=[AlphaAgent(), BetaAgent()])
    assert len(router.agents()) == 2
    assert set(router.agent_names()) == {"alpha", "beta"}


def test_register_agent() -> None:
    router = AgentRouter()
    router.register(AlphaAgent())
    assert router.agent_names() == ("alpha",)


def test_duplicate_agent_rejected() -> None:
    router = AgentRouter()
    router.register(AlphaAgent())
    with pytest.raises(ValueError, match="already registered"):
        router.register(AlphaAgent())


# --- Capabilities ---


def test_all_capabilities_union() -> None:
    router = AgentRouter(agents=[AlphaAgent(), BetaAgent()])
    caps = router.all_capabilities()
    assert caps == frozenset({"alpha-cap", "beta-cap", "shared-cap"})


def test_has_capability_true() -> None:
    router = AgentRouter(agents=[AlphaAgent()])
    assert router.has_capability("alpha-cap") is True
    assert router.has_capability("shared-cap") is True


def test_has_capability_false() -> None:
    router = AgentRouter(agents=[AlphaAgent()])
    assert router.has_capability("beta-cap") is False


def test_has_capability_empty_router() -> None:
    router = AgentRouter()
    assert router.has_capability("anything") is False


# --- Selection ---


def test_select_with_empty_requirements() -> None:
    router = AgentRouter(agents=[AlphaAgent(), BetaAgent()])
    agent = router.select(frozenset())
    assert agent.name == "alpha"


def test_select_exact_match() -> None:
    router = AgentRouter(agents=[AlphaAgent(), BetaAgent()])
    agent = router.select(frozenset({"alpha-cap"}))
    assert agent.name == "alpha"


def test_select_broad_agent_selected() -> None:
    router = AgentRouter(agents=[AlphaAgent(), BetaAgent(), GammaAgent()])
    agent = router.select(frozenset({"alpha-cap"}))
    assert agent.name == "alpha"


def test_select_multiple_requirements() -> None:
    router = AgentRouter(agents=[AlphaAgent(), BetaAgent(), GammaAgent()])
    agent = router.select(frozenset({"alpha-cap", "beta-cap"}))
    assert agent.name == "gamma"


def test_select_deterministic_alphabetical_order() -> None:
    router = AgentRouter(agents=[BetaAgent(), AlphaAgent()])
    agent = router.select(frozenset({"shared-cap"}))
    assert agent.name == "alpha"


def test_unknown_capability_error() -> None:
    router = AgentRouter(agents=[AlphaAgent()])
    with pytest.raises(UnknownCapabilityError) as exc_info:
        router.select(frozenset({"unknown-cap"}))
    assert exc_info.value.capability == "unknown-cap"
    assert "unknown-cap" in str(exc_info.value)


def test_no_matching_agent_error() -> None:
    router = AgentRouter(agents=[AlphaAgent(), BetaAgent()])
    with pytest.raises(NoMatchingAgentError) as exc_info:
        router.select(frozenset({"alpha-cap", "beta-cap"}))
    assert exc_info.value.required == frozenset({"alpha-cap", "beta-cap"})
    assert "alpha-cap" in str(exc_info.value)


def test_no_matching_agent_empty_router() -> None:
    router = AgentRouter()
    with pytest.raises(NoMatchingAgentError):
        router.select(frozenset())


# --- Selection results ---


def test_select_for_step() -> None:
    router = AgentRouter(agents=[AlphaAgent()])
    selection = router.select_for_step(step_id="s1", required_capabilities=frozenset({"alpha-cap"}))
    assert isinstance(selection, AgentSelection)
    assert selection.step_id == "s1"
    assert selection.agent_name == "alpha"
    assert selection.required_capabilities == frozenset({"alpha-cap"})


def test_agent_selection_repr() -> None:
    sel = AgentSelection(
        step_id="x",
        required_capabilities=frozenset({"c1"}),
        agent_name="agent1",
    )
    r = repr(sel)
    assert "x" in r
    assert "c1" in r
    assert "agent1" in r


# --- Error hierarchy ---


def test_routing_errors_are_exception_subclasses() -> None:
    assert issubclass(AgentRoutingError, Exception)
    assert issubclass(UnknownCapabilityError, AgentRoutingError)
    assert issubclass(NoMatchingAgentError, AgentRoutingError)


# --- Provider independence ---


def test_routing_provider_independence() -> None:
    assert "fastapi" not in AgentRouter.__module__
    assert AgentRouter.__module__ == "app.core.routing"
