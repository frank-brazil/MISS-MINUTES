import asyncio

import pytest
from pydantic import BaseModel, ValidationError

from app.tools.base import Tool, ToolArguments, ToolResult


class EchoArguments(BaseModel):
    text: str


class EchoTool(Tool):
    name = "echo"
    description = "Echoes back the provided text."
    input_schema = EchoArguments

    async def execute(self, **kwargs: object) -> ToolResult:
        args = self.parse_args(**kwargs)
        return ToolResult.ok(output=args.text)


class FailingTool(Tool):
    name = "failing-tool"
    description = "A sample tool that always fails."
    input_schema = ToolArguments
    error_message = "simulated tool failure"

    async def execute(self, **kwargs: object) -> ToolResult:
        self.parse_args(**kwargs)
        return ToolResult.fail(error=self.error_message)


def test_tool_is_abstract() -> None:
    with pytest.raises(TypeError):
        Tool()


def test_required_tool_metadata() -> None:
    assert EchoTool.name == "echo"
    assert EchoTool.description == "Echoes back the provided text."
    assert issubclass(EchoTool.input_schema, BaseModel)
    assert EchoTool.input_schema is EchoArguments


def test_missing_metadata_rejected() -> None:
    with pytest.raises(TypeError, match="name"):

        class MissingName(Tool):
            description = "missing name"
            input_schema = ToolArguments

            async def execute(self, **kwargs: object) -> ToolResult:
                return ToolResult.ok()


def test_empty_metadata_rejected() -> None:
    with pytest.raises(TypeError, match="non-empty"):

        class EmptyName(Tool):
            name = ""
            description = "empty name"
            input_schema = ToolArguments

            async def execute(self, **kwargs: object) -> ToolResult:
                return ToolResult.ok()


def test_invalid_input_schema_rejected() -> None:
    with pytest.raises(TypeError, match="input_schema"):

        class BadSchema(Tool):
            name = "bad-schema"
            description = "invalid input schema"
            input_schema = dict

            async def execute(self, **kwargs: object) -> ToolResult:
                return ToolResult.ok()


def test_concrete_tool_satisfies_interface() -> None:
    tool = EchoTool()
    assert isinstance(tool, Tool)
    assert asyncio.run(tool.execute(text="hi")) is not None


def test_successful_execution_result() -> None:
    tool = EchoTool()
    result = asyncio.run(tool.execute(text="hello"))
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.output == "hello"
    assert result.error is None


def test_failure_execution_result() -> None:
    tool = FailingTool()
    result = asyncio.run(tool.execute())
    assert isinstance(result, ToolResult)
    assert result.success is False
    assert result.error == "simulated tool failure"


def test_execute_rejects_invalid_arguments() -> None:
    tool = EchoTool()
    with pytest.raises(ValidationError):
        asyncio.run(tool.execute())
    with pytest.raises(ValidationError):
        asyncio.run(tool.execute(text=123))
