"""Sprite sheet and expression overlay configuration."""

import math
import re

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _positive(value: float, label: str) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be a positive finite number")
    return value


def _positive(value: float, label: str) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be a positive finite number")
    return value


class SpriteSheetConfig(BaseModel):
    """Configuration for a horizontal-strip sprite sheet."""

    model_config = ConfigDict(extra="forbid", validate_default=True)

    image_path: str
    frame_width: int = 50
    frame_height: int = 303
    columns: int = 6
    rows: int = 1
    animations: dict[str, list[int]] = {}
    fps: int = 8

    @field_validator("frame_width", "frame_height", "columns", "rows", "fps")
    @classmethod
    def _positive_dims(cls, value: int) -> int:
        return _positive(value, "dimension")

    @model_validator(mode="after")
    def _validate_animations(self: "SpriteSheetConfig") -> "SpriteSheetConfig":
        total_frames = self.columns * self.rows
        for name, frames in self.animations.items():
            for f in frames:
                if not 0 <= f < total_frames:
                    raise ValueError(
                        f"animation {name!r} frame {f} out of range [0, {total_frames})"
                    )
        return self

    def frame_rect(self, index: int) -> tuple[int, int, int, int]:
        """Return (x, y, w, h) source rect for frame index."""
        col = index % self.columns
        row = index // self.columns
        x = col * self.frame_width
        y = row * self.frame_height
        return (x, y, self.frame_width, self.frame_height)

    def animation_duration(self, name: str) -> float:
        """Return total duration of animation in seconds."""
        frames = self.animations.get(name, [])
        return len(frames) / self.fps if frames else 0.0


class ExpressionOverlayConfig(BaseModel):
    """Configuration for expression image overlays."""

    model_config = ConfigDict(extra="forbid", validate_default=True)

    expressions: dict[str, str] = {}
    overlay_scale: float = 0.35
    overlay_y_offset: float = -20.0

    @field_validator("overlay_scale")
    @classmethod
    def _scale_range(cls, value: float) -> float:
        if not math.isfinite(value) or not 0.0 < value <= 2.0:
            raise ValueError("overlay_scale must be in (0, 2]")
        return value


def _hex_color(value: str) -> str:
    if not _HEX_COLOR.match(value):
        raise ValueError(f"color {value!r} must be a #RGB or #RRGGBB hex string")
    return value.lower()


__all__ = ["SpriteSheetConfig", "ExpressionOverlayConfig"]

