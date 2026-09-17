import asyncio
from collections.abc import Sequence
from uuid import UUID

import pytest

from app.agents.base import Agent, AgentResult
from app.core.ai import AIMessage, AIModel, AIResponse, ToolDefinition
from app.core.orchestrator import OrchestrationResult, Orchestrator
from app.core.task import Task, TaskStatus
from app.memory.base import Memory, MemoryQueryResult, MemoryRecord
from app.tools.base import Tool, ToolArguments, ToolResult


class SampleAgent(Agent):
    name = "orch-agent"
    description = "A sample agent for orchestrator tests."
    capabilities = frozenset({"orch"})

    async def execute(self, task: Task) -> AgentResult:
        return AgentResult.ok(output="worked")


class OtherAgent(Agent):
    name = "other-agent"
    description = "Another sample agent."
    capabilities = frozenset({"other"})

    async def execute(self, task: Task) -> AgentResult:
        return AgentResult.ok()


class SampleTool(Tool):
    name = "orch-tool"
    description = "A sample tool for orchestrator tests."
    input_schema = ToolArguments

    async def execute(self, **kwargs: object) -> ToolResult:
        return ToolResult.ok(output="worked")


class SampleMemory(Memory):
    name = "orch-memory"
    description = "A minimal memory implementation."

    async def store(self, record: MemoryRecord) -> MemoryRecord:
        return record

    async def retrieve(self, query: str, *, limit: int = 10) -> MemoryQueryResult:
        return MemoryQueryResult.ok([])

    async def delete(self, memory_id: UUID) -> bool:
        return False


class FakeAIModel(AIModel):
    name = "fake-ai"
    description = "A fake AI model for orchestrator tests."

    def __init__(self, response: AIResponse | None = None) -> None:
        self._response = response
        self.received_messages: list[AIMessage] = []
        self.received_tools: list[ToolDefinition] | None = None

    async def chat(
        self,
        messages: Sequence[AIMessage],
        *,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AIResponse:
        self.received_messages = list(messages)
        self.received_tools = list(tools) if tools else None
        if self._response is not None:
            return self._response
        return AIResponse.ok(content="fake reply")


def test_orchestrator_creation() -> None:
    orch = Orchestrator()
    assert orch.memory is None
    assert orch.agents() == ()
    assert orch.tools() == ()


def test_memory_injection_without_storage_dependency() -> None:
    memory = SampleMemory()
    orch = Orchestrator(memory=memory)
    assert orch.memory is memory


def test_agent_registration() -> None:
    orch = Orchestrator()
    agent = SampleAgent()
    orch.register_agent(agent)
    assert orch.agent_names() == ("orch-agent",)
    assert orch.agents() == (agent,)


def test_tool_registration() -> None:
    orch = Orchestrator()
    tool = SampleTool()
    orch.register_tool(tool)
    assert orch.tool_names() == ("orch-tool",)
    assert orch.tools() == (tool,)


def test_multiple_agents_registered() -> None:
    orch = Orchestrator()
    orch.register_agent(SampleAgent())
    orch.register_agent(OtherAgent())
    assert set(orch.agent_names()) == {"orch-agent", "other-agent"}
    assert len(orch.agents()) == 2


def test_duplicate_agent_registration_rejected() -> None:
    orch = Orchestrator()
    orch.register_agent(SampleAgent())
    with pytest.raises(ValueError):
        orch.register_agent(SampleAgent())


def test_duplicate_tool_registration_rejected() -> None:
    orch = Orchestrator()
    orch.register_tool(SampleTool())
    with pytest.raises(ValueError):
        orch.register_tool(SampleTool())


def test_orchestration_result_factories() -> None:
    task = Task(description="factory test")
    ok_result = OrchestrationResult.ok(
        task_id=task.task_id,
        status=TaskStatus.COMPLETED,
        output="done",
    )
    assert ok_result.success is True
    assert ok_result.status == TaskStatus.COMPLETED
    assert ok_result.output == "done"
    assert ok_result.error is None
    fail_result = OrchestrationResult.fail(
        task_id=task.task_id,
        status=TaskStatus.FAILED,
        error="boom",
    )
    assert fail_result.success is False
    assert fail_result.status == TaskStatus.FAILED
    assert fail_result.error == "boom"
    assert fail_result.output is None


def test_successful_task_execution_lifecycle() -> None:
    orch = Orchestrator()
    task = Task(description="do placeholder work")
    assert task.status == TaskStatus.PENDING
    result = asyncio.run(orch.execute(task))
    assert isinstance(result, OrchestrationResult)
    assert result.success is True
    assert result.status == TaskStatus.COMPLETED
    assert result.task_id == task.task_id
    assert result.output is not None
    assert result.error is None
    assert task.status == TaskStatus.COMPLETED


def test_task_timestamps_preserved_through_state_changes() -> None:
    orch = Orchestrator()
    task = Task(description="timestamps")
    created_at = task.created_at
    original_updated_at = task.updated_at
    result = asyncio.run(orch.execute(task))
    assert result.success is True
    assert task.created_at == created_at
    assert task.updated_at > original_updated_at
    assert task.updated_at >= task.created_at


def test_failure_handling_sets_task_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    orch = Orchestrator()
    task = Task(description="will fail")
    assert task.status == TaskStatus.PENDING

    async def _raise_error(*args: object, **kwargs: object) -> None:
        raise RuntimeError("internal orchestration failure")

    monkeypatch.setattr(orch, "_orchestrate", _raise_error)
    result = asyncio.run(orch.execute(task))
    assert result.success is False
    assert result.status == TaskStatus.FAILED
    assert result.error == "internal orchestration failure"
    assert task.status == TaskStatus.FAILED


def test_ai_model_injection_and_success() -> None:
    ai_model = FakeAIModel(response=AIResponse.ok(content="ai answered"))
    orch = Orchestrator(ai_model=ai_model)
    assert orch.ai_model is ai_model
    task = Task(description="ask the ai")
    result = asyncio.run(orch.execute(task))
    assert result.success is True
    assert result.status == TaskStatus.COMPLETED
    assert result.output == "ai answered"
    assert task.status == TaskStatus.COMPLETED
    assert len(ai_model.received_messages) == 1
    assert ai_model.received_messages[0].role == "user"
    assert ai_model.received_messages[0].content == "ask the ai"


def test_ai_model_failure_marks_task_failed() -> None:
    ai_model = FakeAIModel(response=AIResponse.fail(error="ai unavailable"))
    orch = Orchestrator(ai_model=ai_model)
    task = Task(description="ask the ai")
    result = asyncio.run(orch.execute(task))
    assert result.success is False
    assert result.status == TaskStatus.FAILED
    assert result.error == "ai unavailable"
    assert task.status == TaskStatus.FAILED
