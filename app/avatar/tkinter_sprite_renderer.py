"""Tkinter sprite sheet renderer backend."""

import logging
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageTk

from app.avatar.config import AvatarConfig
from app.avatar.models import AvatarPart, AvatarState
from app.avatar.renderer import RenderFrame
from app.avatar.sprite_renderer import CachedFrame, CachedOverlay, SpriteSheetRenderer

_logger = logging.getLogger(__name__)


class TkinterSpriteSheetRenderer(SpriteSheetRenderer):
    """Tkinter Canvas based sprite sheet renderer."""

    name = "tkinter-sprite-sheet"
    description = "Tkinter Canvas renderer using sprite sheet frames"

    def __init__(
        self,
        config: AvatarConfig | None = None,
        *,
        now_fn: Any | None = None,
        asset_root: Path | None = None,
        canvas: Any | None = None,
    ) -> None:
        self._canvas = canvas
        self._photo_images: dict[int, ImageTk.PhotoImage] = {}
        self._overlay_photos: dict[str, ImageTk.PhotoImage] = {}
        self._sheet_image: Image.Image | None = None
        self._sheet_photo: ImageTk.PhotoImage | None = None
        self._last_frame_data: dict[str, Any] = {}
        super().__init__(config, now_fn=now_fn, asset_root=asset_root)

    def _load_sheet_image(self, path: Path) -> None:
        """Load the full sprite sheet as a PIL Image."""
        self._sheet_image = Image.open(path).convert("RGBA")

    def _crop_frame(self, sheet_image: Image.Image, x: int, y: int, w: int, h: int) -> ImageTk.PhotoImage:
        """Crop a frame and convert to PhotoImage."""
        frame = sheet_image.crop((x, y, x + w, y + h))
        return ImageTk.PhotoImage(frame)

    def _cache_frame(self, index: int) -> CachedFrame | None:
        """Extract and cache a single frame as PhotoImage."""
        ss = self._config.sprite_sheet
        if ss is None or self._sheet_image is None:
            return None

        if index in self._photo_images:
            cached = self._cached_frames.get(index)
            if cached:
                return cached

        x, y, w, h = ss.frame_rect(index)
        frame_img = self._sheet_image.crop((x, y, x + w, y + h))
        photo = ImageTk.PhotoImage(frame_img)
        self._photo_images[index] = photo

        cached = CachedFrame(index=index, data=photo, width=w, height=h)
        self._cached_frames[index] = cached
        return cached

    def _load_overlay_image(self, name: str, path: Path) -> None:
        """Load and cache an expression overlay as PhotoImage."""
        img = Image.open(path).convert("RGBA")
        img = self._remove_background(img)
        photo = ImageTk.PhotoImage(img)
        self._overlay_photos[name] = photo
        self._cached_overlays[name] = CachedOverlay(
            name=name, data=photo, width=img.width, height=img.height
        )

    def _remove_background(self, img: Image.Image) -> Image.Image:
        """Remove background by making near-white pixels transparent."""
        data = img.getdata()
        new_data = []
        for item in data:
            r, g, b, a = item
            if r > 240 and g > 240 and b > 240:
                new_data.append((r, g, b, 0))
            else:
                new_data.append(item)
        img.putdata(new_data)
        return img

    def _scale_overlay(self, overlay: CachedOverlay, target_w: int, target_h: int) -> ImageTk.PhotoImage:
        """Scale overlay to target size."""
        key = f"{overlay.name}_{target_w}x{target_h}"
        if key in self._overlay_photos:
            return self._overlay_photos[key]

        original_img = Image.open(self._asset_root / self._config.expression_overlays.expressions[overlay.name]).convert("RGBA")
        original_img = self._remove_background(original_img)
        scaled = original_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(scaled)
        self._overlay_photos[key] = photo
        return photo

    def _begin_frame(self) -> None:
        if self._canvas:
            self._canvas.delete("avatar")

    def _end_frame(self) -> RenderFrame:
        return RenderFrame(
            frame_index=self._frame_index,
            state=AvatarState.IDLE,
            expression=self._expression_name,
            pose=self._pose,
            primitives=(),
            viseme=self._viseme,
            gesture=self._gesture,
            walking=self._walking,
            timestamp=self._now_fn(),
        )

    def _draw_sprite_frame(self, frame_idx: int, x: float, y: float, scale: float) -> None:
        if not self._canvas:
            return
        frame = self.get_frame(frame_idx)
        if frame and frame.data:
            self._canvas.create_image(
                x, y,
                image=frame.data,
                anchor="center",
                tags="avatar"
            )

    def _draw_overlay(self, overlay_name: str, x: float, y: float, scale: float) -> None:
        if not self._canvas:
            return
        overlay = self.get_overlay(overlay_name)
        if overlay:
            key = f"{overlay_name}_{int(overlay.width*scale)}x{int(overlay.height*scale)}"
            photo = self._overlay_photos.get(key)
            if photo is None and self._config.expression_overlays:
                photo = self._scale_overlay(overlay, int(overlay.width * scale), int(overlay.height * scale))
            if photo:
                self._canvas.create_image(
                    x, y,
                    image=photo,
                    anchor="center",
                    tags="avatar"
                )

    def _draw_procedural_parts(self) -> None:
        if not self._canvas:
            return
        cfg = self._config
        bob = self._pose.body_bob
        radius = cfg.radius
        center_x = 0
        center_y = bob

        self._draw_clock_face(center_x, center_y, radius, scale=cfg.default_scale)
        self._draw_clock_hands(center_x, center_y, radius)
        self._draw_limbs()

    def _draw_clock_face(self, cx: float, cy: float, radius: float, scale: float) -> None:
        cfg = self._config
        ss = cfg.sprite_sheet
        if ss and self._sheet_loaded:
            return

        face_color = "#FFF0DC"
        face_r = radius * 0.78 * scale
        self._canvas.create_oval(
            cx - face_r, cy - face_r,
            cx + face_r, cy + face_r,
            fill=face_color, outline=cfg.outline_color,
            width=cfg.outline_width * scale, tags="avatar"
        )

        markings = cfg.markings_count
        inner = radius * 0.68 * scale
        outer = inner + cfg.markings_length * scale
        for i in range(markings):
            angle = (i * 360.0 / markings) - 90.0
            rad = math.radians(angle)
            x1 = cx + math.cos(rad) * inner
            y1 = cy + math.sin(rad) * inner
            x2 = cx + math.cos(rad) * outer
            y2 = cy + math.sin(rad) * outer
            self._canvas.create_line(
                x1, y1, x2, y2,
                fill=cfg.markings_color,
                width=cfg.markings_thickness * scale, tags="avatar"
            )

        pivot_r = cfg.center_pivot_size / 2.0 * scale
        self._canvas.create_oval(
            cx - pivot_r, cy - pivot_r,
            cx + pivot_r, cy + pivot_r,
            fill=cfg.center_pivot_color, outline="", tags="avatar"
        )

    def _draw_clock_hands(self, cx: float, cy: float, radius: float) -> None:
        hour_hand, minute_hand = self._clock.set_time(self._hour, self._minute, self._second)
        scale = self._config.default_scale
        thickness = self._config.hand_thickness * scale

        hx, hy = hour_hand.endpoint()
        mx, my = minute_hand.endpoint()

        self._canvas.create_line(
            cx, cy, cx + hx * radius * 0.68, cy + hy * radius * 0.68,
            fill=self._config.hand_color, width=thickness, tags="avatar"
        )
        self._canvas.create_line(
            cx, cy, cx + mx * radius * 0.68, cy + my * radius * 0.68,
            fill=self._config.hand_color, width=thickness, tags="avatar"
        )

    def _draw_limbs(self) -> None:
        if not self._canvas:
            return
        cfg = self._config
        bob = self._pose.body_bob
        scale = cfg.default_scale

        shoe_map = {
            AvatarPart.LEFT_LEG: AvatarPart.LEFT_SHOE,
            AvatarPart.RIGHT_LEG: AvatarPart.RIGHT_SHOE,
        }
        for leg, shoe in shoe_map.items():
            geometry = self._limb_geometry(leg)
            if geometry is None:
                continue
            x1, y1, x2, y2 = geometry
            self._canvas.create_line(
                x1 * scale, (y1 + bob) * scale,
                x2 * scale, (y2 + bob) * scale,
                fill=cfg.leg_color, width=cfg.leg_thickness * scale, tags="avatar"
            )
            shoe_w = cfg.shoe_width / 2.0 * scale
            shoe_h = cfg.shoe_height / 2.0 * scale
            self._canvas.create_oval(
                x2 * scale - shoe_w, (y2 + bob) * scale - shoe_h,
                x2 * scale + shoe_w, (y2 + bob) * scale + shoe_h,
                fill=cfg.shoe_color, outline="", tags="avatar"
            )

        hand_map = {
            AvatarPart.LEFT_ARM: AvatarPart.LEFT_HAND,
            AvatarPart.RIGHT_ARM: AvatarPart.RIGHT_HAND,
        }
        for arm, hand in hand_map.items():
            geometry = self._limb_geometry(arm)
            if geometry is None:
                continue
            x1, y1, x2, y2 = geometry
            self._canvas.create_line(
                x1 * scale, (y1 + bob) * scale,
                x2 * scale, (y2 + bob) * scale,
                fill=cfg.arm_color, width=cfg.arm_thickness * scale, tags="avatar"
            )
            hand_r = cfg.hand_size / 2.0 * scale
            self._canvas.create_oval(
                x2 * scale - hand_r, (y2 + bob) * scale - hand_r,
                x2 * scale + hand_r, (y2 + bob) * scale + hand_r,
                fill=cfg.arm_color, outline="", tags="avatar"
            )

    def _limb_geometry(self, part: AvatarPart) -> tuple[float, float, float, float] | None:
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

    def set_canvas(self, canvas: Any) -> None:
        """Set the Tkinter Canvas to draw on."""
        self._canvas = canvas

    def close(self) -> None:
        super().close()
        for photo in self._photo_images.values():
            try:
                photo.__del__()
            except Exception:
                pass
        for photo in self._overlay_photos.values():
            try:
                photo.__del__()
            except Exception:
                pass
        self._photo_images.clear()
        self._overlay_photos.clear()
        if self._sheet_image:
            self._sheet_image.close()
            self._sheet_image = None


__all__ = ["TkinterSpriteSheetRenderer"]

