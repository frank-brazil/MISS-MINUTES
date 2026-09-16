"""Arm gestures and a sequencing controller.

Named gestures are data/config driven: each :class:`GestureSpec` describes a
duration, priority, looping, interruptibility and the arm/torso deltas to play
from start to finish. A deterministic :class:`GestureController` runs them with
a simple policy: a *strictly higher* priority gesture may interrupt the current
one (unless the current is non-interruptible); otherwise gestures queue FIFO.
Time is injected so everything reproduces exactly offline.
"""

import math
from collections import deque
from enum import StrEnum
from typing import Callable, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from app.avatar.timeline import Easing, ease


class GestureKind(StrEnum):
    """Named gestures the character can perform."""

    WAVE = "wave"
    POINT = "point"
    EXPLAIN = "explain"
    OPEN_HANDS = "open_hands"
    SHRUG = "shrug"
    THINKING_POSE = "thinking_pose"
    CELEBRATE = "celebrate"
    WARNING = "warning"
    STOP = "stop"


class GestureSpec(BaseModel):
    """Behaviour + pose deltas for one gesture."""

    model_config = ConfigDict(frozen=True)

    kind: GestureKind
    duration: float = 1.0
    priority: int = 10
    loop: bool = False
    interruptible: bool = True
    left_arm_start: float = 0.0
    left_arm_end: float = 0.0
    right_arm_start: float = 0.0
    right_arm_end: float = 0.0
    body_tilt_deg: float = 0.0
    lean: float = 0.0

    @field_validator("duration")
    @classmethod
    def _positive_duration(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("gesture duration must be a positive finite number")
        return value

    @field_validator("priority")
    @classmethod
    def _nonnegative_priority(cls, value: int) -> int:
        if value < 0:
            raise ValueError("gesture priority must be non-negative")
        return value

    @field_validator("left_arm_start", "left_arm_end", "right_arm_start", "right_arm_end")
    @classmethod
    def _arm_range(cls, value: float) -> float:
        if not math.isfinite(value) or not -90.0 <= value <= 90.0:
            raise ValueError("gesture arm deltas must be within [-90, 90] degrees")
        return value

    @field_validator("body_tilt_deg")
    @classmethod
    def _tilt_range(cls, value: float) -> float:
        if not math.isfinite(value) or not -60.0 <= value <= 60.0:
            raise ValueError("gesture body_tilt_deg must be within [-60, 60]")
        return value

    @field_validator("lean")
    @classmethod
    def _lean_range(cls, value: float) -> float:
        if not math.isfinite(value) or not -1.0 <= value <= 1.0:
            raise ValueError("gesture lean must be within [-1, 1]")
        return value


GESTURE_SPECS: dict[GestureKind, GestureSpec] = {
    GestureKind.WAVE: GestureSpec(
        kind=GestureKind.WAVE,
        duration=1.2,
        priority=20,
        loop=True,
        left_arm_start=40.0,
        left_arm_end=80.0,
    ),
    GestureKind.POINT: GestureSpec(
        kind=GestureKind.POINT,
        duration=0.9,
        priority=30,
        right_arm_start=0.0,
        right_arm_end=60.0,
        body_tilt_deg=4.0,
    ),
    GestureKind.EXPLAIN: GestureSpec(
        kind=GestureKind.EXPLAIN,
        duration=1.6,
        priority=60,
        left_arm_start=0.0,
        left_arm_end=25.0,
        right_arm_start=0.0,
        right_arm_end=-25.0,
        body_tilt_deg=3.0,
        lean=0.05,
    ),
    GestureKind.OPEN_HANDS: GestureSpec(
        kind=GestureKind.OPEN_HANDS,
        duration=1.0,
        priority=50,
        left_arm_start=-20.0,
        left_arm_end=45.0,
        right_arm_start=-20.0,
        right_arm_end=45.0,
    ),
    GestureKind.SHRUG: GestureSpec(
        kind=GestureKind.SHRUG,
        duration=1.0,
        priority=35,
        left_arm_start=-30.0,
        left_arm_end=30.0,
        right_arm_start=-30.0,
        right_arm_end=30.0,
        body_tilt_deg=6.0,
    ),
    GestureKind.THINKING_POSE: GestureSpec(
        kind=GestureKind.THINKING_POSE,
        duration=1.4,
        priority=40,
        loop=True,
        left_arm_start=-20.0,
        left_arm_end=20.0,
        right_arm_start=55.0,
        right_arm_end=70.0,
        body_tilt_deg=-2.0,
    ),
    GestureKind.CELEBRATE: GestureSpec(
        kind=GestureKind.CELEBRATE,
        duration=1.4,
        priority=90,
        left_arm_start=-40.0,
        left_arm_end=80.0,
        right_arm_start=-40.0,
        right_arm_end=80.0,
        body_tilt_deg=-4.0,
    ),
    GestureKind.WARNING: GestureSpec(
        kind=GestureKind.WARNING,
        duration=1.0,
        priority=100,
        right_arm_start=0.0,
        right_arm_end=70.0,
        body_tilt_deg=2.0,
        lean=0.1,
    ),
    GestureKind.STOP: GestureSpec(
        kind=GestureKind.STOP,
        duration=0.8,
        priority=95,
        left_arm_start=-10.0,
        left_arm_end=40.0,
        body_tilt_deg=2.0,
    ),
}


class GestureFrame(BaseModel):
    """Per-frame pose deltas for an active gesture."""

    model_config = ConfigDict(frozen=True)

    kind: GestureKind
    name: str
    progress: float
    left_arm_swing: float
    right_arm_swing: float
    body_tilt_deg: float
    lean: float
    loop: bool = False
    repeat: int = 0
    timestamp: float = 0.0

    @field_validator("progress")
    @classmethod
    def _unit_progress(cls, value: float) -> float:
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("progress must be in [0, 1]")
        return value

    @field_validator("left_arm_swing", "right_arm_swing")
    @classmethod
    def _arm_range(cls, value: float) -> float:
        if not math.isfinite(value) or not -90.0 <= value <= 90.0:
            raise ValueError("gesture arm swing must be within [-90, 90]")
        return value

    @field_validator("body_tilt_deg")
    @classmethod
    def _tilt_range(cls, value: float) -> float:
        if not math.isfinite(value) or not -60.0 <= value <= 60.0:
            raise ValueError("body tilt must be within [-60, 60]")
        return value

    @field_validator("lean")
    @classmethod
    def _lean_range(cls, value: float) -> float:
        if not math.isfinite(value) or not -1.0 <= value <= 1.0:
            raise ValueError("lean must be within [-1, 1]")
        return value


class GestureController:
    """Runs gestures with priority preemption and FIFO queuing."""

    def __init__(self, now_fn: Callable[[], float] | None = None) -> None:
        import time as _time

        self._now_fn = now_fn or _time.time
        self._active: GestureSpec | None = None
        self._started_at: float | None = None
        self._repeat = 0
        self._queue: deque[GestureSpec] = deque()
        self._finished: deque[GestureKind] = deque()

    @property
    def now_fn(self) -> Callable[[], float]:
        return self._now_fn

    @property
    def active(self) -> GestureSpec | None:
        return self._active

    def is_active(self) -> bool:
        return self._active is not None

    def start(
        self,
        kind: GestureKind,
        *,
        duration: float | None = None,
        loop: bool | None = None,
        at: float | None = None,
    ) -> bool:
        """Queue or (for strictly-higher priority) preempt the active gesture."""
        base = GESTURE_SPECS.get(kind)
        if base is None:
            return False
        spec = base
        if duration is not None:
            spec = spec.model_copy(update={"duration": duration})
        if loop is not None:
            spec = spec.model_copy(update={"loop": loop})
        now = self._now_fn() if at is None else at
        if self._active is None:
            self._active = spec
            self._started_at = now
            self._repeat = 0
            return True
        if spec.priority > self._active.priority and self._active.interruptible:
            self._finished.append(self._active.kind)
            self._active = spec
            self._started_at = now
            self._repeat = 0
            return True
        self._queue.append(spec)
        return True

    def cancel(self, kind: GestureKind) -> bool:
        """Remove a specific gesture from the active slot or the queue."""
        removed = False
        if self._active is not None and self._active.kind is kind:
            self._finished.append(self._active.kind)
            self._active = None
            self._started_at = None
            removed = True
        remaining: deque[GestureSpec] = deque()
        for spec in self._queue:
            if spec.kind is kind:
                removed = True
            else:
                remaining.append(spec)
        self._queue = remaining
        return removed

    def cancel_all(self) -> None:
        """Stop every gesture, active and queued."""
        if self._active is not None:
            self._finished.append(self._active.kind)
        for spec in self._queue:
            self._finished.append(spec.kind)
        self._active = None
        self._started_at = None
        self._queue.clear()

    def consume_finished(self) -> GestureKind | None:
        """Return (once) a gesture that just ended or was replaced."""
        if not self._finished:
            return None
        return self._finished.popleft()

    def _frame_for(self, spec: GestureSpec, progress: float, repeat: int, now: float) -> GestureFrame:
        eased = ease(progress, Easing.EASE_IN_OUT)
        return GestureFrame(
            kind=spec.kind,
            name=spec.kind.value,
            progress=progress,
            left_arm_swing=spec.left_arm_start + (spec.left_arm_end - spec.left_arm_start) * eased,
            right_arm_swing=spec.right_arm_start + (spec.right_arm_end - spec.right_arm_start) * eased,
            body_tilt_deg=spec.body_tilt_deg * eased,
            lean=spec.lean * eased,
            loop=spec.loop,
            repeat=repeat,
            timestamp=now,
        )

    def current(self, now: float) -> GestureFrame | None:
        """Frame for the active gesture at ``now`` (advances the queue)."""
        while self._active is not None:
            assert self._started_at is not None
            elapsed = now - self._started_at
            if elapsed < 0:
                return self._frame_for(self._active, 0.0, 0, now)
            duration = self._active.duration
            if self._active.loop:
                repeat = int(elapsed // duration)
                progress = (elapsed / duration) - repeat
                return self._frame_for(self._active, progress, repeat, now)
            if elapsed < duration:
                return self._frame_for(self._active, elapsed / duration, 0, now)
            self._finished.append(self._active.kind)
            self._active = None
            self._started_at = None
            if self._queue:
                self._active = self._queue.popleft()
                self._started_at = now
                self._repeat = 0
        return None

    def queue_length(self) -> int:
        return len(self._queue)

    def queued_kinds(self) -> tuple[GestureKind, ...]:
        return tuple(spec.kind for spec in self._queue)

    def reset(self) -> None:
        self.cancel_all()


__all__ = [
    "GESTURE_SPECS",
    "GestureController",
    "GestureFrame",
    "GestureKind",
    "GestureSpec",
    "Sequence",
]
