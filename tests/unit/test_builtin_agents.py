import asyncio
import json

from app.agents.base import Agent, AgentResult
from app.agents.coding import CodingAgent
from app.agents.critic import CriticAgent
from app.agents.prediction import PredictionAgent
from app.agents.research import ResearchAgent
from app.agents.system import SystemAgent
from app.agents.verification import VerificationAgent
from app.agents.vision import VisionAgent
from app.core.critic import Critic
from app.core.prediction import (
    Predictor,
)
from app.core.task import Task
from app.core.verification import (
    Verifier,
)
from app.research.base import (
    ResearchProvider,
    ResearchResponse,
    SearchRequest,
    SearchResult,
    Source,
)


def _task(description: str = "some task") -> Task:
    return Task(description=description)


def _run(awaitable):
    return asyncio.run(awaitable)


# ---------------------------------------------------------------------------
# Shared agent contract helpers
# ---------------------------------------------------------------------------


def _assert_success(result: AgentResult) -> None:
    assert isinstance(result, AgentResult)
    assert result.success is True
    assert result.error is None
    assert result.output


# ---------------------------------------------------------------------------
# ResearchAgent
# ---------------------------------------------------------------------------


class FixedResearchProvider(ResearchProvider):
    name = "fixed-research"
    description = "Returns a fixed set of sources."

    async def research(self, request: SearchRequest) -> ResearchResponse:
        source = Source(title="Example Report", url="https://example.com")
        return ResearchResponse.ok(
            query=request.query,
            results=[SearchResult(source=source, rank=1, score=0.9)],
        )


class FailingResearchProvider(ResearchProvider):
    name = "failing-research"
    description = "Always fails."

    async def research(self, request: SearchRequest) -> ResearchResponse:
        return ResearchResponse.fail(query=request.query, error="simulated provider failure")


class RaisingResearchProvider(ResearchProvider):
    name = "raising-research"
    description = "Raises an exception."

    async def research(self, request: SearchRequest) -> ResearchResponse:
        raise RuntimeError("research exploded")


def test_research_agent_metadata() -> None:
    assert ResearchAgent.name == "research"
    assert ResearchAgent.description
    assert ResearchAgent.capabilities == frozenset({"research", "web_search", "evidence"})


def test_research_agent_is_an_agent() -> None:
    assert issubclass(ResearchAgent, Agent)
    agent = ResearchAgent()
    assert isinstance(agent, Agent)


def test_research_agent_without_provider_succeeds_deterministically() -> None:
    result = _run(ResearchAgent().execute(_task("research cat food")))
    _assert_success(result)
    assert "no research provider configured" in result.output.lower()


def test_research_agent_with_provider_returns_sources() -> None:
    agent = ResearchAgent(provider=FixedResearchProvider())
    result = _run(agent.execute(_task("research latest news")))
    _assert_success(result)
    assert "Example Report" in result.output
    assert "1 source" in result.output


def test_research_agent_injects_provider() -> None:
    provider = FixedResearchProvider()
    agent = ResearchAgent(provider=provider)
    assert agent.provider is provider


def test_research_agent_handles_failed_response() -> None:
    agent = ResearchAgent(provider=FailingResearchProvider())
    result = _run(agent.execute(_task("research something")))
    assert result.success is False
    assert result.error == "simulated provider failure"


def test_research_agent_handles_raised_error() -> None:
    agent = ResearchAgent(provider=RaisingResearchProvider())
    result = _run(agent.execute(_task("research something")))
    assert result.success is False
    assert "research exploded" in result.error


def test_research_agent_empty_results() -> None:
    class EmptyProvider(ResearchProvider):
        name = "empty-research"
        description = "Returns no sources."

        async def research(self, request: SearchRequest) -> ResearchResponse:
            return ResearchResponse.ok(query=request.query, results=[])

    result = _run(ResearchAgent(provider=EmptyProvider()).execute(_task("x")))
    _assert_success(result)
    assert "0 source" in result.output


# ---------------------------------------------------------------------------
# CodingAgent
# ---------------------------------------------------------------------------


def test_coding_agent_metadata() -> None:
    assert CodingAgent.name == "coding"
    assert CodingAgent.description
    assert CodingAgent.capabilities == frozenset({"coding", "programming", "code_analysis"})


def test_coding_agent_successful_execution() -> None:
    result = _run(CodingAgent().execute(_task("fix the bug in main.py")))
    _assert_success(result)
    assert "code" in result.output.lower()


