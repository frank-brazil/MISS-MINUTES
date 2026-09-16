"""Injectable action executor boundary.

The executor is the only place where an action is physically performed.  It is
injected so that the loop itself never acquires unrestricted computer control;
the default implementation is a deterministic fake.  An action returns a
structured result (success, output or error, plus optional observation data).
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ActionRequest(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    action_id: UUID = Field(default_factory=uuid4)
    description: str
    expected_outcome: str | None = None
    iteration: int | None = None

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must not be blank")
        return value


class ActionResult(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    action_id: UUID
    success: bool
    output: str | None = None
    error: str | None = None
    description: str | None = None
    expected_outcome: str | None = None
    observation_data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def ok(
        cls,
        action_id: UUID,
        output: str | None = None,
        observation_data: dict[str, Any] | None = None,
    ) -> "ActionResult":
        return cls(
            action_id=action_id,
            success=True,
            output=output,
            observation_data=observation_data or {},
        )

    @classmethod
    def fail(
        cls,
        action_id: UUID,
        error: str,
        output: str | None = None,
    ) -> "ActionResult":
        return cls(
            action_id=action_id,
            success=False,
            error=error,
            output=output,
        )


class ActionExecutor(ABC):
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
    async def execute(self, request: ActionRequest) -> ActionResult:
        raise NotImplementedError
