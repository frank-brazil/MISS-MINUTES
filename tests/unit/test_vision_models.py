from pathlib import Path

import pytest
from pydantic import ValidationError

from app.vision.models import (
    DEFAULT_MAX_IMAGE_BYTES,
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


def test_valid_image_input_with_data() -> None:
    image = ImageInput(data=b"\x89PNG-fake", mime_type="image/png")
    assert image.mime_type == "image/png"
    assert image.data == b"\x89PNG-fake"


def test_valid_image_input_with_path() -> None:
    image = ImageInput(path=Path("shots/x.png"), mime_type="image/jpeg")
    assert image.path == Path("shots/x.png")


def test_mime_type_normalized_to_lowercase() -> None:
    image = ImageInput(data=b"x" * 10, mime_type="image/PNG")
    assert image.mime_type == "image/png"


def test_mime_inferred_from_path_suffix() -> None:
    image = ImageInput(path=Path("shot.png"))
    assert image.mime_type == "image/png"


def test_mime_inferred_jpeg_suffix() -> None:
    image = ImageInput(path=Path("shot.jpg"))
    assert image.mime_type == "image/jpeg"


def test_invalid_mime_type_rejected() -> None:
    with pytest.raises(ValidationError, match="unsupported image type"):
        ImageInput(data=b"x" * 10, mime_type="application/pdf")
    with pytest.raises(ValidationError, match="unsupported image type"):
        ImageInput(data=b"x" * 10, mime_type="text/plain")


def test_unknown_mime_without_path_rejected() -> None:
    with pytest.raises(ValidationError, match="mime_type required"):
        ImageInput(data=b"x" * 10)


def test_missing_path_and_data_rejected() -> None:
    with pytest.raises(ValidationError, match="path or in-memory bytes"):
        ImageInput(mime_type="image/png")


def test_empty_data_rejected() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        ImageInput(data=b"", mime_type="image/png")


def test_oversized_data_rejected() -> None:
    with pytest.raises(ValidationError, match="size limit"):
        ImageInput(data=b"z" * 101, mime_type="image/png", max_bytes=100)


def test_default_size_limit_applied() -> None:
    with pytest.raises(ValidationError, match="size limit"):
        ImageInput(data=b"z" * (DEFAULT_MAX_IMAGE_BYTES + 1), mime_type="image/png")


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError, match="extra"):
        ImageInput(data=b"x" * 5, mime_type="image/png", junk=True)


def test_bounding_box_valid() -> None:
    box = BoundingBox(x=0, y=1, width=2, height=3)
    assert (box.x, box.y, box.width, box.height) == (0, 1, 2, 3)


@pytest.mark.parametrize(
    ("x", "y", "w", "h"),
    [(-1, 0, 10, 10), (0, -1, 10, 10), (0, 0, -1, 10), (0, 0, 10, -1)],
)
def test_bounding_box_negative_values_rejected(x, y, w, h) -> None:
    with pytest.raises(ValidationError):
        BoundingBox(x=x, y=y, width=w, height=h)


def test_bounding_box_zero_size_allowed() -> None:
    box = BoundingBox(x=5, y=5, width=0, height=0)
    assert box.width == 0


def test_detected_element_defaults() -> None:
    element = DetectedElement()
    assert element.element_type == DetectedElementType.UNKNOWN
    assert element.confidence is None
    assert element.interactable is None


def test_detected_element_typed_fields() -> None:
    element = DetectedElement(
        element_id="e1",
        element_type=DetectedElementType.BUTTON,
        label="Submit",
        text="Submit",
        bounding_box=BoundingBox(x=1, y=2, width=3, height=4),
        confidence=0.9,
        interactable=True,
    )
    assert element.element_type == DetectedElementType.BUTTON
    assert element.confidence == 0.9
    assert element.interactable is True


def test_detected_element_confidence_range() -> None:
    with pytest.raises(ValidationError):
        DetectedElement(confidence=1.5)
    with pytest.raises(ValidationError):
        DetectedElement(confidence=-0.1)


def test_detected_element_all_types_valid() -> None:
    for value in (
        "button",
        "text_field",
        "link",
        "image",
        "icon",
        "window",
        "menu",
        "dialog",
        "text",
        "unknown",
    ):
        element = DetectedElement(element_type=value)
        assert element.element_type.value == value


def test_text_region_requires_text() -> None:
    with pytest.raises(ValidationError):
        TextRegion(text="")


def test_text_region_confidence_range() -> None:
    with pytest.raises(ValidationError):
        TextRegion(text="x", confidence=2.0)


def test_vision_result_ok_factory() -> None:
    result = VisionResult.ok(
        summary="ok", confidence=0.8, provider="fake", reference="ref"
    )
    assert result.success is True
    assert result.summary == "ok"
    assert result.detected_elements == []
    assert result.text_regions == []
    assert result.error is None


def test_vision_result_fail_factory() -> None:
    result = VisionResult.fail(error="boom", provider="fake", reference="ref")
    assert result.success is False
    assert result.error == "boom"
    assert result.summary is None


def test_vision_request_defaults() -> None:
    request = VisionRequest(image=ImageInput(data=b"x" * 5, mime_type="image/png"))
    assert request.mode == VisionAnalysisMode.FULL
    assert request.question is None
    assert request.language is None


def test_vision_request_question_length_limit() -> None:
    image = ImageInput(data=b"x" * 5, mime_type="image/png")
    with pytest.raises(ValidationError, match="4000"):
        VisionRequest(image=image, question="q" * 4001)


def test_vision_request_extra_fields_forbidden() -> None:
    image = ImageInput(data=b"x" * 5, mime_type="image/png")
    with pytest.raises(ValidationError, match="extra"):
        VisionRequest(image=image, suspect="yes")


def test_image_reference_uses_path() -> None:
    image = ImageInput(path=Path("shots/a.png"), mime_type="image/png")
    assert image_reference(image) == str(image.path)


def test_image_reference_for_data_is_stable_and_safe() -> None:
    image = ImageInput(data=b"payload-bytes", mime_type="image/png")
    ref = image_reference(image)
    assert ref.startswith("data:")
    assert "payload-bytes" not in ref
    same = ImageInput(data=b"payload-bytes", mime_type="image/png")
    assert image_reference(same) == ref