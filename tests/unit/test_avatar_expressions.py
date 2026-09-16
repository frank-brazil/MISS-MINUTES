"""Expression system and mouth controller."""

import pytest
from pydantic import ValidationError

from app.avatar.expression import (
    DEFAULT_EXPRESSIONS,
    AvatarExpression,
    ExpressionController,
    ExpressionSet,
    PREDEFINED_EXPRESSION_NAMES,
    UnknownExpressionError,
)
from app.avatar.mouth import MouthController, MouthShape, MouthState

PREPARAMS = {
    "eye_openness": 0.8,
    "pupil_x": 0.2,
    "pupil_y": -0.3,
    "eyebrow_lift": 0.5,
    "mouth_shape": "smile",
    "mouth_openness": 0.4,
    "face_tilt_deg": 2.0,
    "body_tilt_deg": -1.0,
}


def test_all_predefined_expressions_present():
    expected = {
        "neutral",
        "happy",
        "sad",
        "concerned",
        "surprised",
        "thinking",
        "focused",
        "warning",
        "success",
        "confused",
        "excited",
    }
    assert set(DEFAULT_EXPRESSIONS) == expected
    assert set(PREDEFINED_EXPRESSION_NAMES) == expected


def test_predefined_are_valid():
    for name, params in DEFAULT_EXPRESSIONS.items():
        assert isinstance(params, AvatarExpression), name
    assert DEFAULT_EXPRESSIONS["neutral"].mouth_shape is MouthShape.CLOSED
    assert DEFAULT_EXPRESSIONS["happy"].mouth_shape is MouthShape.SMILE
    assert DEFAULT_EXPRESSIONS["surprised"].mouth_shape is MouthShape.SURPRISED


@pytest.mark.parametrize("field", ("eye_openness", "eyebrow_lift", "mouth_openness"))
def test_unit_range_validated(field):
    with pytest.raises(ValidationError):
        AvatarExpression(**{field: 1.5})
    with pytest.raises(ValidationError):
        AvatarExpression(**{field: -0.1})


@pytest.mark.parametrize("field", ("pupil_x", "pupil_y"))
def test_pupil_range_validated(field):
    with pytest.raises(ValidationError):
        AvatarExpression(**{field: 2.0})


@pytest.mark.parametrize("field", ("face_tilt_deg", "body_tilt_deg"))
def test_tilt_range_validated(field):
    with pytest.raises(ValidationError):
        AvatarExpression(**{field: 45.0})


def test_valid_expression_roundtrip():
    expression = AvatarExpression(**PREPARAMS)
    assert expression.mouth_shape is MouthShape.SMILE
    assert expression.pupil_x == pytest.approx(0.2)


def test_with_pupil_clamps():
    expression = AvatarExpression().with_pupil(2.0, -3.0)
    assert expression.pupil_x == 1.0
    assert expression.pupil_y == -1.0


def test_neutral_classmethod():
    assert AvatarExpression.neutral() == AvatarExpression()


def test_expression_set_validation():
    with pytest.raises(ValueError):
        ExpressionSet({})
    with pytest.raises(ValueError):
        ExpressionSet({"ok": "not-an-expression"})  # type: ignore[dict-item]


def test_expression_set_lookup():
    eset = ExpressionSet()
    assert eset.has("neutral")
    assert not eset.has("nope")
    assert eset.get("neutral") == DEFAULT_EXPRESSIONS["neutral"]
    with pytest.raises(UnknownExpressionError):
        eset.get("nope")
    assert "happy" in eset.names()


def test_expression_controller_apply():
    controller = ExpressionController()
    assert controller.current == "neutral"
    params = controller.apply("thinking")
    assert params is DEFAULT_EXPRESSIONS["thinking"]
    assert controller.current == "thinking"
    assert controller.params() is DEFAULT_EXPRESSIONS["thinking"]


def test_expression_controller_unknown_raises():
    controller = ExpressionController()
    with pytest.raises(UnknownExpressionError):
        controller.apply("missing-name")


def test_expression_controller_custom_set():
    custom = ExpressionSet({"soft": AvatarExpression(eye_openness=0.5, mouth_shape=MouthShape.SMILE)})
    controller = ExpressionController(custom)
    assert controller.current == "soft"
    assert controller.names() == ("soft",)


def test_expression_set_copy_independent():
    eset = ExpressionSet()
    duplicate = eset.copy()
    assert duplicate.get("neutral") == eset.get("neutral")
    assert duplicate is not eset


def test_mouth_shapes():
    assert set(MouthShape) == {
        MouthShape.CLOSED,
        MouthShape.SMILE,
        MouthShape.OPEN,
        MouthShape.CONCERNED,
        MouthShape.SURPRISED,
        MouthShape.SMALL_OPEN,
        MouthShape.SPEAKING,
    }


def test_mouth_state_validation():
    with pytest.raises(ValidationError):
        MouthState(openness=1.2)


def test_mouth_controller_defaults():
    mouth = MouthController(mouth_size=18.0)
    assert mouth.mouth_size == 18.0
    assert mouth.shape is MouthShape.CLOSED
    assert mouth.state().openness == 0.0


def test_mouth_set_applies_default_openness():
    mouth = MouthController()
    mouth.set(MouthShape.SMILE)
    assert mouth.state().shape is MouthShape.SMILE
    assert mouth.state().openness == pytest.approx(0.35)
    mouth.set(MouthShape.SURPRISED)
    assert mouth.state().openness == pytest.approx(0.95)


def test_mouth_open_override_clamped():
    mouth = MouthController()
    mouth.set(MouthShape.CLOSED)
    mouth.open(2.0)
    assert mouth.state().openness == 1.0
    mouth.open(-1.0)
    assert mouth.state().openness == 0.0


def test_mouth_invalid_size():
    with pytest.raises(ValueError):
        MouthController(mouth_size=0.0)


def test_mouth_reset():
    mouth = MouthController()
    mouth.set(MouthShape.SMILE)
    reset = mouth.reset()
    assert reset.shape is MouthShape.CLOSED
    assert reset.openness == 0.0


def test_mouth_speaking_shape_defaults_and_animate():
    mouth = MouthController()
    state = mouth.set(MouthShape.SPEAKING)
    assert state.openness == pytest.approx(0.5)
    first = mouth.animate(0.0)
    second = mouth.animate(0.2)
    assert first.shape is MouthShape.SPEAKING
    assert 0.15 <= first.openness <= 0.85
    assert first.openness != second.openness  # oscillation is visible
    assert MouthShape.SMALL_OPEN in MouthController.DEFAULT_OPENNESS


def test_mouth_animate_ignores_non_speaking_shapes():
    mouth = MouthController()
    mouth.set(MouthShape.SMILE)
    before = mouth.state()
    after = mouth.animate(0.5)
    assert after == before