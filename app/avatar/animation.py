"""Body movement animation.

A deterministic, configurable animation controller producing ``AvatarPose``
snapshots each tick: idle bob, subtle body tilt, listening/thinking/working
tilts and a single-shot success hop. Time is injected so tests are fully
deterministic; no real-time clock, no hidden global state.
"""

import math
from enum import StrEnum
from typing import Callable

from pydantic import BaseModel, ConfigDict, field_validator

from app.avatar.models import AvatarPose


class AnimationMode(StrEnum):
    """Animation modes that map to character behaviour."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    WORKING = "working"
    SUCCESS = "success"


class AnimationConfig(BaseModel):
    """Tunable animation amplitudes/periods. Everything is positive."""

    model_config = ConfigDict(extra="forbid")

    idle_bob_amplitude: float = 2.5
    idle_bob_period_seconds: float = 2.0
    idle_tilt_amplitude: float = 1.5
    idle_tilt_period_seconds: float = 4.0
    listening_bob_amplitude: float = 3.0
    listening_tilt_deg: float = 5.0
    listening_lean: float = 0.2
    thinking_tilt_deg: float = -4.0
    thinking_lean: float = -0.15
    working_bob_amplitude: float = 1.5
    working_tilt_deg: float = 6.0
    working_lean: float = 0.1
    success_hop_amplitude: float = 8.0
    success_hop_period_seconds: float = 0.9
    success_duration_seconds: float = 1.8
    max_body_bob: float = 20.0

    @field_validator(
        "idle_bob_amplitude",
        "idle_bob_period_seconds",
        "idle_tilt_amplitude",
        "idle_tilt_period_seconds",
        "listening_bob_amplitude",
        "working_bob_amplitude",
        "success_hop_amplitude",
        "success_hop_period_seconds",
        "success_duration_seconds",
        "max_body_bob",
    )
    @classmethod
    def _positive(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("animation values must be positive finite numbers")
        return value

    @field_validator(
        "listening_tilt_deg",
        "thinking_tilt_deg",
        "working_tilt_deg",
        "listening_lean",
        "thinking_lean",
        "working_lean",
    )
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("animation values must be finite")
        return value


class AnimationController:
    """Produces a deterministic pose for a given (injected) time."""

    def __init__(
        self,
        config: AnimationConfig | None = None,
        *,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        import time as _time

        self._config = config or AnimationConfig()
        self._now_fn = now_fn or _time.time
        self._mode = AnimationMode.IDLE
        self._started_at = self._now_fn()
        self._completed: str | None = None

    @property
    def config(self) -> AnimationConfig:
        return self._config

    @property
    def mode(self) -> AnimationMode:
        return self._mode

    def set_mode(self, mode: AnimationMode) -> AnimationMode | None:
        """Switch animation mode. Returns the previous mode, or ``None`` when
        the mode was unchanged."""
        if mode is self._mode:
            return None
        previous = self._mode
        self._mode = mode
        self._started_at = self._now_fn()
        self._completed = None
        return previous

    @property
    def started_at(self) -> float:
        return self._started_at

    def consume_completion(self) -> str | None:
        """Return (once) the name of a single-shot animation that finished."""
        completed = self._completed
        self._completed = None
        return completed

    def _idle_pose(self, now: float) -> AvatarPose:
        bob = self._config.idle_bob_amplitude * math.sin(
            2.0 * math.pi * now / self._config.idle_bob_period_seconds
        )
        tilt = self._config.idle_tilt_amplitude * math.sin(
            2.0 * math.pi * now / self._config.idle_tilt_period_seconds
        )
        return AvatarPose(body_bob=bob, body_tilt_deg=tilt)

    def _listening_pose(self, now: float) -> AvatarPose:
        bob = self._config.listening_bob_amplitude * math.sin(
            2.0 * math.pi * now / self._config.idle_bob_period_seconds
        )
        return AvatarPose(
            body_bob=bob,
            body_tilt_deg=self._config.listening_tilt_deg,
            lean=self._config.listening_lean,
        )

    def _thinking_pose(self, now: float) -> AvatarPose:
        sway = math.sin(2.0 * math.pi * now / self._config.idle_tilt_period_seconds) * 2.0
        return AvatarPose(
            body_bob=sway,
            body_tilt_deg=self._config.thinking_tilt_deg,
            lean=self._config.thinking_lean,
            face_tilt_deg=-3.0,
        )

    def _working_pose(self, now: float) -> AvatarPose:
        micro = self._config.working_bob_amplitude * math.sin(
            2.0 * math.pi * now * 2.0 / self._config.idle_bob_period_seconds
        )
        return AvatarPose(
            body_bob=micro,
            body_tilt_deg=self._config.working_tilt_deg,
            lean=self._config.working_lean,
        )

    def _success_pose(self, now: float) -> AvatarPose:
        elapsed = now - self._started_at
        duration = self._config.success_duration_seconds
        if elapsed >= duration:
            self._completed = AnimationMode.SUCCESS.value
            self._mode = AnimationMode.IDLE
            return self._idle_pose(now)
        hop = self._config.success_hop_amplitude * abs(
            math.sin(math.pi * elapsed / self._config.success_hop_period_seconds)
        )
        return AvatarPose(body_bob=hop, body_tilt_deg=self._config.working_tilt_deg * 0.5)

    def pose(self, now: float) -> AvatarPose:
        """Pure pose computation for a given time."""
        if self._mode is AnimationMode.LISTENING:
            return self._listening_pose(now)
        if self._mode is AnimationMode.THINKING:
            return self._thinking_pose(now)
        if self._mode is AnimationMode.WORKING:
            return self._working_pose(now)
        if self._mode is AnimationMode.SUCCESS:
            return self._success_pose(now)
        return self._idle_pose(now)

    def update(self) -> AvatarPose:
        """Advance one frame using the injected clock."""
        return self.pose(self._now_fn())

    def reset(self) -> None:
        self._mode = AnimationMode.IDLE
        self._started_at = self._now_fn()
        self._completed = None
