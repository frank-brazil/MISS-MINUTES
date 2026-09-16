"""Unit tests for app.api.router — route handler functions."""

import asyncio
from collections.abc import Sequence
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.router import create_task, health, root
from app.api.schemas import TaskRequest
from app.core.ai import AIMessage, AIModel, AIResponse, ToolDefinition
from app.core.orchestrator import Orchestrator, OrchestrationResult
from app.core.task import TaskStatus


class FakeAIModel(AIModel):
    name = "fake-router-test"
    description = "A fake AI model for router unit tests."

    async def chat(
        self,
        messages: Sequence[AIMessage],
        *,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AIResponse:
        return AIResponse.ok(content="router test reply")


def test_root_returns_identity() -> None:
    result = asyncio.run(root())
    assert result["name"] == "MISSMINUTES"
    assert result["version"] == "0.1.0"
    assert result["status"] == "running"
    assert "description" in result


def test_health_returns_ok_status() -> None:
    result = asyncio.run(health())
    assert result.status == "ok"


def test_create_task_delegates_to_orchestrator() -> None:
    orchestrator = Orchestrator(ai_model=FakeAIModel())
    request = TaskRequest(description="test task")
    result = asyncio.run(create_task(request=request, orchestrator=orchestrator))
    assert isinstance(result, OrchestrationResult)
    assert result.success is True
    assert result.status is TaskStatus.COMPLETED


def test_create_task_logs_task_id(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO")
    orchestrator = Orchestrator(ai_model=FakeAIModel())
    request = TaskRequest(description="logged task")
    asyncio.run(create_task(request=request, orchestrator=orchestrator))
    assert "Received task request" in caplog.text


def test_create_task_logs_completion_status(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO")
    orchestrator = Orchestrator(ai_model=FakeAIModel())
    request = TaskRequest(description="status log task")
    asyncio.run(create_task(request=request, orchestrator=orchestrator))
    assert "finished with status" in caplog.text


def test_create_task_with_minimal_description() -> None:
    orchestrator = Orchestrator(ai_model=FakeAIModel())
    request = TaskRequest(description="x")
    result = asyncio.run(create_task(request=request, orchestrator=orchestrator))
    assert result.success is True
