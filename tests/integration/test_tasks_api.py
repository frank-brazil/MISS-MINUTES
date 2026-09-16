from collections.abc import Sequence
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.app import app, create_app
from app.core.ai import AIMessage, AIModel, AIResponse, ToolDefinition
from app.core.orchestrator import Orchestrator


client = TestClient(app)


class FakeAIModel(AIModel):
    name = "fake-ai"
    description = "A fake AI model for API integration tests."

    async def chat(
        self,
        messages: Sequence[AIMessage],
        *,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AIResponse:
        return AIResponse.ok(content="fake provider reply", model_name="fake-model")


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_successful_task_request() -> None:
    response = client.post("/tasks", json={"description": "hello world"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "completed"
    assert data["output"] is not None
    assert data["error"] is None


def test_task_response_structure() -> None:
    response = client.post("/tasks", json={"description": "structure check"})
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"task_id", "success", "status", "output", "error"}
    assert UUID(data["task_id"])


def test_invalid_request_missing_description() -> None:
    response = client.post("/tasks", json={})
    assert response.status_code == 422


def test_invalid_request_empty_description() -> None:
    response = client.post("/tasks", json={"description": ""})
    assert response.status_code == 422


def test_invalid_request_blank_description() -> None:
    response = client.post("/tasks", json={"description": "   "})
    assert response.status_code == 422


def test_create_app_accepts_injected_orchestrator() -> None:
    orch = Orchestrator()
    custom_app = create_app(orchestrator=orch)
    assert custom_app.state.orchestrator is orch


def test_fake_ai_provider_injected_into_app() -> None:
    orch = Orchestrator(ai_model=FakeAIModel())
    custom_app = create_app(orchestrator=orch)
    custom_client = TestClient(custom_app)
    response = custom_client.post("/tasks", json={"description": "hello"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "completed"
    assert data["output"] == "fake provider reply"
    assert data["error"] is None