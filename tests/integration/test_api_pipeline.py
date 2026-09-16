"""Integration tests for the full API request lifecycle."""

from collections.abc import Sequence

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.core.ai import AIMessage, AIModel, AIResponse, ToolDefinition
from app.core.orchestrator import Orchestrator


class TrackingAIModel(AIModel):
    name = "tracking-ai"
    description = "An AI model that records all chat requests."

    def __init__(self, replies: list[str] | None = None) -> None:
        self._replies = replies or ["default reply"]
        self.chat_requests: list[list[AIMessage]] = []
        self._call_count = 0

    async def chat(
        self,
        messages: Sequence[AIMessage],
        *,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AIResponse:
        self.chat_requests.append(list(messages))
        reply = self._replies[min(self._call_count, len(self._replies) - 1)]
        self._call_count += 1
        return AIResponse.ok(content=reply, model_name="tracking-model")


class FailingAIModel(AIModel):
    name = "failing-ai"
    description = "An AI model that always fails."

    async def chat(
        self,
        messages: Sequence[AIMessage],
        *,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AIResponse:
        return AIResponse.fail(error="simulated AI failure")


def test_full_lifecycle_with_custom_ai() -> None:
    ai = TrackingAIModel(replies=["Hello from tracking AI"])
    app = create_app(ai_model=ai)
    client = TestClient(app)

    response = client.post("/tasks", json={"description": "greet me"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "completed"
    assert data["output"] == "Hello from tracking AI"
    assert data["error"] is None

    assert len(ai.chat_requests) == 1
    assert ai.chat_requests[0][0].content == "greet me"


def test_orchestrator_failure_returns_structured_error() -> None:
    ai = FailingAIModel()
    app = create_app(ai_model=ai)
    client = TestClient(app)

    response = client.post("/tasks", json={"description": "will fail"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["error"] is not None


def test_invalid_request_body_returns_422() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post("/tasks", json={})
    assert response.status_code == 422

    response = client.post("/tasks", json={"description": ""})
    assert response.status_code == 422


def test_multiple_sequential_requests_are_independent() -> None:
    ai = TrackingAIModel(replies=["first", "second", "third"])
    app = create_app(ai_model=ai)
    client = TestClient(app)

    r1 = client.post("/tasks", json={"description": "task one"})
    r2 = client.post("/tasks", json={"description": "task two"})
    r3 = client.post("/tasks", json={"description": "task three"})

    assert r1.json()["output"] == "first"
    assert r2.json()["output"] == "second"
    assert r3.json()["output"] == "third"
    assert len(ai.chat_requests) == 3


def test_health_and_root_alongside_tasks() -> None:
    ai = TrackingAIModel()
    app = create_app(ai_model=ai)
    client = TestClient(app)

    root_resp = client.get("/")
    assert root_resp.status_code == 200
    assert root_resp.json()["name"] == "MISSMINUTES"

    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json() == {"status": "ok"}

    task_resp = client.post("/tasks", json={"description": "test"})
    assert task_resp.status_code == 200
    assert task_resp.json()["success"] is True
