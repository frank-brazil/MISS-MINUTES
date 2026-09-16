"""Integration tests for the unified text and voice request paths.

Tests the full pipeline from input → normalization → orchestration → response.
"""

import asyncio
from collections.abc import Sequence

from app.config.schema import MissMinutesConfig
from app.core.ai import AIMessage, AIModel, AIResponse, ToolDefinition
from app.runtime.request import UnifiedRequest, UnifiedResponse
from app.runtime.runtime import MissMinutesRuntime


def _run(coro):
    return asyncio.run(coro)


class _TrackingAI(AIModel):
    name = "tracking-ai"
    description = "AI model that records requests."

    def __init__(self, replies: list[str] | None = None):
        self._replies = replies or ["Hello!"]
        self._count = 0
        self.requests: list[list[AIMessage]] = []

    async def chat(
        self, messages: Sequence[AIMessage], *, tools: Sequence[ToolDefinition] | None = None
    ) -> AIResponse:
        self.requests.append(list(messages))
        reply = self._replies[min(self._count, len(self._replies) - 1)]
        self._count += 1
        return AIResponse.ok(content=reply, model_name="test")


class _FailingAI(AIModel):
    name = "failing-ai"
    description = "AI model that always fails."

    async def chat(
        self, messages: Sequence[AIMessage], *, tools: Sequence[ToolDefinition] | None = None
    ) -> AIResponse:
        return AIResponse.fail(error="simulated failure")


# ------------------------------------------------------------------
# Text request
# ------------------------------------------------------------------

def test_text_request_basic():
    async def flow():
        ai = _TrackingAI(replies=["Found your notes!"])
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config, ai_model=ai)
        await runtime.startup()
        response = await runtime.handle_text("Find my DSA notes")
        assert response.success is True
        assert response.source == "text"
        assert response.text_response == "Found your notes!"
        assert response.task_id is not None
        assert len(ai.requests) == 1
        await runtime.shutdown()
    _run(flow())


def test_text_request_empty_text():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config)
        await runtime.startup()
        response = await runtime.handle_text("")
        assert response.success is False
        await runtime.shutdown()
    _run(flow())


def test_text_request_not_ready():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config)
        # no startup
        response = await runtime.handle_text("Hello")
        assert response.success is False
        assert "not ready" in response.error.lower()
    _run(flow())


def test_text_request_ai_failure():
    async def flow():
        ai = _FailingAI()
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config, ai_model=ai)
        await runtime.startup()
        response = await runtime.handle_text("This will fail")
        assert response.success is False
        assert response.error is not None
        await runtime.shutdown()
    _run(flow())


def test_text_request_increments_count():
    async def flow():
        ai = _TrackingAI()
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime(config, ai_model=ai)
        await runtime.startup()
        assert runtime.request_count == 0
        await runtime.handle_text("one")
        assert runtime.request_count == 1
        await runtime.handle_text("two")
        assert runtime.request_count == 2
        await runtime.shutdown()
    _run(flow())


# ------------------------------------------------------------------
# Voice request
# ------------------------------------------------------------------

def test_voice_request_basic():
    async def flow():
        config = MissMinutesConfig()
        config.voice.enabled = True
        runtime = MissMinutesRuntime(config)
        await runtime.startup()
        assert runtime.voice_service is not None
        response = await runtime.handle_voice(b"hello audio")
        assert response.source == "voice"
        await runtime.shutdown()
    _run(flow())


def test_voice_request_disabled():
    async def flow():
        config = MissMinutesConfig()
        config.voice.enabled = False
        runtime = MissMinutesRuntime(config)
        await runtime.startup()
        response = await runtime.handle_voice(b"hello")
        assert response.success is False
        assert "voice" in response.error.lower()
        await runtime.shutdown()
    _run(flow())


# ------------------------------------------------------------------
# Unified request model
# ------------------------------------------------------------------

def test_unified_request_validation():
    req = UnifiedRequest(source="text", text="hello")
    assert req.source == "text"
    assert req.text == "hello"
    assert req.request_id is not None


def test_unified_response_ok():
    resp = UnifiedResponse.ok("req-1", text_response="hi")
    assert resp.success is True
    assert resp.text_response == "hi"
    assert resp.error is None


def test_unified_response_fail():
    resp = UnifiedResponse.fail("req-1", error="something broke")
    assert resp.success is False
    assert resp.error == "something broke"
