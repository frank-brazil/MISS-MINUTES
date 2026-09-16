from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.vision.models import ImageInput


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Task(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    task_id: UUID = Field(default_factory=uuid4)
    description: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    image: ImageInput | None = Field(
        default=None,
        description=(
            "Optional visual input to analyse (a file reference or validated "
            "image bytes).  Never contains system instructions."
        ),
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Optional structured context for problem-solving plans (e.g. "
            "replanning metadata).  Never contains secret credentials."
        ),
    )

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must not be blank")
        return v

    def change_status(self, new_status: TaskStatus) -> None:
        self.status = new_status
        self.updated_at = _utc_now()