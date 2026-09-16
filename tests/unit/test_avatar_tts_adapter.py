"""TTS-to-lip-sync adapter boundary."""

import pytest
from datetime import timedelta

from app.avatar.lipsync import ApproximateLipSyncProvider, LipSyncController, TimingAccuracy
from app.avatar.tts_adapter import TTSLipSyncAdapter


class _FakeResult:
    def __init__(self, success=True, duration=None):
        self.success = success
        self.duration = duration


def test_adapter_uses_fallback_without_result():
    adapter = TTSLipSyncAdapter()
    timing = adapter.timing_for("hello world")
    assert timing.accuracy is TimingAccuracy.APPROXIMATE
    assert timing.duration_seconds > 0
    assert len(timing.units) > 0


def test_adapter_scales_to_measured_duration():
    adapter = TTSLipSyncAdapter()
    result = _FakeResult(success=True, duration=timedelta(seconds=10.0))
    timing = adapter.timing_for("hello world", result)
    assert timing.accuracy is TimingAccuracy.APPROXIMATE
    assert timing.duration_seconds == pytest.approx(10.0)
    assert len(timing.units) > 0
    for unit in timing.units:
        assert unit.start_time >= 0
        assert unit.start_time + unit.duration <= 10.0 + 1e-9


def test_adapter_uses_fallback_on_failed_result():
    adapter = TTSLipSyncAdapter()
    result = _FakeResult(success=False)
    timing = adapter.timing_for("hello", result)
    assert timing.accuracy is TimingAccuracy.APPROXIMATE
    assert timing.duration_seconds > 0


def test_adapter_uses_fallback_when_no_duration():
    adapter = TTSLipSyncAdapter()
    result = _FakeResult(success=True, duration=None)
    timing = adapter.timing_for("hello", result)
    assert timing.accuracy is TimingAccuracy.APPROXIMATE
    assert timing.duration_seconds > 0


def test_adapter_returns_total_when_no_units():
    provider = ApproximateLipSyncProvider()
    adapter = TTSLipSyncAdapter(provider)
    result = _FakeResult(success=True, duration=timedelta(seconds=5.0))
    timing = adapter.timing_for("", result)  # empty → no units
    assert timing.duration_seconds == pytest.approx(5.0)
    assert timing.units == ()


def test_adapter_controller_factory():
    adapter = TTSLipSyncAdapter(now_fn=lambda: 0.0)
    controller = adapter.controller("hello world")
    assert isinstance(controller, LipSyncController)
    assert controller.active is True
    controller.stop()
