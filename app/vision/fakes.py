"""Deterministic, offline vision/OCR providers for tests and dev."""

from __future__ import annotations

import asyncio
from typing import ClassVar

from app.vision.models import (
    DetectedElement,
    ImageInput,
    TextRegion,
    VisionRequest,
    VisionResult,
    image_reference,
)
from app.vision.ocr import OcrProvider, OcrRequest, OcrResult
from app.vision.provider import VisionProvider


class FakeVisionProvider(VisionProvider):
    """Configurable, deterministic vision provider for offline tests.

    Responses are keyed by the stable image reference (a file path or a
    content hash), so identical input always produces identical output.
    """

    name: ClassVar[str] = "fake_vision"

    def __init__(self) -> None:
        self._image_texts: dict[str, str] = {}
        self._image_elements: dict[str, tuple[DetectedElement, ...]] = {}
        self.calls: list[VisionRequest] = []
        self.fail = False
        self.fail_reference: str | None = None
        self.raise_error: BaseException | None = None
        self.delay: float = 0.0
        self.default_confidence = 0.95
        self.default_text: str | None = None

    def register_image_text(self, reference: str, text: str) -> None:
        self._image_texts[reference] = text

    def register_detected_elements(
        self, reference: str, elements: list[DetectedElement]
    ) -> None:
        self._image_elements[reference] = tuple(elements)

    async def analyze(self, request: VisionRequest) -> VisionResult:
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        self.calls.append(request)
        if self.raise_error is not None:
            raise self.raise_error

        ref = image_reference(request.image)
        if self.fail or (self.fail_reference == ref):
            return VisionResult.fail(
                error="Fake vision analysis failed",
                provider=self.name,
                reference=ref,
            )

        text = self._image_texts.get(ref, self.default_text)
        elements = self._image_elements.get(ref, ())
        text_regions: list[TextRegion] = []
        if text:
            text_regions.append(TextRegion(text=text, confidence=0.95))

        return VisionResult.ok(
            summary=(
                f"Detected {len(elements)} element(s) and "
                f"{len(text_regions)} text region(s) in {ref}."
            ),
            detected_elements=list(elements),
            text_regions=text_regions,
            confidence=self.default_confidence,
            provider=self.name,
            reference=ref,
            image_width=request.image.width,
            image_height=request.image.height,
        )


class FailingVisionProvider(VisionProvider):
    """Always reports a controlled failure."""

    name: ClassVar[str] = "failing_vision"

    async def analyze(self, request: VisionRequest) -> VisionResult:
        return VisionResult.fail(
            error="Vision analysis failed",
            provider=self.name,
            reference=image_reference(request.image),
        )


class FakeOcrProvider(OcrProvider):
    """Deterministic OCR for offline tests."""

    name: ClassVar[str] = "fake_ocr"

    def __init__(self) -> None:
        self._texts: dict[str, str] = {}
        self.calls: list[OcrRequest] = []

    def register_image_text(self, reference: str, text: str) -> None:
        self._texts[reference] = text

    async def extract_text(self, request: OcrRequest) -> OcrResult:
        self.calls.append(request)
        ref = image_reference(request.image)
        text = self._texts.get(ref)
        if text is None:
            return OcrResult.fail(
                error=f"No registered text for {ref}",
                provider=self.name,
            )
        return OcrResult.ok(
            text=text,
            text_regions=[TextRegion(text=text, confidence=0.95)],
            confidence=0.95,
            provider=self.name,
        )