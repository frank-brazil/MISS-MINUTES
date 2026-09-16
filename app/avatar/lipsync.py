"""Lip-sync layer.

Lip-sync is split into three pieces:

* ``LipSyncTiming`` — a validated, deterministic voice timing model. It carries
  an explicit ``TimingAccuracy`` so the engine never claims *exact* per-sound
  timing it did not measure.
* ``LipSyncProvider`` — the boundary any phoneme/viseme source implements. A
  deterministic :class:`ApproximateLipSyncProvider` builds timing offline from
  plain text.
* ``LipSyncController`` — turns a timing into per-frame viseme states (openness)
  and emits one-shot ``started``/``finished``/``interrupted`` events consumed by
  the avatar controller.

Everything is pure and offline; time is injected for determinism.
"""

import math
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Callable, ClassVar

from pydantic import BaseModel, ConfigDict, field_validator


class TimingAccuracy(StrEnum):
    """How trustworthy the timing boundaries are."""

    EXACT = "exact"
    APPROXIMATE = "approximate"


class SpeechUnit(BaseModel):
    """One speech sound/time slice within an utterance."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    start_time: float
    duration: float

    @field_validator("symbol")
    @classmethod
    def _symbol_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("symbol must not be blank")
        return value

    @field_validator("start_time")
    @classmethod
    def _nonnegative_start(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError("start_time must be finite and non-negative")
        return value

    @field_validator("duration")
    @classmethod
    def _positive_duration(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("duration must be a positive finite number")
        return value

    @property
    def end_time(self) -> float:
        return self.start_time + self.duration


class LipSyncTiming(BaseModel):
    """Validated phonetic timing for one utterance."""

    model_config = ConfigDict(frozen=True)

    accuracy: TimingAccuracy
    units: tuple[SpeechUnit, ...] = ()
    duration_seconds: float = 0.0

    @field_validator("duration_seconds")
    @classmethod
    def _nonnegative_duration(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError("duration_seconds must be finite and non-negative")
        return value


class VisemeState(BaseModel):
    """The mouth state implied by the current speech time."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    openness: float
    accuracy: TimingAccuracy
    timestamp: float

    @field_validator("openness")
    @classmethod
    def _unit_openness(cls, value: float) -> float:
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("openness must be in [0, 1]")
        return value

    @field_validator("timestamp")
    @classmethod
    def _finite_timestamp(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("timestamp must be finite")
        return value


class LipSyncProvider(ABC):
    """Boundary for sources that produce voice timing."""

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
    def timing_for(self, text: str) -> LipSyncTiming:
        """Return deterministic timing for ``text``."""
        raise NotImplementedError


class ApproximateLipSyncProvider(LipSyncProvider):
    """Deterministic, offline estimate of speech timing from plain text.

    Unit boundaries are *approximations* derived from word count and length at a
    fixed speaking rate; they are intended to drive believable mouth motion, not
    to be measured against an audio waveform.
    """

    name = "approximate-lipsync-provider"
    description = "Deterministic per-character speech timing estimated from text."

    def __init__(self, speaking_rate_wpm: float = 150.0) -> None:
        if not math.isfinite(speaking_rate_wpm) or speaking_rate_wpm <= 0:
            raise ValueError("speaking_rate_wpm must be a positive finite number")
        self._speaking_rate_wpm = speaking_rate_wpm

    @property
    def speaking_rate_wpm(self) -> float:
        return self._speaking_rate_wpm

    def timing_for(self, text: str) -> LipSyncTiming:
        words = " ".join(str(text).split()).split()
        if not words:
            return LipSyncTiming(
                accuracy=TimingAccuracy.APPROXIMATE,
                units=(),
                duration_seconds=0.0,
            )
        word_seconds = 60.0 / self._speaking_rate_wpm
        units: list[SpeechUnit] = []
        cursor = 0.0
        for word in words:
            duration = word_seconds * (0.6 + 0.4 * min(len(word) / 4.0, 2.5))
            per_char = duration / max(len(word), 1)
            for index, char in enumerate(word):
                units.append(
                    SpeechUnit(
                        symbol=char.lower(),
                        start_time=cursor + index * per_char,
                        duration=per_char,
                    )
                )
            cursor += duration
        return LipSyncTiming(
            accuracy=TimingAccuracy.APPROXIMATE,
            units=tuple(units),
            duration_seconds=cursor,
        )


class LipSyncController:
    """Plays a timing back as per-frame viseme states + lifecycle events."""

    def __init__(
        self,
        provider: LipSyncProvider | None = None,
        *,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        import time as _time

        self._provider = provider or ApproximateLipSyncProvider()
        self._now_fn = now_fn or _time.time
        self._timing: LipSyncTiming | None = None
        self._started_at: float | None = None
        self._pending_event: str | None = None

    @property
    def provider(self) -> LipSyncProvider:
        return self._provider

    @property
    def timing(self) -> LipSyncTiming | None:
        return self._timing

    @property
    def active(self) -> bool:
        return self._timing is not None and self._started_at is not None

    def timing_for(self, text: str) -> LipSyncTiming:
        return self._provider.timing_for(text)

    def start(
        self,
        text: str,
        *,
        timing: LipSyncTiming | None = None,
        at: float | None = None,
    ) -> bool:
        """Begin speaking ``text``. Returns ``False`` for blank input."""
        cleaned = " ".join(str(text).split())
        if not cleaned:
            return False
        self._timing = timing if timing is not None else self._provider.timing_for(cleaned)
        self._started_at = at if at is not None else self._now_fn()
        self._pending_event = "started"
        return True

    def stop(self) -> None:
        """End speech cleanly (no interrupt event)."""
        self._timing = None
        self._started_at = None
        self._pending_event = None

    def interrupt(self) -> bool:
        """Abort ongoing speech. Returns ``True`` when speech was active."""
        if not self.active:
            return False
        self._pending_event = "interrupted"
        self._timing = None
        self._started_at = None
        return True

    def current(self, now: float) -> VisemeState | None:
        """Viseme state for ``now``, or ``None`` when not speaking."""
        if not self.active:
            return None
        assert self._timing is not None and self._started_at is not None
        elapsed = now - self._started_at
        duration = self._timing.duration_seconds
        if elapsed < 0:
            return None
        if duration > 0 and elapsed >= duration:
            if self._pending_event is None:
                self._pending_event = "finished"
            self._timing = None
            self._started_at = None
            return None
        active_unit: SpeechUnit | None = None
        for unit in self._timing.units:
            if unit.start_time <= elapsed < unit.end_time:
                active_unit = unit
                break
        if active_unit is None:
            return VisemeState(
                symbol="",
                openness=0.5,
                accuracy=self._timing.accuracy,
                timestamp=now,
            )
        local = elapsed - active_unit.start_time
        openness = 0.3 + 0.45 * (0.5 - 0.5 * math.cos(2.0 * math.pi * local / active_unit.duration))
        return VisemeState(
            symbol=active_unit.symbol,
            openness=max(0.0, min(1.0, openness)),
            accuracy=self._timing.accuracy,
            timestamp=now,
        )

    def consume_event(self) -> str | None:
        """Return (once) the latest lifecycle event: started/finished/interrupted."""
        event = self._pending_event
        self._pending_event = None
        return event
