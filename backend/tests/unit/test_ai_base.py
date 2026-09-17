import asyncio
from collections.abc import Sequence

import pytest

from app.core.ai import (
    AIError,
    AIMessage,
    AIModel,
    AIResponse,
    ToolDefinition,
)


class SampleAIModel(AIModel):
    name = "sample-ai"
    description = "A sample AI model for tests."

    def __init__(self, response: AIResponse) -> None:
        self._response = response

    async def chat(
        self,
        messages: Sequence[AIMessage],
        *,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AIResponse:
        return self._response


def test_ai_response_model_fields() -> None:
    response = AIResponse(success=True, content="answer", model_name="gpt-x")
    assert response.success is True
    assert response.content == "answer"
    assert response.model_name == "gpt-x"
    assert response.error is None


def test_ai_response_ok_factory() -> None:
    response = AIResponse.ok(content="answer", model_name="gpt-x")
    assert response.success is True
    assert response.content == "answer"
    assert response.model_name == "gpt-x"
    assert response.error is None


def test_ai_response_fail_factory() -> None:
    response = AIResponse.fail(error="boom")
    assert response.success is False
    assert response.error == "boom"
    assert response.content is None
    assert response.model_name is None


def test_ai_message_validation() -> None:
    message = AIMessage(role="user", content="hello")
    assert message.role == "user"
    assert message.content == "hello"


def test_ai_model_is_abstract() -> None:
    with pytest.raises(TypeError):
        AIModel()


def test_ai_model_requires_metadata() -> None:
    with pytest.raises(TypeError, match="name"):

        class MissingMetadata(AIModel):
            async def chat(
                self,
                messages: Sequence[AIMessage],
                *,
                tools: Sequence[ToolDefinition] | None = None,
            ) -> AIResponse:
                return AIResponse.ok(content="x")


def test_concrete_sample_satisfies_interface() -> None:
    model = SampleAIModel(response=AIResponse.ok(content="hi"))
    assert isinstance(model, AIModel)
    result = asyncio.run(model.chat([AIMessage(role="user", content="hi")]))
    assert result.content == "hi"


def test_ai_error_is_exception() -> None:
    error = AIError("boom")
    assert isinstance(error, Exception)
    assert str(error) == "boom"
