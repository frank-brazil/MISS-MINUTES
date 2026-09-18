"""Sprite sheet renderer base class.

Provides common logic for rendering avatar from sprite sheets with expression overlays.
Backend-specific implementations (Tkinter, Web) inherit from this class.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict

from app.avatar.clockface import ClockFace
from app.avatar.config import AvatarConfig
from app.avatar.expression import AvatarExpression
from app.avatar.eyes import EyeState
from app.avatar.gestures import GestureFrame
from app.avatar.limbs import ArmsAndLegs
from app.avatar.lipsync import VisemeState
from app.avatar.models import AvatarPart, AvatarPose, AvatarState, AvatarTransform
from app.avatar.mouth import MouthState
from app.avatar.renderer import AvatarRenderer, RenderFrame, RenderPrimitive
from app.avatar.walking import WalkingFrame

_logger = logging.getLogger(__name__)


class CachedFrame(BaseModel):
    """A cached frame image (backend-specific data)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    index: int
    data: Any
    width: int
    height: int


class CachedOverlay(BaseModel):
    """A cached expression overlay image (backend-specific data)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    data: Any
    width: int
    height: int


class SpriteSheetRenderer(AvatarRenderer, ABC):
    """Base class for sprite sheet based avatar rendering.

    Handles:
    - Loading and caching sprite sheet frames
    - Loading and caching expression overlays
    - Animation state machine (frame index, timing)
    - Compositing body frame + expression overlay
    - Clock hands, limbs rendered procedurally on top
    """

    name = "sprite-sheet-base"
    description = "Base class for sprite sheet based avatar renderers"

    def __init__(
        self,
        config: AvatarConfig | None = None,
        *,
        now_fn: Callable[[], float] | None = None,
        asset_root: Path | None = None,
    ) -> None:
        import time as _time

        self._config = config or AvatarConfig()
        self._now_fn = now_fn or _time.time
        self._asset_root = asset_root or Path("backend/assets/avatar/character")

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

        self._animation_frame = 0
        self._animation_timer = 0.0
        self._current_animation = "idle"
        self._animation_loop = True

        self._cached_frames: dict[int, CachedFrame] = {}
        self._cached_overlays: dict[str, CachedOverlay] = {}
        self._sheet_loaded = False

        self._init_sprite_sheet()
        self._init_expression_overlays()

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

    def _init_sprite_sheet(self) -> None:
        """Load and cache sprite sheet frames."""
        ss = self._config.sprite_sheet
        if ss is None:
            _logger.info("No sprite sheet configured, using procedural rendering")
            return

        sheet_path = self._asset_root / ss.image_path
        if not sheet_path.exists():
            _logger.warning("Sprite sheet not found at %s", sheet_path)
            return

        try:
            self._load_sheet_image(sheet_path)
            self._sheet_loaded = True
            _logger.info("Loaded sprite sheet: %s (%dx%d frames)", sheet_path, ss.columns, ss.rows)
        except Exception as e:
            _logger.error("Failed to load sprite sheet: %s", e)

    @abstractmethod
    def _load_sheet_image(self, path: Path) -> None:
        """Load the full sprite sheet image (backend-specific)."""
        raise NotImplementedError

    @abstractmethod
    def _crop_frame(self, sheet_image: Any, x: int, y: int, w: int, h: int) -> Any:
        """Crop a frame from the sheet image (backend-specific)."""
        raise NotImplementedError

    def _cache_frame(self, index: int) -> CachedFrame | None:
        """Extract and cache a single frame from the sprite sheet."""
        ss = self._config.sprite_sheet
        if ss is None:
            return None

        if index in self._cached_frames:
            return self._cached_frames[index]

        x, y, w, h = ss.frame_rect(index)
        frame_img = self._crop_frame(self._sheet_image, x, y, w, h)
        cached = CachedFrame(index=index, data=frame_img, width=w, height=h)
        self._cached_frames[index] = cached
        return cached

    def get_frame(self, index: int) -> CachedFrame | None:
        """Get cached frame, loading if needed."""
        if not self._sheet_loaded:
            return None
        return self._cached_frames.get(index) or self._cache_frame(index)

    def _init_expression_overlays(self) -> None:
        """Load and cache expression overlay images."""
        eo = self._config.expression_overlays
        if eo is None:
            return

        for name, filename in eo.expressions.items():
            overlay_path = self._asset_root / filename
            if not overlay_path.exists():
                _logger.warning("Expression overlay not found: %s", overlay_path)
                continue
            try:
                self._load_overlay_image(name, overlay_path)
                _logger.debug("Loaded expression overlay: %s", filename)
            except Exception as e:
                _logger.error("Failed to load expression overlay %s: %s", filename, e)

    @abstractmethod
    def _load_overlay_image(self, name: str, path: Path) -> None:
        """Load and cache an expression overlay (backend-specific)."""
        raise NotImplementedError

    @abstractmethod
    def _scale_overlay(self, overlay: CachedOverlay, target_w: int, target_h: int) -> Any:
        """Scale overlay to target size (backend-specific)."""
        raise NotImplementedError

    def get_overlay(self, name: str) -> CachedOverlay | None:
        """Get cached expression overlay."""
        return self._cached_overlays.get(name)

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

    def update_transform(self, part: AvatarPart, transform: AvatarTransform) -> None:
        self._calls.append("update_transform")
        self._transforms[part] = transform

    def set_clock_time(self, hour: int, minute: int, second: int = 0) -> None:
        self._calls.append("set_clock_time")
        self._hour = hour % 24
        self._minute = minute % 60
        self._second = max(0, min(60, second))

    def _update_animation(self, dt: float) -> int:
        """Update animation frame based on current animation and time."""
        ss = self._config.sprite_sheet
        if ss is None or not self._sheet_loaded:
            return 0

        frames = ss.animations.get(self._current_animation, [0])
        if not frames:
            return 0

        frame_duration = 1.0 / ss.fps
        self._animation_timer += dt

        while self._animation_timer >= frame_duration:
            self._animation_timer -= frame_duration
            self._animation_frame += 1
            if self._animation_frame >= len(frames):
                if self._animation_loop:
                    self._animation_frame = 0
                else:
                    self._animation_frame = len(frames) - 1
                    break

        return frames[self._animation_frame]

    def set_animation(self, name: str, loop: bool = True) -> None:
        """Set the current animation by name."""
        ss = self._config.sprite_sheet
        if ss is None or name not in ss.animations:
            name = "idle"
        if name != self._current_animation:
            self._current_animation = name
            self._animation_frame = 0
            self._animation_timer = 0.0
            self._animation_loop = loop

    def _get_state_animation(self, state: AvatarState) -> tuple[str, bool]:
        """Map avatar state to animation name and loop flag."""
        mapping = {
            AvatarState.IDLE: ("idle", True),
            AvatarState.LISTENING: ("idle", True),
            AvatarState.THINKING: ("idle", True),
            AvatarState.WORKING: ("idle", True),
            AvatarState.SPEAKING: ("talk", True),
            AvatarState.HAPPY: ("idle", True),
            AvatarState.CONCERNED: ("idle", True),
            AvatarState.WARNING: ("idle", True),
            AvatarState.SUCCESS: ("idle", True),
            AvatarState.ERROR: ("idle", True),
            AvatarState.SLEEPING: ("idle", True),
            AvatarState.HIDDEN: ("idle", True),
            AvatarState.WALKING: ("walk", True),
            AvatarState.EXPLAINING: ("idle", True),
            AvatarState.INTERRUPTED: ("idle", True),
        }
        return mapping.get(state, ("idle", True))

    def _get_expression_overlay_name(self, expression: str) -> str | None:
        """Map expression name to overlay image name."""
        eo = self._config.expression_overlays
        if eo is None:
            return None
        return eo.expressions.get(expression)

    def _compose_primitives(self) -> list[RenderPrimitive]:
        """Compose the avatar frame as primitives (for FakeRenderer compatibility).

        For sprite sheet backends, this returns an empty list since rendering
        is done directly in the backend's render method.
        """
        return []

    def _draw_sprite_frame(self, frame_idx: int, x: float, y: float, scale: float) -> None:
        """Draw a sprite frame at position (backend-specific)."""
        raise NotImplementedError

    def _draw_overlay(self, overlay_name: str, x: float, y: float, scale: float) -> None:
        """Draw an expression overlay at position (backend-specific)."""
        raise NotImplementedError

    def _draw_procedural_parts(self) -> None:
        """Draw procedural parts: clock hands, limbs (backend-specific)."""
        raise NotImplementedError

    @abstractmethod
    def _begin_frame(self) -> None:
        """Begin a new frame (clear canvas, etc.)."""
        raise NotImplementedError

    @abstractmethod
    def _end_frame(self) -> RenderFrame:
        """End frame and return RenderFrame."""
        raise NotImplementedError

    def render_scene(self) -> RenderFrame:
        """Render one frame of the avatar."""
        self._frame_index += 1

        dt = 1.0 / 60.0
        current_state = AvatarState.IDLE
        if hasattr(self, "_controller_state"):
            current_state = self._controller_state

        frame_idx = self._update_animation(dt)
        anim_name, _ = self._get_state_animation(current_state)
        if anim_name != self._current_animation:
            self.set_animation(anim_name)
            frame_idx = self._update_animation(0.0)

        self._begin_frame()

        scale = self._config.default_scale
        body_x = 0.0
        body_y = self._pose.body_bob

        frame = self.get_frame(frame_idx)
        if frame:
            self._draw_sprite_frame(frame_idx, body_x, body_y, scale)

        overlay_name = self._get_expression_overlay_name(self._expression_name)
        if overlay_name:
            overlay = self.get_overlay(overlay_name)
            if overlay:
                eo = self._config.expression_overlays
                if eo:
                    overlay_x = body_x
                    overlay_y = body_y + eo.overlay_y_offset
                    overlay_scale = scale * eo.overlay_scale
                    self._draw_overlay(overlay_name, overlay_x, overlay_y, overlay_scale)

        self._draw_procedural_parts()

        return self._end_frame()

    def close(self) -> None:
        self._calls.append("close")
        self._closed = True
        self._last_frame = None


__all__ = ["SpriteSheetRenderer", "CachedFrame", "CachedOverlay"]

