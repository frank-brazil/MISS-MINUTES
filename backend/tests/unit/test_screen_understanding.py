import asyncio
from pathlib import Path

from app.tools.screenshot import (
    ScreenshotError,
    ScreenshotProvider,
    ScreenshotResult,
)
from app.vision.fakes import (
    FailingVisionProvider,
    FakeOcrProvider,
    FakeVisionProvider,
)
from app.vision.models import (
    DEFAULT_MAX_IMAGE_BYTES,
    ImageInput,
    VisionAnalysisMode,
)
from app.vision.ocr import UnsupportedOcrProvider
from app.vision.screen_understanding import ScreenUnderstandingService


def _run(coro):
    return asyncio.run(coro)


class FakeScreenshotProvider(ScreenshotProvider):
    def __init__(
        self,
        *,
        format: str = "png",
        width: int = 800,
        height: int = 600,
        fail: bool = False,
        raise_error: bool = False,
    ) -> None:
        self.format = format
        self.width = width
        self.height = height
        self.fail = fail
        self.raise_error = raise_error
        self.calls: list[Path] = []

    async def capture(self, output_path: Path) -> ScreenshotResult:
        self.calls.append(output_path)
        if self.fail:
            raise ScreenshotError("capture unsupported")
        if self.raise_error:
            raise RuntimeError("engine exploded")
        output_path.write_bytes(b"\x89PNG-fake-bytes")
        return ScreenshotResult(
            path=output_path,
            width=self.width,
            height=self.height,
            format=self.format,
            size_bytes=len(b"\x89PNG-fake-bytes"),
        )


def _service(
    *,
    screenshot: ScreenshotProvider | None = None,
    vision: FakeVisionProvider | None = None,
    workspace: Path | None = None,
    max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
    timeout: float | None = 30.0,
    ocr=None,
) -> ScreenUnderstandingService:
    return ScreenUnderstandingService(
        screenshot or FakeScreenshotProvider(),
        vision or FakeVisionProvider(),
        workspace=workspace,
        max_image_bytes=max_image_bytes,
        timeout_seconds=timeout,
        ocr_provider=ocr,
    )


def test_screen_understanding_success(tmp_path: Path) -> None:
    vision = FakeVisionProvider()
    vision.default_text = "Dashboard title"
    service = _service(vision=vision, workspace=tmp_path)

    result = _run(service.understand())

    assert result.success is True
    assert result.provider == "fake_vision"
    assert result.reference is not None
    assert [t.text for t in result.text_regions] == ["Dashboard title"]
    saved = list(tmp_path.glob("screenshot-*.png"))
    assert len(saved) == 1
    assert saved[0].exists()


def test_screen_understanding_preserves_dimensions(tmp_path: Path) -> None:
    vision = FakeVisionProvider()
    service = _service(vision=vision, workspace=tmp_path)

    result = _run(service.understand())

    assert result.success is True
    assert result.image_width == 800
    assert result.image_height == 600


def test_screen_understanding_missing_workspace() -> None:
    service = _service(workspace=None)
    result = _run(service.understand())
    assert result.success is False
    assert "workspace" in (result.error or "")


def test_screen_understanding_workspace_not_directory(tmp_path: Path) -> None:
    file_ws = tmp_path / "not-a-dir"
    file_ws.write_text("x")
    service = _service(workspace=file_ws)
    result = _run(service.understand())
    assert result.success is False
    assert "not a directory" in (result.error or "")


def test_screenshot_failure_is_controlled(tmp_path: Path) -> None:
    service = _service(screenshot=FakeScreenshotProvider(fail=True), workspace=tmp_path)
    result = _run(service.understand())
    assert result.success is False
    assert "Screenshot failed" in (result.error or "")


def test_screenshot_unexpected_exception_is_controlled(tmp_path: Path) -> None:
    service = _service(screenshot=FakeScreenshotProvider(raise_error=True), workspace=tmp_path)
    result = _run(service.understand())
    assert result.success is False
    assert "Screenshot failed: RuntimeError" in (result.error or "")


def test_vision_provider_failure_is_propagated_as_controlled(tmp_path: Path) -> None:
    service = _service(vision=FailingVisionProvider(), workspace=tmp_path)
    result = _run(service.understand())
    assert result.success is False
    assert "Vision analysis failed" in (result.error or "")


