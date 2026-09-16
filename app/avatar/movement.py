"""Avatar movement controller.

A minimal, deterministic position interpolator. The avatar engine does not own
GUI/screen coordinates, so movement works in an abstract relative space
(units-per-second along a straight line from a start to a target point).
"""

import math
from typing import Callable

from pydantic import BaseModel, ConfigDict, field_validator


class MovementConfig(BaseModel):
    """Movement speed and easing."""

    model_config = ConfigDict(extra="forbid")

    speed: float = 40.0

    @field_validator("speed")
    @classmethod
    def _positive_speed(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("movement speed must be a positive finite number")
        return value


class AvatarMovementController:
    """Interpolates the character position toward a target."""

    def __init__(
        self,
        config: MovementConfig | None = None,
        *,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        import time as _time

        self._config = config or MovementConfig()
        self._now_fn = now_fn or _time.time
        self._start: tuple[float, float] = (0.0, 0.0)
        self._target: tuple[float, float] | None = None
        self._started_at: float | None = None
        self._position: tuple[float, float] = (0.0, 0.0)

    @property
    def config(self) -> MovementConfig:
        return self._config

    @property
    def position(self) -> tuple[float, float]:
        return self._position

    @property
    def target(self) -> tuple[float, float] | None:
        return self._target

    @property
    def moving(self) -> bool:
        return self._target is not None

    def _clamp_pair(self, x: float, y: float) -> tuple[float, float]:
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("movement coordinates must be finite")
        return (x, y)

    def move_to(self, x: float, y: float, *, at: float | None = None) -> bool:
        """Begin moving to ``(x, y)``. Returns ``False`` when already there."""
        target = self._clamp_pair(x, y)
        if self._target is not None and self._target == target:
            return False
        self._start = (self._position[0], self._position[1])
        self._target = target
        self._started_at = self._now_fn() if at is None else at
        return True

    def stop(self) -> bool:
        """Freeze in place. Returns ``True`` when a move was in progress."""
        was = self.moving
        self._target = None
        self._started_at = None
        return was

    def update(self, now: float) -> tuple[float, float]:
        """Advance toward the target and return the current position."""
        if not self.moving or self._target is None or self._started_at is None:
            return self._position
        dx = self._target[0] - self._start[0]
        dy = self._target[1] - self._start[1]
        distance = math.hypot(dx, dy)
        travelled = max(0.0, now - self._started_at) * self._config.speed
        if distance <= 0 or travelled >= distance:
            self._position = self._target
            self._target = None
            self._started_at = None
            return self._position
        fraction = travelled / distance
        self._position = (
            self._start[0] + dx * fraction,
            self._start[1] + dy * fraction,
        )
        return self._position

    def reset(self) -> None:
        self._target = None
        self._started_at = None
        self._position = (0.0, 0.0)