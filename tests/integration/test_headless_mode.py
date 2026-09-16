"""Integration tests for the headless runtime mode.

Verifies that the headless runtime is suitable for CI/tests: no hardware,
no network, all fakes, deterministic behavior.
"""

import asyncio

from app.config.schema import MissMinutesConfig
from app.runtime.runtime import MissMinutesRuntime


def _run(coro):
    return asyncio.run(coro)


def test_headless_creates_with_defaults():
    config = MissMinutesConfig()
    runtime = MissMinutesRuntime.create_headless(config)
    assert runtime is not None
    assert runtime.config is config
    assert runtime.ready is False


def test_headless_startup_all_fakes():
    async def flow():
        config = MissMinutesConfig()
        config.voice.enabled = True
        runtime = MissMinutesRuntime.create_headless(config)
        await runtime.startup()
        assert runtime.ready is True
        # All subsystems available with fakes
        assert runtime.orchestrator is not None
        assert runtime.security is not None
        assert runtime.voice_service is not None
        await runtime.shutdown()
    _run(flow())


def test_headless_text_request():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime.create_headless(config)
        await runtime.startup()
        response = await runtime.handle_text("Hello headless")
        assert response.success is True
        assert response.source == "text"
        assert response.text_response is not None
        await runtime.shutdown()
    _run(flow())


def test_headless_voice_request():
    async def flow():
        config = MissMinutesConfig()
        config.voice.enabled = True
        runtime = MissMinutesRuntime.create_headless(config)
        await runtime.startup()
        response = await runtime.handle_voice(b"test audio")
        assert response.source == "voice"
        await runtime.shutdown()
    _run(flow())


def test_headless_multiple_requests():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime.create_headless(config)
        await runtime.startup()
        for i in range(5):
            response = await runtime.handle_text(f"Request {i}")
            assert response.success is True
        assert runtime.request_count == 5
        await runtime.shutdown()
    _run(flow())


def test_headless_capabilities():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime.create_headless(config)
        await runtime.startup()
        caps = runtime.capabilities.all_capabilities()
        # Core capabilities should be available
        assert caps.get("text") is True
        assert caps.get("agents") is True
        assert caps.get("security") is True
        await runtime.shutdown()
    _run(flow())


def test_headless_health_report():
    async def flow():
        config = MissMinutesConfig()
        runtime = MissMinutesRuntime.create_headless(config)
        await runtime.startup()
        report = runtime.capabilities.health_report(
            ready=runtime.ready,
            request_count=runtime.request_count,
        )
        assert report.ready is True
        assert report.uptime_seconds >= 0
        assert report.request_count == 0
        await runtime.shutdown()
    _run(flow())


def test_headless_no_real_providers():
    """Verify headless mode does not import real providers."""
    async def flow():
        config = MissMinutesConfig()
        config.voice.enabled = True
        runtime = MissMinutesRuntime.create_headless(config)
        await runtime.startup()
        # Voice service should use fake STT/TTS
        if runtime.voice_service is not None:
            stt = runtime.voice_service._stt
            tts = runtime.voice_service._tts
            assert "fake" in type(stt).__name__.lower() or "fake" in stt.name.lower()
            assert "fake" in type(tts).__name__.lower() or "fake" in tts.name.lower()
        await runtime.shutdown()
    _run(flow())
