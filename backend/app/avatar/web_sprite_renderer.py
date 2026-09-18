"""Web/HTML Canvas sprite sheet renderer backend.

Generates JavaScript code for rendering avatar on HTML Canvas.
"""

import base64
import json
import logging
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from app.avatar.config import AvatarConfig
from app.avatar.models import AvatarPart, AvatarState
from app.avatar.renderer import RenderFrame
from app.avatar.sprite_renderer import CachedFrame, CachedOverlay, SpriteSheetRenderer

_logger = logging.getLogger(__name__)


class WebSpriteSheetRenderer(SpriteSheetRenderer):
    """Web/HTML Canvas based sprite sheet renderer.

    Generates JavaScript drawImage calls for rendering on an HTML Canvas element.
    The renderer produces a JSON-serializable frame description that can be
    sent to the frontend for rendering.
    """

    name = "web-sprite-sheet"
    description = "Web HTML Canvas renderer using sprite sheet frames"

    def __init__(
        self,
        config: AvatarConfig | None = None,
        *,
        now_fn: Any | None = None,
        asset_root: Path | None = None,
    ) -> None:
        self._sheet_b64: str | None = None
        self._sheet_width = 0
        self._sheet_height = 0
        self._overlay_b64: dict[str, str] = {}
        self._overlay_dims: dict[str, tuple[int, int]] = {}
        self._frame_data: dict[str, Any] = {}
        super().__init__(config, now_fn=now_fn, asset_root=asset_root)

    def _load_sheet_image(self, path: Path) -> None:
        """Load the full sprite sheet and encode as base64."""
        img = Image.open(path).convert("RGBA")
        self._sheet_width = img.width
        self._sheet_height = img.height
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        self._sheet_b64 = base64.b64encode(buffered.getvalue()).decode("ascii")
        _logger.info("Encoded sprite sheet: %dx%d", img.width, img.height)

    def _crop_frame(self, sheet_image: Any, x: int, y: int, w: int, h: int) -> dict:
        """Return source rect for a frame (used by JS drawImage)."""
        return {"sx": x, "sy": y, "sw": w, "sh": h}

    def _cache_frame(self, index: int) -> CachedFrame | None:
        """Cache frame source rect (not image data - sent as base64 sheet)."""
        ss = self._config.sprite_sheet
        if ss is None:
            return None

        if index in self._cached_frames:
            return self._cached_frames[index]

        x, y, w, h = ss.frame_rect(index)
        frame_data = {"sx": x, "sy": y, "sw": w, "sh": w, "dw": w, "dh": h}
        cached = CachedFrame(index=index, data=frame_data, width=w, height=h)
        self._cached_frames[index] = cached
        return cached

    def _load_overlay_image(self, name: str, path: Path) -> None:
        """Load and cache an expression overlay as base64."""
        img = Image.open(path).convert("RGBA")
        img = self._remove_background(img)
        self._overlay_dims[name] = (img.width, img.height)

        buffered = BytesIO()
        img.save(buffered, format="PNG")
        self._overlay_b64[name] = base64.b64encode(buffered.getvalue()).decode("ascii")
        _logger.debug("Encoded overlay %s: %dx%d", name, img.width, img.height)

        self._cached_overlays[name] = CachedOverlay(
            name=name, data=self._overlay_b64[name], width=img.width, height=img.height
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

    def _scale_overlay(self, overlay: CachedOverlay, target_w: int, target_h: int) -> dict:
        """Return scaled draw params for overlay (handled in JS)."""
        return {
            "b64": overlay.data,
            "dw": target_w,
            "dh": target_h,
            "sw": overlay.width,
            "sh": overlay.height,
        }

    def get_frame_rect(self, index: int) -> dict | None:
        """Get frame source rect for JS drawImage."""
        frame = self.get_frame(index)
        if frame and frame.data:
            return frame.data
        return None

    def get_overlay_data(self, name: str) -> dict | None:
        """Get overlay base64 and dimensions for JS."""
        overlay = self.get_overlay(name)
        if overlay:
            return {
                "b64": overlay.data,
                "width": overlay.width,
                "height": overlay.height,
            }
        return None

    def _begin_frame(self) -> None:
        self._frame_data = {
            "type": "frame",
            "frameIndex": self._frame_index,
            "drawCalls": [],
        }

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
        rect = self.get_frame_rect(frame_idx)
        if rect and self._sheet_b64:
            self._frame_data["drawCalls"].append({
                "type": "sprite",
                "image": f"data:image/png;base64,{self._sheet_b64}",
                "sx": rect["sx"],
                "sy": rect["sy"],
                "sw": rect["sw"],
                "sh": rect["sh"],
                "dx": x - rect["dw"] * scale / 2,
                "dy": y - rect["dh"] * scale / 2,
                "dw": rect["dw"] * scale,
                "dh": rect["dh"] * scale,
            })

    def _draw_overlay(self, overlay_name: str, x: float, y: float, scale: float) -> None:
        overlay = self.get_overlay(overlay_name)
        if overlay and self._config.expression_overlays:
            eo = self._config.expression_overlays
            draw_params = self._scale_overlay(
                overlay,
                int(overlay.width * eo.overlay_scale * scale),
                int(overlay.height * eo.overlay_scale * scale),
            )
            self._frame_data["drawCalls"].append({
                "type": "overlay",
                "image": f"data:image/png;base64,{draw_params['b64']}",
                "sx": 0,
                "sy": 0,
                "sw": draw_params["sw"],
                "sh": draw_params["sh"],
                "dx": x - draw_params["dw"] / 2,
                "dy": y - draw_params["dh"] / 2 + eo.overlay_y_offset * scale,
                "dw": draw_params["dw"],
                "dh": draw_params["dh"],
            })

    def _draw_procedural_parts(self) -> None:
        cfg = self._config
        bob = self._pose.body_bob
        radius = cfg.radius
        scale = cfg.default_scale
        center_x = 0
        center_y = bob

        self._draw_clock_face_js(center_x, center_y, radius, scale)
        self._draw_clock_hands_js(center_x, center_y, radius, scale)
        self._draw_limbs_js(scale, bob)

    def _draw_clock_face_js(self, cx: float, cy: float, radius: float, scale: float) -> None:
        cfg = self._config
        ss = cfg.sprite_sheet
        if ss and self._sheet_loaded:
            return

        face_color = "#FFF0DC"
        face_r = radius * 0.78 * scale
        self._frame_data["drawCalls"].append({
            "type": "ellipse",
            "x": cx,
            "y": cy,
            "rx": face_r,
            "ry": face_r,
            "fill": face_color,
            "stroke": cfg.outline_color,
            "strokeWidth": cfg.outline_width * scale,
        })

        markings = cfg.markings_count
        inner = radius * 0.68 * scale
        outer = inner + cfg.markings_length * scale
        for i in range(markings):
            angle = (i * 360.0 / markings) - 90.0
            import math
            rad = math.radians(angle)
            x1 = cx + math.cos(rad) * inner
            y1 = cy + math.sin(rad) * inner
            x2 = cx + math.cos(rad) * outer
            y2 = cy + math.sin(rad) * outer
            self._frame_data["drawCalls"].append({
                "type": "line",
                "x1": x1, "y1": y1,
                "x2": x2, "y2": y2,
                "stroke": cfg.markings_color,
                "strokeWidth": cfg.markings_thickness * scale,
            })

        pivot_r = cfg.center_pivot_size / 2.0 * scale
        self._frame_data["drawCalls"].append({
            "type": "circle",
            "x": cx, "y": cy,
            "r": pivot_r,
            "fill": cfg.center_pivot_color,
        })

    def _draw_clock_hands_js(self, cx: float, cy: float, radius: float, scale: float) -> None:
        cfg = self._config
        hour_hand, minute_hand = self._clock.set_time(self._hour, self._minute, self._second)
        thickness = cfg.hand_thickness * scale

        hx, hy = hour_hand.endpoint()
        mx, my = minute_hand.endpoint()
        hand_r = radius * 0.68 * scale

        self._frame_data["drawCalls"].append({
            "type": "line",
            "x1": cx, "y1": cy,
            "x2": cx + hx * hand_r, "y2": cy + hy * hand_r,
            "stroke": cfg.hand_color, "strokeWidth": thickness,
        })
        self._frame_data["drawCalls"].append({
            "type": "line",
            "x1": cx, "y1": cy,
            "x2": cx + mx * hand_r, "y2": cy + my * hand_r,
            "stroke": cfg.hand_color, "strokeWidth": thickness,
        })

    def _draw_limbs_js(self, scale: float, bob: float) -> None:
        cfg = self._config

        shoe_map = {
            AvatarPart.LEFT_LEG: AvatarPart.LEFT_SHOE,
            AvatarPart.RIGHT_LEG: AvatarPart.RIGHT_SHOE,
        }
        for leg, shoe in shoe_map.items():
            geometry = self._limb_geometry(leg)
            if geometry is None:
                continue
            x1, y1, x2, y2 = geometry
            self._frame_data["drawCalls"].append({
                "type": "line",
                "x1": x1 * scale, "y1": (y1 + bob) * scale,
                "x2": x2 * scale, "y2": (y2 + bob) * scale,
                "stroke": cfg.leg_color, "strokeWidth": cfg.leg_thickness * scale,
            })
            shoe_w = cfg.shoe_width / 2.0 * scale
            shoe_h = cfg.shoe_height / 2.0 * scale
            self._frame_data["drawCalls"].append({
                "type": "ellipse",
                "x": x2 * scale, "y": (y2 + bob) * scale,
                "rx": shoe_w, "ry": shoe_h,
                "fill": cfg.shoe_color,
            })

        hand_map = {
            AvatarPart.LEFT_ARM: AvatarPart.LEFT_HAND,
            AvatarPart.RIGHT_ARM: AvatarPart.RIGHT_HAND,
        }
        for arm, hand in hand_map.items():
            geometry = self._limb_geometry(arm)
            if geometry is None:
                continue
            x1, y1, x2, y2 = geometry
            self._frame_data["drawCalls"].append({
                "type": "line",
                "x1": x1 * scale, "y1": (y1 + bob) * scale,
                "x2": x2 * scale, "y2": (y2 + bob) * scale,
                "stroke": cfg.arm_color, "strokeWidth": cfg.arm_thickness * scale,
            })
            hand_r = cfg.hand_size / 2.0 * scale
            self._frame_data["drawCalls"].append({
                "type": "circle",
                "x": x2 * scale, "y": (y2 + bob) * scale,
                "r": hand_r,
                "fill": cfg.arm_color,
            })

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
        import math
        radians = math.radians(rotation)
        dx = math.sin(radians) * limb.length
        dy = math.cos(radians) * limb.length
        return (attach[0], attach[1], attach[0] + dx, attach[1] + dy)

    def get_frame_data(self) -> dict:
        """Get the current frame draw data for sending to frontend."""
        return self._frame_data

    def get_sprite_sheet_b64(self) -> str | None:
        """Get base64 encoded sprite sheet."""
        return self._sheet_b64

    def get_overlays_b64(self) -> dict[str, str]:
        """Get base64 encoded overlays."""
        return self._overlay_b64.copy()

    def to_json(self) -> str:
        """Serialize frame data as JSON for frontend."""
        return json.dumps(self._frame_data)

    def close(self) -> None:
        super().close()
        self._sheet_b64 = None
        self._overlay_b64.clear()
        self._overlay_dims.clear()


__all__ = ["WebSpriteSheetRenderer"]

