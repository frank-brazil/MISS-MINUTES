"""Core avatar models.

Typed enums and value objects shared across the avatar engine: the character
state, the named body parts, per-part transforms, and the posture snapshot the
animation layer produces. These models carry no behaviour and no global state;
they are validated value containers used by every other avatar module.
"""

import math
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator


class AvatarState(StrEnum):
    """Lifecycle/presentation state of the MISSMINUTES character.

    These are *character* states, deliberately distinct from the voice session
    state machine (``avatar`` is independent of it): the avatar may be
    listening while the underlying session is transcribing, or hidden while
    still processing.
    """

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    WORKING = "working"
    SPEAKING = "speaking"
    HAPPY = "happy"
    CONCERNED = "concerned"
    WARNING = "warning"
    SUCCESS = "success"
    ERROR = "error"
    SLEEPING = "sleeping"
    HIDDEN = "hidden"
    WALKING = "walking"
    EXPLAINING = "explaining"
    INTERRUPTED = "interrupted"


class AvatarPart(StrEnum):
    """Named body part identifiers used by transforms and renderers."""

    CLOCK_BODY = "clock_body"
    CLOCK_FACE = "clock_face"
    HOUR_HAND = "hour_hand"
    MINUTE_HAND = "minute_hand"
    CENTER_PIVOT = "center_pivot"
    LEFT_EYE = "left_eye"
    RIGHT_EYE = "right_eye"
    MOUTH = "mouth"
    LEFT_ARM = "left_arm"
    RIGHT_ARM = "right_arm"
    LEFT_HAND = "left_hand"
    RIGHT_HAND = "right_hand"
    LEFT_LEG = "left_leg"
    RIGHT_LEG = "right_leg"
    LEFT_SHOE = "left_shoe"
    RIGHT_SHOE = "right_shoe"


def _finite(value: float, label: str, lo: float | None = None, hi: float | None = None) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    if lo is not None and value < lo:
        raise ValueError(f"{label} must be >= {lo}")
    if hi is not None and value > hi:
        raise ValueError(f"{label} must be <= {hi}")
    return value


class AvatarTransform(BaseModel):
    """A typed placement/rotation/scale transform for one body part."""

    model_config = ConfigDict(frozen=True)

    part: AvatarPart
    offset_x: float = 0.0
    offset_y: float = 0.0
    rotation_deg: float = 0.0
    scale: float = 1.0

    @field_validator("offset_x", "offset_y", "rotation_deg")
    @classmethod
    def _finite_offsets(cls, value: float, info: object) -> float:
        return _finite(value, info.field_name)  # type: ignore[attr-defined]

    @field_validator("scale")
    @classmethod
    def _positive_scale(cls, value: float) -> float:
        return _finite(value, "scale", lo=1e-9, hi=8.0)


class AvatarPose(BaseModel):
    """Posture snapshot produced by the animation layer each tick.

    All values are animation deltas applied on top of the static character
    layout defined in ``AvatarConfig``."""

    body_bob: float = 0.0
    body_tilt_deg: float = 0.0
    face_tilt_deg: float = 0.0
    lean: float = 0.0
    left_arm_swing: float = 0.0
    right_arm_swing: float = 0.0
    left_leg_raise: float = 0.0
    right_leg_raise: float = 0.0

    @field_validator("body_bob", "lean")
    @classmethod
    def _bounded_pose(cls, value: float, info: object) -> float:
        if info.field_name == "lean":  # type: ignore[attr-defined]
            return _finite(value, "lean", lo=-1.0, hi=1.0)
        return _finite(value, "body_bob")

    @field_validator("body_tilt_deg", "face_tilt_deg")
    @classmethod
    def _bounded_tilt(cls, value: float, info: object) -> float:
        return _finite(value, info.field_name, lo=-60.0, hi=60.0)  # type: ignore[attr-defined]

    @field_validator("left_arm_swing", "right_arm_swing")
    @classmethod
    def _bounded_swing(cls, value: float, info: object) -> float:
        return _finite(value, info.field_name, lo=-90.0, hi=90.0)  # type: ignore[attr-defined]

    @field_validator("left_leg_raise", "right_leg_raise")
    @classmethod
    def _bounded_raise(cls, value: float, info: object) -> float:
        return _finite(value, info.field_name, lo=-10.0, hi=120.0)  # type: ignore[attr-defined]

    @classmethod
    def idle(cls) -> "AvatarPose":
        """The neutral, resting posture."""
        return cls()