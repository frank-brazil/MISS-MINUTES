import asyncio

import pytest

from app.vision.fakes import (
    FakeVisionProvider,
    FailingVisionProvider,
)
from app.vision.models import (
    BoundingBox,
    DetectedElement,
    DetectedElementType,
    ImageInput,
    VisionRequest,
    VisionResult,
    image_reference,
)
from app.vision.provider import VisionProvider


def _run(coro):
    return asyncio.run(coro)


def _png() -> ImageInput:
    return ImageInput(data=b"\x89PNG-fake", mime_type="image/png")


def test_vision_provider_is_abstract() -> None:
    with pytest.raises(TypeError):
        VisionProvider()


def test_fake_vision_provider_success() -> None:
    provider = FakeVisionProvider()
    ref = image_reference(_png())
    provider.register_image_text(ref, "Hello world")
    element = DetectedElement(
        element_type=DetectedElementType.BUTTON,
        label="Go",
        bounding_box=BoundingBox(x=1, y=2, width=3, height=4),
        confidence=0.9,
        interactable=True,
    )
    provider.register_detected_elements(ref, [element])

    result = _run(provider.analyze(VisionRequest(image=_png())))
    assert isinstance(result, VisionResult)
    assert result.success is True
    assert result.provider == "fake_vision"
    assert result.reference == ref
    assert [t.text for t in result.text_regions] == ["Hello world"]
    assert result.detected_elements == [element]
    assert result.confidence == 0.95


def test_fake_vision_provider_registered_by_path() -> None:
    provider = FakeVisionProvider()
    image = ImageInput(path="C:/shots/s1.png")
    provider.register_image_text(image_reference(image), "offline text")
    result = _run(provider.analyze(VisionRequest(image=image)))
    assert result.success is True
    assert [t.text for t in result.text_regions] == ["offline text"]
    assert result.reference == image_reference(image)


def test_fake_vision_provider_is_deterministic_and_records_calls() -> None:
    provider = FakeVisionProvider()
    provider.register_image_text(image_reference(_png()), "same")
    first = _run(provider.analyze(VisionRequest(image=_png())))
    second = _run(provider.analyze(VisionRequest(image=_png())))
    assert first.text_regions == second.text_regions
    assert first.summary == second.summary
    assert len(provider.calls) == 2
    assert provider.calls[0].image.mime_type == "image/png"


def test_fake_vision_provider_failure_flag() -> None:
    provider = FakeVisionProvider()
    provider.fail = True
    result = _run(provider.analyze(VisionRequest(image=_png())))
    assert result.success is False
    assert "failed" in (result.error or "")


def test_fake_vision_provider_failure_by_reference() -> None:
    provider = FakeVisionProvider()
    ref = image_reference(_png())
    provider.fail_reference = ref
    result = _run(provider.analyze(VisionRequest(image=_png())))
    assert result.success is False
    # a different image still succeeds
    provider.fail_reference = "data:other"
    other = _run(provider.analyze(VisionRequest(image=_png())))
    assert other.success is True


def test_fake_vision_provider_controlled_exception() -> None:
    provider = FakeVisionProvider()
    provider.raise_error = RuntimeError("engine down")
    with pytest.raises(RuntimeError, match="engine down"):
        _run(provider.analyze(VisionRequest(image=_png())))


def test_failing_vision_provider_returns_controlled_failure() -> None:
    provider = FailingVisionProvider()
    result = _run(provider.analyze(VisionRequest(image=_png())))
    assert result.success is False
    assert result.error == "Vision analysis failed"
    assert result.provider == "failing_vision"