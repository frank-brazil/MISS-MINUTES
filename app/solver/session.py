"""Problem-solving session lifecycle and metadata.

A session records ``where`` an autonomous problem-solving run is, how many
attempts it has used, and a concise observable trace of what steps happened.
It deliberately never carries chain-of-thought or private reasoning: events
are short, human-readable status messages.
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.planner import Plan


def _utc_now() -> datetime:
    return datetime.now(UTC)


DEFAULT_MAX_ITERATIONS = 3


class ProblemSolvingStatus(StrEnum):
    """Lifecycle states of a problem-solving session."""

    PENDING = "pending"
    UNDERSTANDING = "understanding"
    RESEARCHING = "researching"
    PLANNING = "planning"
    DELEGATING = "delegating"
    PREDICTING = "predicting"
    CRITIQUING = "critiquing"
    ACTING = "acting"
    OBSERVING = "observing"
    VERIFYING = "verifying"
    REPLANNING = "replanning"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class AttemptSummary(BaseModel):
    """Brief, safe metadata about a single execution attempt.

    This is not a reasoning record: it only keeps counts and statuses that a
    replan iteration needs in order to avoid repeating the same mistake.
    """

    model_config = ConfigDict(validate_assignment=True)

    attempt_number: int
    plan_id: UUID | None = None
    steps_succeeded: int = 0
    steps_failed: int = 0
    action_success: bool | None = None
    verification_status: str | None = None
    outcome: str | None = None


class ProblemSolvingSession(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    session_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    status: ProblemSolvingStatus = ProblemSolvingStatus.PENDING
    current_iteration: int = 1
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    started_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    final_result: str | None = None
    failure_reason: str | None = None
    cancelled: bool = False
    cancelled_at: datetime | None = None
    plan: Plan | None = None
    attempts: list[AttemptSummary] = Field(default_factory=list)
    research_results: list["ResearchResponse"] = Field(default_factory=list)
    events: list["ExecutionEvent"] = Field(default_factory=list)

    @field_validator("max_iterations", "current_iteration")
    @classmethod
    def _iterations_at_least_one(cls, value: int) -> int:
        if value < 1:
            raise ValueError("iterations must be at least 1")
        return value

    def change_status(self, new_status: ProblemSolvingStatus) -> None:
        self.status = new_status
        self.updated_at = _utc_now()

    def record_event(self, event: "ExecutionEvent") -> None:
        self.events.append(event)
        self.updated_at = _utc_now()


from app.research.base import ResearchResponse  # noqa: E402
from app.solver.events import ExecutionEvent  # noqa: E402
