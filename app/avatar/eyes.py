"""Eye controller.

Controls left/right look, up/down look, blinks (with configurable duration)
and deterministic idle eye movement. A provider-independent ``EyeTrackingInput``
boundary paves the way for future camera-based eye tracking; no camera is
required now and a deterministic fake is provided for offline tests.
"""

import math
from abc import ABC, abstractmethod
from typing import Callable, ClassVar

from pydantic import BaseModel, ConfigDict, field_validator

from app.avatar.config import AvatarConfig
from app.avatar.expression import AvatarExpression


class EyeConfig(BaseModel):
    """Eye-motion parameters (blink timing + idle drift + interpolation)."""

    model_config = ConfigDict(extra="forbid")

    auto_blink_period_seconds: float = 3.0
    blink_duration: float = 0.15
    idle_pupil_radius: float = 0.25
    interpolation_speed: float = 8.0
    blink_jitter_seconds: float = 0.0

    @field_validator("auto_blink_period_seconds", "blink_duration", "idle_pupil_radius", "interpolation_speed", "blink_jitter_seconds")
    @classmethod
    def _nonnegative(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError("eye timing values must be finite and non-negative")
        return value


class EyeTarget(BaseModel):
    """A gaze target in normalized [-1, 1] space."""

    model_config = ConfigDict(frozen=True)

    x: float = 0.0
    y: float = 0.0

    @field_validator("x", "y")
    @classmethod
    def _unit(cls, value: float) -> float:
        if not math.isfinite(value) or not -1.0 <= value <= 1.0:
            raise ValueError("eye target must be in [-1, 1]")
        return value


class EyeTrackingInput(ABC):
    """Boundary for future camera/eye tracking. Returns ``None`` when idle."""

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
    def read(self) -> EyeTarget | None:
        """Return the latest gaze target, or ``None`` when no signal exists."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Release any tracking resources."""
        raise NotImplementedError


class FakeEyeTracker(EyeTrackingInput):
    """Deterministic, scripted eye tracking for offline tests."""

    name = "fake-eye-tracker"
    description = "Deterministic scripted eye tracking input."

    def __init__(self, targets: list[EyeTarget | None] | None = None) -> None:
        self._targets: list[EyeTarget | None] = list(targets or [])

    def feed(self, *targets: EyeTarget | None) -> None:
        self._targets.extend(targets)

    def read(self) -> EyeTarget | None:
        if not self._targets:
            return None
        return self._targets.pop(0)

    def close(self) -> None:
        self._targets.clear()


class EyeState(BaseModel):
    """Snapshot of the eyes for the current frame."""

    model_config = ConfigDict(frozen=True)

    left_openness: float = 1.0
    right_openness: float = 1.0
    pupil_x: float = 0.0
    pupil_y: float = 0.0
    blinking: bool = False

    @field_validator("left_openness", "right_openness")
    @classmethod
    def _openness(cls, value: float) -> float:
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("eye openness must be in [0, 1]")
        return value

    @field_validator("pupil_x", "pupil_y")
    @classmethod
    def _unit(cls, value: float) -> float:
        if not math.isfinite(value) or not -1.0 <= value <= 1.0:
            raise ValueError("pupil offset must be in [-1, 1]")
        return value


class EyeController:
    """Deterministic eye motion: look, blink, idle drift, tracking input."""

    def __init__(
        self,
        config: AvatarConfig | None = None,
        *,
        eye_config: EyeConfig | None = None,
        now_fn: Callable[[], float] | None = None,
        tracking: EyeTrackingInput | None = None,
    ) -> None:
        self._config = config or AvatarConfig()
        self._eye_config = eye_config or EyeConfig()
        import time as _time

        self._now_fn = now_fn or _time.time
        self._tracking = tracking
        self._look: EyeTarget = EyeTarget()
        self._manual_look: bool = False
        self._current: EyeTarget = EyeTarget()
        self._last_pupil_at: float | None = None
        self._manual_blink_duration: float = self._eye_config.blink_duration
        self._manual_blink_started_at: float | None = None
        self._auto_blink_started_at: float | None = None
        self._next_auto_blink_at: float | None = None
        self._jitter_seed: int = 0

    @property
    def tracking(self) -> EyeTrackingInput | None:
        return self._tracking

    def set_tracking(self, tracking: EyeTrackingInput | None) -> None:
        self._tracking = tracking

    def look(self, x: float, y: float) -> EyeTarget:
        """Set an explicit gaze direction (clamped to bounds)."""
        self._look = EyeTarget(
            x=max(-1.0, min(1.0, x)),
            y=max(-1.0, min(1.0, y)),
        )
        self._manual_look = True
        return self._look

    def clear_look(self) -> None:
        """Return to autonomous (idle drift / tracking) behaviour."""
        self._manual_look = False

    def look_at(self, target: EyeTarget) -> EyeTarget:
        """Set gaze from a validated eye target (clamped to bounds)."""
        self._look = EyeTarget(
            x=max(-1.0, min(1.0, target.x)),
            y=max(-1.0, min(1.0, target.y)),
        )
        self._manual_look = True
        return self._look

    def look_center(self) -> EyeTarget:
        return self.look_at(EyeTarget(x=0.0, y=0.0))

    def look_up(self) -> EyeTarget:
        return self.look_at(EyeTarget(x=0.0, y=-0.6))

    def look_down(self) -> EyeTarget:
        return self.look_at(EyeTarget(x=0.0, y=0.6))

    def look_left(self) -> EyeTarget:
        return self.look_at(EyeTarget(x=-0.6, y=0.0))

    def look_right(self) -> EyeTarget:
        return self.look_at(EyeTarget(x=0.6, y=0.0))

    def look_up_left(self) -> EyeTarget:
        return self.look_at(EyeTarget(x=-0.5, y=-0.5))

    def look_up_right(self) -> EyeTarget:
        return self.look_at(EyeTarget(x=0.5, y=-0.5))

    def blink(self, duration: float | None = None) -> bool:
        """Start an explicit blink that lasts ``duration`` seconds from now."""
        if duration is not None:
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError("blink duration must be a positive finite number")
            self._manual_blink_duration = duration
        self._manual_blink_started_at = self._now_fn()
        return True

    def cancel_blink(self) -> bool:
        """Abort any in-progress or scheduled blink, opening the eyes fully."""
        had = self._manual_blink_started_at is not None or self._auto_blink_started_at is not None
        self._manual_blink_started_at = None
        self._auto_blink_started_at = None
        self._next_auto_blink_at = None
        return had

    def is_blinking(self) -> bool:
        now = self._now_fn()
        if self._manual_blink_started_at is not None:
            elapsed = now - self._manual_blink_started_at
            if elapsed >= self._manual_blink_duration:
                self._manual_blink_started_at = None
            else:
                return True
        if self._auto_blink_started_at is not None:
            elapsed = now - self._auto_blink_started_at
            if elapsed >= self._eye_config.blink_duration:
                self._auto_blink_started_at = None
            else:
                return True
        return False

    def _jitter_offset(self) -> float:
        """Deterministic, reproducible jitter offset in [-jitter, +jitter]."""
        jitter = self._eye_config.blink_jitter_seconds
        if jitter <= 0:
            return 0.0
        self._jitter_seed += 1
        raw = math.sin(self._jitter_seed * 12.9898) * 43758.5453
        frac = raw - math.floor(raw)
        return (frac * 2.0 - 1.0) * jitter

    def _schedule_auto_blink(self, now: float) -> None:
        period = self._eye_config.auto_blink_period_seconds
        if period <= 0:
            self._next_auto_blink_at = None
            return
        if self._next_auto_blink_at is None:
            self._next_auto_blink_at = now + period + self._jitter_offset()

    def _desired_pupil(self, now: float) -> EyeTarget:
        if self._tracking is not None:
            target = self._tracking.read()
            if target is not None:
                return target
        if self._manual_look:
            return self._look
        radius = self._eye_config.idle_pupil_radius
        return EyeTarget(
            x=max(-1.0, min(1.0, math.sin(now * 0.9) * radius)),
            y=max(-1.0, min(1.0, math.cos(now * 0.7) * radius * 0.6)),
        )

    def dynamic_pupil(self, now: float) -> EyeTarget:
        """Pupil position from tracking > explicit look > idle drift.

        The current pupil eases toward the desired target (exponential
        approach) so gaze changes look smooth. The first call after a reset
        snaps directly to the target so behaviour stays deterministic.
        """
        target = self._desired_pupil(now)
        previous = self._last_pupil_at
        speed = self._eye_config.interpolation_speed
        if previous is None or now < previous or speed <= 0:
            self._current = target
        else:
            dt = now - previous
            if dt > 0:
                amount = 1.0 - math.exp(-speed * dt)
                self._current = EyeTarget(
                    x=max(-1.0, min(1.0, self._current.x + (target.x - self._current.x) * amount)),
                    y=max(-1.0, min(1.0, self._current.y + (target.y - self._current.y) * amount)),
                )
        self._last_pupil_at = now
        return self._current

    def _blink_factor(self, started_at: float, duration: float, now: float) -> float:
        """Blink factor: 1 = fully open, 0 = fully closed.

        Curve: close over the first 25%, hold closed to 55%, reopen by 100%.
        """
        elapsed = now - started_at
        if elapsed < 0:
            return 1.0
        if elapsed >= duration:
            return 1.0
        progress = elapsed / duration
        if progress <= 0.25:
            return 1.0 - progress / 0.25
        if progress <= 0.55:
            return 0.0
        return (progress - 0.55) / 0.45

    def openness(self, now: float) -> float:
        """Combined openness from explicit + scheduled automatic blinks."""
        factor = 1.0
        if self._manual_blink_started_at is not None:
            if now - self._manual_blink_started_at >= self._manual_blink_duration:
                self._manual_blink_started_at = None
            else:
                factor = min(
                    factor,
                    self._blink_factor(self._manual_blink_started_at, self._manual_blink_duration, now),
                )
        period = self._eye_config.auto_blink_period_seconds
        if period > 0:
            self._schedule_auto_blink(now)
            if self._auto_blink_started_at is None and self._next_auto_blink_at is not None and now >= self._next_auto_blink_at:
                self._auto_blink_started_at = self._next_auto_blink_at
                self._next_auto_blink_at = self._next_auto_blink_at + period + self._jitter_offset()
            if self._auto_blink_started_at is not None:
                if now - self._auto_blink_started_at >= self._eye_config.blink_duration:
                    self._auto_blink_started_at = None
                else:
                    factor = min(
                        factor,
                        self._blink_factor(self._auto_blink_started_at, self._eye_config.blink_duration, now),
                    )
        return max(0.0, min(1.0, factor))

    def state(self, now: float) -> EyeState:
        """Current eye state for a given (injected) time."""
        openness = self.openness(now)
        pupil = self.dynamic_pupil(now)
        return EyeState(
            left_openness=openness,
            right_openness=openness,
            pupil_x=pupil.x,
            pupil_y=pupil.y,
            blinking=openness < 0.95,
        )

    def combine(self, state: EyeState, expression: AvatarExpression | None) -> EyeState:
        """Add the expression's static pupil offset on top of dynamic look."""
        if expression is None:
            return state
        x = max(-1.0, min(1.0, state.pupil_x + expression.pupil_x))
        y = max(-1.0, min(1.0, state.pupil_y + expression.pupil_y))
        return state.model_copy(update={"pupil_x": x, "pupil_y": y})

    @property
    def config(self) -> AvatarConfig:
        return self._config

    def close(self) -> None:
        if self._tracking is not None:
            self._tracking.close()
