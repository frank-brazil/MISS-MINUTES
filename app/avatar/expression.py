"""Expression system.

Expressions are data/config driven: they are named collections of parameter
deltas controlling eye openness, pupil position, eyebrow lift, mouth shape and
openness, face tilt and body tilt. A default set ships in code and is mirrored
as JSON data under ``ui/avatar/assets/expressions/`` so appearance can be
adjusted without touching behaviour.
"""

import math
from typing import Mapping

from pydantic import BaseModel, ConfigDict, field_validator

from app.avatar.mouth import MouthShape


class AvatarExpression(BaseModel):
    """Parameter deltas that describe one facial expression."""

    model_config = ConfigDict(frozen=True)

    eye_openness: float = 1.0
    pupil_x: float = 0.0
    pupil_y: float = 0.0
    eyebrow_lift: float = 0.0
    mouth_shape: MouthShape = MouthShape.CLOSED
    mouth_openness: float = 0.0
    face_tilt_deg: float = 0.0
    body_tilt_deg: float = 0.0

    @field_validator("eye_openness", "eyebrow_lift", "mouth_openness")
    @classmethod
    def _unit_range(cls, value: float) -> float:
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("value must be in [0, 1]")
        return value

    @field_validator("pupil_x", "pupil_y")
    @classmethod
    def _pupil_range(cls, value: float) -> float:
        if not math.isfinite(value) or not -1.0 <= value <= 1.0:
            raise ValueError("pupil offset must be in [-1, 1]")
        return value

    @field_validator("face_tilt_deg", "body_tilt_deg")
    @classmethod
    def _tilt_range(cls, value: float) -> float:
        if not math.isfinite(value) or not -30.0 <= value <= 30.0:
            raise ValueError("tilt must be in [-30, 30] degrees")
        return value

    @classmethod
    def neutral(cls) -> "AvatarExpression":
        return cls()

    def with_pupil(self, x: float, y: float) -> "AvatarExpression":
        """Copy with a new static pupil offset (clamped)."""
        return self.model_copy(
            update={
                "pupil_x": max(-1.0, min(1.0, x)),
                "pupil_y": max(-1.0, min(1.0, y)),
            }
        )


DEFAULT_EXPRESSIONS: dict[str, AvatarExpression] = {
    "neutral": AvatarExpression(eye_openness=1.0, mouth_shape=MouthShape.CLOSED),
    "happy": AvatarExpression(
        eye_openness=0.9,
        eyebrow_lift=0.4,
        mouth_shape=MouthShape.SMILE,
        mouth_openness=0.3,
    ),
    "sad": AvatarExpression(
        eye_openness=0.6,
        pupil_y=0.3,
        mouth_shape=MouthShape.CONCERNED,
        mouth_openness=0.1,
        face_tilt_deg=-2.0,
    ),
    "concerned": AvatarExpression(
        eye_openness=0.8,
        eyebrow_lift=0.5,
        mouth_shape=MouthShape.CONCERNED,
        mouth_openness=0.15,
    ),
    "surprised": AvatarExpression(
        eye_openness=1.0,
        pupil_y=-0.3,
        eyebrow_lift=1.0,
        mouth_shape=MouthShape.SURPRISED,
        mouth_openness=0.95,
    ),
    "thinking": AvatarExpression(
        eye_openness=0.7,
        pupil_y=-0.4,
        pupil_x=0.3,
        eyebrow_lift=0.3,
        mouth_shape=MouthShape.CLOSED,
        face_tilt_deg=3.0,
    ),
    "focused": AvatarExpression(
        eye_openness=0.9,
        pupil_x=0.0,
        eyebrow_lift=0.1,
        mouth_shape=MouthShape.CLOSED,
    ),
    "warning": AvatarExpression(
        eye_openness=0.95,
        eyebrow_lift=0.8,
        mouth_shape=MouthShape.CLOSED,
    ),
    "success": AvatarExpression(
        eye_openness=0.95,
        pupil_y=-0.2,
        eyebrow_lift=0.5,
        mouth_shape=MouthShape.SMILE,
        mouth_openness=0.4,
    ),
    "confused": AvatarExpression(
        eye_openness=0.8,
        pupil_x=0.6,
        pupil_y=-0.2,
        eyebrow_lift=0.0,
        mouth_shape=MouthShape.CONCERNED,
        mouth_openness=0.2,
    ),
    "excited": AvatarExpression(
        eye_openness=1.0,
        pupil_y=-0.2,
        eyebrow_lift=0.8,
        mouth_shape=MouthShape.SMILE,
        mouth_openness=0.5,
        face_tilt_deg=2.0,
    ),
}

PREDEFINED_EXPRESSION_NAMES: tuple[str, ...] = tuple(DEFAULT_EXPRESSIONS)


class UnknownExpressionError(KeyError):
    """Raised when referencing an expression name that does not exist."""


class ExpressionSet:
    """A validated, data-driven collection of named expressions."""

    def __init__(self, expressions: Mapping[str, AvatarExpression] | None = None) -> None:
        data = dict(DEFAULT_EXPRESSIONS if expressions is None else expressions)
        if not data:
            raise ValueError("at least one expression is required")
        for name, params in data.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("expression names must be non-empty strings")
            if not isinstance(params, AvatarExpression):
                raise ValueError(f"expression {name!r} must be an AvatarExpression")
        self._expressions: dict[str, AvatarExpression] = dict(data)

    def names(self) -> tuple[str, ...]:
        return tuple(self._expressions)

    def has(self, name: str) -> bool:
        return name in self._expressions

    def get(self, name: str) -> AvatarExpression:
        if name not in self._expressions:
            raise UnknownExpressionError(name)
        return self._expressions[name]

    def copy(self) -> "ExpressionSet":
        return ExpressionSet(dict(self._expressions))


class ExpressionController:
    """Applies an expression to the character and tracks the active one."""

    def __init__(self, expressions: ExpressionSet | None = None) -> None:
        self._set = expressions or ExpressionSet()
        self._current = "neutral" if self._set.has("neutral") else self._set.names()[0]

    @property
    def expressions(self) -> ExpressionSet:
        return self._set

    @property
    def current(self) -> str:
        return self._current

    def params(self) -> AvatarExpression:
        return self._set.get(self._current)

    def apply(self, name: str) -> AvatarExpression:
        params = self._set.get(name)  # raises UnknownExpressionError safely
        self._current = name
        return params

    def names(self) -> tuple[str, ...]:
        return self._set.names()
