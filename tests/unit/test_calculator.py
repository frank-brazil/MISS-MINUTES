import asyncio

import pytest
from pydantic import BaseModel, ValidationError

from app.tools.base import Tool, ToolResult
from app.tools.calculator import (
    CalculatorArguments,
    CalculatorOperation,
    CalculatorTool,
)


def test_calculator_metadata() -> None:
    assert CalculatorTool.name == "calculator"
    assert isinstance(CalculatorTool.description, str)
    assert CalculatorTool.description
    assert issubclass(CalculatorTool.input_schema, BaseModel)
    assert CalculatorTool.input_schema is CalculatorArguments


def test_concrete_calculator_satisfies_tool_interface() -> None:
    assert issubclass(CalculatorTool, Tool)
    tool = CalculatorTool()
    assert isinstance(tool, Tool)


def test_addition() -> None:
    tool = CalculatorTool()
    result = asyncio.run(
        tool.execute(operation="add", a=2, b=3)
    )
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.output == "5"
    assert result.error is None


def test_subtraction() -> None:
    tool = CalculatorTool()
    result = asyncio.run(
        tool.execute(operation="subtract", a=10, b=4)
    )
    assert result.success is True
    assert result.output == "6"


def test_multiplication() -> None:
    tool = CalculatorTool()
    result = asyncio.run(
        tool.execute(operation="multiply", a=6, b=7)
    )
    assert result.success is True
    assert result.output == "42"


def test_division() -> None:
    tool = CalculatorTool()
    result = asyncio.run(
        tool.execute(operation="divide", a=20, b=5)
    )
    assert result.success is True
    assert result.output == "4"


def test_division_returns_float_for_non_exact() -> None:
    tool = CalculatorTool()
    result = asyncio.run(
        tool.execute(operation="divide", a=1, b=3)
    )
    assert result.success is True
    assert float(result.output or "") == pytest.approx(1 / 3)


def test_operation_enum_values() -> None:
    assert CalculatorOperation.ADD == "add"
    assert CalculatorOperation.SUBTRACT == "subtract"
    assert CalculatorOperation.MULTIPLY == "multiply"
    assert CalculatorOperation.DIVIDE == "divide"


def test_operation_accepts_enum_and_string() -> None:
    tool = CalculatorTool()
    enum_result = asyncio.run(
        tool.execute(operation=CalculatorOperation.ADD, a=1, b=2)
    )
    string_result = asyncio.run(
        tool.execute(operation="add", a=1, b=2)
    )
    assert enum_result.success is True
    assert string_result.success is True
    assert enum_result.output == string_result.output


def test_division_by_zero_rejected() -> None:
    tool = CalculatorTool()
    result = asyncio.run(
        tool.execute(operation="divide", a=10, b=0)
    )
    assert isinstance(result, ToolResult)
    assert result.success is False
    assert result.error is not None
    assert "zero" in (result.error or "").lower()
    assert result.output is None


def test_negative_numbers() -> None:
    tool = CalculatorTool()
    result = asyncio.run(
        tool.execute(operation="add", a=-5, b=3)
    )
    assert result.success is True
    assert result.output == "-2"


def test_decimal_operands() -> None:
    tool = CalculatorTool()
    result = asyncio.run(
        tool.execute(operation="multiply", a=1.5, b=2.5)
    )
    assert result.success is True
    assert float(result.output or "") == pytest.approx(3.75)


def test_invalid_operation_rejected() -> None:
    tool = CalculatorTool()
    with pytest.raises(ValidationError):
        asyncio.run(tool.execute(operation="power", a=2, b=3))


def test_missing_operands_rejected() -> None:
    tool = CalculatorTool()
    with pytest.raises(ValidationError):
        asyncio.run(tool.execute(operation="add", a=2))


def test_non_numeric_operands_rejected() -> None:
    tool = CalculatorTool()
    with pytest.raises(ValidationError):
        asyncio.run(tool.execute(operation="add", a="x", b=3))


def test_extra_arguments_rejected_by_schema() -> None:
    args = CalculatorArguments(operation="add", a=1, b=2)
    with pytest.raises(ValidationError):
        args.model_validate({"operation": "add", "a": 1, "b": 2, "extra": "x"})


def test_risk_expression_string_rejected() -> None:
    tool = CalculatorTool()
    with pytest.raises(ValidationError):
        asyncio.run(
            tool.execute(operation="add", a="__import__('os')", b=1)
        )
