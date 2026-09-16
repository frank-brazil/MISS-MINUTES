"""Clock-face component.

The clock face (outer body, simple markings, hour hand, minute hand, center
pivot) renders independently from facial expressions. Hand angles are computed
deterministically from wall-clock time.
"""

import math

from pydantic import BaseModel, ConfigDict, field_validator

from app.avatar.config import AvatarConfig
from app.avatar.models import AvatarPart, AvatarTransform


class ClockHandState(BaseModel):
    """One clock hand snapshot."""

    model_config = ConfigDict(frozen=True)

    part: AvatarPart
    length: float
    thickness: float
    color: str
    angle_deg: float = 0.0

    @field_validator("length", "thickness")
    @classmethod
    def _positive(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("hand length/thickness must be positive finite numbers")
        return value

    @field_validator("angle_deg")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("hand angle must be finite")
        return value

    def endpoint(self) -> tuple[float, float]:
        """Endpoint using 12-o'clock = 0 degrees, clockwise positive."""
        radians = math.radians(self.angle_deg - 90.0)
        x = self.length * math.cos(radians)
        y = self.length * math.sin(radians)
        return (x, y)


class ClockFace:
    """Computes markings and hand transforms from a configuration."""

    def __init__(self, config: AvatarConfig | None = None) -> None:
        self._config = config or AvatarConfig()

    @property
    def config(self) -> AvatarConfig:
        return self._config

    @property
    def radius(self) -> float:
        return self._config.radius

    def marking_angles(self) -> tuple[float, ...]:
        """Angles (degrees from 12 o'clock, clockwise) per marking."""
        count = self._config.markings_count
        spacing = 360.0 / count
        return tuple((k * spacing) % 360.0 for k in range(count))

    @classmethod
    def validate_hand(cls, hand: ClockHandState) -> None:
        """Validate a hand snapshot fits inside the clock body."""
        if hand.length <= 0 or not math.isfinite(hand.length):
            raise ValueError("hand length must be a positive finite number")
        if hand.thickness <= 0 or not math.isfinite(hand.thickness):
            raise ValueError("hand thickness must be a positive finite number")
        if hand.part not in (AvatarPart.HOUR_HAND, AvatarPart.MINUTE_HAND):
            raise ValueError(f"{hand.part} is not a clock hand part")

    @classmethod
    def hand_angles(cls, hour: int, minute: int, second: int = 0) -> tuple[float, float]:
        """(hour_hand_angle, minute_hand_angle) in degrees from 12 o'clock."""
        hour_angle = ((hour % 12) + minute / 60.0) * 30.0
        minute_angle = minute * 6.0 + second * 0.1
        return (hour_angle % 360.0, minute_angle % 360.0)

    def set_time(self, hour: int, minute: int, second: int = 0) -> tuple[ClockHandState, ClockHandState]:
        """Return stable hand snapshots for the given wall-clock time."""
        hour_angle, minute_angle = self.hand_angles(hour, minute, second)
        cfg = self._config
        hour_hand = ClockHandState(
            part=AvatarPart.HOUR_HAND,
            length=cfg.hour_hand_length,
            thickness=cfg.hand_thickness,
            color=cfg.hand_color,
            angle_deg=hour_angle,
        )
        minute_hand = ClockHandState(
            part=AvatarPart.MINUTE_HAND,
            length=cfg.minute_hand_length,
            thickness=cfg.hand_thickness,
            color=cfg.hand_color,
            angle_deg=minute_angle,
        )
        return (hour_hand, minute_hand)

    def transforms_for(
        self, hour: int, minute: int, second: int = 0, *, scale: float = 1.0
    ) -> tuple[AvatarTransform, ...]:
        """(center pivot, hour hand, minute hand) transforms."""
        hour_hand, minute_hand = self.set_time(hour, minute, second)
        pivot = AvatarTransform(
            part=AvatarPart.CENTER_PIVOT,
            offset_x=0.0,
            offset_y=0.0,
            rotation_deg=0.0,
            scale=scale,
        )
        return (
            pivot,
            AvatarTransform(part=AvatarPart.HOUR_HAND, rotation_deg=hour_hand.angle_deg, scale=scale),
            AvatarTransform(part=AvatarPart.MINUTE_HAND, rotation_deg=minute_hand.angle_deg, scale=scale),
        )

    def center_pivot(self) -> AvatarTransform:
        return AvatarTransform(part=AvatarPart.CENTER_PIVOT, scale=1.0)