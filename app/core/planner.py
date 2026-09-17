import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.task import Task, TaskStatus


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PlanStep(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    step_id: UUID = Field(default_factory=uuid4)
    description: str
    status: TaskStatus = TaskStatus.PENDING
    dependencies: frozenset[UUID] = Field(default_factory=frozenset)
    required_capabilities: frozenset[str] = Field(default_factory=frozenset)

    @field_validator("description")
    @classmethod
    def _description_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must not be blank")
        return v

    @field_validator("required_capabilities")
    @classmethod
    def _required_capabilities_not_blank(cls, v: frozenset[str]) -> frozenset[str]:
        for cap in v:
            if not cap.strip():
                raise ValueError("required capabilities must not be blank")
        return v


class Plan(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    plan_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    goal: str
    steps: list[PlanStep]
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("goal")
    @classmethod
    def _goal_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("goal must not be blank")
        return v

    @model_validator(mode="after")
    def _validate_steps(self) -> "Plan":
        if not self.steps:
            raise ValueError("plan must contain at least one step")

        seen: set[UUID] = set()
        order: dict[UUID, int] = {}
        for index, step in enumerate(self.steps):
            if step.step_id in seen:
                raise ValueError(f"duplicate step id: {step.step_id}")
            seen.add(step.step_id)
            order[step.step_id] = index

        for step in self.steps:
            for dependency in step.dependencies:
                if dependency == step.step_id:
                    raise ValueError("a step cannot depend on itself")
                if dependency not in seen:
                    raise ValueError(f"dependency references unknown step: {dependency}")
                if order[dependency] >= order[step.step_id]:
                    raise ValueError("dependency must reference an earlier step")
        return self


class Planner(ABC):
    name: ClassVar[str]
    description: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [
            attribute for attribute in ("name", "description") if not hasattr(cls, attribute)
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} must define required attribute(s): {', '.join(missing)}"
            )

    @abstractmethod
    async def plan(self, task: Task) -> Plan:
        raise NotImplementedError


class ManualPlanner(Planner):
    name = "manual"
    description = (
        "Builds a deterministic plan from manually provided step descriptions. "
        "Provider-independent."
    )

    def __init__(self, step_descriptions: Sequence[str]) -> None:
        self._logger = logging.getLogger(__name__)
        self._step_descriptions = tuple(description.strip() for description in step_descriptions)

    async def plan(self, task: Task) -> Plan:
        steps = [PlanStep(description=description) for description in self._step_descriptions]
        plan = Plan(
            task_id=task.task_id,
            goal=task.description,
            steps=steps,
        )
        self._logger.info(
            "Built plan %s with %d step(s) for task %s",
            plan.plan_id,
            len(steps),
            task.task_id,
        )
        return plan
