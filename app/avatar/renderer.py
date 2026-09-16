"""Renderer abstraction.

``AvatarRenderer`` is the boundary every concrete backend (SVG, Tkinter, Qt,
HTML canvas, …) implements. The engine drives it with poses, expressions,
per-part transforms, eye/mouth snapshots and frame rendering; the renderer
never talks to the avatar state machine. A deterministic ``FakeAvatarRenderer``
composes the character from primitives for offline tests.
"""

import logging
import math
from abc import ABC, abstractmethod
from typing import Callable, ClassVar, Literal, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.avatar.clockface import ClockFace, ClockHandState
from app.avatar.config import AvatarConfig
from app.avatar.expression import AvatarExpression
from app.avatar.eyes import EyeState
from app.avatar.gestures import GestureFrame
from app.avatar.limbs import ArmsAndLegs
from app.avatar.lipsync import VisemeState
from app.avatar.mouth import MouthShape, MouthState
from app.avatar.models import AvatarPart, AvatarPose, AvatarState, AvatarTransform
from app.avatar.walking import WalkingFrame

_PRIMITIVE_KINDS = ("circle", "line", "ellipse")


class RenderPrimitive(BaseModel):
    """One deterministic drawing command."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["circle", "line", "ellipse"]
    part: AvatarPart | None = None
    color: str = "#000000"
    x: float = 0.0
    y: float = 0.0
    x2: float | None = None
    y2: float | None = None
    radius: float | None = None
    rx: float | None = None
    ry: float | None = None
    thickness: float | None = None
    fill: bool = True

    @field_validator("x", "y", "x2", "y2")
    @classmethod
    def _finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("primitive coordinates must be finite")
        return value

    @model_validator(mode="after")
    def _by_kind(self: "RenderPrimitive") -> "RenderPrimitive":
        if self.kind == "circle":
            if self.radius is None or self.radius <= 0:
                raise ValueError("circle primitive requires a positive radius")
        elif self.kind == "line":
            if self.x2 is None or self.y2 is None or self.thickness is None or self.thickness <= 0:
                raise ValueError("line primitive requires x2, y2 and a positive thickness")
        elif self.kind == "ellipse":
            if self.rx is None or self.ry is None or self.rx <= 0 or self.ry <= 0:
                raise ValueError("ellipse primitive requires positive rx and ry")
        return self


class RenderFrame(BaseModel):
    """A rendered character frame."""

    model_config = ConfigDict(frozen=True)

    frame_index: int
    state: AvatarState
    expression: str
    pose: AvatarPose
    primitives: tuple[RenderPrimitive, ...] = ()
    viseme: VisemeState | None = None
    gesture: GestureFrame | None = None
    walking: WalkingFrame | None = None
    timestamp: float = 0.0

    def primitives_for(self, part: AvatarPart) -> tuple[RenderPrimitive, ...]:
        return tuple(
            primitive for primitive in self.primitives if primitive.part is part
        )


class AvatarRenderer(ABC):
    """Boundary between the avatar engine and a concrete rendering backend."""

    name: ClassVar[str]
    description: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [
            attribute
            for attribute in ("name", "description")
            if not hasattr(cls, attribute)
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} must define required attribute(s): {', '.join(missing)}"
            )

    @abstractmethod
    def update_pose(self, pose: AvatarPose) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_expression(self, name: str, params: AvatarExpression) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_eyes(self, eyes: EyeState) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_mouth(self, mouth: MouthState) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_viseme(self, viseme: VisemeState | None) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_gesture(self, gesture: GestureFrame | None) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_walking(self, walking: WalkingFrame | None) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_transform(self, part: AvatarPart, transform: AvatarTransform) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_clock_time(self, hour: int, minute: int, second: int = 0) -> None:
        raise NotImplementedError

    @abstractmethod
    def render_scene(self) -> RenderFrame:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


class FakeAvatarRenderer(AvatarRenderer):
    """Deterministic offline renderer that composes the character as
    structured primitives. Values are approximate visual targets — the intent
    is to exercise the engine, not to ship final art."""

    name = "fake-avatar-renderer"
    description = "Deterministic primitive composition for offline avatar tests."

    FACE_COLOR = "#FFF0DC"

    def __init__(
        self,
        config: AvatarConfig | None = None,
        *,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        import time as _time

        self._config = config or AvatarConfig()
        self._now_fn = now_fn or _time.time
        self._pose = AvatarPose.idle()
        self._expression_name = "neutral"
        self._expression = AvatarExpression.neutral()
        self._eyes = EyeState()
        self._mouth = MouthState()
        self._viseme: VisemeState | None = None
        self._gesture: GestureFrame | None = None
        self._walking: WalkingFrame | None = None
        self._transforms: dict[AvatarPart, AvatarTransform] = {}
        self._arms = ArmsAndLegs(self._config)
        self._clock = ClockFace(self._config)
        self._hour, self._minute, self._second = 10, 10, 0
        self._frame_index = 0
        self._last_frame: RenderFrame | None = None
        self._closed = False
        self._calls: list[str] = []
        self._logger = logging.getLogger(__name__)

    @property
    def config(self) -> AvatarConfig:
        return self._config

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def last_frame(self) -> RenderFrame | None:
        return self._last_frame

    @property
    def calls(self) -> tuple[str, ...]:
        return tuple(self._calls)

    def update_pose(self, pose: AvatarPose) -> None:
        self._calls.append("update_pose")
        self._pose = pose

    def update_expression(self, name: str, params: AvatarExpression) -> None:
        self._calls.append("update_expression")
        self._expression_name = name
        self._expression = params

    def update_eyes(self, eyes: EyeState) -> None:
        self._calls.append("update_eyes")
        self._eyes = eyes

    def update_mouth(self, mouth: MouthState) -> None:
        self._calls.append("update_mouth")
        self._mouth = mouth

    def update_viseme(self, viseme: VisemeState | None) -> None:
        self._calls.append("update_viseme")
        self._viseme = viseme

    def update_gesture(self, gesture: GestureFrame | None) -> None:
        self._calls.append("update_gesture")
        self._gesture = gesture

    def update_walking(self, walking: WalkingFrame | None) -> None:
        self._calls.append("update_walking")
        self._walking = walking

    @property
    def viseme(self) -> VisemeState | None:
        return self._viseme

    @property
    def gesture(self) -> GestureFrame | None:
        return self._gesture

    @property
    def walking(self) -> WalkingFrame | None:
        return self._walking

    def update_transform(self, part: AvatarPart, transform: AvatarTransform) -> None:
        self._calls.append("update_transform")
        self._transforms[part] = transform

    def set_clock_time(self, hour: int, minute: int, second: int = 0) -> None:
        self._calls.append("set_clock_time")
        self._hour = hour % 24
        self._minute = minute % 60
        self._second = max(0, min(60, second))

    def _limb_geometry(self, part: AvatarPart) -> tuple[float, float, float, float] | None:
        """(x1, y1, x2, y2) for a limb line, honouring overridden transforms."""
        transform = self._transforms.get(part)
        limb = self._arms.limb(part)
        if limb is None:
            return None
        attach = (limb.attach_x, limb.attach_y)
        rotation = limb.base_swing_deg
        if transform is not None:
            attach = (transform.offset_x, transform.offset_y)
            rotation = transform.rotation_deg
        radians = math.radians(rotation)
        dx = math.sin(radians) * limb.length
        dy = math.cos(radians) * limb.length
        return (attach[0], attach[1], attach[0] + dx, attach[1] + dy)

    def _hand_endpoints(self) -> tuple[tuple[float, float], tuple[float, float]]:
        hour_hand, minute_hand = self._clock.set_time(self._hour, self._minute, self._second)
        return (hour_hand.endpoint(), minute_hand.endpoint())

    def _compose(self) -> list[RenderPrimitive]:
        cfg = self._config
        bob = self._pose.body_bob
        radius = cfg.radius
        primitives: list[RenderPrimitive] = []

        # Clock body (outline behind solid body).
        primitives.append(
            RenderPrimitive(
                kind="ellipse",
                part=AvatarPart.CLOCK_BODY,
                color=cfg.outline_color,
                x=0.0,
                y=bob,
                rx=radius + cfg.outline_width / 2.0,
                ry=radius + cfg.outline_width / 2.0,
                fill=True,
            )
        )
        primitives.append(
            RenderPrimitive(
                kind="ellipse",
                part=AvatarPart.CLOCK_BODY,
                color=cfg.body_color,
                x=0.0,
                y=bob,
                rx=radius,
                ry=radius,
                fill=True,
            )
        )

        # Legs and shoes.
        shoe_map = {
            AvatarPart.LEFT_LEG: AvatarPart.LEFT_SHOE,
            AvatarPart.RIGHT_LEG: AvatarPart.RIGHT_SHOE,
        }
        for leg, shoe in shoe_map.items():
            geometry = self._limb_geometry(leg)
            if geometry is None:
                continue
            x1, y1, x2, y2 = geometry
            primitives.append(
                RenderPrimitive(
                    kind="line",
                    part=leg,
                    color=cfg.leg_color,
                    x=x1,
                    y=y1,
                    x2=x2,
                    y2=y2,
                    thickness=cfg.leg_thickness,
                    fill=False,
                )
            )
            primitives.append(
                RenderPrimitive(
                    kind="ellipse",
                    part=shoe,
                    color=cfg.shoe_color,
                    x=x2,
                    y=y2 + cfg.shoe_height / 2.0,
                    rx=cfg.shoe_width / 2.0,
                    ry=cfg.shoe_height / 2.0,
                    fill=True,
                )
            )

        # Arms and hands.
        hand_map = {
            AvatarPart.LEFT_ARM: AvatarPart.LEFT_HAND,
            AvatarPart.RIGHT_ARM: AvatarPart.RIGHT_HAND,
        }
        for arm, hand in hand_map.items():
            geometry = self._limb_geometry(arm)
            if geometry is None:
                continue
            x1, y1, x2, y2 = geometry
            primitives.append(
                RenderPrimitive(
                    kind="line",
                    part=arm,
                    color=cfg.arm_color,
                    x=x1,
                    y=y1,
                    x2=x2,
                    y2=y2,
                    thickness=cfg.arm_thickness,
                    fill=False,
                )
            )
            primitives.append(
                RenderPrimitive(
                    kind="circle",
                    part=hand,
                    color=cfg.arm_color,
                    x=x2,
                    y=y2,
                    radius=cfg.hand_size / 2.0,
                    fill=True,
                )
            )

        # Clock face, markings, hands, pivot.
        primitives.append(
            RenderPrimitive(
                kind="ellipse",
                part=AvatarPart.CLOCK_FACE,
                color=self.FACE_COLOR,
                x=0.0,
                y=bob,
                rx=radius * 0.78,
                ry=radius * 0.78,
                fill=True,
            )
        )
        inner = radius * 0.68
        outer = inner + cfg.markings_length
        for angle in self._clock.marking_angles():
            radians = math.radians(angle - 90.0)
            primitives.append(
                RenderPrimitive(
                    kind="line",
                    part=AvatarPart.CLOCK_FACE,
                    color=cfg.markings_color,
                    x=math.cos(radians) * inner,
                    y=bob + math.sin(radians) * inner,
                    x2=math.cos(radians) * outer,
                    y2=bob + math.sin(radians) * outer,
                    thickness=cfg.markings_thickness,
                    fill=False,
                )
            )
        hour_end, minute_end = self._hand_endpoints()
        primitives.append(
            RenderPrimitive(
                kind="line",
                part=AvatarPart.MINUTE_HAND,
                color=cfg.hand_color,
                x=0.0,
                y=bob,
                x2=minute_end[0],
                y2=bob + minute_end[1],
                thickness=cfg.hand_thickness,
                fill=False,
            )
        )
        primitives.append(
            RenderPrimitive(
                kind="line",
                part=AvatarPart.HOUR_HAND,
                color=cfg.hand_color,
                x=0.0,
                y=bob,
                x2=hour_end[0],
                y2=bob + hour_end[1],
                thickness=cfg.hand_thickness,
                fill=False,
            )
        )
        primitives.append(
            RenderPrimitive(
                kind="circle",
                part=AvatarPart.CENTER_PIVOT,
                color=cfg.center_pivot_color,
                x=0.0,
                y=bob,
                radius=cfg.center_pivot_size / 2.0,
                fill=True,
            )
        )

        # Eyes and pupils.
        openness = self._eyes.left_openness
        eye_radius = cfg.eye_size / 2.0
        for side in (-1.0, 1.0):
            cx = side * cfg.eye_spacing / 2.0
            cy = cfg.eye_y_offset + bob
            part = AvatarPart.LEFT_EYE if side < 0 else AvatarPart.RIGHT_EYE
            primitives.append(
                RenderPrimitive(
                    kind="ellipse",
                    part=part,
                    color=cfg.eye_color,
                    x=cx,
                    y=cy,
                    rx=eye_radius,
                    ry=max(eye_radius * openness, 1.0),
                    fill=True,
                )
            )
            pupil_radius = (cfg.pupil_size / 2.0) * (0.5 + 0.5 * openness)
            px = cx + self._eyes.pupil_x * (eye_radius - pupil_radius)
            py = cy + self._eyes.pupil_y * (eye_radius - pupil_radius)
            primitives.append(
                RenderPrimitive(
                    kind="circle",
                    part=part,
                    color=cfg.pupil_color,
                    x=px,
                    y=py,
                    radius=pupil_radius,
                    fill=True,
                )
            )

        # Mouth.
        mouth_y = cfg.mouth_y_offset + bob
        mouth_half = cfg.mouth_size / 2.0
        shape = self._mouth.shape
        if shape in (MouthShape.OPEN, MouthShape.SURPRISED, MouthShape.SPEAKING, MouthShape.SMALL_OPEN):
            openness_m = self._mouth.openness
            primitives.append(
                RenderPrimitive(
                    kind="ellipse",
                    part=AvatarPart.MOUTH,
                    color=cfg.mouth_color,
                    x=0.0,
                    y=mouth_y,
                    rx=mouth_half * 0.6,
                    ry=max(mouth_half * openness_m, 1.0),
                    fill=True,
                )
            )
        elif shape is MouthShape.SMILE or shape is MouthShape.CONCERNED:
            flip = -1.0 if shape is MouthShape.SMILE else 1.0
            primitives.append(
                RenderPrimitive(
                    kind="line",
                    part=AvatarPart.MOUTH,
                    color=cfg.mouth_color,
                    x=-mouth_half,
                    y=mouth_y + flip * 0.2 * mouth_half,
                    x2=mouth_half,
                    y2=mouth_y - flip * 0.2 * mouth_half,
                    thickness=max(cfg.outline_width / 2.0, 1.0),
                    fill=False,
                )
            )
        else:  # CLOSED
            primitives.append(
                RenderPrimitive(
                    kind="line",
                    part=AvatarPart.MOUTH,
                    color=cfg.mouth_color,
                    x=-mouth_half,
                    y=mouth_y,
                    x2=mouth_half,
                    y2=mouth_y,
                    thickness=max(cfg.outline_width / 2.0, 1.0),
                    fill=False,
                )
            )
        return primitives

    def render_scene(self) -> RenderFrame:
        """Compose and return the next deterministic frame."""
        self._frame_index += 1
        frame = RenderFrame(
            frame_index=self._frame_index,
            state=AvatarState.IDLE,
            expression=self._expression_name,
            pose=self._pose,
            primitives=tuple(self._compose()),
            viseme=self._viseme,
            gesture=self._gesture,
            walking=self._walking,
            timestamp=self._now_fn(),
        )
        self._last_frame = frame
        self._logger.info("Avatar frame %d rendered", frame.frame_index)
        return frame

    def close(self) -> None:
        self._calls.append("close")
        self._closed = True
        self._last_frame = None


__all__ = [
    "AvatarRenderer",
    "FakeAvatarRenderer",
    "RenderFrame",
    "RenderPrimitive",
    "AvatarPart",
    "AvatarPose",
    "AvatarState",
    "AvatarTransform",
    "ClockHandState",
    "GestureFrame",
    "VisemeState",
    "WalkingFrame",
]