import asyncio
from pathlib import Path
from uuid import UUID

from app.core.task import Task
from app.memory.base import Memory, MemoryQueryResult, MemoryRecord
from app.solver.engine import ProblemSolvingEngine
from app.solver.fakes import FakeActionExecutor, FakeObservationProvider
from app.solver.session import ProblemSolvingStatus

_SOLVER_DIR = (
    Path(__file__).resolve().parents[2] / "app" / "solver"
)

_BANNED_NETWORK_IMPORTS = (
    "import httpx",
    "from httpx",
    "import requests",
    "from requests",
    "import openai",
    "from openai",
    "import aiohttp",
    "from aiohttp",
    "import urllib3",
    "from urllib3",
    "import socket",
)


def _run(coro):
    return asyncio.run(coro)


def test_solver_sources_have_no_network_clients() -> None:
    source_files = sorted(_SOLVER_DIR.glob("*.py"))
    assert source_files, "expected app/solver source files to exist"
    offending: list[str] = []
    for path in source_files:
        content = path.read_text(encoding="utf-8")
        for banned in _BANNED_NETWORK_IMPORTS:
            if banned in content:
                offending.append(f"{path.name}: {banned}")
    assert not offending, "banned network imports found in solver sources"


def test_solver_sources_do_not_reach_into_browser_or_vision() -> None:
    source_files = sorted(_SOLVER_DIR.glob("*.py"))
    for path in source_files:
        content = path.read_text(encoding="utf-8")
        for module in ("app.browser", "app.screen", "app.vision", "app.tools"):
            assert module not in content, (
                f"{path.name} must not import {module}"
            )


def test_engine_defaults_are_deterministic_fakes() -> None:
    from app.agents.base import Agent, AgentResult
    from app.core.planner import ManualPlanner
    from app.core.problem_solver import FakeProblemSolver
    from app.core.routing import AgentRouter

    class TrivialAgent(Agent):
        name = "trivial-agent"
        description = "Trivial agent for the default-engine security check."
        capabilities = frozenset()

        async def execute(self, task: Task) -> AgentResult:
            return AgentResult.ok(output="done")

    engine = ProblemSolvingEngine(
        problem_solver=FakeProblemSolver(),
        planner=ManualPlanner(["step one"]),
        agent_router=AgentRouter([TrivialAgent()]),
    )
    assert isinstance(engine.action_executor, FakeActionExecutor)
    assert isinstance(engine.observation_provider, FakeObservationProvider)


def test_results_never_leak_tracebacks_or_reasoning() -> None:
    from app.agents.base import Agent, AgentResult
    from app.core.critic import FakeCritic
    from app.core.planner import ManualPlanner
    from app.core.prediction import FakePredictor
    from app.core.problem_solver import FakeProblemSolver
    from app.core.routing import AgentRouter
    from app.core.verification import FakeVerifier

    class TrivialAgent(Agent):
        name = "trivial-agent"
        description = "Trivial agent for the trace-leak security check."
        capabilities = frozenset()

        async def execute(self, task: Task) -> AgentResult:
            return AgentResult.ok(output="done")

    engine = ProblemSolvingEngine(
        problem_solver=FakeProblemSolver(),
        planner=ManualPlanner(["step one"]),
        agent_router=AgentRouter([TrivialAgent()]),
        predictor=FakePredictor(),
        critic=FakeCritic(),
        verifier=FakeVerifier(),
        observation_provider=FakeObservationProvider(
            observations=["A clearer understanding of causes, constraints, and context. observed"],
            action_succeeded=True,
        ),
    )
    task = Task(description="sensitive-run")
    result = _run(engine.solve(task))
    rendered = "; ".join(
        [*(event.message for event in result.events), result.failure_reason or ""]
    ).lower()
    for forbidden in ("traceback", "chain-of-thought", "```"):
        assert forbidden not in rendered
    session = engine.get_session(result.session_id)
    assert session is not None
    assert session.status is ProblemSolvingStatus.COMPLETED


class RecordingMemory(Memory):
    name = "recording-memory"
    description = "Recording memory for security checks."

    def __init__(self) -> None:
        self.records: list[MemoryRecord] = []

    async def store(self, record: MemoryRecord) -> MemoryRecord:
        self.records.append(record)
        return record

    async def retrieve(
        self, query: str, *, limit: int = 10
    ) -> MemoryQueryResult:
        return MemoryQueryResult.ok([])

    async def delete(self, memory_id: UUID) -> bool:
        return False


def test_memory_never_contains_raw_task_content() -> None:
    from app.agents.base import Agent, AgentResult
    from app.core.planner import ManualPlanner
    from app.core.problem_solver import FakeProblemSolver
    from app.core.routing import AgentRouter
    from app.core.verification import FakeVerifier

    class TrivialAgent(Agent):
        name = "trivial-agent"
        description = "Trivial agent for the memory security check."
        capabilities = frozenset()

        async def execute(self, task: Task) -> AgentResult:
            return AgentResult.ok(output="done")

    memory = RecordingMemory()
    engine = ProblemSolvingEngine(
        problem_solver=FakeProblemSolver(),
        planner=ManualPlanner(["step one"]),
        agent_router=AgentRouter([TrivialAgent()]),
        verifier=FakeVerifier(),
        observation_provider=FakeObservationProvider(
            observations=[
                "A clearer understanding of causes, constraints, and context. observed"
            ],
            action_succeeded=True,
        ),
        memory=memory,
    )
    task = Task(description="top-secret experiment payload")
    result = _run(engine.solve(task))
    assert result.success is True
    assert len(memory.records) == 1
    content = memory.records[0].content.lower()
    assert "top-secret" not in content
    assert "payload" not in content
