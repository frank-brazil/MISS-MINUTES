import asyncio
from pathlib import Path

import pytest

from app.core.permissions import ToolPermission
from app.tools.base import Tool, ToolResult
from app.tools.file_config import FileToolConfig
from app.tools.screenshot import (
    ScreenshotError,
    ScreenshotProvider,
    ScreenshotResult,
    ScreenshotTool,
    UnsupportedScreenshotProvider,
)


class FakeScreenshotProvider(ScreenshotProvider):
    """Writes a small fake image and returns metadata."""

    async def capture(self, output_path: Path) -> ScreenshotResult:
        output_path.write_bytes(b"\x89PNG-fake-bytes")
        return ScreenshotResult(
            path=output_path,
            width=800,
            height=600,
            format="png",
            size_bytes=len(b"\x89PNG-fake-bytes"),
        )


class FailingScreenshotProvider(ScreenshotProvider):
    async def capture(self, output_path: Path) -> ScreenshotResult:
        raise ScreenshotError("screen capture backend unavailable")


class RaisingScreenshotProvider(ScreenshotProvider):
    async def capture(self, output_path: Path) -> ScreenshotResult:
        raise RuntimeError("boom")


@pytest.fixture
def config(tmp_path: Path) -> FileToolConfig:
    root = tmp_path / "shots"
    root.mkdir()
    return FileToolConfig(allowed_roots=(root,))


def test_screenshot_metadata(config: FileToolConfig) -> None:
    assert ScreenshotTool.name == "screenshot"
    assert isinstance(ScreenshotTool.description, str)
    assert issubclass(ScreenshotTool, Tool)
    assert ScreenshotTool.permission == ToolPermission.WRITE


def test_screenshot_provider_success(config: FileToolConfig, tmp_path: Path) -> None:
    tool = ScreenshotTool(provider=FakeScreenshotProvider(), config=config)
    target = tmp_path / "shots" / "cap.png"
    result = asyncio.run(tool.execute(output_path=str(target)))
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.error is None
    assert str(target) in (result.output or "")
    assert target.read_bytes() == b"\x89PNG-fake-bytes"


def test_screenshot_unsupported_environment(config: FileToolConfig) -> None:
    tool = ScreenshotTool(config=config)
    result = asyncio.run(
        tool.execute(output_path=str(config.allowed_roots[0] / "cap.png"))
    )
    assert result.success is False
    assert "not supported" in (result.error or "").lower()


def test_screenshot_provider_failure_is_controlled(
    config: FileToolConfig, tmp_path: Path
) -> None:
    tool = ScreenshotTool(provider=FailingScreenshotProvider(), config=config)
    result = asyncio.run(
        tool.execute(output_path=str(tmp_path / "shots" / "cap.png"))
    )
    assert result.success is False
    assert "backend unavailable" in (result.error or "")


def test_screenshot_provider_exception_is_controlled(
    config: FileToolConfig, tmp_path: Path
) -> None:
    tool = ScreenshotTool(provider=RaisingScreenshotProvider(), config=config)
    result = asyncio.run(
        tool.execute(output_path=str(tmp_path / "shots" / "cap.png"))
    )
    assert result.success is False
    assert "RuntimeError" in (result.error or "")


def test_screenshot_output_path_outside_root(config: FileToolConfig) -> None:
    tool = ScreenshotTool(provider=FakeScreenshotProvider(), config=config)
    result = asyncio.run(
        tool.execute(output_path=r"C:\\tmp-outside\\cap.png")
    )
    assert result.success is False
    assert "not allowed" in (result.error or "")


def test_screenshot_output_directory_missing(
    config: FileToolConfig, tmp_path: Path
) -> None:
    tool = ScreenshotTool(provider=FakeScreenshotProvider(), config=config)
    result = asyncio.run(
        tool.execute(output_path=str(tmp_path / "shots" / "missing" / "cap.png"))
    )
    assert result.success is False
    assert "Output directory does not exist" in (result.error or "")


def test_screenshot_default_provider_is_unsupported() -> None:
    provider = UnsupportedScreenshotProvider()
    with pytest.raises(ScreenshotError):
        asyncio.run(provider.capture(Path("dummy.png")))


def test_screenshot_no_upload_or_content_in_output(
    config: FileToolConfig, tmp_path: Path
) -> None:
    tool = ScreenshotTool(provider=FakeScreenshotProvider(), config=config)
    target = tmp_path / "shots" / "cap.png"
    result = asyncio.run(tool.execute(output_path=str(target)))
    assert "fake-bytes" not in (result.output or "")