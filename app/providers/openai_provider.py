import json
import logging
import os
from collections.abc import Sequence

from openai import AsyncOpenAI

from app.core.ai import (
    AIMessage,
    AIModel,
    AIResponse,
    ToolCall,
    ToolDefinition,
)

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
# ADD API HERE: OPENAI_API_KEY
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
# ADD API HERE: OPENAI_MODEL
OPENAI_MODEL_ENV = "OPENAI_MODEL"


class OpenAIProvider(AIModel):
    name = "openai"
    description = "OpenAI chat completions provider."

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self._api_key = self._resolve_api_key(api_key)
        self._model = (model or os.getenv(OPENAI_MODEL_ENV) or DEFAULT_OPENAI_MODEL).strip()
        self._client = client

    @property
    def model(self) -> str:
        return self._model

    def _resolve_api_key(self, api_key: str | None) -> str | None:
        if api_key is not None:
            return api_key.strip() or None
        return os.getenv(OPENAI_API_KEY_ENV) or None

    def _build_messages_payload(self, messages: Sequence[AIMessage]) -> list[dict]:
        payload: list[dict] = []
        for message in messages:
            item: dict = {"role": message.role, "content": message.content}
            if message.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.name,
                            "arguments": json.dumps(tool_call.arguments),
                        },
                    }
                    for tool_call in message.tool_calls
                ]
            if message.tool_call_id is not None:
                item["tool_call_id"] = message.tool_call_id
            payload.append(item)
        return payload

    def _build_tools_payload(self, tools: Sequence[ToolDefinition]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    def _parse_tool_calls(self, raw_tool_calls: object) -> list[ToolCall] | None:
        tool_calls: list[ToolCall] = []
        for raw in raw_tool_calls or []:
            arguments = getattr(getattr(raw, "function", None), "arguments", None)
            try:
                parsed_arguments = json.loads(arguments) if isinstance(arguments, str) else {}
            except json.JSONDecodeError:
                parsed_arguments = {}
            tool_calls.append(
                ToolCall(
                    id=getattr(raw, "id", "") or "",
                    name=getattr(raw.function, "name", "") or "",
                    arguments=parsed_arguments,
                )
            )
        return tool_calls or None

    async def chat(
        self,
        messages: Sequence[AIMessage],
        *,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AIResponse:
        if self._client is None:
            if not self._api_key:
                self._logger.error(
                    "OpenAI provider is not configured: %s is missing or empty",
                    OPENAI_API_KEY_ENV,
                )
                return AIResponse.fail("OpenAI provider is not configured: API key is missing")
            self._client = AsyncOpenAI(api_key=self._api_key)

        payload = self._build_messages_payload(messages)
        kwargs: dict = {}
        if tools:
            kwargs["tools"] = self._build_tools_payload(tools)
        try:
            completion = await self._client.chat.completions.create(
                model=self._model,
                messages=payload,
                **kwargs,
            )
        except Exception as exc:
            self._logger.error("OpenAI chat completion failed: %s", type(exc).__name__)
            return AIResponse.fail("OpenAI provider call failed")

        message = completion.choices[0].message
        content = message.content or ""
        raw_tool_calls = getattr(message, "tool_calls", None)
        tool_calls = self._parse_tool_calls(raw_tool_calls) if raw_tool_calls else None
        return AIResponse.ok(
            content=content,
            model_name=completion.model,
            tool_calls=tool_calls,
        )
