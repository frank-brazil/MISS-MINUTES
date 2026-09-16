"""Deterministic animation timelines.

A timeline is a list of keyframes (time + value mapping); evaluating at a time
interpolates between the surrounding keyframes with a named easing function.
Timelines are provider-independent and driven by an injected clock, so they
reproduce exactly offline. ``Easing``/``ease`` are also used by the gesture
layer to shape per-frame pose deltas.
"""

import math
from enum import StrEnum
from typing import Callable, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, field_validator


class Easing(StrEnum):
    """Named interpolation curves over a normalised progress in [0, 1]."""

    LINEAR = "linear"
    EASE_IN = "ease_in"
    EASE_OUT = "ease_out"
    EASE_IN_OUT = "ease_in_out"


def ease(value: float, easing: Easing = Easing.LINEAR) -> float:
    """Apply an easing curve to a normalised (clamped) progress value."""
    if not math.isfinite(value):
        raise ValueError("ease input must be finite")
    t = max(0.0, min(1.0, value))
    if easing is Easing.EASE_IN:
        return t * t
    if easing is Easing.EASE_OUT:
        return t * (2.0 - t)
    if easing is Easing.EASE_IN_OUT:
        return 3.0 * t * t - 2.0 * t * t * t
    return t


class TimelineKeyframe(BaseModel):
    """A single timeline keyframe: absolute time + named values."""

    model_config = ConfigDict(frozen=True)

    time: float
    values: Mapping[str, float]
    easing: Easing = Easing.LINEAR

    @field_validator("time")
    @classmethod
    def _nonnegative_time(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError("keyframe time must be finite and non-negative")
        return value

    @field_validator("values")
    @classmethod
    def _finite_values(cls, value: Mapping[str, float]) -> Mapping[str, float]:
        for name, number in value.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("timeline value names must be non-empty strings")
            if not isinstance(number, (int, float)) or not math.isfinite(float(number)):
                raise ValueError(f"timeline value {name!r} must be finite")
        return value


class AnimationTimeline:
    """Plays keyframes with easing; deterministic under an injected clock."""

    def __init__(
        self,
        keyframes: Iterable[TimelineKeyframe] | None = None,
        *,
        duration: float | None = None,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        import time as _time

        self._now_fn = now_fn or _time.time
        self._keyframes: list[TimelineKeyframe] = list(keyframes or [])
        self._sorted = False
        self._duration = duration
        self._started_at: float | None = None
        self._completed: str | None = None

    @property
    def duration(self) -> float:
        if self._duration is not None:
            return self._duration
        if not self._keyframes:
            return 0.0
        return max(keyframe.time for keyframe in self._sorted_keyframes())

    @property
    def playing(self) -> bool:
        return self._started_at is not None

    def _sorted_keyframes(self) -> list[TimelineKeyframe]:
        if not self._sorted:
            self._keyframes.sort(key=lambda keyframe: keyframe.time)
            self._sorted = True
        return self._keyframes

    def add(self, keyframe: TimelineKeyframe) -> None:
        self._keyframes.append(keyframe)
        self._sorted = False

    def _all_names(self) -> list[str]:
        names: list[str] = []
        for keyframe in self._sorted_keyframes():
            for name in keyframe.values:
                if name not in names:
                    names.append(name)
        return names

    def play(self, at: float | None = None) -> bool:
        """Start (or restart) playback. Returns ``False`` if already playing."""
        if self.playing:
            return False
        self._started_at = self._now_fn() if at is None else at
        self._completed = None
        return True

    def pause(self) -> bool:
        """Pause playback. Returns ``True`` when playback was active."""
        if not self.playing:
            return False
        self._started_at = None
        self._completed = None
        return True

    def cancel(self) -> bool:
        """Stop and reset playback. Returns ``True`` when playback was active."""
        active = self.playing
        self._started_at = None
        self._completed = None
        return active

    def _value_at(self, keyframes: list[TimelineKeyframe], name: str, t: float) -> float:
        previous: TimelineKeyframe | None = None
        for keyframe in keyframes:
            if keyframe.time > t:
                if previous is None:
                    return float(keyframe.values.get(name, 0.0))
                seg_span = keyframe.time - previous.time
                if seg_span <= 0:
                    return float(keyframe.values.get(name, 0.0))
                progress = (t - previous.time) / seg_span
                eased = ease(progress, previous.easing)
                from_value = float(previous.values.get(name, 0.0))
                to_value = float(keyframe.values.get(name, from_value))
                return from_value + (to_value - from_value) * eased
            previous = keyframe
        if previous is not None:
            return float(previous.values.get(name, 0.0))
        return 0.0

    def evaluate(self, now: float) -> dict[str, float] | None:
        """Interpolated values at ``now``, or ``None`` when not playing."""
        if not self.playing or self._started_at is None:
            return None
        keyframes = self._sorted_keyframes()
        if not keyframes:
            return {}
        t = max(0.0, now - self._started_at)
        duration = self.duration
        if duration > 0 and t >= duration:
            self.pause()
            self._completed = "timeline"
            final: dict[str, float] = {}
            for keyframe in keyframes:
                final.update({name: float(value) for name, value in keyframe.values.items()})
            return final
        return {name: self._value_at(keyframes, name, t) for name in self._all_names()}

    def consume_completion(self) -> str | None:
        """Return (once) ``"timeline"`` when playback reached its end."""
        completed = self._completed
        self._completed = None
        return completed

    def reset(self) -> None:
        self.cancel()
        self._completed = None


__all__ = [
    "AnimationTimeline",
    "Easing",
    "TimelineKeyframe",
    "ease",
]
