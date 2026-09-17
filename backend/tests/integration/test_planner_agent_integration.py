"""Integration tests for the Planner → Router → Agent execution pipeline.

Verifies that:
1. Plans with capability-tagged steps are routed to correct agents.
2. Step results are collected on the orchestrator (last_plan / last_step_results).
3. Failure at any step stops the pipeline and raises PlanExecutionError.
4. Existing AI-loop and placeholder paths are not affected.
5. The /tasks API JSON shape remains {task_id, success, status, output, error}.
"""

import asyncio
from collections.abc import Sequence

import pytest
from app.agents.base import Agent, AgentResult
from app.api.app import create_app
from app.core.orchestrator import (
    Orchestrator,
    PlanExecutionError,
)
from app.core.planner import Plan, Planner, PlanStep
from app.core.task import Task, TaskStatus
from fastapi.testclient import TestClient
from pydantic import ValidationError

# ------------------------------------------------------------------
# Test doubles
# ------------------------------------------------------------------


class PlannerThatRaises(Planner):
    name = "failing-planner"
    description = "Always raises."

    async def plan(self, task: Task) -> Plan:
        raise RuntimeError("planner exploded")


class FakePlanner(Planner):
    name = "fake-planner"
    description = "Returns a canned plan."

    def __init__(
        self,
        descriptions: Sequence[str],
        capabilities: Sequence[frozenset[str]] = (),
    ) -> None:
        self._descriptions = list(descriptions)
        self._caps = list(capabilities)

    async def plan(self, task: Task) -> Plan:
        steps: list[PlanStep] = []
        for i, desc in enumerate(self._descriptions):
            cap = self._caps[i] if i < len(self._caps) else frozenset()
            steps.append(PlanStep(description=desc, required_capabilities=cap))
        return Plan(task_id=task.task_id, goal=task.description, steps=steps)


class ExecutingAgent(Agent):
    name = "executor"
    description = "Echo agent."
    capabilities = frozenset({"exec"})

    async def execute(self, task: Task) -> AgentResult:
        return AgentResult.ok(output=f"executed: {task.description}")


class FailingAgent(Agent):
    name = "failer"
    description = "Always fails."
    capabilities = frozenset({"fail"})

    async def execute(self, task: Task) -> AgentResult:
        return AgentResult.fail(error="intentional failure")


class RaisingAgent(Agent):
    name = "raiser"
    description = "Always raises an exception."
    capabilities = frozenset({"raise"})

    async def execute(self, task: Task) -> AgentResult:
        raise RuntimeError("agent exploded")


class AlphaCapAgent(Agent):
    name = "alpha-agent"
    description = "Handles alpha-cap."
    capabilities = frozenset({"alpha-cap"})

    async def execute(self, task: Task) -> AgentResult:
        return AgentResult.ok(output="alpha done")


class BetaCapAgent(Agent):
    name = "beta-agent"
    description = "Handles beta-cap."
    capabilities = frozenset({"beta-cap"})

    async def execute(self, task: Task) -> AgentResult:
        return AgentResult.ok(output="beta done")


class MultiCapAgent(Agent):
    name = "multi-agent"
    description = "Handles both alpha-cap and beta-cap."
    capabilities = frozenset({"alpha-cap", "beta-cap"})

    async def execute(self, task: Task) -> AgentResult:
        return AgentResult.ok(output="multi done")


# ------------------------------------------------------------------
# PlanStep required_capabilities
# ------------------------------------------------------------------


def test_plan_step_default_no_capabilities() -> None:
    step = PlanStep(description="basic step")
    assert step.required_capabilities == frozenset()


def test_plan_step_with_capabilities() -> None:
    step = PlanStep(description="cap step", required_capabilities={"c1", "c2"})
    assert step.required_capabilities == frozenset({"c1", "c2"})


def test_plan_step_blank_capability_rejected() -> None:
    with pytest.raises(ValidationError):
        PlanStep(description="bad", required_capabilities={""})


