"""Avatar character configuration.

Appearance lives here, not in the avatar state machine. The character is a
compact, cute cartoon clock: a large circular orange body with two arms, two
hands, two thin short legs, oversized orange shoes, large expressive eyes,
a small mouth, clock hands and simple clock markings, all with dark outlines.

Every visual value is configurable. Proportions are approximated from the user
supplied design reference — they are *targets inspired by the reference*, not
measurements of any copyrighted source asset.
"""

import math
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _positive(value: float, label: str) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be a positive finite number")
    return value


class AvatarConfig(BaseModel):
    """Fully configurable appearance of the MISSMINUTES character."""

    model_config = ConfigDict(extra="forbid", validate_default=True)

    # Clock body dominates the character.
    body_width: float = 180.0
    body_height: float = 180.0
    body_color: str = "#FF8C2A"
    outline_color: str = "#2A1A0F"
    outline_width: float = 6.0

    # Eyes are large relative to the body.
    eye_size: float = 26.0
    eye_spacing: float = 44.0
    eye_color: str = "#FFFFFF"
    pupil_size: float = 10.0
    pupil_color: str = "#202020"
    eye_y_offset: float = -12.0

    # The mouth is small relative to the body.
    mouth_size: float = 16.0
    mouth_color: str = "#2A1A0F"
    mouth_y_offset: float = 28.0

    # Arms are thin relative to the body.
    arm_length: float = 48.0
    arm_thickness: float = 8.0
    arm_color: str = "#FF8C2A"
    hand_size: float = 12.0

    # Legs are thin and short; shoes are larger than the legs.
    leg_length: float = 36.0
    leg_thickness: float = 10.0
    leg_color: str = "#FF8C2A"
    shoe_width: float = 26.0
    shoe_height: float = 12.0
    shoe_color: str = "#FFB84C"

    # Clock hands fit inside the circular body.
    hour_hand_length: float = 42.0
    minute_hand_length: float = 62.0
    hand_thickness: float = 6.0
    hand_color: str = "#2A1A0F"

    # Simple clock markings.
    markings_count: int = 12
    markings_length: float = 9.0
    markings_thickness: float = 3.0
    markings_color: str = "#2A1A0F"

    center_pivot_size: float = 7.0
    center_pivot_color: str = "#2A1A0F"

    default_scale: float = 1.0

    @field_validator(
        "body_width",
        "body_height",
        "outline_width",
        "eye_size",
        "eye_spacing",
        "pupil_size",
        "mouth_size",
        "arm_length",
        "arm_thickness",
        "hand_size",
        "leg_length",
        "leg_thickness",
        "shoe_width",
        "shoe_height",
        "hour_hand_length",
        "minute_hand_length",
        "hand_thickness",
        "markings_length",
        "markings_thickness",
        "center_pivot_size",
        "default_scale",
    )
    @classmethod
    def _positive_dims(cls, value: float) -> float:
        return _positive(value, "dimension")

    @field_validator(
        "body_color",
        "outline_color",
        "eye_color",
        "pupil_color",
        "arm_color",
        "leg_color",
        "shoe_color",
        "hand_color",
        "markings_color",
        "center_pivot_color",
        "mouth_color",
    )
    @classmethod
    def _hex_color(cls, value: str) -> str:
        if not _HEX_COLOR.match(value):
            raise ValueError(f"color {value!r} must be a #RGB or #RRGGBB hex string")
        return value.lower()

    @field_validator("markings_count")
    @classmethod
    def _markings_count(cls, value: int) -> int:
        if not 1 <= value <= 72:
            raise ValueError("markings_count must be between 1 and 72")
        return value

    @model_validator(mode="after")
    def _consistent(self: "AvatarConfig") -> "AvatarConfig":
        if self.pupil_size > self.eye_size:
            raise ValueError("pupil_size must not exceed eye_size")
        radius = min(self.body_width, self.body_height) / 2.0
        if self.hour_hand_length >= radius:
            raise ValueError("hour_hand_length must fit inside the clock body")
        if self.minute_hand_length >= radius:
            raise ValueError("minute_hand_length must fit inside the clock body")
        return self

    @property
    def radius(self) -> float:
        """Radius of the clock body (half the smaller dimension)."""
        return min(self.body_width, self.body_height) / 2.0

    def body_rect(self) -> tuple[float, float]:
        """(width, height) of the clock body."""
        return (self.body_width, self.body_height)

    def model_dump_default(self) -> dict[str, Any]:
        """Serialisable JSON representation for the asset layout."""
        return self.model_dump()


class AvatarProportions(BaseModel):
    """Approximate character proportions derived from a configuration.

    These are documented design targets inspired by the supplied reference —
    not exact measurements of a copyrighted source asset.
    """

    model_config = ConfigDict(frozen=True)

    body_dominance: float
    arm_thinness: float
    leg_thinness: float
    leg_shortness: float
    shoe_to_leg_ratio: float
    eye_to_body_ratio: float
    pupil_to_eye_ratio: float
    mouth_to_body_ratio: float
    hand_to_body_ratio: float

    @field_validator(
        "body_dominance",
        "arm_thinness",
        "leg_thinness",
        "leg_shortness",
        "shoe_to_leg_ratio",
        "eye_to_body_ratio",
        "pupil_to_eye_ratio",
        "mouth_to_body_ratio",
        "hand_to_body_ratio",
    )
    @classmethod
    def _ratio(cls, value: float) -> float:
        return _finite_ratio(value)

    @classmethod
    def from_config(cls, config: AvatarConfig) -> "AvatarProportions":
        dominant = max(config.arm_length, config.leg_length)
        return cls(
            body_dominance=config.body_width / (config.body_width + dominant + config.shoe_height),
            arm_thinness=config.arm_thickness / config.body_width,
            leg_thinness=config.leg_thickness / config.body_width,
            leg_shortness=config.leg_length / config.body_height,
            shoe_to_leg_ratio=config.shoe_width / config.leg_length,
            eye_to_body_ratio=config.eye_size / config.body_width,
            pupil_to_eye_ratio=config.pupil_size / config.eye_size,
            mouth_to_body_ratio=config.mouth_size / config.body_width,
            hand_to_body_ratio=config.hand_size / config.body_width,
        )


def _finite_ratio(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("proportion must be finite")
    if not 0.0 < value <= 1.0:
        raise ValueError("proportion must be in (0, 1]")
    return value
