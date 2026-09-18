"""Screen understanding service: coordinates screenshot + vision providers.

The service captures a screenshot through the injected
:class:`ScreenshotProvider` (the CHUNK 25 provider boundary, reused), then
analyses it through an injected :class:`VisionProvider`.  Every failure mode
(screenshot failure, unreadable image, oversized payload, provider failure,
timeout) is returned as a controlled ``VisionResult.fail``.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import ClassVar
from uuid import uuid4

from pydantic import ValidationError

from app.tools.screenshot import ScreenshotError, ScreenshotProvider
from app.vision.models import (
    DEFAULT_MAX_IMAGE_BYTES,
    ImageInput,
    VisionAnalysisMode,
    VisionRequest,
    VisionResult,
)
from app.vision.ocr import OcrProvider, OcrRequest, OcrResult
from app.vision.provider import VisionError, VisionProvider

logger = logging.getLogger(__name__)


class ScreenUnderstandingService:
    """Coordinates screenshot capture and vision analysis.

    The providers are injected, so every test and environment can supply
    deterministic fakes.  This service never performs autonomous actions on
    the things it observes; it only produces structured observations.
    """

    name: ClassVar[str] = "screen_understanding"

    def __init__(
        self,
        screenshot_provider: ScreenshotProvider,
        vision_provider: VisionProvider,
        *,
        workspace: Path | None = None,
        max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
        timeout_seconds: float | None = 30.0,
        ocr_provider: OcrProvider | None = None,
    ) -> None:
        self._screenshot = screenshot_provider
        self._vision = vision_provider
        self._workspace = workspace
        self._max_image_bytes = max_image_bytes
        self._timeout_seconds = timeout_seconds
        self._ocr = ocr_provider

    @property
    def vision_provider(self) -> VisionProvider:
        return self._vision

    @property
    def screenshot_provider(self) -> ScreenshotProvider:
        return self._screenshot

    async def understand(
        self,
        *,
        question: str | None = None,
        language: str | None = None,
        mode: VisionAnalysisMode = VisionAnalysisMode.FULL,
    ) -> VisionResult:
        """Capture the current screen and produce structured understanding."""
        if self._workspace is None:
            return VisionResult.fail(
                error=("Cannot capture a screenshot: no screenshot workspace is configured")
            )
        if not self._workspace.is_dir():
            return VisionResult.fail(
                error=f"Screenshot workspace is not a directory: {self._workspace}"
            )

        target = self._workspace / f"screenshot-{uuid4().hex}.png"
        try:
            shot = await self._screenshot.capture(target)
        except ScreenshotError as exc:
            logger.warning("screen_understanding screenshot failed: %s", exc)
            return VisionResult.fail(error=f"Screenshot failed: {exc}")
        except Exception as exc:  # noqa: BLE001 - controlled failure
            logger.warning(
                "screen_understanding screenshot failed: %s",
                type(exc).__name__,
            )
            return VisionResult.fail(error=f"Screenshot failed: {type(exc).__name__}")

        logger.info("screen_understanding captured %s", shot.path)
        image = ImageInput(
            path=shot.path,
            mime_type=None,
            width=shot.width,
            height=shot.height,
        )
        return await self.analyze_image(image, question=question, language=language, mode=mode)

    async def analyze_image(
        self,
        image: ImageInput,
        *,
        question: str | None = None,
        language: str | None = None,
        mode: VisionAnalysisMode = VisionAnalysisMode.FULL,
    ) -> VisionResult:
        """Analyse a supplied image (already-validated or freshly validated)."""

        data = image.data
        if data is None and image.path is not None:
            if not image.path.is_file():
                return VisionResult.fail(error=f"Image file does not exist: {image.path}")
            try:
                data = image.path.read_bytes()
            except OSError as exc:
                logger.warning("screen_understanding read error: %s", type(exc).__name__)
                return VisionResult.fail(error=f"Failed to read image: {type(exc).__name__}")

        if not data:
            return VisionResult.fail(error="Image data is empty")

        if len(data) > self._max_image_bytes:
            return VisionResult.fail(
                error=(f"Image exceeds maximum size of {self._max_image_bytes} bytes")
            )

        try:
            built = ImageInput(
                path=image.path,
                data=data,
                mime_type=image.mime_type,
                width=image.width,
                height=image.height,
                max_bytes=self._max_image_bytes,
            )
        except ValidationError as exc:
            message = exc.errors()[0].get("msg", "invalid image")
            logger.warning("screen_understanding invalid image: %s", message)
            return VisionResult.fail(error=f"Invalid image: {message}")

        try:
            request = VisionRequest(image=built, question=question, language=language, mode=mode)
        except ValidationError as exc:
            message = exc.errors()[0].get("msg", "invalid request")
            return VisionResult.fail(error=f"Invalid vision request: {message}")

        return await self._run_analysis(request)

    async def extract_text(self, image: ImageInput) -> OcrResult:
        """Extract text through the optional OCR provider, if configured."""
        if self._ocr is None:
            return OcrResult.fail(error="No OCR provider is configured")

        data = image.data
        if data is None and image.path is not None:
            if not image.path.is_file():
                return OcrResult.fail(error=f"Image file does not exist: {image.path}")
            try:
                data = image.path.read_bytes()
            except OSError as exc:
                return OcrResult.fail(error=f"Failed to read image: {type(exc).__name__}")
        if not data:
            return OcrResult.fail(error="Image data is empty")
        if len(data) > self._max_image_bytes:
            return OcrResult.fail(
                error=f"Image exceeds maximum size of {self._max_image_bytes} bytes"
            )

        try:
            built = ImageInput(
                path=image.path,
                data=data,
                mime_type=image.mime_type,
                width=image.width,
                height=image.height,
                max_bytes=self._max_image_bytes,
            )
        except ValidationError as exc:
            return OcrResult.fail(error=f"Invalid image: {exc.errors()[0].get('msg', 'invalid')}")

        return await self._ocr.extract_text(OcrRequest(image=built))

    async def _run_analysis(self, request: VisionRequest) -> VisionResult:
        coro = self._vision.analyze(request)
        if self._timeout_seconds is None:
            try:
                return await coro
            except VisionError as exc:
                return VisionResult.fail(error=f"Vision provider error: {exc}")
            except Exception as exc:  # noqa: BLE001 - controlled failure
                logger.warning("screen_understanding vision error: %s", type(exc).__name__)
                return VisionResult.fail(error=f"Vision provider raised: {type(exc).__name__}")

        try:
            return await asyncio.wait_for(coro, timeout=self._timeout_seconds)
        except asyncio.TimeoutError:
            logger.warning("screen_understanding vision timed out")
            return VisionResult.fail(
                error=(f"Vision analysis timed out after {self._timeout_seconds:g} seconds")
            )
        except VisionError as exc:
            return VisionResult.fail(error=f"Vision provider error: {exc}")
        except Exception as exc:  # noqa: BLE001 - controlled failure
            logger.warning("screen_understanding vision error: %s", type(exc).__name__)
            return VisionResult.fail(error=f"Vision provider raised: {type(exc).__name__}")
