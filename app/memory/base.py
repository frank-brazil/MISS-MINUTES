from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(UTC)


class MemoryRecord(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    memory_id: UUID = Field(default_factory=uuid4)
    content: str
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def _content_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be empty")
        return v


class MemoryQueryResult(BaseModel):
    results: list[MemoryRecord]
    count: int
    success: bool = True
    error: str | None = None

    @classmethod
    def ok(cls, results: list[MemoryRecord]) -> "MemoryQueryResult":
        return cls(results=results, count=len(results), success=True)

    @classmethod
    def fail(cls, error: str) -> "MemoryQueryResult":
        return cls(results=[], count=0, success=False, error=error)


class MemoryBackendError(Exception):
    pass


class Memory(ABC):
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
    async def store(self, record: MemoryRecord) -> MemoryRecord:
        raise NotImplementedError

    @abstractmethod
    async def retrieve(self, query: str, *, limit: int = 10) -> MemoryQueryResult:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, memory_id: UUID) -> bool:
        raise NotImplementedError
