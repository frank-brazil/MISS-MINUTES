"""Lip-sync timing, controller and provider."""

import pytest
from app.avatar.lipsync import (
    ApproximateLipSyncProvider,
    LipSyncController,
    LipSyncTiming,
    SpeechUnit,
    TimingAccuracy,
    VisemeState,
)
from pydantic import ValidationError


def test_speech_unit_validation():
    with pytest.raises(ValidationError):
        SpeechUnit(symbol="", start_time=0.0, duration=1.0)
    with pytest.raises(ValidationError):
        SpeechUnit(symbol="a", start_time=-1.0, duration=1.0)
    with pytest.raises(ValidationError):
        SpeechUnit(symbol="a", start_time=0.0, duration=0.0)
    unit = SpeechUnit(symbol="a", start_time=0.0, duration=0.5)
    assert unit.end_time == pytest.approx(0.5)


def test_lipsync_timing_validation():
    with pytest.raises(ValidationError):
        LipSyncTiming(accuracy=TimingAccuracy.APPROXIMATE, duration_seconds=-1.0)


def test_viseme_state_validation():
    with pytest.raises(ValidationError):
        VisemeState(symbol="a", openness=1.5, accuracy=TimingAccuracy.APPROXIMATE, timestamp=0.0)
    with pytest.raises(ValidationError):
        VisemeState(
            symbol="a", openness=0.5, accuracy=TimingAccuracy.APPROXIMATE, timestamp=float("nan")
        )


def test_approximate_provider_empty():
    provider = ApproximateLipSyncProvider()
    timing = provider.timing_for("")
    assert timing.units == ()
    assert timing.duration_seconds == pytest.approx(0.0)
    assert timing.accuracy is TimingAccuracy.APPROXIMATE


def test_approximate_provider_words():
    provider = ApproximateLipSyncProvider(speaking_rate_wpm=120.0)
    timing = provider.timing_for("hello world")
    assert timing.accuracy is TimingAccuracy.APPROXIMATE
    assert len(timing.units) == 10  # 5 + 5 chars
    assert timing.duration_seconds > 0
    for unit in timing.units:
        assert unit.duration > 0
        assert unit.start_time >= 0


def test_approximate_provider_deterministic():
    provider = ApproximateLipSyncProvider()
    first = provider.timing_for("test message")
    second = provider.timing_for("test message")
    assert first.duration_seconds == second.duration_seconds
    assert len(first.units) == len(second.units)
    for a, b in zip(first.units, second.units):
        assert a.start_time == b.start_time
        assert a.duration == b.duration


def test_lipsync_controller_start_stop():
    controller = LipSyncController(now_fn=lambda: 0.0)
    assert controller.active is False
    assert controller.start("hello world") is True
    assert controller.active is True
    controller.stop()
    assert controller.active is False


def test_lipsync_controller_blank_rejected():
    controller = LipSyncController(now_fn=lambda: 0.0)
    assert controller.start("") is False
    assert controller.start("   ") is False
    assert controller.active is False


def test_lipsync_controller_current_viseme():
    controller = LipSyncController(now_fn=lambda: 0.0)
    controller.start("hello", at=0.0)
    viseme = controller.current(0.05)
    assert viseme is not None
    assert viseme.openness > 0
    assert viseme.accuracy is TimingAccuracy.APPROXIMATE
    assert viseme.timestamp == pytest.approx(0.05)


def test_lipsync_controller_finish_event():
    controller = LipSyncController(now_fn=lambda: 0.0)
    controller.start("hi", at=0.0)
    assert controller.consume_event() == "started"  # consume start event first
    timing = controller.timing
    assert timing is not None
    controller.current(timing.duration_seconds + 0.1)
    assert controller.active is False
    assert controller.consume_event() == "finished"
    assert controller.consume_event() is None


def test_lipsync_controller_interrupt():
    controller = LipSyncController(now_fn=lambda: 0.0)
    controller.start("long text", at=0.0)
    assert controller.active is True
    assert controller.interrupt() is True
    assert controller.active is False
    assert controller.consume_event() == "interrupted"
    assert controller.interrupt() is False  # nothing to interrupt


def test_lipsync_controller_custom_timing():
    custom = LipSyncTiming(
        accuracy=TimingAccuracy.EXACT,
        units=(SpeechUnit(symbol="x", start_time=0.0, duration=1.0),),
        duration_seconds=1.0,
    )
    controller = LipSyncController(now_fn=lambda: 0.0)
    controller.start("text", timing=custom)
    assert controller.timing.accuracy is TimingAccuracy.EXACT
    viseme = controller.current(0.5)
    assert viseme is not None
    assert viseme.accuracy is TimingAccuracy.EXACT
