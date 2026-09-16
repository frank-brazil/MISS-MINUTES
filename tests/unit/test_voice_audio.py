import asyncio

import pytest
from pydantic import ValidationError

from app.voice.audio import (
    AudioCaptureProvider,
    AudioCaptureState,
    AudioFrame,
    CaptureError,
    FakeAudioCaptureProvider,
)
from app.voice.base import AudioData, SpeechError

FRAME_BYTES = b"hello there"


def _audio(content: bytes = FRAME_BYTES, *, format: str = "wav") -> AudioData:
    return AudioData(content=content, format=format, sample_rate=16000)


def test_capture_error_is_speech_error() -> None:
    assert issubclass(CaptureError, SpeechError)


def test_audio_frame_defaults_are_unique() -> None:
    frame_a = AudioFrame(content=FRAME_BYTES, format="wav")
    frame_b = AudioFrame(content=FRAME_BYTES, format="wav")
    assert frame_a.frame_id != frame_b.frame_id
    assert frame_a.captured_at is not None


def test_audio_frame_rejects_invalid_sample_rate() -> None:
    with pytest.raises(ValidationError):
        AudioFrame(content=FRAME_BYTES, format="wav", sample_rate=0)


def test_audio_frame_subclass_of_audio_data() -> None:
    frame = AudioFrame(content=FRAME_BYTES, format="wav")
    assert frame.content == FRAME_BYTES
    assert frame.format == "wav"
    assert frame.sample_rate == 16000


def test_abstract_capture_provider_requires_metadata() -> None:
    with pytest.raises(TypeError):

        class MissingMetadata(AudioCaptureProvider):
            async def start(self) -> None:
                pass


def test_fake_capture_delivers_frames_in_order() -> None:
    provider = FakeAudioCaptureProvider([_audio(b"one"), _audio(b"two")])

    async def scenario() -> tuple:
        await provider.start()
        first = await provider.read()
        second = await provider.read()
        empty = await provider.read()
        await provider.close()
        return first, second, empty

    first, second, empty = asyncio.run(scenario())
    assert first is not None and first.content == b"one"
    assert second is not None and second.content == b"two"
    assert empty is None
    assert provider.requested_frames == 2
    assert provider.pending_frames == 0
    assert provider.state is AudioCaptureState.STOPPED


def test_fake_capture_normalizes_bytes_into_frames() -> None:
    provider = FakeAudioCaptureProvider([b"bytes-frame"])
    assert provider.pending_frames == 1
    delivered = asyncio.run(_read_all(provider))
    assert delivered[0].content == b"bytes-frame"
    assert delivered[0].format == "wav"


async def _read_all(provider: FakeAudioCaptureProvider):
    frames = []
    while True:
        frame = await provider.read()
        if frame is None:
            return frames
        frames.append(frame)


def test_fake_capture_start_failure_raises_capture_error() -> None:
    provider = FakeAudioCaptureProvider(fail_start=True)

    async def scenario() -> None:
        await provider.start()

    with pytest.raises(CaptureError):
        asyncio.run(scenario())
    assert provider.state is AudioCaptureState.ERROR


def test_fake_capture_raise_on_start_propagates() -> None:
    provider = FakeAudioCaptureProvider(
        raise_on_start=RuntimeError("boom")
    )

    async def scenario() -> None:
        await provider.start()

    with pytest.raises(RuntimeError):
        asyncio.run(scenario())


def test_fake_capture_raise_on_read_propagates() -> None:
    provider = FakeAudioCaptureProvider(raise_on_read=CaptureError("mic dead"))

    async def scenario() -> None:
        await provider.read()

    with pytest.raises(CaptureError):
        asyncio.run(scenario())


def test_fake_capture_close_clears_queue() -> None:
    provider = FakeAudioCaptureProvider([_audio(b"a"), _audio(b"b")])

    async def scenario() -> None:
        await provider.close()
        return await provider.read()

    assert asyncio.run(scenario()) is None
    assert provider.pending_frames == 0
