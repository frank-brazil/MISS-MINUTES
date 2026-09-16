import asyncio

import pytest

from app.core.ai import AIMessage, AIResponse, ToolCall, ToolDefinition
from app.providers.openai_provider import (
    DEFAULT_OPENAI_MODEL,
    OPENAI_API_KEY_ENV,
    OPENAI_MODEL_ENV,
    OpenAIProvider,
)


class FakeMessage:
    content = "hello from openai"


class FakeChoice:
    message = FakeMessage()


class FakeCompletion:
    model = "fake-model"
    choices = [FakeChoice()]


class FakeCompletions:
    @staticmethod
    async def create(**kwargs: object) -> FakeCompletion:
        return FakeCompletion()


class FakeChat:
    completions = FakeCompletions()


class FakeClient:
    chat = FakeChat()


class RaisingCompletions:
    @staticmethod
    async def create(**kwargs: object) -> FakeCompletion:
        raise RuntimeError("connection refused")


class RaisingChat:
    completions = RaisingCompletions()


class RaisingClient:
    chat = RaisingChat()


class RecordingCompletions:
    def __init__(self) -> None:
        self.last_kwargs: dict = {}

    async def create(self, **kwargs: object) -> FakeCompletion:
        self.last_kwargs = dict(kwargs)
        return FakeCompletion()


class RecordingChat:
    def __init__(self) -> None:
        self.completions = RecordingCompletions()


class RecordingClient:
    def __init__(self) -> None:
        self.chat = RecordingChat()


class ToolCallFunction:
    name = "calculator"
    arguments = '{"operation": "add", "a": 1, "b": 2}'


class RawToolCall:
    id = "call_abc"
    function = ToolCallFunction()


class ToolCallingMessage:
    content = ""
    tool_calls = [RawToolCall()]


class ToolCallingChoice:
    message = ToolCallingMessage()


class ToolCallingCompletion:
    model = "fake-model"
    choices = [ToolCallingChoice()]


class ToolCallingCompletions:
    @staticmethod
    async def create(**kwargs: object) -> ToolCallingCompletion:
        return ToolCallingCompletion()


class ToolCallingChat:
    completions = ToolCallingCompletions()


class ToolCallingClient:
    chat = ToolCallingChat()


def test_provider_reads_env_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENAI_API_KEY_ENV, "sk-env-key")
    monkeypatch.setenv(OPENAI_MODEL_ENV, "gpt-4o")
    provider = OpenAIProvider(client=FakeClient())
    assert provider.model == "gpt-4o"
    result = asyncio.run(provider.chat([AIMessage(role="user", content="hi")]))
    assert result.success is True
    assert result.content == "hello from openai"


def test_explicit_config_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OPENAI_API_KEY_ENV, "sk-env-key")
    monkeypatch.setenv(OPENAI_MODEL_ENV, "gpt-4o")
    provider = OpenAIProvider(api_key="sk-explicit", model="gpt-4o-mini")
    assert provider.model == "gpt-4o-mini"


def test_default_model_when_env_and_arg_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(OPENAI_MODEL_ENV, raising=False)
    provider = OpenAIProvider(api_key="sk-test")
    assert provider.model == DEFAULT_OPENAI_MODEL


def test_missing_api_key_returns_controlled_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(OPENAI_API_KEY_ENV, raising=False)
    monkeypatch.delenv(OPENAI_MODEL_ENV, raising=False)
    provider = OpenAIProvider()
    result = asyncio.run(provider.chat([AIMessage(role="user", content="hi")]))
    assert isinstance(result, AIResponse)
    assert result.success is False
    assert result.error is not None
    assert "API key" in (result.error or "")
    assert result.content is None


def test_blank_api_key_treated_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(OPENAI_API_KEY_ENV, raising=False)
    provider = OpenAIProvider(api_key="   ")
    result = asyncio.run(provider.chat([AIMessage(role="user", content="hi")]))
    assert result.success is False


def test_successful_provider_call_with_mocked_client() -> None:
    provider = OpenAIProvider(api_key="sk-test", client=FakeClient())
    result = asyncio.run(provider.chat([AIMessage(role="user", content="hi")]))
    assert result.success is True
    assert result.content == "hello from openai"
    assert result.model_name == "fake-model"
    assert result.error is None


def test_provider_failure_with_mocked_client() -> None:
    provider = OpenAIProvider(api_key="sk-test", client=RaisingClient())
    result = asyncio.run(provider.chat([AIMessage(role="user", content="hi")]))
    assert result.success is False
    assert result.error == "OpenAI provider call failed"
    assert result.content is None


def test_provider_sends_tool_definitions_to_client() -> None:
    client = RecordingClient()
    provider = OpenAIProvider(api_key="sk-test", client=client)
    messages = [AIMessage(role="user", content="calculate 1 + 2")]
    tools = [
        ToolDefinition(
            name="calculator",
            description="Adds numbers.",
            parameters={"type": "object", "properties": {}},
        )
    ]
    result = asyncio.run(provider.chat(messages, tools=tools))
    assert result.success is True
    sent_tools = client.chat.completions.last_kwargs.get("tools")
    assert sent_tools is not None
    assert len(sent_tools) == 1
    assert sent_tools[0]["type"] == "function"
    assert sent_tools[0]["function"]["name"] == "calculator"


def test_provider_omits_tools_when_none_supplied() -> None:
    client = RecordingClient()
    provider = OpenAIProvider(api_key="sk-test", client=client)
    result = asyncio.run(
        provider.chat([AIMessage(role="user", content="hi")])
    )
    assert result.success is True
    assert "tools" not in client.chat.completions.last_kwargs


def test_provider_parses_tool_calls() -> None:
    provider = OpenAIProvider(api_key="sk-test", client=ToolCallingClient())
    result = asyncio.run(
        provider.chat([AIMessage(role="user", content="calculate")])
    )
    assert result.success is True
    assert result.content == ""
    assert result.tool_calls is not None
    tool_call = result.tool_calls[0]
    assert isinstance(tool_call, ToolCall)
    assert tool_call.id == "call_abc"
    assert tool_call.name == "calculator"
    assert tool_call.arguments == {"operation": "add", "a": 1, "b": 2}


def test_provider_messages_include_tool_result_metadata() -> None:
    client = RecordingClient()
    provider = OpenAIProvider(api_key="sk-test", client=client)
    messages = [
        AIMessage(role="user", content="calculate"),
        AIMessage(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(
                    id="call_1",
                    name="calculator",
                    arguments={"operation": "add", "a": 1, "b": 2},
                )
            ],
        ),
        AIMessage(role="tool", content="3", tool_call_id="call_1"),
    ]
    result = asyncio.run(provider.chat(messages))
    assert result.success is True
    sent = client.chat.completions.last_kwargs.get("messages")
    assert sent is not None
    assert sent[0] == {"role": "user", "content": "calculate"}
    assert sent[1]["role"] == "assistant"
    assert sent[1]["tool_calls"][0]["id"] == "call_1"
    assert sent[1]["tool_calls"][0]["type"] == "function"
    assert sent[1]["tool_calls"][0]["function"]["name"] == "calculator"
    assert sent[2] == {"role": "tool", "content": "3", "tool_call_id": "call_1"}
