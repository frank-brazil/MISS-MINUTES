import asyncio
from collections.abc import Sequence

import pytest
from app.agents.base import Agent, AgentResult
from app.core.ai import AIMessage, AIModel, AIResponse, ToolCall, ToolDefinition
from app.core.orchestrator import Orchestrator
from app.core.permissions import ToolPermission
from app.core.planner import ManualPlanner
from app.core.problem_solver import FakeProblemSolver
from app.core.routing import AgentRouter
from app.core.task import Task
from app.core.verification import FakeVerifier
from app.distributed.coordinator import DistributedCoordinator
from app.distributed.events import DistributedEventType
from app.distributed.executor import FakeWorkerExecutor
from app.distributed.fakes import FakeWorkerTransport
from app.distributed.models import (
    DistributedTask,
    DistributedTaskStatus,
    WorkerInfo,
)
from app.distributed.queue import DistributedTaskQueue
from app.distributed.registry import WorkerRegistry
from app.distributed.service import WorkerService
from app.security.models import (
    Permission,
    PermissionCategory,
    PermissionRule,
    RiskLevel,
)
from app.security.policy import (
    AllowDenyPolicy,
    DefaultPolicy,
    DenyAllPolicy,
)
from app.solver.engine import ProblemSolvingEngine
from app.solver.fakes import FakeActionExecutor, FakeObservationProvider
from app.tools.base import Tool, ToolArguments, ToolResult


def _run(coro):
    return asyncio.run(coro)


# ----------------------------------------------------------------------
# Shared deterministic components
# ----------------------------------------------------------------------


class TrivialAgent(Agent):
    name = "trivial-agent"
    description = "Deterministic agent for security integration tests."
    capabilities = frozenset()

    async def execute(self, task: Task) -> AgentResult:
        return AgentResult.ok(output="done")


class ReadTool(Tool):
    name = "read-tool"
    description = "A read-only tool for security integration tests."
    input_schema = ToolArguments
    permission: ToolPermission = ToolPermission.READ

    def __init__(self) -> None:
        self.called = False

    async def execute(self, **kwargs: object) -> ToolResult:
        self.called = True
        return ToolResult.ok(output="read-output")


class SystemTool(Tool):
    name = "system-tool"
    description = "A system-level tool for security integration tests."
    input_schema = ToolArguments
    permission: ToolPermission = ToolPermission.SYSTEM

    def __init__(self) -> None:
        self.called = False

    async def execute(self, **kwargs: object) -> ToolResult:
        self.called = True
        return ToolResult.ok(output="system-output")


class UndeclaredTool(Tool):
    name = "undeclared-tool"
    description = "A tool that forgets to declare its permission."
    input_schema = ToolArguments

    async def execute(self, **kwargs: object) -> ToolResult:
        return ToolResult.ok(output="should-not-run")


