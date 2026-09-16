"""Arms and legs.

The character keeps four simple limbs — left/right arm and left/right leg —
represented as typed ``LimbState`` transforms with safe movement hooks. CHUNK 33
will expand this into walking cycles and detailed gestures; here limbs provide
basic idle positioning and hooked rotation/swing.
"""

import math
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from app.avatar.config import AvatarConfig
from app.avatar.models import AvatarPart, AvatarPose, AvatarTransform


class LimbSide(StrEnum):
    LEFT = "left"
    RIGHT = "right"


class LimbState(BaseModel):
    """Typed transform/state for one limb."""

    model_config = ConfigDict(frozen=True)

    part: AvatarPart
    side: LimbSide
    attach_x: float
    attach_y: float
    length: float
    thickness: float
    base_swing_deg: float = 0.0

    @field_validator("attach_x", "attach_y", "base_swing_deg")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("limb values must be finite")
        return value

    @field_validator("length", "thickness")
    @classmethod
    def _positive(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("limb length/thickness must be positive finite numbers")
        return value

    @classmethod
    def validate_transform(cls, transform: AvatarTransform) -> None:
        """Validate a derived transform for a limb part."""
        if transform.scale <= 0 or not math.isfinite(transform.scale):
            raise ValueError("limb transform scale must be a positive finite number")
        if not math.isfinite(transform.offset_x) or not math.isfinite(transform.offset_y):
            raise ValueError("limb transform offsets must be finite")
        if transform.part not in {
            AvatarPart.LEFT_ARM,
            AvatarPart.RIGHT_ARM,
            AvatarPart.LEFT_LEG,
            AvatarPart.RIGHT_LEG,
        }:
            raise ValueError(f"{transform.part} is not a limb part")

    def end_point(self) -> tuple[float, float]:
        """Endpoint (hand/shoe position) for rotation 0 = straight down."""
        radians = math.radians(self.base_swing_deg)
        x = self.attach_x + self.length * math.sin(radians)
        y = self.attach_y + self.length * math.cos(radians)
        return (x, y)


class ArmsAndLegs:
    """Rests the four limbs from an ``AvatarConfig`` and applies pose deltas."""

    def __init__(self, config: AvatarConfig | None = None) -> None:
        self._config = config or AvatarConfig()
        self._limbs: dict[AvatarPart, LimbState] = self._build()

    def _build(self) -> dict[AvatarPart, LimbState]:
        cfg = self._config
        half = cfg.body_width / 2.0
        arm_attach_y = -cfg.body_height / 2.0 * 0.15
        leg_attach_x = cfg.body_width * 0.24
        leg_attach_y = cfg.body_height / 2.0
        arms: dict[AvatarPart, LimbState] = {}
        for side, part, sign in (
            (LimbSide.LEFT, AvatarPart.LEFT_ARM, -1.0),
            (LimbSide.RIGHT, AvatarPart.RIGHT_ARM, 1.0),
        ):
            arms[part] = LimbState(
                part=part,
                side=side,
                attach_x=sign * (half - cfg.arm_thickness / 2.0 - 2.0),
                attach_y=arm_attach_y,
                length=cfg.arm_length,
                thickness=cfg.arm_thickness,
            )
        for side, part, sign in (
            (LimbSide.LEFT, AvatarPart.LEFT_LEG, -1.0),
            (LimbSide.RIGHT, AvatarPart.RIGHT_LEG, 1.0),
        ):
            arms[part] = LimbState(
                part=part,
                side=side,
                attach_x=sign * leg_attach_x,
                attach_y=leg_attach_y,
                length=cfg.leg_length,
                thickness=cfg.leg_thickness,
            )
        return arms

    @property
    def config(self) -> AvatarConfig:
        return self._config

    def limb(self, part: AvatarPart) -> LimbState | None:
        return self._limbs.get(part)

    def limbs(self) -> tuple[LimbState, ...]:
        return tuple(
            self._limbs[p]
            for p in (AvatarPart.LEFT_ARM, AvatarPart.RIGHT_ARM, AvatarPart.LEFT_LEG, AvatarPart.RIGHT_LEG)
        )

    def swing(self, part: AvatarPart, degrees: float) -> LimbState:
        """Rotate a limb from neutral: positive = clockwise (right hand rule)."""
        if not math.isfinite(degrees):
            raise ValueError("degrees must be finite")
        if part not in self._limbs:
            raise ValueError(f"{part} is not a limb")
        current = self._limbs[part]
        self._limbs[part] = current.model_copy(
            update={"base_swing_deg": max(-90.0, min(90.0, degrees))}
        )
        return self._limbs[part]

    def raise_leg(self, part: AvatarPart, degrees: float) -> LimbState:
        """Lift a leg forward (interpreted as negative swing for the left)."""
        if part not in (AvatarPart.LEFT_LEG, AvatarPart.RIGHT_LEG):
            raise ValueError("raise_leg only applies to legs")
        sign = -1.0 if part is AvatarPart.LEFT_LEG else 1.0
        return self.swing(part, max(-90.0, min(90.0, sign * degrees)))

    def reset(self) -> None:
        for part in list(self._limbs):
            current = self._limbs[part]
            self._limbs[part] = current.model_copy(update={"base_swing_deg": 0.0})

    def transforms(self, pose: AvatarPose | None = None) -> tuple[AvatarTransform, ...]:
        """Derive renderable transforms for each limb from the current pose."""
        pose = pose or AvatarPose.idle()
        out: list[AvatarTransform] = []
        for limb in self.limbs():
            extra: float
            if limb.part is AvatarPart.LEFT_ARM:
                extra = pose.left_arm_swing
            elif limb.part is AvatarPart.RIGHT_ARM:
                extra = pose.right_arm_swing
            elif limb.part is AvatarPart.LEFT_LEG:
                extra = pose.left_leg_raise
            else:
                extra = pose.right_leg_raise
            rotation = limb.base_swing_deg + extra
            out.append(
                AvatarTransform(
                    part=limb.part,
                    offset_x=limb.attach_x,
                    offset_y=limb.attach_y,
                    rotation_deg=max(-180.0, min(180.0, rotation)),
                    scale=1.0,
                )
            )
        return tuple(out)