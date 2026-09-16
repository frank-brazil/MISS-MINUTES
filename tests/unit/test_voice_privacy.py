from app.voice.audio import AudioData
from app.voice.privacy import (
    VoiceAudioBuffer,
    VoicePrivacyConfig,
    VoicePrivacyGuard,
    VoicePrivacyMode,
)


def _audio(content: bytes = b"mic-frames") -> AudioData:
    return AudioData(content=content, format="wav", sample_rate=16000)


def test_local_only_is_default() -> None:
    guard = VoicePrivacyGuard()
    assert guard.local_only is True
    assert guard.config.mode is VoicePrivacyMode.LOCAL_ONLY
    assert guard.would_persist() is False
    assert guard.can_upload("any-provider") is False


def test_guard_tracks_retain_and_release() -> None:
    guard = VoicePrivacyGuard()
    audio = _audio(b"bytes-here")
    buffer_id = guard.retain_audio(audio)
    assert guard.retained_bytes == len(b"bytes-here")
    assert len(guard.live_buffers()) == 1
    assert isinstance(guard.live_buffers()[0], VoiceAudioBuffer)
    released = guard.release_audio(buffer_id)
    assert released == len(b"bytes-here")
    assert guard.live_buffers() == ()
    assert guard.retained_bytes == 0
    assert guard.released_bytes == len(b"bytes-here")


def test_release_unknown_buffer_is_benign() -> None:
    guard = VoicePrivacyGuard()
    assert guard.release_audio(_buffer_id()) == 0


def test_upload_requires_configured_provider() -> None:
    config = VoicePrivacyConfig(
        mode=VoicePrivacyMode.CONFIGURED_UPLOAD,
        allow_audio_upload=True,
        upload_providers=frozenset({"cloud-voice"}),
    )
    guard = VoicePrivacyGuard(config)
    assert guard.can_upload("cloud-voice") is True
    assert guard.can_upload("other-provider") is False


def test_configured_upload_without_enable_is_blocked() -> None:
    config = VoicePrivacyConfig(
        mode=VoicePrivacyMode.CONFIGURED_UPLOAD,
        allow_audio_upload=False,
        upload_providers=frozenset({"cloud-voice"}),
    )
    guard = VoicePrivacyGuard(config)
    assert guard.can_upload("cloud-voice") is False


def test_local_only_blocks_upload_even_if_provider_listed() -> None:
    config = VoicePrivacyConfig(
        mode=VoicePrivacyMode.LOCAL_ONLY,
        allow_audio_upload=True,
        upload_providers=frozenset({"cloud-voice"}),
    )
    guard = VoicePrivacyGuard(config)
    assert guard.can_upload("cloud-voice") is False


def test_persistence_flag() -> None:
    assert VoicePrivacyGuard().would_persist() is False
    guard = VoicePrivacyGuard(VoicePrivacyConfig(persist_audio=True))
    assert guard.would_persist() is True


def test_transcript_metadata_hides_content_by_default() -> None:
    guard = VoicePrivacyGuard()
    assert guard.transcript_metadata("delete all project files") == "<24 chars>"
    assert guard.transcript_metadata(None) == "<no transcript>"


def test_transcript_metadata_reveals_only_when_configured() -> None:
    guard = VoicePrivacyGuard(VoicePrivacyConfig(log_transcripts=True))
    assert guard.transcript_metadata("secret phrase") == "secret phrase"


def _buffer_id():
    from uuid import uuid4

    return uuid4()