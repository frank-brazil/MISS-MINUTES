import asyncio

import pytest
from app.voice.audio import AudioFrame
from app.voice.vad import (
    FakeVoiceActivityDetector,
    VADResult,
    VADState,
    VoiceActivityDetector,
)
from pydantic import ValidationError


def _frame(seq: int = 0) -> AudioFrame:
    return AudioFrame(content=f"f{seq}".encode(), format="wav")


def _run(coro):
    return asyncio.run(coro)


def test_vad_result_validates_confidence() -> None:
    with pytest.raises(ValidationError):
        VADResult(speech=True, confidence=1.5)
    VADResult(speech=False, confidence=None)


def test_abstract_vad_requires_metadata() -> None:
    with pytest.raises(TypeError):

        class MissingMetadata(VoiceActivityDetector):
            async def feed(self, frame: AudioFrame) -> VADResult:
                return VADResult(speech=False)


def test_fake_vad_reports_started_and_ended() -> None:
    detector = FakeVoiceActivityDetector([False, True, True, False])

    async def scenario() -> list:
        await detector.reset()
        results = []
        for index in range(4):
            result = await detector.feed(_frame(index))
            results.append(result)
        return results

    results = _run(scenario())
    assert results[0] == VADResult(speech=False)
    assert results[1].started is True
    assert results[1].ended is False
    assert results[2].started is False
    assert results[2].ended is False
    assert results[3].ended is True
    assert detector.feed_count == 4
    assert detector.state is VADState.SILENCE


def test_fake_vad_default_active_falls_back() -> None:
    detector = FakeVoiceActivityDetector([True], default_active=False)
    results = _run(detect_all(detector, 3))
    assert results[1].speech is False
    assert results[2].speech is False


async def detect_all(detector: FakeVoiceActivityDetector, count: int) -> list:
    await detector.reset()
    out = []
    for index in range(count):
        out.append(await detector.feed(_frame(index)))
    return out


def test_fake_vad_reset_clears_state() -> None:
    detector = FakeVoiceActivityDetector([True, False])
    _run(detect_all(detector, 2))
    _run(detect_all(detector, 1))
    assert detector.feed_count == 1
    assert detector.speech is True
    await_reset = asyncio.run(detector.reset())
    assert await_reset is None
    assert detector.speech is False
    assert detector.state is VADState.INACTIVE


def test_fake_vad_raise_error_propagates() -> None:
    detector = FakeVoiceActivityDetector(raise_error=RuntimeError("vad boom"))
    with pytest.raises(RuntimeError):
        _run(detector.feed(_frame()))