def test_vision_provider_exception_is_controlled(tmp_path: Path) -> None:
    vision = FakeVisionProvider()
    vision.raise_error = RuntimeError("boom")
    service = _service(vision=vision, workspace=tmp_path)
    result = _run(service.understand())
    assert result.success is False
    assert "Vision provider raised: RuntimeError" in (result.error or "")


def test_vision_timeout_is_controlled(tmp_path: Path) -> None:
    vision = FakeVisionProvider()
    vision.delay = 5.0
    service = _service(vision=vision, workspace=tmp_path, timeout=0.05)
    result = _run(service.understand())
    assert result.success is False
    assert "timed out" in (result.error or "")


def test_analyze_image_with_nonexistent_path_is_controlled() -> None:
    service = _service(workspace=None)
    image = ImageInput(path=Path("missing/image.png"))
    result = _run(service.analyze_image(image))
    assert result.success is False
    assert "does not exist" in (result.error or "")


def test_analyze_image_empty_file_is_controlled(tmp_path: Path) -> None:
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    service = _service(workspace=None)
    result = _run(service.analyze_image(ImageInput(path=empty)))
    assert result.success is False
    assert "empty" in (result.error or "")


def test_analyze_image_oversized_payload_is_controlled(tmp_path: Path) -> None:
    big = tmp_path / "big.png"
    big.write_bytes(b"y" * 2048)
    service = _service(workspace=None, max_image_bytes=1024)
    image = ImageInput(path=big)
    result = _run(service.analyze_image(image))
    assert result.success is False
    assert "exceeds maximum size" in (result.error or "")


def test_analyze_image_invalid_question_is_controlled() -> None:
    service = _service(workspace=None)
    image = ImageInput(data=b"x" * 5, mime_type="image/png")
    result = _run(service.analyze_image(image, question="q" * 5000))
    assert result.success is False
    assert "Invalid vision request" in (result.error or "")


def test_analyze_image_success_with_data() -> None:
    vision = FakeVisionProvider()
    vision.default_text = "seen"
    service = _service(vision=vision, workspace=None)
    image = ImageInput(data=b"fake-image-bytes", mime_type="image/png")
    result = _run(service.analyze_image(image, question="what is here?"))
    assert result.success is True
    assert [t.text for t in result.text_regions] == ["seen"]
    assert len(vision.calls) == 1
    assert vision.calls[0].question == "what is here?"


def test_analyze_image_reads_path_and_keeps_reference(tmp_path: Path) -> None:
    shot = tmp_path / "frame.png"
    shot.write_bytes(b"frame-data")
    vision = FakeVisionProvider()
    vision.register_image_text(str(shot), "from disk")
    service = _service(vision=vision, workspace=None)

    result = _run(service.analyze_image(ImageInput(path=shot)))

    assert result.success is True
    assert [t.text for t in result.text_regions] == ["from disk"]
    assert result.reference == str(shot)


def test_extract_text_without_ocr_provider_is_controlled() -> None:
    service = _service(workspace=None)
    image = ImageInput(data=b"x" * 5, mime_type="image/png")
    result = _run(service.extract_text(image))
    assert result.success is False
    assert "No OCR provider" in (result.error or "")


def test_extract_text_with_unsupported_ocr_is_controlled() -> None:
    service = _service(workspace=None, ocr=UnsupportedOcrProvider())
    image = ImageInput(data=b"x" * 5, mime_type="image/png")
    result = _run(service.extract_text(image))
    assert result.success is False
    assert "not supported" in (result.error or "").lower()


def test_extract_text_with_fake_ocr(tmp_path: Path) -> None:
    ocr = FakeOcrProvider()
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"data")
    from app.vision.models import image_reference

    ocr.register_image_text(image_reference(ImageInput(path=shot)), "OCR says hi")
    service = _service(workspace=None, ocr=ocr)
    result = _run(service.extract_text(ImageInput(path=shot)))
    assert result.success is True
    assert result.text == "OCR says hi"


def test_understand_with_explicit_question_and_mode(tmp_path: Path) -> None:
    vision = FakeVisionProvider()
    service = _service(vision=vision, workspace=tmp_path)
    result = _run(service.understand(question="any question", mode=VisionAnalysisMode.OCR))
    assert result.success is True
    assert vision.calls[0].question == "any question"
    assert vision.calls[0].mode == VisionAnalysisMode.OCR
