import pytest
from pydantic import ValidationError

from app.core.ai import AIMessage, AIResponse, ToolCall, ToolDefinition
from app.tools.base import ToolArguments
from app.tools.calculator import CalculatorTool


def test_tool_definition_fields() -> None:
    definition = ToolDefinition(
        name="greet",
        description="Greets a user.",
        parameters={"type": "object", "properties": {}},
    )
    assert definition.name == "greet"
    assert definition.description == "Greets a user."
    assert definition.parameters == {"type": "object", "properties": {}}


def test_tool_definition_requires_name() -> None:
    with pytest.raises(ValidationError):
        ToolDefinition(name="", description="d", parameters={})


def test_tool_call_fields() -> None:
    call = ToolCall(
        id="call_abc",
        name="calculator",
        arguments={"operation": "add", "a": 1, "b": 2},
    )
    assert call.id == "call_abc"
    assert call.name == "calculator"
    assert call.arguments["a"] == 1


def test_tool_to_tool_definition() -> None:
    tool = CalculatorTool()
    definition = tool.to_tool_definition()
    assert isinstance(definition, ToolDefinition)
    assert definition.name == "calculator"
    assert "add" in definition.description.lower()
    assert definition.parameters["type"] == "object"
    properties = definition.parameters["properties"]
    assert "operation" in properties
    assert "a" in properties
    assert "b" in properties
    assert definition.parameters["required"] == ["operation", "a", "b"]


def test_tool_to_tool_definition_has_no_title() -> None:
    tool = CalculatorTool()
    definition = tool.to_tool_definition()
    assert "title" not in definition.parameters
    assert "title" not in definition.parameters["properties"]["a"]


def test_empty_tool_arguments_definition() -> None:
    tool = EmptyArgsTool()
    definition = tool.to_tool_definition()
    assert definition.name == "empty-args"
    assert definition.parameters["type"] == "object"


def test_ai_message_supports_tool_fields() -> None:
    message = AIMessage(
        role="assistant",
        content="",
        tool_calls=[
            ToolCall(
                id="call_1",
                name="calculator",
                arguments={"operation": "add", "a": 1, "b": 2},
            )
        ],
    )
    assert message.tool_calls is not None
    assert message.tool_calls[0].name == "calculator"


def test_ai_message_supports_tool_role() -> None:
    message = AIMessage(
        role="tool",
        content="3",
        tool_call_id="call_1",
    )
    assert message.role == "tool"
    assert message.tool_call_id == "call_1"


def test_ai_message_invalid_tool_role_rejected() -> None:
    with pytest.raises(ValidationError):
        AIMessage(role="function", content="x")


def test_ai_response_supports_tool_calls() -> None:
    response = AIResponse.ok(
        content="Thinking...",
        model_name="fake-model",
        tool_calls=[
            ToolCall(
                id="call_1",
                name="calculator",
                arguments={"operation": "add", "a": 2, "b": 2},
            )
        ],
    )
    assert response.success is True
    assert response.tool_calls is not None
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "calculator"


def test_ai_response_tool_calls_default_none() -> None:
    response = AIResponse.ok(content="plain answer")
    assert response.tool_calls is None


def test_parse_args_validates_calculator_arguments() -> None:
    tool = CalculatorTool()
    parsed = tool.parse_args(operation="add", a=8, b=4)
    assert parsed.operation == "add"
    assert parsed.a == 8
    assert parsed.b == 4


def test_parse_args_rejects_invalid_operation() -> None:
    tool = CalculatorTool()
    with pytest.raises(ValidationError):
        tool.parse_args(operation="sqrt", a=8, b=4)


def test_parse_args_rejects_unknown_kwargs() -> None:
    tool = CalculatorTool()
    with pytest.raises(ValidationError):
        tool.parse_args(operation="add", a=8, b=4, power=2)


class ToolStubBase(CalculatorTool):
    pass


class EmptyArgsTool(ToolStubBase):
    name = "empty-args"
    description = "A tool with no arguments."
    input_schema = ToolArguments
