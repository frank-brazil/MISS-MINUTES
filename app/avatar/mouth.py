"""Mouth controller.

Controls the character mouth for CHUNK 32: closed, smile, open, concerned and
surprised shapes. Phoneme-level lip-sync is explicitly out of scope until
CHUNK 33; this controller only picks a shape and an openness amount.
"""

import math
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator


class MouthShape(StrEnum):
    """Supported mouth shapes. ``SPEAKING`` and ``SMALL_OPEN`` feed lip-sync
    motion (CHUNK 33); the rest are static facial-expression shapes."""

    CLOSED = "closed"
    SMILE = "smile"
    OPEN = "open"
    CONCERNED = "concerned"
    SURPRISED = "surprised"
    SMALL_OPEN = "small_open"
    SPEAKING = "speaking"


class MouthState(BaseModel):
    """Current mouth configuration."""

    model_config = ConfigDict(frozen=True)

    shape: MouthShape = MouthShape.CLOSED
    openness: float = 0.0

    @field_validator("openness")
    @classmethod
    def _openness(cls, value: float) -> float:
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("openness must be in [0, 1]")
        return value


class MouthController:
    """Applies mouth shapes with sensible default openness."""

    DEFAULT_OPENNESS: dict[MouthShape, float] = {
        MouthShape.CLOSED: 0.0,
        MouthShape.SMILE: 0.35,
        MouthShape.OPEN: 0.8,
        MouthShape.CONCERNED: 0.15,
        MouthShape.SURPRISED: 0.95,
        MouthShape.SMALL_OPEN: 0.4,
        MouthShape.SPEAKING: 0.5,
    }

    def __init__(self, mouth_size: float = 16.0, speaking_period_seconds: float = 0.35) -> None:
        if not math.isfinite(mouth_size) or mouth_size <= 0:
            raise ValueError("mouth_size must be a positive finite number")
        if not math.isfinite(speaking_period_seconds) or speaking_period_seconds <= 0:
            raise ValueError("speaking_period_seconds must be a positive finite number")
        self._mouth_size = mouth_size
        self._speaking_period_seconds = speaking_period_seconds
        self._shape = MouthShape.CLOSED
        self._openness = 0.0

    @property
    def mouth_size(self) -> float:
        return self._mouth_size

    @property
    def speaking_period_seconds(self) -> float:
        return self._speaking_period_seconds

    @property
    def shape(self) -> MouthShape:
        return self._shape

    def set(self, shape: MouthShape) -> MouthState:
        """Switch to a shape, applying its default openness."""
        self._shape = shape
        self._openness = self.DEFAULT_OPENNESS[shape]
        return self.state()

    def open(self, amount: float) -> MouthState:
        """Override openness within [0, 1] (used by later lip motion hooks)."""
        if not math.isfinite(amount):
            raise ValueError("amount must be finite")
        self._openness = max(0.0, min(1.0, amount))
        return self.state()

    def animate(self, now: float) -> MouthState:
        """Drive lip motion when the mouth is in ``SPEAKING`` shape.

        Produces a deterministic openness oscillation so the renderer can
        animate the mouth while the character is speaking. Non-speaking shapes
        are untouched (their state is returned as-is).
        """
        if not math.isfinite(now):
            raise ValueError("now must be finite")
        if self._shape is not MouthShape.SPEAKING:
            return self.state()
        cycle = 2.0 * math.pi * now / self._speaking_period_seconds
        self._openness = max(0.15, min(0.85, 0.5 + 0.28 * math.sin(cycle)))
        return self.state()

    def state(self) -> MouthState:
        return MouthState(shape=self._shape, openness=self._openness)

    def reset(self) -> MouthState:
        """Return to the neutral closed mouth."""
        return self.set(MouthShape.CLOSED)