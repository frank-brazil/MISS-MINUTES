from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.solver.events import ExecutionEvent, ExecutionEventType


def test_event_type_values() -> None:
    values = {member.value for member in ExecutionEventType}
    assert "understanding" in values
    assert "research" in values
    assert "plan" in values
    assert "delegation" in values
    assert "prediction" in values
    assert "critique" in values
    assert "action" in values
    assert "observation" in values
    assert "verification" in values
    assert "replan" in values
    assert "completed" in values
    assert "failed" in values
    assert "cancelled" in values
    assert "timed_out" in values
    assert "notice" in values


def test_event_requires_message() -> None:
    with pytest.raises(ValidationError):
        ExecutionEvent(event_type=ExecutionEventType.NOTICE)  # type: ignore[call-arg]


def test_event_defaults() -> None:
    event = ExecutionEvent(
        event_type=ExecutionEventType.PLAN,
        message="Plan created.",
    )
    assert isinstance(event.event_id, UUID)
    assert isinstance(event.timestamp, datetime)
    assert event.timestamp.tzinfo is not None
    assert event.event_type is ExecutionEventType.PLAN
    assert event.status is None
    assert event.success is None
    assert event.agent_name is None
    assert event.tool_name is None
    assert event.iteration is None


def test_event_full_fields() -> None:
    event = ExecutionEvent(
        event_type=ExecutionEventType.DELEGATION,
        status="delegating",
        message="Executed step 1 with agent 'worker'.",
        success=True,
        agent_name="worker",
        tool_name=None,
        iteration=1,
    )
    assert event.status == "delegating"
    assert event.success is True
    assert event.agent_name == "worker"
    assert event.iteration == 1


def test_event_rejects_blank_message() -> None:
    with pytest.raises(ValidationError):
        ExecutionEvent(event_type=ExecutionEventType.NOTICE, message="")


def test_event_rejects_whitespace_message() -> None:
    with pytest.raises(ValidationError):
        ExecutionEvent(event_type=ExecutionEventType.NOTICE, message="   ")


def test_events_are_concise_by_construction() -> None:
    event = ExecutionEvent(
        event_type=ExecutionEventType.REPLAN,
        message="Replanning attempt 2 of 3.",
        success=True,
        iteration=2,
    )
    assert len(event.message) < 100
    assert "attempt" in event.message