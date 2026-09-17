"""Voice activity detection for continuous voice sessions.

Provides the provider-independent detection interface, typed per-frame
results, and a deterministic scripted fake. The detector is responsible for
recognising the start and end of speech and for identifying silence, so the
orchestrator can bound utterances and timeouts without depending on any audio
library.
"""

import logging
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, field_validator

from app.voice.audio import AudioFrame


class VADState(StrEnum):
    """Detector state over the stream of frames it has seen."""

    INACTIVE = "inactive"
    SPEECH = "speech"
    SILENCE = "silence"


class VoiceActivityDetector(ABC):
    """Detects speech start/end and silence across a stream of frames."""

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
    async def feed(self, frame: AudioFrame) -> "VADResult":
        """Process one frame and report activity for it."""
        raise NotImplementedError

    @abstractmethod
    async def reset(self) -> None:
        """Clear detector state between utterances."""
        raise NotImplementedError


class VADResult(BaseModel):
    """Per-frame voice activity outcome.

    ``speech`` reports whether the frame is voiced. ``started`` is True on the
    first voiced frame after silence; ``ended`` is True on the first silent
    frame after speech.
    """

    speech: bool
    started: bool = False
    ended: bool = False
    confidence: float | None = None

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value


class FakeVoiceActivityDetector(VoiceActivityDetector):
    """Deterministic scripted voice activity detector for offline tests.

    A configurable per-frame speech map drives the detector: frame ``i`` is
    active when ``active_frames[i]`` is True (falling back to
    ``default_active`` past the end of the script). ``started`` and ``ended``
    are derived from state transitions, mirroring a real VAD's behaviour
    without any audio processing.
    """

    name = "fake-vad"
    description = "Deterministic scripted voice activity detector for offline tests."

    def __init__(
        self,
        active_frames: list[bool] | None = None,
        *,
        default_active: bool = False,
        confidence: float = 0.9,
        raise_error: Exception | None = None,
    ) -> None:
        if not (0.0 <= confidence <= 1.0):
            raise ValueError("confidence must be between 0 and 1")
        self._active_frames = list(active_frames or [])
        self._default_active = default_active
        self._confidence = confidence
        self._raise_error = raise_error
        self._index = 0
        self._speech = False
        self._state = VADState.INACTIVE
        self._logger = logging.getLogger(__name__)

    @property
    def state(self) -> VADState:
        return self._state

    @property
    def speech(self) -> bool:
        return self._speech

    @property
    def feed_count(self) -> int:
        return self._index

    async def feed(self, frame: AudioFrame) -> VADResult:
        if self._raise_error is not None:
            self._logger.error("Fake VAD feed raising: %s", type(self._raise_error).__name__)
            raise self._raise_error
        if self._index < len(self._active_frames):
            active = self._active_frames[self._index]
        else:
            active = self._default_active
        self._index += 1
        started = active and not self._speech
        ended = not active and self._speech
        self._speech = active
        if active:
            self._state = VADState.SPEECH
        elif self._state is VADState.SPEECH:
            self._state = VADState.SILENCE
        self._logger.info(
            "Fake VAD feed frame=%d: speech=%s started=%s ended=%s",
            self._index,
            active,
            started,
            ended,
        )
        return VADResult(
            speech=active,
            started=started,
            ended=ended,
            confidence=self._confidence if active else None,
        )

    async def reset(self) -> None:
        self._index = 0
        self._speech = False
        self._state = VADState.INACTIVE
        self._logger.info("Fake VAD reset")
