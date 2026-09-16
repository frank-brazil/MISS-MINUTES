"""Wake word detection for continuous voice sessions.

Provides the provider-independent wake word interface, the typed detection
result, and a deterministic scripted fake. The default phrase is
``MissMinutes`` and may be reconfigured per provider. Detection never requires
a continuous external API call: implementations may be local, streaming, or
wake-on-chip.
"""

import logging
from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, field_validator

from app.voice.audio import AudioFrame


class WakeWordResult(BaseModel):
    """Outcome of a wake word check on one audio frame."""

    detected: bool
    confidence: float | None = None
    phrase: str

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value


class WakeWordDetector(ABC):
    """Detects a configured wake phrase within a live audio stream."""

    wake_phrase: ClassVar[str] = "MissMinutes"

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
    async def detect(self, frame: AudioFrame) -> WakeWordResult:
        """Check one frame for the wake phrase."""
        raise NotImplementedError

    @abstractmethod
    async def reset(self) -> None:
        """Clear detector state between listening sessions."""
        raise NotImplementedError


class FakeWakeWordDetector(WakeWordDetector):
    """Deterministic scripted wake word detector for offline tests.

    A configurable per-frame detection map triggers the wake phrase; past the
    end of the script the detector falls back to ``default``. The recognised
    phrase is configurable and defaults to ``MissMinutes``.
    """

    name = "fake-wake-word"
    description = "Deterministic scripted wake word detector for offline tests."

    def __init__(
        self,
        detections: list[bool] | None = None,
        *,
        default: bool = False,
        phrase: str = "MissMinutes",
        confidence: float = 0.99,
        raise_error: Exception | None = None,
    ) -> None:
        if not phrase.strip():
            raise ValueError("wake phrase must not be blank")
        if not (0.0 <= confidence <= 1.0):
            raise ValueError("confidence must be between 0 and 1")
        self.wake_phrase = phrase
        self._detections = list(detections or [])
        self._default = default
        self._confidence = confidence
        self._raise_error = raise_error
        self._index = 0
        self._results: list[WakeWordResult] = []
        self._logger = logging.getLogger(__name__)

    @property
    def feed_count(self) -> int:
        return self._index

    @property
    def results(self) -> tuple[WakeWordResult, ...]:
        return tuple(self._results)

    async def detect(self, frame: AudioFrame) -> WakeWordResult:
        if self._raise_error is not None:
            self._logger.error(
                "Fake wake word detect raising: %s", type(self._raise_error).__name__
            )
            raise self._raise_error
        if self._index < len(self._detections):
            detected = self._detections[self._index]
        else:
            detected = self._default
        self._index += 1
        result = WakeWordResult(
            detected=detected,
            confidence=self._confidence if detected else None,
            phrase=self.wake_phrase,
        )
        self._results.append(result)
        self._logger.info(
            "Fake wake word feed frame=%d: detected=%s phrase=%s",
            self._index,
            detected,
            self.wake_phrase,
        )
        return result

    async def reset(self) -> None:
        self._index = 0
        self._results.clear()
        self._logger.info("Fake wake word detector reset")