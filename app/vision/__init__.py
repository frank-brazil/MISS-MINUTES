"""Vision subsystem: analysis and screen understanding.

Provides the provider-independent vision abstraction, typed image/results
models, an OCR/text-extraction boundary, a screen-understanding service, and
offline fake providers used by tests and development.
"""

from app.vision.fakes import (
    FakeOcrProvider,
    FakeVisionProvider,
    FailingVisionProvider,
)
from app.vision.models import (
    DEFAULT_MAX_IMAGE_BYTES,
    SUPPORTED_IMAGE_MIME_TYPES,
    BoundingBox,
    DetectedElement,
    DetectedElementType,
    ImageInput,
    TextRegion,
    VisionAnalysisMode,
    VisionRequest,
    VisionResult,
    image_reference,
)
from app.vision.ocr import (
    OcrProvider,
    OcrRequest,
    OcrResult,
    UnsupportedOcrProvider,
)
from app.vision.provider import VisionError, VisionProvider
from app.vision.screen_understanding import ScreenUnderstandingService

__all__ = [
    "BoundingBox",
    "DEFAULT_MAX_IMAGE_BYTES",
    "DetectedElement",
    "DetectedElementType",
    "FakeOcrProvider",
    "FakeVisionProvider",
    "FailingVisionProvider",
    "ImageInput",
    "OcrProvider",
    "OcrRequest",
    "OcrResult",
    "SUPPORTED_IMAGE_MIME_TYPES",
    "ScreenUnderstandingService",
    "TextRegion",
    "UnsupportedOcrProvider",
    "VisionAnalysisMode",
    "VisionError",
    "VisionProvider",
    "VisionRequest",
    "VisionResult",
    "image_reference",
]