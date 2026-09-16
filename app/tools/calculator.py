from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.tools.base import Tool, ToolResult


class CalculatorOperation(StrEnum):
    ADD = "add"
    SUBTRACT = "subtract"
    MULTIPLY = "multiply"
    DIVIDE = "divide"


class CalculatorArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: CalculatorOperation = Field(description="Arithmetic operation to perform")
    a: float = Field(description="First operand")
    b: float = Field(description="Second operand")


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value)


class CalculatorTool(Tool):
    name = "calculator"
    description = (
        "Performs basic arithmetic on two numbers. Supported operations: "
        "add, subtract, multiply, divide."
    )
    input_schema = CalculatorArguments

    async def execute(self, **kwargs: object) -> ToolResult:
        args = self.parse_args(**kwargs)
        try:
            if args.operation == CalculatorOperation.ADD:
                result = args.a + args.b
            elif args.operation == CalculatorOperation.SUBTRACT:
                result = args.a - args.b
            elif args.operation == CalculatorOperation.MULTIPLY:
                result = args.a * args.b
            elif args.operation == CalculatorOperation.DIVIDE:
                if args.b == 0:
                    return ToolResult.fail(error="Division by zero is not allowed")
                result = args.a / args.b
            else:
                return ToolResult.fail(error=f"Unknown operation: {args.operation}")
        except Exception as exc:
            return ToolResult.fail(error=f"Calculator error: {type(exc).__name__}")
        return ToolResult.ok(output=_format_number(result))