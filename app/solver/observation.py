"""Injectable observation provider boundary.

Observations describe what happened after an action in a structured way.  The
provider is injected and defaults to a deterministic fake; the loop never reads
the real screen, browser or computer state directly.
"""

from abc import ABC, abstractmethod
from typing import ClassVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ObservationRequest(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    observation_id: UUID = Field(default_factory=uuid4)
    description: str
    action_ref: UUID | None = None
    expected_outcome: str | None = None

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must not be blank")
        return value


class ObservationResult(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    observation_id: UUID
    success: bool
    observations: list[str] = Field(default_factory=list)
    error: str | None = None
    action_succeeded: bool | None = None

    @classmethod
    def ok(
        cls,
        observation_id: UUID,
        observations: list[str] | None = None,
        action_succeeded: bool | None = None,
    ) -> "ObservationResult":
        return cls(
            observation_id=observation_id,
            success=True,
            observations=observations or [],
            action_succeeded=action_succeeded,
        )

    @classmethod
    def fail(
        cls,
        observation_id: UUID,
        error: str,
        observations: list[str] | None = None,
    ) -> "ObservationResult":
        return cls(
            observation_id=observation_id,
            success=False,
            error=error,
            observations=observations or [],
        )


class ObservationProvider(ABC):
    name: ClassVar[str]
    description: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [
            attribute
            for attribute in ("name", "description")
            if not hasattr(cls, attribute)
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} must define required attribute(s): "
                f"{', '.join(missing)}"
            )

    @abstractmethod
    async def observe(self, request: ObservationRequest) -> ObservationResult:
        raise NotImplementedError