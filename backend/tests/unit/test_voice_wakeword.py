import asyncio

import pytest
from app.voice.audio import AudioFrame
from app.voice.wakeword import (
    FakeWakeWordDetector,
    WakeWordDetector,
    WakeWordResult,
)
from pydantic import ValidationError


def _frame() -> AudioFrame:
    return AudioFrame(content=b"wake", format="wav")


def _run(coro):
    return asyncio.run(coro)


def test_wake_word_result_validates_confidence() -> None:
    with pytest.raises(ValidationError):
        WakeWordResult(detected=True, confidence=2.0, phrase="MissMinutes")
    result = WakeWordResult(detected=False, phrase="MissMinutes")
    assert result.confidence is None


def test_abstract_wakeword_requires_metadata() -> None:
    with pytest.raises(TypeError):

        class MissingMetadata(WakeWordDetector):
            async def detect(self, frame: AudioFrame) -> WakeWordResult:
                return WakeWordResult(detected=False, phrase="MissMinutes")


def test_default_phrase_is_missminutes() -> None:
    detector = FakeWakeWordDetector()
    assert detector.wake_phrase == "MissMinutes"
    assert WakeWordDetector.wake_phrase == "MissMinutes"


def test_wake_phrase_is_configurable() -> None:
    detector = FakeWakeWordDetector(phrase="Hey Minutes")
    assert detector.wake_phrase == "Hey Minutes"
    result = _run(detector.detect(_frame()))
    assert result.phrase == "Hey Minutes"


def test_fake_wakeword_detects_scripted_frames() -> None:
    detector = FakeWakeWordDetector([False, True], default=False)

    async def scenario() -> list:
        await detector.reset()
        results = []
        for _ in range(3):
            results.append(await detector.detect(_frame()))
        return results

    results = _run(scenario())
    assert results[0].detected is False
    assert results[1].detected is True
    assert results[1].confidence is not None
    assert results[2].detected is False
    assert detector.feed_count == 3
    assert len(detector.results) == 3


def test_fake_wakeword_default_falls_back() -> None:
    detector = FakeWakeWordDetector([True], default=False)
    results = _run(detect_many(detector, 2))
    assert results[1].detected is False


async def detect_many(detector: FakeWakeWordDetector, count: int) -> list:
    await detector.reset()
    return [await detector.detect(_frame()) for _ in range(count)]


def test_fake_wakeword_reset_clears_results() -> None:
    detector = FakeWakeWordDetector([True])
    _run(detect_many(detector, 1))
    assert _run(detector.reset()) is None
    assert detector.feed_count == 0
    assert detector.results == ()


def test_fake_wakeword_rejects_blank_phrase() -> None:
    with pytest.raises(ValueError):
        FakeWakeWordDetector(phrase="   ")
