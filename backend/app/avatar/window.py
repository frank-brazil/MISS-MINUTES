"""Desktop UI boundary.

``AvatarWindow`` keeps the avatar character-first and provider-independent:
it exposes show/hide, size, position, always-on-top and transparent background
via configuration, isolated from any concrete GUI framework. A deterministic
``FakeAvatarWindow`` records operations for offline tests.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator

from app.avatar.renderer import AvatarRenderer, RenderFrame


class AvatarWindowConfig(BaseModel):
    """Character-first window preferences (no dashboard chrome)."""

    model_config = ConfigDict(extra="forbid")

    width: int = 420
    height: int = 520
    position_x: int | None = None
    position_y: int | None = None
    always_on_top: bool = True
    transparent_background: bool = True
    visible_on_start: bool = False
    character_first: bool = True

    @field_validator("width", "height")
    @classmethod
    def _size(cls, value: int) -> int:
        if value < 64 or value > 4096:
            raise ValueError("window width/height must be within [64, 4096] pixels")
        return value


class AvatarWindow(ABC):
    """Boundary for the character window."""

    name: ClassVar[str]
    description: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [
            attribute for attribute in ("name", "description") if not hasattr(cls, attribute)
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} must define required attribute(s): {', '.join(missing)}"
            )

    @abstractmethod
    def attach_renderer(self, renderer: AvatarRenderer) -> None:
        raise NotImplementedError

    @abstractmethod
    def show(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def hide(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_position(self, x: int, y: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_size(self, width: int, height: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_always_on_top(self, enabled: bool) -> None:
        raise NotImplementedError

    @abstractmethod
    def paint(self) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def visible(self) -> bool:
        raise NotImplementedError

    @property
    @abstractmethod
    def position(self) -> tuple[int, int]:
        raise NotImplementedError

    @property
    @abstractmethod
    def size(self) -> tuple[int, int]:
        raise NotImplementedError

    @property
    @abstractmethod
    def closed(self) -> bool:
        raise NotImplementedError

    @property
    @abstractmethod
    def config(self) -> AvatarWindowConfig:
        raise NotImplementedError

    @property
    @abstractmethod
    def last_frame(self) -> RenderFrame | None:
        raise NotImplementedError


class FakeAvatarWindow(AvatarWindow):
    """Deterministic fake window that records every operation."""

    name = "fake-avatar-window"
    description = "Deterministic in-memory character window for offline tests."

    def __init__(self, config: AvatarWindowConfig | None = None) -> None:
        self._config = config or AvatarWindowConfig()
        self._renderer: AvatarRenderer | None = None
        self._visible: bool = self._config.visible_on_start
        self._closed = False
        self._position: tuple[int, int] = (
            self._config.position_x if self._config.position_x is not None else 100,
            self._config.position_y if self._config.position_y is not None else 100,
        )
        self._size: tuple[int, int] = (self._config.width, self._config.height)
        self._always_on_top = self._config.always_on_top
        self._paint_count = 0
        self._last_frame: RenderFrame | None = None
        self._ops: list[tuple[str, tuple[object, ...]]] = []

    @property
    def config(self) -> AvatarWindowConfig:
        return self._config

    @property
    def ops(self) -> tuple[tuple[str, tuple[object, ...]], ...]:
        return tuple(self._ops)

    @property
    def paint_count(self) -> int:
        return self._paint_count

    def attach_renderer(self, renderer: AvatarRenderer) -> None:
        self._ops.append(("attach_renderer", ()))
        self._renderer = renderer

    def show(self) -> None:
        self._ops.append(("show", ()))
        self._visible = True

    def hide(self) -> None:
        self._ops.append(("hide", ()))
        self._visible = False

    def close(self) -> None:
        self._ops.append(("close", ()))
        self._closed = True
        self._visible = False

    def set_position(self, x: int, y: int) -> None:
        self._ops.append(("set_position", (x, y)))
        self._position = (x, y)

    def set_size(self, width: int, height: int) -> None:
        self._ops.append(("set_size", (width, height)))
        config = self._config.model_copy(update={"width": width, "height": height})
        self._config = config
        self._size = (width, height)

    def set_always_on_top(self, enabled: bool) -> None:
        self._ops.append(("set_always_on_top", (enabled,)))
        self._always_on_top = enabled

    def paint(self) -> None:
        """Push the renderer's latest frame. Never re-renders: the engine
        rendered the frame already, the window just displays it."""
        self._ops.append(("paint", ()))
        self._paint_count += 1
        if self._renderer is not None:
            self._last_frame = self._renderer.last_frame

    @property
    def visible(self) -> bool:
        return self._visible

    @property
    def position(self) -> tuple[int, int]:
        return self._position

    @property
    def size(self) -> tuple[int, int]:
        return self._size

    @property
    def always_on_top(self) -> bool:
        return self._always_on_top

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def last_frame(self) -> RenderFrame | None:
        return self._last_frame
