from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.core.ai import ToolDefinition


def _strip_schema_titles(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_schema_titles(item) for key, item in value.items() if key != "title"}
    if isinstance(value, list):
        return [_strip_schema_titles(item) for item in value]
    return value


class ToolArguments(BaseModel):
    pass


class ToolResult(BaseModel):
    success: bool
    output: str | None = None
    error: str | None = None

    @classmethod
    def ok(cls, output: str | None = None) -> "ToolResult":
        return cls(success=True, output=output)

    @classmethod
    def fail(cls, error: str, output: str | None = None) -> "ToolResult":
        return cls(success=False, error=error, output=output)


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    input_schema: ClassVar[type[BaseModel]]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [
            attribute
            for attribute in ("name", "description", "input_schema")
            if not hasattr(cls, attribute)
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} must define required attribute(s): {', '.join(missing)}"
            )
        for attribute in ("name", "description"):
            value = getattr(cls, attribute)
            if not isinstance(value, str) or not value.strip():
                raise TypeError(f"{cls.__name__}.{attribute} must be a non-empty string")
        if not (isinstance(cls.input_schema, type) and issubclass(cls.input_schema, BaseModel)):
            raise TypeError(f"{cls.__name__}.input_schema must be a pydantic BaseModel subclass")

    def parse_args(self, **kwargs: object) -> BaseModel:
        return self.input_schema.model_validate(kwargs)

    def to_tool_definition(self) -> "ToolDefinition":
        from app.core.ai import ToolDefinition as _ToolDefinition

        return _ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=_strip_schema_titles(self.input_schema.model_json_schema()),
        )

    @abstractmethod
    async def execute(self, **kwargs: object) -> ToolResult:
        raise NotImplementedError
