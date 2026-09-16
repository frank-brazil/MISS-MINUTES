"""Walking system.

A deterministic :class:`WalkingController` drives leg/arm/bob deltas from a
sinusoidal cycle and accumulates walked steps. It is a pure motion generator:
it knows nothing about position on screen — :class:`app.avatar.movement` turns
motion into an interpolated position.
"""

import math
from enum import StrEnum
from typing import Callable

from pydantic import BaseModel, ConfigDict, field_validator


class WalkState(StrEnum):
    """Current walking/locomotion state."""

    STANDING = "standing"
    WALKING_FORWARD = "walking_forward"
    WALKING_BACKWARD = "walking_backward"
    TURNING = "turning"


class WalkConfig(BaseModel):
    """Walking cadence and amplitude."""

    model_config = ConfigDict(extra="forbid")

    step_period_seconds: float = 1.2
    step_amplitude_deg: float = 32.0
    arm_swing_deg: float = 16.0
    bob_amplitude: float = 3.0

    @field_validator("step_period_seconds", "step_amplitude_deg", "arm_swing_deg", "bob_amplitude")
    @classmethod
    def _positive(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("walking values must be positive finite numbers")
        return value


class WalkingFrame(BaseModel):
    """Per-frame pose deltas while walking."""

    model_config = ConfigDict(frozen=True)

    state: WalkState
    phase: float
    left_leg_raise: float
    right_leg_raise: float
    left_arm_swing: float
    right_arm_swing: float
    bob: float
    timestamp: float = 0.0

    @field_validator("phase", "left_leg_raise", "right_leg_raise", "left_arm_swing", "right_arm_swing", "bob")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("walking frame values must be finite")
        return value


class WalkingController:
    """Generates walking motion and accumulates step counts."""

    def __init__(
        self,
        config: WalkConfig | None = None,
        *,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        import time as _time

        self._config = config or WalkConfig()
        self._now_fn = now_fn or _time.time
        self._state = WalkState.STANDING
        self._started_at: float | None = None
        self._last_tick: float | None = None
        self._walked_steps: float = 0.0

    @property
    def config(self) -> WalkConfig:
        return self._config

    @property
    def state(self) -> WalkState:
        return self._state

    @property
    def walked_steps(self) -> float:
        """Accumulated steps since motion started (backward counts negative)."""
        return self._walked_steps

    def walked_distance(self, step_length: float = 0.5) -> float:
        """Distance covered assuming a fixed ``step_length`` per step."""
        if not math.isfinite(step_length) or step_length <= 0:
            raise ValueError("step_length must be a positive finite number")
        return self._walked_steps * step_length

    def start_forward(self, at: float | None = None) -> bool:
        if self._state is WalkState.WALKING_FORWARD:
            return False
        was = self.is_walking()
        self._state = WalkState.WALKING_FORWARD
        self._started_at = self._now_fn() if at is None else at
        self._last_tick = self._started_at
        return not was

    def start_backward(self, at: float | None = None) -> bool:
        if self._state is WalkState.WALKING_BACKWARD:
            return False
        was = self.is_walking()
        self._state = WalkState.WALKING_BACKWARD
        self._started_at = self._now_fn() if at is None else at
        self._last_tick = self._started_at
        return not was

    def turn(self, at: float | None = None) -> bool:
        if self._state is WalkState.TURNING:
            return False
        was = self.is_walking()
        self._state = WalkState.TURNING
        self._started_at = self._now_fn() if at is None else at
        self._last_tick = self._started_at
        return not was

    def is_walking(self) -> bool:
        return self._state is not WalkState.STANDING

    def stop(self) -> bool:
        """Return to standing. Returns ``True`` when motion was active."""
        was = self.is_walking()
        self._state = WalkState.STANDING
        self._started_at = None
        self._last_tick = None
        return was

    def update(self, now: float) -> WalkingFrame | None:
        """Advance the cycle and return the current walking frame, if any."""
        if not self.is_walking() or self._started_at is None:
            return None
        if self._last_tick is not None and now > self._last_tick:
            dt = now - self._last_tick
            direction = 1.0 if self._state is WalkState.WALKING_FORWARD else -1.0
            if self._state is WalkState.TURNING:
                direction = 0.0
            if direction != 0.0:
                self._walked_steps += direction * dt / self._config.step_period_seconds
        self._last_tick = now
        phase = ((now - self._started_at) / self._config.step_period_seconds) % 1.0
        direction = 1.0 if self._state is WalkState.WALKING_FORWARD else -1.0
        if self._state is WalkState.TURNING:
            direction = 0.0
        angle = 2.0 * math.pi * phase
        return WalkingFrame(
            state=self._state,
            phase=phase,
            left_leg_raise=max(0.0, direction * abs(math.sin(angle)) * self._config.step_amplitude_deg),
            right_leg_raise=max(0.0, direction * abs(math.sin(angle + math.pi)) * self._config.step_amplitude_deg),
            left_arm_swing=-math.sin(angle) * self._config.arm_swing_deg,
            right_arm_swing=math.sin(angle) * self._config.arm_swing_deg,
            bob=abs(math.cos(angle)) * self._config.bob_amplitude,
            timestamp=now,
        )

    def reset(self) -> None:
        self._state = WalkState.STANDING
        self._started_at = None
        self._last_tick = None
        self._walked_steps = 0.0
