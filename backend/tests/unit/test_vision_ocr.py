import asyncio

import pytest
from app.vision.fakes import FakeOcrProvider
from app.vision.models import (
    ImageInput,
    TextRegion,
)
from app.vision.ocr import (
    OcrProvider,
    OcrRequest,
    OcrResult,
    UnsupportedOcrProvider,
)


def _run(coro):
    return asyncio.run(coro)


def _png() -> ImageInput:
    return ImageInput(data=b"\x89PNG-fake", mime_type="image/png")


def test_ocr_provider_is_abstract() -> None:
    with pytest.raises(TypeError):
        OcrProvider()


def test_unsupported_ocr_provider_returns_controlled_failure() -> None:
    provider = UnsupportedOcrProvider()
    result = _run(provider.extract_text(OcrRequest(image=_png())))
    assert result.success is False
    assert "not supported" in (result.error or "").lower()


def test_fake_ocr_success() -> None:
    provider = FakeOcrProvider()
    provider.register_image_text("data:abc", "Hello OCR")
    image = ImageInput(data=b"some-data-for-abc", mime_type="image/png")
    # register by data hash (need exact bytes match for reference)
    from app.vision.models import image_reference

    ref = image_reference(image)
    provider.register_image_text(ref, "Hello OCR")

    result = _run(provider.extract_text(OcrRequest(image=image)))
    assert result.success is True
    assert result.text == "Hello OCR"
    assert len(result.text_regions) == 1
    assert result.text_regions[0].text == "Hello OCR"
    assert result.confidence == 0.95


def test_fake_ocr_returns_failure_when_not_registered() -> None:
    provider = FakeOcrProvider()
    result = _run(provider.extract_text(OcrRequest(image=_png())))
    assert result.success is False
    assert "No registered text" in (result.error or "")


def test_fake_ocr_records_requests() -> None:
    provider = FakeOcrProvider()
    image = ImageInput(data=b"x" * 5, mime_type="image/png")
    from app.vision.models import image_reference

    provider.register_image_text(image_reference(image), "record me")
    _run(provider.extract_text(OcrRequest(image=image)))
    _run(provider.extract_text(OcrRequest(image=image)))
    assert len(provider.calls) == 2
    assert provider.calls[0].image.data == b"x" * 5


def test_ocr_result_ok_factory() -> None:
    result = OcrResult.ok(
        text="read text",
        text_regions=[TextRegion(text="x")],
        confidence=0.8,
        provider="ocr",
    )
    assert result.success is True
    assert result.text == "read text"


def test_ocr_result_fail_factory() -> None:
    result = OcrResult.fail(error="ocr failure", provider="ocr")
    assert result.success is False
    assert result.error == "ocr failure"
