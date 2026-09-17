from uuid import UUID

import pytest
from app.core.verification import VerificationStatus
from app.solver.events import ExecutionEvent, ExecutionEventType
from app.solver.result import ProblemSolvingResult
from app.solver.session import ProblemSolvingStatus
from pydantic import ValidationError


def test_result_requires_core_fields() -> None:
    with pytest.raises(ValidationError):
        ProblemSolvingResult(
            success=True,
            status=ProblemSolvingStatus.COMPLETED,
            session_id=UUID(int=1),
            iterations_used=1,
        )


def test_result_defaults() -> None:
    result = ProblemSolvingResult(
        success=True,
        status=ProblemSolvingStatus.COMPLETED,
        session_id=UUID(int=1),
        task_id=UUID(int=2),
        iterations_used=2,
    )
    assert isinstance(result.result_id, UUID)
    assert result.final_output is None
    assert result.verification_status is None
    assert result.failure_reason is None
    assert result.completed_steps == []
    assert result.events == []


def test_result_full_fields() -> None:
    event = ExecutionEvent(
        event_type=ExecutionEventType.COMPLETED,
        message="Done.",
        success=True,
    )
    result = ProblemSolvingResult(
        success=True,
        status=ProblemSolvingStatus.COMPLETED,
        session_id=UUID(int=1),
        task_id=UUID(int=2),
        iterations_used=1,
        final_output="completed",
        verification_status=VerificationStatus.VERIFIED,
        completed_steps=["step one"],
        events=[event],
    )
    assert result.final_output == "completed"
    assert result.verification_status is VerificationStatus.VERIFIED
    assert result.completed_steps == ["step one"]
    assert result.trace_summary == ["Done."]


def test_result_trace_summary_mirrors_messages() -> None:
    result = ProblemSolvingResult(
        success=False,
        status=ProblemSolvingStatus.FAILED,
        session_id=UUID(int=1),
        task_id=UUID(int=2),
        iterations_used=3,
        failure_reason="no luck",
        events=[
            ExecutionEvent(
                event_type=ExecutionEventType.REPLAN,
                message="Replanning attempt 2 of 3.",
                success=True,
            ),
            ExecutionEvent(
                event_type=ExecutionEventType.FAILED,
                message="Problem-solving failed: no luck.",
                success=False,
            ),
        ],
    )
    assert result.trace_summary == [
        "Replanning attempt 2 of 3.",
        "Problem-solving failed: no luck.",
    ]
    assert len(result.trace_summary) == 2