# ------------------------------------------------------------------
# Orchestrator properties
# ------------------------------------------------------------------


def test_orchestrator_planner_and_router_properties() -> None:
    planner = FakePlanner(["s1"])
    from app.core.routing import AgentRouter

    router = AgentRouter(agents=[ExecutingAgent()])
    orch = Orchestrator(planner=planner, agent_router=router)
    assert orch.planner is planner
    assert orch.agent_router is router


def test_orchestrator_default_router_is_empty() -> None:
    orch = Orchestrator()
    assert orch.agent_router.agents() == ()


def test_orchestrator_last_plan_initially_none() -> None:
    orch = Orchestrator()
    assert orch.last_plan is None
    assert orch.last_step_results == ()


# ------------------------------------------------------------------
# Plan-based execution path
# ------------------------------------------------------------------


def test_single_step_plan_executes_successfully() -> None:
    planner = FakePlanner(["do something"], [frozenset({"exec"})])
    orch = Orchestrator(planner=planner)
    orch.register_agent(ExecutingAgent())
    task = Task(description="single step task")
    result = asyncio.run(orch.execute(task))
    assert result.success is True
    assert result.status == TaskStatus.COMPLETED
    assert "1 step(s)" in result.output
    assert orch.last_plan is not None
    assert len(orch.last_step_results) == 1
    assert orch.last_step_results[0].success is True


def test_multi_step_plan_executes_in_order() -> None:
    planner = FakePlanner(
        ["step one", "step two", "step three"],
        [frozenset({"exec"})] * 3,
    )
    orch = Orchestrator(planner=planner)
    orch.register_agent(ExecutingAgent())
    task = Task(description="multi step")
    result = asyncio.run(orch.execute(task))
    assert result.success is True
    assert "3 step(s)" in result.output
    assert len(orch.last_step_results) == 3
    assert [r.description for r in orch.last_step_results] == [
        "step one",
        "step two",
        "step three",
    ]


def test_routed_to_correct_agent_by_capability() -> None:
    planner = FakePlanner(
        ["alpha task", "beta task"],
        [frozenset({"alpha-cap"}), frozenset({"beta-cap"})],
    )
    orch = Orchestrator(planner=planner)
    orch.register_agent(AlphaCapAgent())
    orch.register_agent(BetaCapAgent())
    task = Task(description="capability routing")
    result = asyncio.run(orch.execute(task))
    assert result.success is True
    names = [r.agent_name for r in orch.last_step_results]
    assert names == ["alpha-agent", "beta-agent"]


def test_broad_agent_selected_for_multiple_requirements() -> None:
    planner = FakePlanner(
        ["combined task"],
        [frozenset({"alpha-cap", "beta-cap"})],
    )
    orch = Orchestrator(planner=planner)
    orch.register_agent(AlphaCapAgent())
    orch.register_agent(BetaCapAgent())
    orch.register_agent(MultiCapAgent())
    task = Task(description="broad match")
    result = asyncio.run(orch.execute(task))
    assert result.success is True
    assert orch.last_step_results[0].agent_name == "multi-agent"


def test_empty_capabilities_matches_any_agent() -> None:
    planner = FakePlanner(["generic task"], [frozenset()])
    orch = Orchestrator(planner=planner)
    orch.register_agent(ExecutingAgent())
    task = Task(description="generic")
    result = asyncio.run(orch.execute(task))
    assert result.success is True
    assert orch.last_step_results[0].agent_name == "executor"


# ------------------------------------------------------------------
# Failure handling
# ------------------------------------------------------------------


