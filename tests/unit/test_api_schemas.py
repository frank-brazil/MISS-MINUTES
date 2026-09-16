"""Unit tests for app.api.schemas — TaskRequest and HealthResponse models."""

import pytest
from pydantic import ValidationError

from app.api.schemas import HealthResponse, TaskRequest


def test_task_request_accepts_valid_description() -> None:
    request = TaskRequest(description="hello world")
    assert request.description == "hello world"


def test_task_request_rejects_empty_description() -> None:
    with pytest.raises(ValidationError):
        TaskRequest(description="")


def test_task_request_rejects_blank_description() -> None:
    with pytest.raises(ValidationError):
        TaskRequest(description="   ")


def test_task_request_rejects_missing_description() -> None:
    with pytest.raises(ValidationError):
        TaskRequest()


def test_task_request_preserves_original_whitespace() -> None:
    request = TaskRequest(description="  valid  ")
    assert request.description == "  valid  "


def test_health_response_construction() -> None:
    response = HealthResponse(status="ok")
    assert response.status == "ok"


def test_health_response_allows_any_status_string() -> None:
    response = HealthResponse(status="degraded")
    assert response.status == "degraded"