class ScriptedAIModel(AIModel):
    name = "scripted-ai"
    description = "A model whose responses are scripted for security tests."

    def __init__(self, tool_call: ToolCall) -> None:
        self._tool_call = tool_call
        self._calls = 0

    async def chat(
        self,
        messages: Sequence[AIMessage],
        *,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AIResponse:
        self._calls += 1
        if self._calls == 1:
            return AIResponse.ok(
                content="calling a tool",
                tool_calls=[self._tool_call],
            )
        return AIResponse.ok(content="done")


def _orchestrator_with_tool(
    tool: Tool,
    security,
    tool_call: ToolCall | None = None,
) -> Orchestrator:
    orch = Orchestrator(
        ai_model=ScriptedAIModel(tool_call or ToolCall(id="call-1", name=tool.name, arguments={})),
        security=security,
    )
    orch.register_tool(tool)
    return orch


# ----------------------------------------------------------------------
# Orchestrator tool-calling path
# ----------------------------------------------------------------------


def test_orchestrator_allows_read_tool_under_default_policy() -> None:
    tool = ReadTool()
    orch = _orchestrator_with_tool(tool, DefaultPolicy())
    result = _run(orch.execute(Task(description="read something")))
    assert result.success is True
    assert tool.called is True
    assert orch.security is not None
    decisions = [event.decision for event in orch.security.audit_store.snapshot()]
    assert decisions == ["allow"]


def test_orchestrator_denies_read_tool_under_deny_all() -> None:
    tool = ReadTool()
    orch = _orchestrator_with_tool(tool, DenyAllPolicy())
    result = _run(orch.execute(Task(description="read something")))
    assert result.success is True  # loop itself finishes
    assert tool.called is False
    assert orch.security is not None
    events = orch.security.audit_store.snapshot()
    denied = [event for event in events if event.reason_code == "deny_all"]
    assert denied


def test_orchestrator_confirmation_gates_system_tool() -> None:
    tool = SystemTool()
    security = AllowDenyPolicy(
        rules=[
            PermissionRule(
                permission=Permission(category=PermissionCategory.SYSTEM),
                effect="allow",
            )
        ]
    )
    orch = _orchestrator_with_tool(tool, security)
    result = _run(orch.execute(Task(description="run system thing")))
    assert result.success is True
    assert tool.called is False
    assert orch.security is not None
    assert orch.security.confirmation.pending() != ()


def test_orchestrator_denies_tool_without_declared_permission() -> None:
    tool = UndeclaredTool()
    orch = _orchestrator_with_tool(tool, DefaultPolicy())
    result = _run(orch.execute(Task(description="do whatever")))
    assert result.success is True
    assert orch.security is not None
    undeclared = [
        event
        for event in orch.security.audit_store.snapshot()
        if event.reason_code == "undeclared_permission"
    ]
    assert undeclared


def test_orchestrator_accepts_bare_policy_as_security() -> None:
    tool = ReadTool()
    orch = _orchestrator_with_tool(tool, DefaultPolicy())
    assert orch.security is not None
    _run(orch.execute(Task(description="read something")))
    assert tool.called is True


def test_orchestrator_rejects_invalid_security_type() -> None:
    with pytest.raises(TypeError):
        Orchestrator(security="not-security")  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Problem-solving loop
# ----------------------------------------------------------------------


def _engine(security, *, action_executor: FakeActionExecutor | None = None) -> ProblemSolvingEngine:
    return ProblemSolvingEngine(
        problem_solver=FakeProblemSolver(),
        planner=ManualPlanner(["step one"]),
        agent_router=AgentRouter([TrivialAgent()]),
        verifier=FakeVerifier(),
        observation_provider=FakeObservationProvider(
            observations=["A clearer understanding of causes, constraints, and context. observed"],
            action_succeeded=True,
        ),
        action_executor=action_executor or FakeActionExecutor(),
        security=security,
    )


def test_loop_executes_action_under_default_policy() -> None:
    executor = FakeActionExecutor()
    engine = _engine(DefaultPolicy(), action_executor=executor)
    result = _run(engine.solve(Task(description="investigate a problem")))
    assert result.success is True
    assert executor.requests  # the action ran


def test_loop_denies_action_under_deny_all() -> None:
    executor = FakeActionExecutor()
    engine = _engine(DenyAllPolicy(), action_executor=executor)
    result = _run(engine.solve(Task(description="investigate a problem")))
    assert result.success is False
    assert executor.requests == ()
    assert engine.security is not None
    rendered = " ".join([*(event.message for event in result.events), result.failure_reason or ""])
    assert "denied by security policy" in rendered


def test_loop_gates_action_behind_confirmation() -> None:
    executor = FakeActionExecutor()
    security = AllowDenyPolicy(
        rules=[
            PermissionRule(
                permission=Permission(category=PermissionCategory.EXECUTE),
                effect="allow",
            )
        ],
        require_confirmation=(RiskLevel.MEDIUM,),
    )
    engine = _engine(security, action_executor=executor)
    result = _run(engine.solve(Task(description="investigate a problem")))
    assert result.success is False
    assert executor.requests == ()
    assert engine.security is not None
    assert engine.security.confirmation.pending() != ()
    rendered = " ".join([*(event.message for event in result.events), result.failure_reason or ""])
    assert "requires confirmation" in rendered


# ----------------------------------------------------------------------
# Distributed coordinator (master side)
# ----------------------------------------------------------------------


def _coordinator(security) -> DistributedCoordinator:
    registry = WorkerRegistry()
    queue = DistributedTaskQueue()
    coordinator = DistributedCoordinator(
        registry=registry,
        queue=queue,
        transport=FakeWorkerTransport(executor=FakeWorkerExecutor()),
        security=security,
    )
    worker = WorkerInfo(worker_name="worker-a", capabilities=frozenset({"analysis"}))
    registry.register(worker)
    return coordinator


def test_coordinator_denies_dispatch_under_deny_all() -> None:
    coordinator = _coordinator(DenyAllPolicy())
    task = coordinator.submit(DistributedTask(task_type="analysis"))
    assignment = coordinator.dispatch_next()
    assert assignment is None
    assert task.status is DistributedTaskStatus.FAILED
    assert task.last_error == "task denied by security policy: deny_all"
    event_types = [event.event_type for event in coordinator.events]
    assert DistributedEventType.TASK_FAILED in event_types
    assert coordinator.security is not None
    denied = [
        event
        for event in coordinator.security.audit_store.snapshot()
        if event.reason_code == "deny_all"
    ]
    assert denied


def test_coordinator_dispatch_allowed_by_explicit_rule() -> None:
    security = AllowDenyPolicy(
        rules=[
            PermissionRule(
                permission=Permission(
                    category=PermissionCategory.DISTRIBUTED,
                    resource="analysis",
                ),
                effect="allow",
            )
        ]
    )
    coordinator = _coordinator(security)
    task = coordinator.submit(DistributedTask(task_type="analysis"))
    assignment = coordinator.dispatch_next()
    assert assignment is not None
    assert assignment.task_id == task.distributed_task_id
    assert task.status is DistributedTaskStatus.ASSIGNED


# ----------------------------------------------------------------------
# Distributed worker service
# ----------------------------------------------------------------------


def test_worker_denies_task_under_deny_all() -> None:
    executor = FakeWorkerExecutor()
    service = WorkerService(
        worker_info=WorkerInfo(worker_name="worker-a", capabilities=frozenset({"analysis"})),
        executor=executor,
        security=DenyAllPolicy(),
    )
    result = _run(service.handle_task(DistributedTask(task_type="analysis")))
    assert result.success is False
    assert "denied by worker security policy" in (result.error or "")
    assert executor.requests == ()


def test_worker_allows_task_by_explicit_rule() -> None:
    executor = FakeWorkerExecutor()
    service = WorkerService(
        worker_info=WorkerInfo(worker_name="worker-a", capabilities=frozenset({"analysis"})),
        executor=executor,
        security=AllowDenyPolicy(
            rules=[
                PermissionRule(
                    permission=Permission(
                        category=PermissionCategory.DISTRIBUTED,
                        resource="analysis",
                    ),
                    effect="allow",
                )
            ]
        ),
    )
    task = DistributedTask(task_type="analysis")
    result = _run(service.handle_task(task))
    assert result.success is True
    assert executor.requests == (task,)


# ----------------------------------------------------------------------
# Boundary: security package must stay isolated and offline
# ----------------------------------------------------------------------


def test_security_sources_have_no_banned_imports() -> None:
    from pathlib import Path

    security_dir = Path(__file__).resolve().parents[2] / "app" / "security"
    banned = (
        "app.browser",
        "app.vision",
        "app.screen",
        "app.tools",
        "import httpx",
        "import requests",
        "import openai",
        "import aiohttp",
        "import socket",
    )
    source_files = sorted(security_dir.glob("*.py"))
    assert source_files, "expected security sources to exist"
    for path in source_files:
        content = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in content, f"{path.name} must not contain '{token}'"
