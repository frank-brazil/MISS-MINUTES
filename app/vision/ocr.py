"""OCR / text-extraction boundary.

OCR is optional and provider-independent: environments without OCR can inject
``UnsupportedOcrProvider`` and receive a controlled failure rather than a
hard dependency.  Structured text regions and confidence metadata are exposed
when the backing implementation provides them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.vision.models import ImageInput, TextRegion


class OcrRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image: ImageInput
    language: str | None = Field(default=None, max_length=64)


class OcrResult(BaseModel):
    success: bool
    text: str | None = None
    text_regions: list[TextRegion] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provider: str | None = None
    error: str | None = None

    @classmethod
    def ok(
        cls,
        *,
        text: str,
        text_regions: list[TextRegion] | None = None,
        confidence: float | None = None,
        provider: str | None = None,
    ) -> "OcrResult":
        return cls(
            success=True,
            text=text,
            text_regions=text_regions or [],
            confidence=confidence,
            provider=provider,
        )

    @classmethod
    def fail(cls, error: str, *, provider: str | None = None) -> "OcrResult":
        return cls(success=False, error=error, provider=provider)


class OcrProvider(ABC):
    """Extracts text from an image.  Never requires a live OCR dependency."""

    name: ClassVar[str] = "ocr"

    @abstractmethod
    async def extract_text(self, request: OcrRequest) -> OcrResult:
        raise NotImplementedError


class UnsupportedOcrProvider(OcrProvider):
    """Graceful fallback when OCR is not available in the environment."""

    name: ClassVar[str] = "unsupported_ocr"

    async def extract_text(self, request: OcrRequest) -> OcrResult:
        return OcrResult.fail(
            error="OCR is not supported in this environment",
            provider=self.name,
        )
