"""Audio output/playback for the voice experience.

Provides the provider-independent playback interface, typed playback results,
and a deterministic in-memory fake. The orchestrating service uses the
interface to start/stop speaking and to detect active playback for barge-in
and safety timeouts; implementations never couple the core to a speaker
library.
"""

import logging
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel

from app.voice.base import AudioData


class PlaybackStatus(StrEnum):
    """Resulting status of a playback request."""

    PLAYING = "playing"
    STOPPED = "stopped"
    INTERRUPTED = "interrupted"
    ERROR = "error"


class AudioPlaybackResult(BaseModel):
    """Outcome of a playback request."""

    success: bool
    status: PlaybackStatus
    error: str | None = None

    @classmethod
    def ok(cls, status: PlaybackStatus = PlaybackStatus.PLAYING) -> "AudioPlaybackResult":
        return cls(success=True, status=status)

    @classmethod
    def fail(cls, error: str) -> "AudioPlaybackResult":
        return cls(success=False, status=PlaybackStatus.ERROR, error=error)


class AudioOutputProvider(ABC):
    """Interface for playing audio to the user and stopping it."""

    name: ClassVar[str]
    description: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [
            attribute for attribute in ("name", "description") if not hasattr(cls, attribute)
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} must define required attribute(s): {', '.join(missing)}"
            )

    @abstractmethod
    async def play(self, audio: AudioData) -> AudioPlaybackResult:
        """Begin playing ``audio``."""
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> AudioPlaybackResult:
        """Stop active playback."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Release output resources."""
        raise NotImplementedError

    @abstractmethod
    def is_speaking(self) -> bool:
        """Return True while audio is being played."""
        raise NotImplementedError


class FakeAudioOutputProvider(AudioOutputProvider):
    """Deterministic, offline audio output provider.

    ``play`` marks the provider as speaking and records the audio; ``stop``
    ends playback. With ``auto_stop_after`` the provider stops speaking after
    a fixed number of ``is_speaking`` polls, letting tests model a completed
    utterance without a clock. Playback failures are configurable.
    """

    name = "fake-audio-output"
    description = "Deterministic in-memory audio output provider for offline tests."

    def __init__(
        self,
        *,
        fail_play: bool = False,
        fail_message: str = "simulated playback failure",
        raise_error: Exception | None = None,
        auto_stop_after: int | None = None,
    ) -> None:
        if auto_stop_after is not None and auto_stop_after < 1:
            raise ValueError("auto_stop_after must be a positive integer or None")
        self._playing = False
        self._polls = 0
        self._auto_stop_after = auto_stop_after
        self._fail_play = fail_play
        self._fail_message = fail_message
        self._raise_error = raise_error
        self.played: list[AudioData] = []
        self.stop_requests = 0
        self._logger = logging.getLogger(__name__)

    @property
    def speaking(self) -> bool:
        return self._playing

    async def play(self, audio: AudioData) -> AudioPlaybackResult:
        if self._raise_error is not None:
            self._logger.error("Fake playback play raising: %s", type(self._raise_error).__name__)
            raise self._raise_error
        if self._fail_play:
            self._logger.warning("Fake playback play configured to fail")
            return AudioPlaybackResult.fail(self._fail_message)
        self.played.append(audio)
        self._playing = True
        self._polls = 0
        self._logger.info(
            "Fake playback started: bytes=%d format=%s",
            len(audio.content),
            audio.format,
        )
        return AudioPlaybackResult.ok(PlaybackStatus.PLAYING)

    async def stop(self) -> AudioPlaybackResult:
        if self._raise_error is not None:
            self._logger.error("Fake playback stop raising: %s", type(self._raise_error).__name__)
            raise self._raise_error
        self._playing = False
        self.stop_requests += 1
        self._logger.info("Fake playback stopped")
        return AudioPlaybackResult.ok(PlaybackStatus.STOPPED)

    def is_speaking(self) -> bool:
        if not self._playing:
            return False
        self._polls += 1
        if self._auto_stop_after is not None and self._polls >= self._auto_stop_after:
            self._playing = False
            return False
        return True

    async def close(self) -> None:
        self._playing = False
        self._polls = 0
        self._logger.info("Fake playback closed: played=%d", len(self.played))
