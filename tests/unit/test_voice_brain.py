import asyncio
from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from app.core.ai import AIMessage, AIModel, AIResponse, ToolCall, ToolDefinition
from app.core.orchestrator import Orchestrator
from app.core.permissions import ToolPermission
from app.core.task import Task
from app.security.policy import DenyAllPolicy
from app.tools.base import Tool, ToolArguments, ToolResult
from app.voice.brain import (
    ConversationalVoiceBrain,
    FakeVoiceBrain,
    OrchestratorVoiceBrain,
    VoiceBrain,
    VoiceBrainRequest,
    VoiceBrainResult,
)
from app.voice.fakes import FakeAIModel
from app.voice.language import LanguageLabel, ResponseStyle


def _run(coro):
    return asyncio.run(coro)


def _request(text: str = "hello there", *, style: ResponseStyle | None = None) -> VoiceBrainRequest:
    return VoiceBrainRequest(
        session_id="s1",
        turn_id=1,
        text=text,
        language="en",
        style=style or ResponseStyle(label=LanguageLabel.ENGLISH),
    )


def test_brain_request_rejects_blank_text() -> None:
    with pytest.raises(ValidationError):
        VoiceBrainRequest(text="   ")


def test_brain_result_factories() -> None:
    ok = VoiceBrainResult.ok("Hi")
    assert ok.success is True
    assert ok.response == "Hi"
    failed = VoiceBrainResult.fail("boom", denied=True, reason_code="security_denial")
    assert failed.success is False
    assert failed.denied is True
    assert failed.reason_code == "security_denial"


def test_abstract_brain_requires_metadata() -> None:
    with pytest.raises(TypeError):

        class MissingMetadata(VoiceBrain):
            async def respond(self, request: VoiceBrainRequest) -> VoiceBrainResult:
                return VoiceBrainResult.ok("hi")


def test_conversational_brain_replies_and_keeps_history() -> None:
    model = FakeAIModel(default_reply="Hello there, how can I help?")
    brain = ConversationalVoiceBrain(model)
    first = _run(brain.respond(_request("hello there")))
    second = _run(brain.respond(_request("mera laptop")))
    assert first.success is True
    assert first.response == "Hello there, how can I help?"
    assert second.success is True
    assert len(brain.history) == 4  # user+assistant twice
    assert brain.history[0].role == "user"
    assert brain.history[0].content == "hello there"


def test_conversational_brain_includes_style_guidance() -> None:
    model = FakeAIModel(default_reply="आप कैसे हैं?")
    brain = ConversationalVoiceBrain(model)
    _run(
        brain.respond(
            _request("hindi namaste", style=ResponseStyle(label=LanguageLabel.HINDI))
        )
    )
    messages = model.chat_requests[0]
    joint = " ".join(f"{message.role}:{message.content}" for message in messages)
    assert "Response style" in joint
    assert "Reply in Hindi" in joint


def test_conversational_brain_controlled_failures() -> None:
    failing = FakeAIModel(respond_fail=True)
    result = _run(ConversationalVoiceBrain(failing).respond(_request()))
    assert result.success is False


def test_conversational_brain_handles_provider_exception() -> None:
    class ExplodingModel(FakeAIModel):
        async def chat(self, messages, *, tools=None) -> AIResponse:
            raise RuntimeError("ai down")

    model = ExplodingModel()
    result = _run(ConversationalVoiceBrain(model).respond(_request()))
    assert result.success is False
    assert "raised an error" in (result.error or "")


class ReadTool(Tool):
    name = "read-tool"
    description = "Read-only tool for the voice security test."
    input_schema = ToolArguments
    permission: ToolPermission = ToolPermission.READ

    def __init__(self) -> None:
        self.called = False

    async def execute(self, **kwargs: object) -> ToolResult:
        self.called = True
        return ToolResult.ok(output="read-output")


class ScriptedAIModel(AIModel):
    name = "scripted-tool-ai"
    description = "Scripted AI that issues one tool call."

    def __init__(self, tool_call: ToolCall) -> None:
        self._tool_call = tool_call
        self._calls = 0

    async def chat(
        self,
        messages: Sequence[AIMessage],
        *,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AIResponse:
        self._calls += 1
        if self._calls == 1:
            return AIResponse.ok(content="calling a tool", tool_calls=[self._tool_call])
        return AIResponse.ok(content="")


def test_orchestrator_brain_cannot_bypass_security() -> None:
    tool = ReadTool()
    orchestrator = Orchestrator(
        ai_model=ScriptedAIModel(ToolCall(id="call-1", name=tool.name, arguments={})),
        security=DenyAllPolicy(),
    )
    orchestrator.register_tool(tool)
    brain = OrchestratorVoiceBrain(orchestrator)

    result = _run(brain.respond(_request("Delete all project files.")))

    assert tool.called is False
    assert orchestrator.security is not None
    denied = [
        event
        for event in orchestrator.security.audit_store.snapshot()
        if event.reason_code == "deny_all"
    ]
    assert denied
    dispatch_events = [
        event
        for event in orchestrator.security.audit_store.snapshot()
        if event.action == "voice:dispatch_task"
    ]
    assert dispatch_events
    assert dispatch_events[0].origin == "voice"


def test_orchestrator_brain_allows_under_allowed_policy() -> None:
    from app.security.models import (
        Permission,
        PermissionCategory,
        PermissionRule,
    )
    from app.security.policy import AllowDenyPolicy

    tool = ReadTool()
    policy = AllowDenyPolicy(
        rules=[
            PermissionRule(
                permission=Permission(category=PermissionCategory.READ),
                effect="allow",
            )
        ]
    )
    orchestrator = Orchestrator(
        ai_model=ScriptedAIModel(ToolCall(id="call-2", name=tool.name, arguments={})),
        security=policy,
    )
    orchestrator.register_tool(tool)
    brain = OrchestratorVoiceBrain(orchestrator)

    result = _run(brain.respond(_request("read something")))
    assert result.success is True
    assert tool.called is True
    assert result.response == "Understood."


def test_fake_brain_scripted_results() -> None:
    brain = FakeVoiceBrain(
        results=[
            VoiceBrainResult.ok("first"),
            VoiceBrainResult.fail("nope", denied=True),
        ]
    )
    first = _run(brain.respond(_request("a")))
    second = _run(brain.respond(_request("b")))
    third = _run(brain.respond(_request("c")))
    assert first.response == "first"
    assert second.denied is True
    assert third.response == "Understood."
    assert len(brain.requests) == 3


def test_fake_brain_can_raise() -> None:
    brain = FakeVoiceBrain(raise_error=RuntimeError("brain boom"))
    with pytest.raises(RuntimeError):
        _run(brain.respond(_request("x")))