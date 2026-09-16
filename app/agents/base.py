from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel

from app.core.task import Task


class AgentResult(BaseModel):
    success: bool
    output: str | None = None
    error: str | None = None

    @classmethod
    def ok(cls, output: str | None = None) -> "AgentResult":
        return cls(success=True, output=output)

    @classmethod
    def fail(cls, error: str, output: str | None = None) -> "AgentResult":
        return cls(success=False, error=error, output=output)


class Agent(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    capabilities: ClassVar[frozenset[str]]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [
            attribute
            for attribute in ("name", "description", "capabilities")
            if not hasattr(cls, attribute)
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} must define required attribute(s): {', '.join(missing)}"
            )

    @abstractmethod
    async def execute(self, task: Task) -> AgentResult:
        raise NotImplementedError