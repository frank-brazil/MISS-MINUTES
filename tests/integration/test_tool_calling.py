import asyncio
from collections.abc import Sequence

import pytest

from app.core.ai import AIMessage, AIModel, AIResponse, ToolCall, ToolDefinition
from app.core.orchestrator import Orchestrator
from app.core.task import Task
from app.tools.calculator import CalculatorTool


class ScriptedAIModel(AIModel):
    name = "scripted-ai"
    description = "A fake AI model that follows a fixed response script."

    def __init__(self, responses: Sequence[AIResponse]) -> None:
        if not responses:
            raise ValueError("responses must not be empty")
        self._responses = list(responses)
        self.call_count = 0
        self.received_messages: list[list[AIMessage]] = []
        self.received_tools: list[Sequence[ToolDefinition] | None] = []
        self.requested_tool_calls: list[list[ToolCall]] = []

    async def chat(
        self,
        messages: Sequence[AIMessage],
        *,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AIResponse:
        self.received_messages.append(list(messages))
        self.received_tools.append(tools)
        if self.call_count < len(self._responses):
            response = self._responses[self.call_count]
        else:
            response = self._responses[-1]
        self.call_count += 1
        if response.tool_calls:
            self.requested_tool_calls.append(list(response.tool_calls))
        return response

    @property
    def user_messages(self) -> list[str]:
        return [
            message.content
            for messages in self.received_messages
            for message in messages
            if message.role == "user"
        ]

    @property
    def assistant_tool_calls(self) -> list[list[ToolCall]]:
        return self.requested_tool_calls

    @property
    def tool_result_messages(self) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for messages in self.received_messages:
            for message in messages:
                if message.role == "tool" and message.tool_call_id:
                    item = (message.tool_call_id, message.content)
                    if item not in seen:
                        seen.add(item)
                        results.append(item)
        return results


def test_single_calculator_tool_call() -> None:
    ai = ScriptedAIModel(
        [
            AIResponse(
                success=True,
                content="I will calculate.",
                tool_calls=[
                    ToolCall(
                        id="call_add",
                        name="calculator",
                        arguments={"operation": "add", "a": 2, "b": 3},
                    )
                ],
            ),
            AIResponse.ok(content="2 + 3 equals 5."),
        ]
    )
    orch = Orchestrator(ai_model=ai)
    orch.register_tool(CalculatorTool())
    task = Task(description="What is 2 + 3?")
    result = asyncio.run(orch.execute(task))

    assert result.success is True
    assert result.status == "completed"
    assert result.output == "2 + 3 equals 5."
    assert result.error is None

    assert len(ai.received_messages) == 2
    assert ai.received_tools[0] is not None
    assert [t.name for t in ai.received_tools[0] or ()] == ["calculator"]

    tool_call = ai.assistant_tool_calls[0][0]
    assert tool_call.name == "calculator"

    results = ai.tool_result_messages
    assert len(results) == 1
    assert results[0][0] == "call_add"
    assert results[0][1] == "5"


def test_multiple_sequential_tool_calls() -> None:
    first = AIResponse(
        success=True,
        content="",
        tool_calls=[
            ToolCall(
                id="call_mul",
                name="calculator",
                arguments={"operation": "multiply", "a": 6, "b": 7},
            )
        ],
    )
    second = AIResponse(
        success=True,
        content="",
        tool_calls=[
            ToolCall(
                id="call_add",
                name="calculator",
                arguments={"operation": "add", "a": 42, "b": 8},
            )
        ],
    )
    final = AIResponse.ok(content="6 * 7 is 42, and 42 + 8 is 50.")
    ai = ScriptedAIModel([first, second, final])
    orch = Orchestrator(ai_model=ai)
    orch.register_tool(CalculatorTool())
    task = Task(description="What is 6 * 7, then add 8?")
    result = asyncio.run(orch.execute(task))

    assert result.success is True
    assert "50" in (result.output or "")

    calls = ai.assistant_tool_calls
    assert len(calls) == 2
    assert calls[0][0].name == "calculator"
    assert calls[1][0].name == "calculator"

    results = ai.tool_result_messages
    assert len(results) == 2
    assert results[0][1] == "42"
    assert results[1][1] == "50"


def test_multiple_tool_calls_in_one_response() -> None:
    response = AIResponse(
        success=True,
        content="",
        tool_calls=[
            ToolCall(
                id="call_1",
                name="calculator",
                arguments={"operation": "add", "a": 1, "b": 2},
            ),
            ToolCall(
                id="call_2",
                name="calculator",
                arguments={"operation": "subtract", "a": 10, "b": 4},
            ),
        ],
    )
    ai = ScriptedAIModel([response, AIResponse.ok(content="Done.")])
    orch = Orchestrator(ai_model=ai)
    orch.register_tool(CalculatorTool())
    task = Task(description="Perform two calculations.")
    result = asyncio.run(orch.execute(task))

    assert result.success is True
    assert result.output == "Done."
    results = ai.tool_result_messages
    assert len(results) == 2
    assert results[0][1] == "3"
    assert results[1][1] == "6"


def test_unknown_tool_call_returns_controlled_failure() -> None:
    ai = ScriptedAIModel(
        [
            AIResponse(
                success=True,
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_unknown",
                        name="definitely-not-registered",
                        arguments={},
                    )
                ],
            ),
            AIResponse.ok(content="I cannot do that."),
        ]
    )
    orch = Orchestrator(ai_model=ai)
    orch.register_tool(CalculatorTool())
    task = Task(description="Try an unknown tool.")
    result = asyncio.run(orch.execute(task))

    assert result.success is True
    assert result.output == "I cannot do that."
    result_messages = ai.tool_result_messages
    assert len(result_messages) == 1
    assert "Unknown tool" in result_messages[0][1]


