from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal, Sequence

from pydantic import BaseModel, field_validator


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]

    @field_validator("name", "description")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class AIMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None


class AIResponse(BaseModel):
    success: bool
    content: str | None = None
    error: str | None = None
    model_name: str | None = None
    tool_calls: list[ToolCall] | None = None

    @classmethod
    def ok(
        cls,
        content: str,
        model_name: str | None = None,
        tool_calls: list[ToolCall] | None = None,
    ) -> "AIResponse":
        return cls(
            success=True, content=content, model_name=model_name, tool_calls=tool_calls
        )

    @classmethod
    def fail(cls, error: str) -> "AIResponse":
        return cls(success=False, error=error)


class AIError(Exception):
    pass


class AIModel(ABC):
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
                f"{cls.__name__} must define required attribute(s): {', '.join(missing)}"
            )

    @abstractmethod
    async def chat(
        self,
        messages: Sequence[AIMessage],
        *,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AIResponse:
        raise NotImplementedError
