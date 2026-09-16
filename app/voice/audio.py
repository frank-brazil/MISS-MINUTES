"""Microphone audio capture for continuous voice sessions.

This layer is provider-independent: it only defines the capture interface,
the typed frame model, and a deterministic in-memory fake. Real microphone
providers (OS audio APIs, browser capture, remote devices) can be plugged in
without touching the rest of the voice subsystem. The interface deliberately
says nothing about audio libraries and never uploads audio anywhere.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import StrEnum
from typing import ClassVar
from uuid import UUID, uuid4

from pydantic import Field

from app.voice.base import AudioData, SpeechError


class CaptureError(SpeechError):
    """Raised when microphone capture is unavailable or fails.

    Converted into a structured session event by the voice service; it is
    never swallowed silently.
    """


class AudioCaptureState(StrEnum):
    """Lifecycle state of an audio capture provider."""

    STOPPED = "stopped"
    READY = "ready"
    CAPTURING = "capturing"
    ERROR = "error"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AudioFrame(AudioData):
    """A single captured audio frame plus capture metadata.

    Frames reuse ``AudioData`` semantics (encoded bytes + descriptive
    metadata) and add a stable frame identifier and capture timestamp.
    Microphone frames default to a 16 kHz sample rate when a provider does
    not declare one.
    """

    frame_id: UUID = Field(default_factory=uuid4)
    captured_at: datetime = Field(default_factory=_utc_now)
    sample_rate: int | None = 16000


class AudioCaptureProvider(ABC):
    """Interface for streaming microphone audio.

    ``read()`` returns the next available frame or ``None`` when no frame is
    currently available (callers poll). Transport errors raise
    :class:`CaptureError`.
    """

    name: ClassVar[str]
    description: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [
            attribute
            for attribute in ("name", "description")
            if not hasattr(cls, attribute)
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} must define required attribute(s): {', '.join(missing)}"
            )

    @abstractmethod
    async def start(self) -> None:
        """Begin capturing audio."""
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        """Stop capturing audio."""
        raise NotImplementedError

    @abstractmethod
    async def read(self) -> AudioFrame | None:
        """Return the next frame, or ``None`` when none is available."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Release capture resources."""
        raise NotImplementedError

    @property
    def state(self) -> AudioCaptureState:
        raise NotImplementedError


class FakeAudioCaptureProvider(AudioCaptureProvider):
    """Deterministic, offline audio capture provider.

    Delivers a pre-authored frame queue in order. Frames are consumed exactly
    once; when the queue is empty, ``read()`` returns ``None`` so callers can
    poll without blocking. Start/read failures are configurable to exercise
    structured error handling.
    """

    name = "fake-audio-capture"
    description = "Deterministic in-memory audio capture provider for offline tests."

    def __init__(
        self,
        frames: list[AudioData | bytes] | None = None,
        *,
        fail_start: bool = False,
        fail_start_message: str = "simulated microphone start failure",
        raise_on_start: Exception | None = None,
        raise_on_read: Exception | None = None,
    ) -> None:
        self._queue: list[AudioFrame] = [
            self._normalize(frame) for frame in (frames or [])
        ]
        self._consumed: list[AudioFrame] = []
        self._fail_start = fail_start
        self._fail_start_message = fail_start_message
        self._raise_on_start = raise_on_start
        self._raise_on_read = raise_on_read
        self._started = False
        self._closed = False
        self._state = AudioCaptureState.STOPPED
        self._logger = logging.getLogger(__name__)

    @staticmethod
    def _normalize(entry: AudioData | bytes) -> AudioFrame:
        if isinstance(entry, AudioData):
            return AudioFrame.model_validate(entry.model_dump())
        return AudioFrame(
            content=entry,
            format="wav",
            sample_rate=16000,
        )

    @property
    def state(self) -> AudioCaptureState:
        return self._state

    @property
    def requested_frames(self) -> int:
        return len(self._consumed)

    @property
    def consumed(self) -> tuple[AudioFrame, ...]:
        return tuple(self._consumed)

    @property
    def pending_frames(self) -> int:
        return len(self._queue)

    async def start(self) -> None:
        if self._closed:
            raise CaptureError("capture provider is already closed")
        if self._raise_on_start is not None:
            self._logger.error(
                "Fake capture start raising: %s", type(self._raise_on_start).__name__
            )
            raise self._raise_on_start
        if self._fail_start:
            self._logger.warning("Fake capture start configured to fail")
            self._state = AudioCaptureState.ERROR
            raise CaptureError(self._fail_start_message)
        self._started = True
        self._state = AudioCaptureState.CAPTURING
        self._logger.info(
            "Fake capture started: queued_frames=%d", len(self._queue)
        )

    async def stop(self) -> None:
        self._started = False
        self._state = AudioCaptureState.READY
        self._logger.info("Fake capture stopped")

    async def read(self) -> AudioFrame | None:
        if self._raise_on_read is not None:
            self._logger.error(
                "Fake capture read raising: %s", type(self._raise_on_read).__name__
            )
            raise self._raise_on_read
        if not self._queue:
            return None
        frame = self._queue.pop(0)
        self._consumed.append(frame)
        self._logger.info(
            "Fake capture delivered frame: bytes=%d format=%s",
            len(frame.content),
            frame.format,
        )
        return frame

    async def close(self) -> None:
        self._closed = True
        self._queue.clear()
        self._started = False
        self._state = AudioCaptureState.STOPPED
        self._logger.info("Fake capture closed: consumed=%d", len(self._consumed))