def test_tool_execution_failure_path() -> None:
    ai = ScriptedAIModel(
        [
            AIResponse(
                success=True,
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_div0",
                        name="calculator",
                        arguments={"operation": "divide", "a": 10, "b": 0},
                    )
                ],
            ),
            AIResponse.ok(content="Division by zero is not allowed."),
        ]
    )
    orch = Orchestrator(ai_model=ai)
    orch.register_tool(CalculatorTool())
    task = Task(description="Divide by zero.")
    result = asyncio.run(orch.execute(task))

    assert result.success is True
    assert result.output == "Division by zero is not allowed."
    result_messages = ai.tool_result_messages
    assert len(result_messages) == 1
    assert "zero" in result_messages[0][1].lower()


def test_infinite_tool_loop_prevented() -> None:
    forever = AIResponse(
        success=True,
        content="",
        tool_calls=[
            ToolCall(
                id="call_loop",
                name="calculator",
                arguments={"operation": "add", "a": 1, "b": 1},
            )
        ],
    )
    ai = ScriptedAIModel([forever])
    orch = Orchestrator(ai_model=ai)
    orch.register_tool(CalculatorTool())
    task = Task(description="Loop forever.")
    result = asyncio.run(orch.execute(task))

    assert result.success is False
    assert result.status == "failed"
    assert result.error is not None
    assert "Maximum tool-call limit" in result.error
    assert ai.call_count <= 11


def test_ai_model_failure_after_tool_call() -> None:
    ai = ScriptedAIModel(
        [
            AIResponse(
                success=True,
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_add",
                        name="calculator",
                        arguments={"operation": "add", "a": 1, "b": 1},
                    )
                ],
            ),
            AIResponse.fail(error="model went down"),
        ]
    )
    orch = Orchestrator(ai_model=ai)
    orch.register_tool(CalculatorTool())
    task = Task(description="Calculate then fail.")
    result = asyncio.run(orch.execute(task))

    assert result.success is False
    assert result.status == "failed"
    assert result.error == "model went down"


def test_tools_are_sent_to_ai_without_registration() -> None:
    ai = ScriptedAIModel([AIResponse.ok(content="no tools")])
    orch = Orchestrator(ai_model=ai)
    task = Task(description="Simple task.")
    result = asyncio.run(orch.execute(task))

    assert result.success is True
    assert result.output == "no tools"
    assert ai.received_tools[0] is None