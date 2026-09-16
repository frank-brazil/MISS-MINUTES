import asyncio

from app.agents.base import Agent, AgentResult
from app.core.orchestrator import Orchestrator, OrchestrationResult
from app.core.planner import ManualPlanner
from app.core.problem_solver import FakeProblemSolver
from app.core.routing import AgentRouter
from app.core.task import Task, TaskStatus
from app.core.verification import FakeVerifier
from app.solver.engine import ProblemSolvingEngine
from app.solver.fakes import FakeActionExecutor, FakeObservationProvider


def _run(coro):
    return asyncio.run(coro)


class EchoAgent(Agent):
    name = "echo-agent"
    description = "Agent that returns a fixed success output."
    capabilities = frozenset()

    async def execute(self, task: Task) -> AgentResult:
        return AgentResult.ok(output="done")


_VERIFY_OBSERVATIONS = [
    "A clearer understanding of causes, constraints, and context. observed"
]


def make_success_engine() -> ProblemSolvingEngine:
    return ProblemSolvingEngine(
        problem_solver=FakeProblemSolver(),
        planner=ManualPlanner(["step one", "step two"]),
        agent_router=AgentRouter([EchoAgent()]),
        verifier=FakeVerifier(),
        action_executor=FakeActionExecutor(),
        observation_provider=FakeObservationProvider(
            observations=list(_VERIFY_OBSERVATIONS),
            action_succeeded=True,
        ),
    )


def make_failing_engine() -> ProblemSolvingEngine:
    return ProblemSolvingEngine(
        problem_solver=FakeProblemSolver(
            raise_error=RuntimeError("solver unavailable")
        ),
        planner=ManualPlanner(["step one"]),
        agent_router=AgentRouter([EchoAgent()]),
        verifier=FakeVerifier(),
    )


def test_orchestrator_defaults_have_no_engine() -> None:
    orch = Orchestrator()
    assert orch.problem_solving_engine is None


def test_orchestrator_exposes_configured_engine() -> None:
    engine = make_success_engine()
    orch = Orchestrator(problem_solving_engine=engine)
    assert orch.problem_solving_engine is engine


def test_orchestrator_routes_task_through_engine_on_success() -> None:
    engine = make_success_engine()
    orch = Orchestrator(problem_solving_engine=engine)
    task = Task(description="solve through engine")
    result = _run(orch.execute(task))
    assert isinstance(result, OrchestrationResult)
    assert result.success is True
    assert result.status is TaskStatus.COMPLETED
    assert result.task_id == task.task_id
    assert result.output is not None
    assert result.error is None
    assert task.status is TaskStatus.COMPLETED
    assert "verified result" in (result.output or "")


def test_orchestrator_engine_failure_marks_task_failed_cleanly() -> None:
    engine = make_failing_engine()
    orch = Orchestrator(problem_solving_engine=engine)
    task = Task(description="will fail in the engine")
    result = _run(orch.execute(task))
    assert result.success is False
    assert result.status is TaskStatus.FAILED
    assert task.status is TaskStatus.FAILED
    assert result.error is not None
    assert "Problem understanding failed" in result.error
    assert "Traceback" not in (result.error or "")


def test_engine_path_runs_even_when_planner_and_agents_also_present() -> None:
    engine = make_success_engine()
    orch = Orchestrator(
        planner=ManualPlanner(["ignored step"]),
        agent_router=AgentRouter([EchoAgent()]),
        problem_solving_engine=engine,
    )
    task = Task(description="engine wins the dispatch")
    result = _run(orch.execute(task))
    assert result.success is True
    assert orch.last_plan is None
    assert orch.last_step_results == ()


def test_without_engine_previous_paths_are_preserved() -> None:
    orch = Orchestrator()
    task = Task(description="placeholder still works")
    result = _run(orch.execute(task))
    assert result.success is True
    assert result.output == (
        f"Task '{task.description}' orchestrated successfully"
    )