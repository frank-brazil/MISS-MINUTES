"""Screenshot capture tool behind a provider/interface boundary.

The tool itself never captures pixels: all capture work happens in a
:class:`ScreenshotProvider` that is injected.  The default provider fails
gracefully on unsupported/headless environments.  Screenshots are written to
disk inside an allowed writable directory and are never uploaded or logged.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.path_safety import PathSafetyError, PathSafety
from app.core.permissions import ToolPermission
from app.tools.base import Tool, ToolResult
from app.tools.file_config import FileToolConfig


class ScreenshotError(Exception):
    """Raised by providers when a screenshot cannot be captured."""


@dataclass(frozen=True)
class ScreenshotResult:
    """Metadata about a captured screenshot.  Never contains pixel data."""

    path: Path
    width: int | None = None
    height: int | None = None
    format: str | None = None
    size_bytes: int | None = None


class ScreenshotProvider(ABC):
    """Captures the current screen to ``output_path``."""

    @abstractmethod
    async def capture(self, output_path: Path) -> ScreenshotResult:
        raise NotImplementedError


class UnsupportedScreenshotProvider(ScreenshotProvider):
    """Fails gracefully when the environment cannot capture a screen."""

    async def capture(self, output_path: Path) -> ScreenshotResult:
        raise ScreenshotError(
            "Screenshot capture is not supported in this environment"
        )


class ScreenshotArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_path: str = Field(
        description=(
            "Absolute path where the screenshot image will be saved.  Must "
            "be inside an explicitly permitted writable directory."
        )
    )


class ScreenshotTool(Tool):
    """Capture the current screen through an injected provider.

    The default provider reports an unsupported environment.  Callers that
    run on a captured-capable machine inject a real provider.
    """

    name = "screenshot"
    description = (
        "Captures the current screen and saves it to an explicitly "
        "permitted path. Returns the saved image path and metadata."
    )
    input_schema = ScreenshotArguments
    permission: ClassVar[ToolPermission] = ToolPermission.WRITE

    def __init__(
        self,
        provider: ScreenshotProvider | None = None,
        config: FileToolConfig | None = None,
    ) -> None:
        self._provider = (
            provider if provider is not None else UnsupportedScreenshotProvider()
        )
        self._config = config or FileToolConfig()
        self._safety = PathSafety(self._config.allowed_roots)

    async def execute(self, **kwargs: object) -> ToolResult:
        args = self.parse_args(**kwargs)

        try:
            resolved = self._safety.ensure_within(args.output_path)
        except PathSafetyError as exc:
            return ToolResult.fail(error=f"Output path not allowed: {exc}")

        parent = resolved.parent
        if not parent.exists():
            return ToolResult.fail(
                error=f"Output directory does not exist: {parent}"
            )
        if not parent.is_dir():
            return ToolResult.fail(
                error=f"Output parent is not a directory: {parent}"
            )

        if resolved.exists() and not resolved.is_file():
            return ToolResult.fail(
                error=f"Output path is not a regular file: {resolved}"
            )

        try:
            shot = await self._provider.capture(resolved)
        except ScreenshotError as exc:
            return ToolResult.fail(error=str(exc))
        except Exception as exc:
            return ToolResult.fail(
                error=f"Screenshot failed: {type(exc).__name__}"
            )

        return ToolResult.ok(
            output=f"Screenshot saved to {shot.path}"
        )