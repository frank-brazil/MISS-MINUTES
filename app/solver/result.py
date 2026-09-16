"""Final outcome of a problem-solving session.

The result carries a concise trace of what happened and what was completed
(never chain-of-thought), plus the verification status so callers know whether
"success" was actually verified or merely unverified.
"""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.core.verification import VerificationStatus
from app.solver.events import ExecutionEvent
from app.solver.session import ProblemSolvingStatus


class ProblemSolvingResult(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    result_id: UUID = Field(default_factory=uuid4)
    success: bool
    status: ProblemSolvingStatus
    session_id: UUID
    task_id: UUID
    iterations_used: int
    final_output: str | None = None
    verification_status: VerificationStatus | None = None
    failure_reason: str | None = None
    completed_steps: list[str] = Field(default_factory=list)
    events: list[ExecutionEvent] = Field(default_factory=list)

    @property
    def trace_summary(self) -> list[str]:
        return [event.message for event in self.events]