"""Unit tests for app.api.app — create_app factory."""

from collections.abc import Sequence

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.core.ai import AIMessage, AIModel, AIResponse, ToolDefinition
from app.core.orchestrator import Orchestrator


class FakeAIModel(AIModel):
    name = "fake-app-test"
    description = "A fake AI model for app factory tests."

    async def chat(
        self,
        messages: Sequence[AIMessage],
        *,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AIResponse:
        return AIResponse.ok(content="app factory test reply")


def test_create_app_default_has_orchestrator() -> None:
    application = create_app()
    assert application.state.orchestrator is not None
    assert isinstance(application.state.orchestrator, Orchestrator)


def test_create_app_custom_orchestrator_attached() -> None:
    orch = Orchestrator()
    application = create_app(orchestrator=orch)
    assert application.state.orchestrator is orch


def test_create_app_no_security_manager_by_default() -> None:
    application = create_app()
    assert not hasattr(application.state, "security_manager") or application.state.security_manager is None


def test_create_app_routes_are_included() -> None:
    application = create_app()
    client = TestClient(application)
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["name"] == "MISSMINUTES"


def test_create_app_with_ai_model_and_memory() -> None:
    application = create_app(ai_model=FakeAIModel(), memory="fake-memory")
    client = TestClient(application)
    response = client.post("/tasks", json={"description": "test"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["output"] == "app factory test reply"