def test_coding_agent_deterministic() -> None:
    first = _run(CodingAgent().execute(_task("write a function")))
    second = _run(CodingAgent().execute(_task("write a function")))
    assert first.output == second.output


def test_coding_agent_does_not_run_shell() -> None:
    import sys

    module = sys.modules[CodingAgent.__module__]
    with open(module.__file__, encoding="utf-8") as handle:
        content = handle.read()
    assert "subprocess" not in content
    assert "os.system" not in content
    assert "exec(" not in content


# ---------------------------------------------------------------------------
# VisionAgent
# ---------------------------------------------------------------------------


def test_vision_agent_metadata() -> None:
    assert VisionAgent.name == "vision"
    assert VisionAgent.description
    assert VisionAgent.capabilities == frozenset(
        {"vision", "image_analysis", "screen_understanding"}
    )


def test_vision_agent_without_injection_succeeds() -> None:
    result = _run(VisionAgent().execute(_task("describe this screenshot")))
    _assert_success(result)
    assert "no vision provider" in result.output.lower()


def test_vision_agent_with_injected_callable() -> None:
    async def fake_vision(task: Task) -> AgentResult:
        return AgentResult.ok(output=f"vision processed '{task.description}'")

    agent = VisionAgent(vision_fn=fake_vision)
    result = _run(agent.execute(_task("look at image")))
    _assert_success(result)
    assert "vision processed 'look at image'" == result.output


def test_vision_agent_preserves_injected_callable() -> None:
    async def fake_vision(task: Task) -> AgentResult:
        return AgentResult.ok()

    agent = VisionAgent(vision_fn=fake_vision)
    assert agent.vision_fn is fake_vision


# ---------------------------------------------------------------------------
# PredictionAgent (dependency injection)
# ---------------------------------------------------------------------------


def test_prediction_agent_metadata() -> None:
    assert PredictionAgent.name == "prediction"
    assert PredictionAgent.description
    assert PredictionAgent.capabilities == frozenset(
        {"prediction", "decision_analysis", "risk_analysis"}
    )


def test_prediction_agent_without_predictor_succeeds() -> None:
    result = _run(PredictionAgent().execute(_task("predict outcome")))
    _assert_success(result)
    assert "no predictor configured" in result.output.lower()


def test_prediction_agent_with_fake_predictor() -> None:
    from app.core.prediction import FakePredictor

    agent = PredictionAgent(predictor=FakePredictor())
    result = _run(agent.execute(_task("will the service be fast?")))
    _assert_success(result)
    summary = json.loads(result.output)
    assert summary["predictions_count"] >= 1
    assert summary["options_count"] >= 1
    assert summary["has_recommendation"] is True
    assert 0.0 <= summary["confidence"] <= 1.0


def test_prediction_agent_injects_predictor() -> None:
    from app.core.prediction import FakePredictor

    predictor = FakePredictor()
    assert isinstance(predictor, Predictor)
    agent = PredictionAgent(predictor=predictor)
    assert agent.predictor is predictor


def test_prediction_agent_handles_predictor_error() -> None:
    from app.core.prediction import FakePredictor

    predictor = FakePredictor(raise_error=RuntimeError("predictor down"))
    result = _run(PredictionAgent(predictor=predictor).execute(_task("predict")))
    assert result.success is False
    assert "predictor down" in result.error


# ---------------------------------------------------------------------------
# CriticAgent (dependency injection)
# ---------------------------------------------------------------------------


def test_critic_agent_metadata() -> None:
    assert CriticAgent.name == "critic"
    assert CriticAgent.description
    assert CriticAgent.capabilities == frozenset({"critique", "risk_review", "quality_review"})


def test_critic_agent_without_critic_succeeds() -> None:
    result = _run(CriticAgent().execute(_task("review this plan")))
    _assert_success(result)
    assert "no critic configured" in result.output.lower()


def test_critic_agent_with_fake_critic() -> None:
    from app.core.critic import FakeCritic

    agent = CriticAgent(critic=FakeCritic())
    result = _run(agent.execute(_task("review this solution")))
    _assert_success(result)
    summary = json.loads(result.output)
    assert summary["points_count"] >= 4
    assert summary["overall_severity"] == "medium"
    assert summary["has_weaknesses"] is True
    assert summary["has_risks"] is True
    assert 0.0 <= summary["confidence"] <= 1.0


def test_critic_agent_injects_critic() -> None:
    from app.core.critic import FakeCritic

    critic = FakeCritic()
    assert isinstance(critic, Critic)
    agent = CriticAgent(critic=critic)
    assert agent.critic is critic


