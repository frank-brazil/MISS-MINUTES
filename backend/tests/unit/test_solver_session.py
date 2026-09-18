from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.core.task import Task
from app.research.base import ResearchResponse
from app.solver.events import ExecutionEvent, ExecutionEventType
from app.solver.session import (
    DEFAULT_MAX_ITERATIONS,
    AttemptSummary,
    ProblemSolvingSession,
    ProblemSolvingStatus,
)


def test_status_values() -> None:
    values = {
        ProblemSolvingStatus.PENDING.value,
        ProblemSolvingStatus.UNDERSTANDING.value,
        ProblemSolvingStatus.RESEARCHING.value,
        ProblemSolvingStatus.PLANNING.value,
        ProblemSolvingStatus.DELEGATING.value,
        ProblemSolvingStatus.PREDICTING.value,
        ProblemSolvingStatus.CRITIQUING.value,
        ProblemSolvingStatus.ACTING.value,
        ProblemSolvingStatus.OBSERVING.value,
        ProblemSolvingStatus.VERIFYING.value,
        ProblemSolvingStatus.REPLANNING.value,
        ProblemSolvingStatus.COMPLETED.value,
        ProblemSolvingStatus.FAILED.value,
        ProblemSolvingStatus.CANCELLED.value,
        ProblemSolvingStatus.TIMED_OUT.value,
    }
    assert "pending" in values
    assert "replanning" in values
    assert "timed_out" in values
    assert len(values) == 15


def test_default_max_iterations() -> None:
    assert DEFAULT_MAX_ITERATIONS == 3


def test_session_requires_task_id() -> None:
    with pytest.raises(ValidationError):
        ProblemSolvingSession()  # type: ignore[call-arg]


def test_session_defaults() -> None:
    task = Task(description="solve")
    session = ProblemSolvingSession(task_id=task.task_id)
    assert isinstance(session.session_id, UUID)
    assert session.task_id == task.task_id
    assert session.status is ProblemSolvingStatus.PENDING
    assert session.current_iteration == 1
    assert session.max_iterations == DEFAULT_MAX_ITERATIONS
    assert session.final_result is None
    assert session.failure_reason is None
    assert session.cancelled is False
    assert session.cancelled_at is None
    assert session.plan is None
    assert session.attempts == []
    assert session.research_results == []
    assert session.events == []
    assert isinstance(session.started_at, datetime)
    assert session.started_at.tzinfo is not None


def test_session_accepts_custom_max_iterations() -> None:
    task = Task(description="solve")
    session = ProblemSolvingSession(task_id=task.task_id, max_iterations=1)
    assert session.max_iterations == 1


def test_session_rejects_invalid_iterations() -> None:
    task = Task(description="solve")
    with pytest.raises(ValidationError):
        ProblemSolvingSession(task_id=task.task_id, max_iterations=0)
    with pytest.raises(ValidationError):
        ProblemSolvingSession(task_id=task.task_id, current_iteration=0)


def test_change_status_updates_updated_at() -> None:
    task = Task(description="solve")
    session = ProblemSolvingSession(task_id=task.task_id)
    original = session.updated_at
    session.change_status(ProblemSolvingStatus.REPLANNING)
    assert session.status is ProblemSolvingStatus.REPLANNING
    assert session.updated_at >= original


def test_record_event_updates_events_and_timestamp() -> None:
    task = Task(description="solve")
    session = ProblemSolvingSession(task_id=task.task_id)
    event = ExecutionEvent(
        event_type=ExecutionEventType.PLAN,
        message="Plan created with 2 step(s).",
        success=True,
    )
    session.record_event(event)
    assert session.events == [event]
    assert session.updated_at >= session.started_at


def test_session_research_results_accept_structured_responses() -> None:
    task = Task(description="solve")
    session = ProblemSolvingSession(task_id=task.task_id)
    response = ResearchResponse.ok(query="q", results=[])
    session.research_results.append(response)
    assert session.research_results[0].success is True


def test_attempt_summary_defaults() -> None:
    summary = AttemptSummary(attempt_number=2)
    assert summary.attempt_number == 2
    assert summary.plan_id is None
    assert summary.steps_succeeded == 0
    assert summary.steps_failed == 0
    assert summary.action_success is None
    assert summary.verification_status is None
    assert summary.outcome is None
