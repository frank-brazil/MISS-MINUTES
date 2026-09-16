import asyncio

import pytest

from app.voice.audio import AudioData
from app.voice.output import (
    AudioOutputProvider,
    AudioPlaybackResult,
    FakeAudioOutputProvider,
    PlaybackStatus,
)


def _audio(content: bytes = b"hello") -> AudioData:
    return AudioData(content=content, format="wav", sample_rate=16000)


def _run(coro):
    return asyncio.run(coro)


def test_playback_result_statuses() -> None:
    ok = AudioPlaybackResult.ok()
    assert ok.success is True
    assert ok.status is PlaybackStatus.PLAYING
    stopped = AudioPlaybackResult.ok(PlaybackStatus.STOPPED)
    assert stopped.status is PlaybackStatus.STOPPED
    failed = AudioPlaybackResult.fail("boom")
    assert failed.success is False
    assert failed.status is PlaybackStatus.ERROR
    assert failed.error == "boom"


def test_abstract_output_requires_metadata() -> None:
    with pytest.raises(TypeError):

        class MissingMetadata(AudioOutputProvider):
            async def play(self, audio: AudioData) -> AudioPlaybackResult:
                return AudioPlaybackResult.ok()


def test_fake_output_plays_and_stops() -> None:
    provider = FakeAudioOutputProvider()

    async def scenario() -> tuple:
        first = await provider.play(_audio(b"a"))
        playing = provider.is_speaking()
        stopped = await provider.stop()
        after = provider.is_speaking()
        return first, playing, stopped, after

    first, playing, stopped, after = _run(scenario())
    assert first.success is True
    assert playing is True
    assert stopped.success is True
    assert after is False
    assert len(provider.played) == 1
    assert provider.played[0].content == b"a"
    assert provider.stop_requests == 1


def test_fake_output_play_failure() -> None:
    provider = FakeAudioOutputProvider(fail_play=True)
    result = _run(provider.play(_audio()))
    assert result.success is False
    assert provider.played == []
    assert provider.is_speaking() is False


def test_fake_output_raise_error_propagates() -> None:
    provider = FakeAudioOutputProvider(raise_error=RuntimeError("speaker boom"))
    with pytest.raises(RuntimeError):
        _run(provider.play(_audio()))


def test_fake_output_auto_stop_after_polls() -> None:
    provider = FakeAudioOutputProvider(auto_stop_after=2)
    _run(provider.play(_audio()))
    assert provider.is_speaking() is True
    poll_two = provider.is_speaking()
    poll_three = provider.is_speaking()
    assert provider.is_speaking() is False


def test_fake_output_rejects_bad_auto_stop() -> None:
    with pytest.raises(ValueError):
        FakeAudioOutputProvider(auto_stop_after=0)


def test_fake_output_close_ends_playback() -> None:
    provider = FakeAudioOutputProvider()
    _run(provider.play(_audio()))
    assert provider.speaking is True
    _run(provider.close())
    assert provider.speaking is False