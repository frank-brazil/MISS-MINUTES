"""Vision models: typed image input, detected elements, and results.

These models describe *observations* only.  Detected elements and visible
text are never treated as commands or system instructions.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SUPPORTED_IMAGE_MIME_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp"}
)
DEFAULT_MAX_IMAGE_BYTES = 4_000_000

_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


class VisionAnalysisMode(StrEnum):
    FULL = "full"
    SUMMARY = "summary"
    OCR = "ocr"
    OBJECTS = "objects"
    LAYOUT = "layout"


class DetectedElementType(StrEnum):
    BUTTON = "button"
    TEXT_FIELD = "text_field"
    LINK = "link"
    IMAGE = "image"
    ICON = "icon"
    WINDOW = "window"
    MENU = "menu"
    DIALOG = "dialog"
    TEXT = "text"
    UNKNOWN = "unknown"


class BoundingBox(BaseModel):
    """Rectangular region expressed in pixel coordinates (origin top-left)."""

    x: int = Field(ge=0, description="Left edge in pixels.")
    y: int = Field(ge=0, description="Top edge in pixels.")
    width: int = Field(ge=0, description="Width in pixels.")
    height: int = Field(ge=0, description="Height in pixels.")


class DetectedElement(BaseModel):
    """A visually detected UI element, reported strictly as an observation.

    ``interactable`` and ``confidence`` are provider-reported or heuristic;
    the system never claims certainty beyond what the provider reported.
    """

    element_id: str | None = None
    element_type: DetectedElementType = DetectedElementType.UNKNOWN
    label: str | None = None
    text: str | None = None
    bounding_box: BoundingBox | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    interactable: bool | None = None


class TextRegion(BaseModel):
    """A snippet of text observed in an image, with optional location/confidence."""

    text: str = Field(min_length=1)
    bounding_box: BoundingBox | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ImageInput(BaseModel):
    """A safe typed reference to image content.

    Either a file path or raw bytes must be provided.  MIME type is validated
    against an allow-list and in-memory payloads are subject to a size limit.
    """

    model_config = ConfigDict(extra="forbid")

    path: Path | None = None
    data: bytes | None = None
    mime_type: str | None = Field(
        default=None,
        description=(
            "MIME type of the image.  Inferred from the file suffix when a "
            "path is given and this field is omitted."
        ),
    )
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    max_bytes: int | None = Field(
        default=None,
        description="Override for the enforced payload size limit.",
    )

    @field_validator("mime_type")
    @classmethod
    def _lowercase_mime(cls, v: str | None) -> str | None:
        return v.lower() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _validate_image(self) -> "ImageInput":
        if self.path is None and self.data is None:
            raise ValueError("image must provide a file path or in-memory bytes")

        mime = self.mime_type
        if mime is None:
            mime = _MIME_BY_SUFFIX.get(self.path.suffix.lower()) if self.path else None
        if mime is None:
            raise ValueError("unsupported image type: mime_type required")
        if mime not in SUPPORTED_IMAGE_MIME_TYPES:
            raise ValueError(f"unsupported image type: {mime}")
        self.mime_type = mime

        if self.data is not None:
            if len(self.data) == 0:
                raise ValueError("image data must not be empty")
            limit = self.max_bytes or DEFAULT_MAX_IMAGE_BYTES
            if len(self.data) > limit:
                raise ValueError(f"image data exceeds size limit of {limit} bytes")

        return self


class VisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image: ImageInput
    question: str | None = Field(default=None, max_length=4000)
    language: str | None = Field(default=None, max_length=64)
    mode: VisionAnalysisMode = VisionAnalysisMode.FULL


class VisionResult(BaseModel):
    """Structured output of a vision analysis.  Provider-agnostic."""

    success: bool
    summary: str | None = None
    detected_elements: list[DetectedElement] = Field(default_factory=list)
    text_regions: list[TextRegion] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provider: str | None = None
    reference: str | None = None
    image_width: int | None = Field(default=None, ge=1)
    image_height: int | None = Field(default=None, ge=1)
    error: str | None = None

    @classmethod
    def ok(
        cls,
        *,
        summary: str | None = None,
        detected_elements: list[DetectedElement] | None = None,
        text_regions: list[TextRegion] | None = None,
        confidence: float | None = None,
        provider: str | None = None,
        reference: str | None = None,
        image_width: int | None = None,
        image_height: int | None = None,
    ) -> "VisionResult":
        return cls(
            success=True,
            summary=summary,
            detected_elements=detected_elements or [],
            text_regions=text_regions or [],
            confidence=confidence,
            provider=provider,
            reference=reference,
            image_width=image_width,
            image_height=image_height,
        )

    @classmethod
    def fail(
        cls,
        error: str,
        *,
        provider: str | None = None,
        reference: str | None = None,
    ) -> "VisionResult":
        return cls(
            success=False,
            error=error,
            provider=provider,
            reference=reference,
        )


def image_reference(image: ImageInput) -> str:
    """Stable, log-safe reference for an image (never raw bytes)."""
    if image.path is not None:
        return str(image.path)
    digest = hashlib.md5(image.data or b"").hexdigest()[:16]
    return f"data:{digest}"
