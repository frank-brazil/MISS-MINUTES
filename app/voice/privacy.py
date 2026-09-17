"""Microphone and transcript privacy boundary for the voice experience.

Raw microphone audio is never persisted or uploaded by default. Upload to a
provider happens only when the provider is explicitly configured AND audio
upload is enabled. Temporary buffers are tracked and released, and transcript
content is reduced to length-only metadata for events.
"""

import logging
import time
from enum import StrEnum
from typing import Callable
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.voice.base import AudioData


class VoicePrivacyMode(StrEnum):
    """Privacy posture for microphone audio."""

    LOCAL_ONLY = "local_only"
    CONFIGURED_UPLOAD = "configured_upload"


class VoicePrivacyConfig(BaseModel):
    """Declarative privacy settings for a voice deployment."""

    mode: VoicePrivacyMode = VoicePrivacyMode.LOCAL_ONLY
    allow_audio_upload: bool = False
    persist_audio: bool = False
    log_transcripts: bool = False
    upload_providers: frozenset[str] = frozenset()


class VoiceAudioBuffer(BaseModel):
    """Tracked reference to one retained audio buffer."""

    buffer_id: UUID = Field(default_factory=uuid4)
    size_bytes: int
    retained_at: float
    released_at: float | None = None


class VoicePrivacyGuard:
    """Enforces the documented privacy boundary for live audio.

    Safe by default: ``local_only`` mode, no upload, no persistence, no
    transcript logging. Any upload or persistence requires explicit
    configuration.
    """

    def __init__(
        self,
        config: VoicePrivacyConfig | None = None,
        *,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self._config = config or VoicePrivacyConfig()
        self._now_fn = now_fn or time.time
        self._buffers: dict[UUID, VoiceAudioBuffer] = {}
        self._released_bytes = 0
        self._logger = logging.getLogger(__name__)

    @property
    def config(self) -> VoicePrivacyConfig:
        return self._config

    def retain_audio(self, audio: AudioData) -> UUID:
        """Register a temporary buffer and return its id."""
        buffer = VoiceAudioBuffer(
            size_bytes=len(audio.content),
            retained_at=self._now_fn(),
        )
        self._buffers[buffer.buffer_id] = buffer
        self._logger.info(
            "Voice buffer retained: id=%s bytes=%d",
            buffer.buffer_id,
            buffer.size_bytes,
        )
        return buffer.buffer_id

    def release_audio(self, buffer_id: UUID) -> int:
        """Release a retained buffer and return the freed byte count."""
        buffer = self._buffers.pop(buffer_id, None)
        if buffer is None:
            self._logger.warning("Voice buffer release for unknown id %s", buffer_id)
            return 0
        buffer.released_at = self._now_fn()
        self._released_bytes += buffer.size_bytes
        self._logger.info("Voice buffer released: id=%s bytes=%d", buffer_id, buffer.size_bytes)
        return buffer.size_bytes

    def live_buffers(self) -> tuple[VoiceAudioBuffer, ...]:
        return tuple(self._buffers.values())

    @property
    def retained_bytes(self) -> int:
        return sum(buffer.size_bytes for buffer in self._buffers.values())

    @property
    def released_bytes(self) -> int:
        return self._released_bytes

    @property
    def local_only(self) -> bool:
        return self._config.mode is VoicePrivacyMode.LOCAL_ONLY

    def would_persist(self) -> bool:
        return self._config.persist_audio

    def can_upload(self, provider_name: str) -> bool:
        """Return True only when upload is enabled and provider configured."""
        if self._config.mode is not VoicePrivacyMode.CONFIGURED_UPLOAD:
            return False
        if not self._config.allow_audio_upload:
            return False
        return provider_name in self._config.upload_providers

    def transcript_metadata(self, text: str | None) -> str:
        """Return a privacy-safe transcript descriptor (no content by default)."""
        if text is None:
            return "<no transcript>"
        if self._config.log_transcripts:
            return text
        return f"<{len(text)} chars>"
