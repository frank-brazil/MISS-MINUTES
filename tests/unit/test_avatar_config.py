"""Avatar config: defaults, validation and customization."""

import pytest
from pydantic import ValidationError

from app.avatar.config import AvatarConfig, AvatarProportions


def test_defaults_are_characteric():
    config = AvatarConfig()
    assert config.body_width == 180.0
    assert config.body_height == 180.0
    assert config.body_color.lower() == "#ff8c2a"
    assert config.outline_width == 6.0
    assert config.eye_size == 26.0
    assert config.pupil_size == 10.0
    assert config.mouth_size == 16.0
    assert config.arm_length == 48.0
    assert config.leg_length == 36.0
    assert config.shoe_width == 26.0
    assert config.shoe_height == 12.0
    assert config.hour_hand_length == 42.0
    assert config.minute_hand_length == 62.0
    assert config.markings_count == 12
    assert config.center_pivot_size == 7.0
    assert config.default_scale == 1.0


def test_radius_and_rect():
    config = AvatarConfig()
    assert config.radius == 90.0
    assert config.body_rect() == (180.0, 180.0)
    wide = AvatarConfig(body_width=200.0, body_height=160.0)
    assert wide.radius == 80.0


def test_rejects_negative_dimensions():
    for kwargs in (
        {"body_width": 0.0},
        {"arm_length": -4.0},
        {"eye_size": -1.0},
        {"default_scale": 0.0},
    ):
        with pytest.raises(ValidationError):
            AvatarConfig(**kwargs)


def test_rejects_nonfinite():
    with pytest.raises(ValidationError):
        AvatarConfig(body_width=float("nan"))


def test_rejects_bad_colors():
    for color in ("red", "#GGGGGG", "FF8C2A", ""):
        with pytest.raises(ValidationError):
            AvatarConfig(body_color=color)


def test_accepts_short_hex_and_uppercase():
    assert AvatarConfig(body_color="#F80").body_color == "#f80"
    assert AvatarConfig(outline_color="#FF8C2A").outline_color == "#ff8c2a"


def test_pupil_must_fit_eye():
    with pytest.raises(ValidationError):
        AvatarConfig(eye_size=20.0, pupil_size=25.0)


def test_hands_must_fit_body():
    with pytest.raises(ValidationError):
        AvatarConfig(body_width=120.0, hour_hand_length=70.0)
    with pytest.raises(ValidationError):
        AvatarConfig(minute_hand_length=200.0)


def test_markings_count_range():
    with pytest.raises(ValidationError):
        AvatarConfig(markings_count=0)
    with pytest.raises(ValidationError):
        AvatarConfig(markings_count=73)


def test_customization_is_adjustable():
    config = AvatarConfig(
        body_width=220.0,
        body_color="#FF9632",
        eye_size=32.0,
        eye_spacing=56.0,
        arm_length=54.0,
        markings_count=4,
    )
    assert config.body_width == 220.0
    assert config.eye_spacing == 56.0
    assert config.arm_thickness > 0
    assert (
        config.radius == 90.0 * (220.0 / 180.0)
        if False
        else config.radius == min(220.0, 180.0) / 2.0
    )


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        AvatarConfig(body_magic="glow")  # type: ignore[call-arg]


def test_proportions_from_config_default():
    proportions = AvatarProportions.from_config(AvatarConfig())
    assert 0.0 < proportions.body_dominance <= 1.0
    assert 0.0 < proportions.eye_to_body_ratio <= 1.0
    assert 0.0 < proportions.shoe_to_leg_ratio <= 1.0
    assert proportions.pupil_to_eye_ratio < 1.0
    assert proportions.arm_thinness < proportions.eye_to_body_ratio
    assert proportions.mouth_to_body_ratio < proportions.eye_to_body_ratio
    assert proportions.leg_shortness < 1.0


def test_proportions_follow_configuration():
    base = AvatarConfig()
    tall = AvatarConfig(leg_length=90.0)
    assert (
        AvatarProportions.from_config(tall).leg_shortness
        > AvatarProportions.from_config(base).leg_shortness
    )


def test_proportions_reject_out_of_range():
    with pytest.raises(ValidationError):
        AvatarProportions(
            body_dominance=1.5,
            arm_thinness=0.1,
            leg_thinness=0.1,
            leg_shortness=0.3,
            shoe_to_leg_ratio=0.7,
            eye_to_body_ratio=0.1,
            pupil_to_eye_ratio=0.4,
            mouth_to_body_ratio=0.1,
            hand_to_body_ratio=0.1,
        )
