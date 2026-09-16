"""Safe observability events for the distributed layer.

Events only carry concise, safe metadata: worker ID, task ID, attempt,
status, success/failure and a short message.  They **never** carry auth
tokens, credentials, raw sensitive task content or arbitrary payloads.
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DistributedEventType(StrEnum):
    WORKER_REGISTERED = "worker_registered"
    HEARTBEAT_RECEIVED = "heartbeat_received"
    TASK_QUEUED = "task_queued"
    TASK_ASSIGNED = "task_assigned"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_RETRIED = "task_retried"
    TASK_REQUEUED = "task_requeued"
    TASK_REROUTED = "task_rerouted"
    TASK_CANCELLED = "task_cancelled"
    WORKER_STALE = "worker_stale"
    WORKER_REMOVED = "worker_removed"


class DistributedEvent(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=_utc_now)
    event_type: DistributedEventType
    message: str
    success: bool | None = None
    worker_id: UUID | None = None
    task_id: UUID | None = None
    attempt: int | None = None

    @field_validator("message")
    @classmethod
    def _message_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value