def test_agent_execution_failure_stops_pipeline() -> None:
    planner = FakePlanner(
        ["good step", "bad step", "never reached"],
        [frozenset({"exec"}), frozenset({"fail"}), frozenset({"exec"})],
    )
    orch = Orchestrator(planner=planner)
    orch.register_agent(ExecutingAgent())
    orch.register_agent(FailingAgent())
    task = Task(description="fail mid plan")
    result = asyncio.run(orch.execute(task))
    assert result.success is False
    assert result.status == TaskStatus.FAILED
    assert "failed" in result.error.lower()
    assert len(orch.last_step_results) == 2
    assert orch.last_step_results[0].success is True
    assert orch.last_step_results[1].success is False
    assert orch.last_step_results[1].agent_name == "failer"


def test_routing_error_no_matching_agent() -> None:
    planner = FakePlanner(
        ["impossible task"],
        [frozenset({"nonexistent-cap"})],
    )
    orch = Orchestrator(planner=planner)
    orch.register_agent(ExecutingAgent())
    task = Task(description="no match")
    result = asyncio.run(orch.execute(task))
    assert result.success is False
    assert "No agent registered" in result.error
    assert len(orch.last_step_results) == 1
    assert orch.last_step_results[0].success is False


def test_planner_failure_propagates() -> None:
    planner = PlannerThatRaises()
    orch = Orchestrator(planner=planner)
    orch.register_agent(ExecutingAgent())
    task = Task(description="planner fails")
    result = asyncio.run(orch.execute(task))
    assert result.success is False
    assert "Planner raised RuntimeError" in result.error


def test_agent_exception_wraps_gracefully() -> None:
    planner = FakePlanner(["explode"], [frozenset({"raise"})])
    orch = Orchestrator(planner=planner)
    orch.register_agent(RaisingAgent())
    task = Task(description="agent raises")
    result = asyncio.run(orch.execute(task))
    assert result.success is False
    assert len(orch.last_step_results) == 1
    assert orch.last_step_results[0].success is False


def test_orchestration_error_is_exception() -> None:
    assert issubclass(PlanExecutionError, Exception)


# ------------------------------------------------------------------
# Backward-compat: /tasks API JSON shape unchanged
# ------------------------------------------------------------------


def test_tasks_api_json_shape_unchanged() -> None:
    orch = Orchestrator()
    app = create_app(orchestrator=orch)
    client = TestClient(app)
    response = client.post("/tasks", json={"description": "shape check"})
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"task_id", "success", "status", "output", "error"}


def test_tasks_api_shape_with_plan() -> None:
    planner = FakePlanner(["step a"], [frozenset({"exec"})])
    orch = Orchestrator(planner=planner)
    orch.register_agent(ExecutingAgent())
    app = create_app(orchestrator=orch)
    client = TestClient(app)
    response = client.post("/tasks", json={"description": "plan shape check"})
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"task_id", "success", "status", "output", "error"}
    assert data["success"] is True


# ------------------------------------------------------------------
# Execution path selection
# ------------------------------------------------------------------


def test_no_planner_uses_placeholder() -> None:
    orch = Orchestrator()
    task = Task(description="no planner")
    result = asyncio.run(orch.execute(task))
    assert result.success is True
    assert "orchestrated successfully" in result.output


def test_planner_without_agents_uses_placeholder() -> None:
    planner = FakePlanner(["step"], [frozenset({"exec"})])
    orch = Orchestrator(planner=planner)
    task = Task(description="no agents")
    result = asyncio.run(orch.execute(task))
    assert result.success is True


def test_ai_model_still_works_with_planner_registered() -> None:
    from app.core.ai import AIModel, AIResponse

    class SimpleAI(AIModel):
        name = "simple"
        description = "simple ai"

        async def chat(self, messages, *, tools=None) -> AIResponse:
            return AIResponse.ok(content="ai reply")

    planner = FakePlanner(["step"], [frozenset({"exec"})])
    orch = Orchestrator(ai_model=SimpleAI(), planner=planner)
    task = Task(description="has both")
    result = asyncio.run(orch.execute(task))
    assert result.success is True
    assert result.output == "ai reply"