def test_critic_agent_handles_critic_error() -> None:
    from app.core.critic import FakeCritic

    critic = FakeCritic(raise_error=RuntimeError("critic down"))
    result = _run(CriticAgent(critic=critic).execute(_task("review")))
    assert result.success is False
    assert "critic down" in result.error


# ---------------------------------------------------------------------------
# VerificationAgent (dependency injection)
# ---------------------------------------------------------------------------


def test_verification_agent_metadata() -> None:
    assert VerificationAgent.name == "verification"
    assert VerificationAgent.description
    assert VerificationAgent.capabilities == frozenset(
        {"verification", "validation", "result_checking"}
    )


def test_verification_agent_without_verifier_succeeds() -> None:
    result = _run(VerificationAgent().execute(_task("verify result")))
    _assert_success(result)
    assert "no verifier configured" in result.output.lower()


def test_verification_agent_with_fake_verifier() -> None:
    from app.core.verification import FakeVerifier

    agent = VerificationAgent(verifier=FakeVerifier())
    result = _run(agent.execute(_task("the service responds with HTTP 200")))
    _assert_success(result)
    summary = json.loads(result.output)
    assert summary["status"] in {
        "verified",
        "failed",
        "inconclusive",
        "not_run",
    }
    assert "result_id" in summary


def test_verification_agent_injects_verifier() -> None:
    from app.core.verification import FakeVerifier

    verifier = FakeVerifier()
    assert isinstance(verifier, Verifier)
    agent = VerificationAgent(verifier=verifier)
    assert agent.verifier is verifier


def test_verification_agent_handles_verifier_error() -> None:
    from app.core.verification import FakeVerifier

    verifier = FakeVerifier(raise_error=RuntimeError("verifier down"))
    result = _run(VerificationAgent(verifier=verifier).execute(_task("verify")))
    assert result.success is False
    assert "verifier down" in result.error


# ---------------------------------------------------------------------------
# SystemAgent
# ---------------------------------------------------------------------------


def test_system_agent_metadata() -> None:
    assert SystemAgent.name == "system"
    assert SystemAgent.description
    assert SystemAgent.capabilities == frozenset(
        {"system_information", "application_control", "system_tasks"}
    )


def test_system_agent_successful_execution() -> None:
    result = _run(SystemAgent().execute(_task("check system status")))
    _assert_success(result)
    assert "python" in result.output.lower()
    assert "no computer control" in result.output.lower()


def test_system_agent_does_not_control_computer() -> None:
    import sys

    module = sys.modules[SystemAgent.__module__]
    with open(module.__file__, encoding="utf-8") as handle:
        content = handle.read()
    assert "subprocess" not in content
    assert "os.system" not in content
    assert "exec(" not in content
    assert "open(" not in content


# ---------------------------------------------------------------------------
# Cross-agent contract
# ---------------------------------------------------------------------------


def test_all_builtin_agents_satisfy_agent_contract() -> None:
    agents = [
        ResearchAgent(),
        CodingAgent(),
        VisionAgent(),
        PredictionAgent(),
        CriticAgent(),
        VerificationAgent(),
        SystemAgent(),
    ]
    names = {agent.name for agent in agents}
    assert names == {
        "research",
        "coding",
        "vision",
        "prediction",
        "critic",
        "verification",
        "system",
    }
    for agent in agents:
        assert agent.description
        assert agent.capabilities
        result = _run(agent.execute(_task("a generic task")))
        assert isinstance(result, AgentResult)
        assert result.output


def test_agents_importable_from_package() -> None:
    from app.agents import (  # noqa: F401
        CodingAgent,
        CriticAgent,
        PredictionAgent,
        ResearchAgent,
        SystemAgent,
        VerificationAgent,
        VisionAgent,
    )

    assert True


def test_agent_module_has_no_network_dependencies() -> None:
    forbidden = ("httpx", "import requests", "openai", "aiohttp", "urllib3")
    import sys

    for module_name in (
        "app.agents.research",
        "app.agents.coding",
        "app.agents.vision",
        "app.agents.prediction",
        "app.agents.critic",
        "app.agents.verification",
        "app.agents.system",
    ):
        module = sys.modules[module_name]
        with open(module.__file__, encoding="utf-8") as handle:
            content = handle.read()
        for line in content.splitlines():
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            for token in forbidden:
                assert token not in line, f"{module_name} imports {token}"
