import asyncio
from uuid import uuid4

import pytest

from app.voice.audio import AudioFrame
from app.voice.base import AudioData, TextToSpeechRequest
from app.voice.streaming import (
    FakeStreamingSTTProvider,
    FakeStreamingTTSProvider,
    StreamingError,
    StreamingSTTProvider,
    StreamingTTSProvider,
    StreamingTtsStream,
)


def _run(coro):
    return asyncio.run(coro)


def _frame(content: bytes, seq: int = 0) -> AudioFrame:
    return AudioFrame(content=content, format="wav", sample_rate=16000)


def test_streaming_stt_delivers_partials_and_final() -> None:
    provider = FakeStreamingSTTProvider(
        fixtures={b"hello there".decode("utf-8"): "Hello there, how can I help?"}
    )

    async def scenario() -> tuple:
        session_id = await provider.start_transcription()
        partial = await provider.push_audio(session_id, _frame(b"hello "))
        interim = await provider.push_audio(session_id, _frame(b"there"))
        final = await provider.finalize(session_id)
        return partial, interim, final

    partial, interim, final = _run(scenario())
    assert partial.final is False
    assert partial.text == "hello "
    assert interim.text == "hello there"
    assert final is not None and final.success is True
    assert final.text == "Hello there, how can I help?"
    assert provider.active_sessions == ()


def test_streaming_stt_failure_is_controlled() -> None:
    provider = FakeStreamingSTTProvider(fixtures={"x": "y"}, fail=True)
    result = _run(session_flow(provider))
    assert result.success is False
    assert result.text is None


async def session_flow(provider: FakeStreamingSTTProvider) -> object:
    session_id = await provider.start_transcription()
    await provider.push_audio(session_id, _frame(b"x"))
    return await provider.finalize(session_id)


def test_streaming_stt_unknown_audio_fails() -> None:
    provider = FakeStreamingSTTProvider(fixtures={})
    result = _run(session_flow(provider))
    assert result.success is False
    assert "fixture" in (result.error or "")


def test_streaming_stt_raise_error_propagates() -> None:
    provider = FakeStreamingSTTProvider(raise_error=StreamingError("boom"))

    async def scenario() -> None:
        session_id = await provider.start_transcription()
        await provider.push_audio(session_id, _frame(b"x"))

    with pytest.raises(StreamingError):
        _run(scenario())


def test_streaming_stt_duplicate_session_rejected() -> None:
    provider = FakeStreamingSTTProvider()
    session_id = uuid4()

    async def scenario() -> None:
        await provider.start_transcription(transcription_id=session_id)
        await provider.start_transcription(transcription_id=session_id)

    with pytest.raises(ValueError):
        _run(scenario())


def test_streaming_tts_splits_words_into_chunks() -> None:
    provider = FakeStreamingTTSProvider()

    async def scenario() -> list:
        stream = await provider.synthesize_stream(
            TextToSpeechRequest(text="hello there world")
        )
        chunks = []
        while True:
            chunk = await stream.next_chunk()
            if chunk is None:
                break
            chunks.append(chunk)
        await stream.close()
        return chunks

    chunks = _run(scenario())
    assert [chunk.content.decode("utf-8") for chunk in chunks] == [
        "hello",
        "there",
        "world",
    ]
    assert len(provider.requests) == 1


def test_streaming_tts_failure_raises_streaming_error() -> None:
    provider = FakeStreamingTTSProvider(fail=True)

    async def scenario() -> None:
        stream = await provider.synthesize_stream(TextToSpeechRequest(text="hi"))
        await stream.next_chunk()

    with pytest.raises(StreamingError):
        _run(scenario())


def test_streaming_tts_raise_error_propagates() -> None:
    provider = FakeStreamingTTSProvider(raise_error=StreamingError("tts boom"))

    async def scenario() -> None:
        await provider.synthesize_stream(TextToSpeechRequest(text="hi"))

    with pytest.raises(StreamingError):
        _run(scenario())


def test_streaming_tts_closed_stream_returns_none() -> None:
    provider = FakeStreamingTTSProvider()

    async def scenario() -> tuple:
        stream = await provider.synthesize_stream(TextToSpeechRequest(text="hi"))
        await stream.close()
        return stream.closed, await stream.next_chunk()

    closed, chunk = _run(scenario())
    assert closed is True
    assert chunk is None


def test_streaming_stt_and_tts_are_distinct_boundaries() -> None:
    assert not issubclass(FakeStreamingSTTProvider, StreamingTTSProvider)
    assert not issubclass(FakeStreamingTTSProvider, StreamingSTTProvider)
    assert isinstance(StreamingTtsStream, type)