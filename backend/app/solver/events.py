"""Concise observable trace events for problem-solving sessions.

Events are short status messages ("Plan created with 3 steps.").  They are
intentionally **not** chain-of-thought: no private reasoning, no intermediate
conjectures, no hidden decision internals, and never raw tool arguments or
credentials.
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ExecutionEventType(StrEnum):
    UNDERSTANDING = "understanding"
    RESEARCH = "research"
    PLAN = "plan"
    DELEGATION = "delegation"
    PREDICTION = "prediction"
    CRITIQUE = "critique"
    ACTION = "action"
    OBSERVATION = "observation"
    VERIFICATION = "verification"
    REPLAN = "replan"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    NOTICE = "notice"


class ExecutionEvent(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=_utc_now)
    event_type: ExecutionEventType
    status: str | None = None
    message: str
    success: bool | None = None
    agent_name: str | None = None
    tool_name: str | None = None
    iteration: int | None = None

    @field_validator("message")
    @classmethod
    def _message_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value
